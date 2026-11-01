"""Explicit private roster mappings: real HTTP, SQLite and bounded import parser."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.classic import ClassicClient, ClassicError
from server.storage import pack

PASSWORD = 'Testing-password-1234'
OBSERVED = '2026-10-20T12:00:00Z'


def login(client, username='piwig'):
    response = client.post('/api/login', json={'username': username, 'password': PASSWORD})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path, PASSWORD, secure=False)
    with TestClient(app) as client:
        headers = login(client)
        yield app, client, headers


def preview(client, headers, content=None, filename='players.json'):
    content = content if content is not None else json.dumps([{'id': '42', 'name': 'Synthetic player', 'strength': 7}]).encode()
    return client.post('/api/import/preview', headers=headers, files={'file': (filename, content)})


def mapping(doc, team_id='72450', cohort='seniors', **extra):
    return {'dataset_id': doc['datasets'][0]['id'], 'team_id': team_id, 'cohort': cohort, 'observed_at': OBSERVED, **extra}


def confirm(client, headers, doc, mappings=None):
    return client.post('/api/import/confirm', headers=headers, json={'token': doc['token'], 'mappings': mappings if mappings is not None else [mapping(doc)]})


def test_preview_is_read_only_and_confirmation_requires_explicit_destination(env):
    app, client, headers = env
    with app.state.store.db() as db:
        before = db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
    response = preview(client, headers)
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc['datasets'][0]['players'][0]['name'] == 'Synthetic player'
    assert doc['datasets'][0]['observed_at'] is None
    assert 'team_id' not in doc['datasets'][0]
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == before
    assert confirm(client, headers, doc, []).status_code == 422
    assert confirm(client, headers, doc).status_code == 200
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad'][0]['name'] == 'Synthetic player'
    assert state['squad_source']['observed_at'].startswith('2026-10-20T12:00:00')
    assert confirm(client, headers, doc).status_code == 404


def test_source_date_is_required_and_unknown_destinations_never_write(env):
    app, client, headers = env
    doc = preview(client, headers).json()
    row = mapping(doc)
    row.pop('observed_at')
    assert confirm(client, headers, doc, [row]).status_code == 422
    assert confirm(client, headers, doc, [mapping(doc, team_id='99999999')]).status_code == 422
    assert confirm(client, headers, doc, [mapping(doc, observed_at='2099-01-01T00:00:00Z')]).status_code == 422
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0


def test_changed_roster_rejects_stale_preview_and_preserves_concurrent_observation(env):
    app, client, headers = env
    doc = preview(client, headers).json()
    app.state.store.save_snapshot('72450', False, [{'id': '99', 'name': 'Newer'}], 'Concurrent', OBSERVED)
    assert confirm(client, headers, doc).status_code == 409
    assert client.get('/api/state?team_id=72450').json()['squad'][0]['id'] == '99'


def test_other_manager_cannot_use_preview_and_routes_require_csrf(env):
    app, client, headers = env
    doc = preview(client, headers).json()
    assert preview(client, {}).status_code == 403
    assert confirm(client, {}, doc).status_code == 403
    app.state.accounts.create('other-manager', PASSWORD)
    other = login(client, 'other-manager')
    assert confirm(client, other, doc).status_code == 404
    headers = login(client)
    assert confirm(client, headers, doc).status_code == 200


def workbook():
    tables = []
    for name, player in [('players', 'First'), ('latouff_players', 'Second')]:
        tables.append(f'<table:table table:name="{name}"><table:table-row><table:table-cell><text:p>id</text:p></table:table-cell><table:table-cell><text:p>name</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell><text:p>42</text:p></table:table-cell><table:table-cell><text:p>{player}</text:p></table:table-cell></table:table-row></table:table>')
    tables.append('<table:table table:name="private_analysis"/>')
    xml = '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>' + ''.join(tables) + '</office:spreadsheet></office:body></office:document-content>'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('content.xml', xml)
    return stream.getvalue()


def test_legacy_sheet_names_do_not_route_and_collision_is_atomic(env):
    app, client, headers = env
    doc = preview(client, headers, workbook(), 'rosters.ods').json()
    assert len(doc['datasets']) == 2
    assert 'private_analysis' in [entry['name'] for entry in doc['excluded']]
    rows = [mapping(doc), {**mapping(doc), 'dataset_id': doc['datasets'][1]['id']}]
    assert confirm(client, headers, doc, rows).status_code == 422
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0
    rows[1] = {'dataset_id': doc['datasets'][1]['id'], 'skip': True}
    result = confirm(client, headers, doc, rows)
    assert result.status_code == 200, result.text
    assert result.json()['skipped'][0]['sheet'] == 'latouff_players'
    assert client.get('/api/state?team_id=72450').json()['squad'][0]['name'] == 'First'
    assert client.get('/api/state?team_id=72444').json()['squad'] == []


@pytest.mark.parametrize('content,filename', [(b'[]', 'empty.json'), (b'{"players":[]}', 'empty.json'), (b'id,name\n42,A\n42,B', 'duplicate.csv'), (b'{bad', 'malformed.json'), (b'x', 'file.exe')])
def test_bad_or_empty_files_are_rejected_without_writes(env, content, filename):
    app, client, headers = env
    assert preview(client, headers, content, filename).status_code == 422
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0


def connect_selection(app, kind='u20'):
    store = app.state.store
    store.set('classic_account', {'id': '123', 'team_ids': ['72450'], 'selection_ids': [kind + ':9'], 'selection_revision': 1})
    store.set('api_manager', store.cipher.encrypt(pack({'m': '123', 'mk': 'synthetic-key'}).encode()).decode())
    with store.db() as db:
        db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?)', (kind + ':9', 'Synthetic selection', 'BE'))


def mandate(monkeypatch, manager='123', kind='u20', owner_only=False, during=None):
    async def request(self, resource, **params):
        if resource == 'm':
            assert params == {'memberid': '123'}
            return {'members': {'123': {'id': '123', 'email': 'synthetic@example.invalid'}}}
        assert params.get('u20' if kind == 'u20' else 'nat') == '1'
        assert params['teamid'] == '9'
        if resource == 't':
            team = {'id': '9', 'country_iso': 'BE', 'name': 'Selection', 'manager': manager}
            if owner_only:
                team.pop('manager')
                team.update(owner=manager, u20=1)
            return {'teams': {'9': team}}
        if resource == 'p':
            if during:
                during()
            return {'players': {'42': {'id': '42', 'name': 'API observation'}}, 'gameDate': {'season': 62, 'round': 9, 'day': 5}}
        raise AssertionError(resource)
    monkeypatch.setattr(ClassicClient, 'request', request)


@pytest.mark.parametrize('kind', ['u20', 'nt'])
def test_current_selection_mandate_rechecked_without_saving_remote_roster(env, monkeypatch, kind):
    app, client, headers = env
    connect_selection(app, kind)
    mandate(monkeypatch, kind=kind)
    doc = preview(client, headers).json()
    result = confirm(client, headers, doc, [mapping(doc, team_id=kind + ':9', cohort='selection')])
    assert result.status_code == 200, result.text
    state = client.get('/api/state?team_id=' + kind + ':9').json()
    assert state['squad'][0]['name'] == 'Synthetic player'
    assert state['academy'] == []


@pytest.mark.parametrize('kind,owner_only', [('u20', False), ('nt', True)])
def test_lost_or_unproven_mandate_blocks_entire_batch(env, monkeypatch, kind, owner_only):
    app, client, headers = env
    connect_selection(app, kind)
    mandate(monkeypatch, manager='456' if not owner_only else '123', kind=kind, owner_only=owner_only)
    doc = preview(client, headers, workbook(), 'rosters.ods').json()
    rows = [mapping(doc), {**mapping(doc, team_id=kind + ':9', cohort='selection'), 'dataset_id': '1'}]
    assert confirm(client, headers, doc, rows).status_code == 422
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['pause', 'account', 'credentials'])
def test_selection_context_change_invalidates_preview(env, monkeypatch, change):
    app, client, headers = env
    connect_selection(app)
    doc = preview(client, headers).json()
    if change == 'pause':
        account = app.state.store.get('classic_account')
        app.state.store.set('classic_account', {**account, 'selection_ids': [], 'selection_revision': 2})
    elif change == 'account':
        app.state.store.set('classic_account', {'id': '456', 'selection_ids': ['u20:9']})
    else:
        app.state.store.set('api_manager', 'changed')
    assert confirm(client, headers, doc, [mapping(doc, team_id='u20:9', cohort='selection')]).status_code == 409
    assert confirm(client, headers, doc).status_code == 404


def test_account_change_during_remote_mandate_read_cannot_commit(env, monkeypatch):
    app, client, headers = env
    connect_selection(app)
    mandate(monkeypatch, during=lambda: app.state.store.set('classic_account', {'id': '456'}))
    doc = preview(client, headers).json()
    assert confirm(client, headers, doc, [mapping(doc, team_id='u20:9', cohort='selection')]).status_code == 409
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0


def test_expired_preview_cannot_write(env, monkeypatch):
    import server.import_preview as module
    app, client, headers = env
    monkeypatch.setattr(module, 'TTL_SECONDS', -1)
    doc = preview(client, headers).json()
    assert confirm(client, headers, doc).status_code == 404


def test_older_identical_file_does_not_refresh_original_observation(env):
    app, client, headers = env
    players = [{'id': '42', 'name': 'Synthetic player', 'strength': 7, 'pops': [], 'reveals': []}]
    app.state.store.save_snapshot('72450', False, players, 'Original', '2026-10-25T12:00:00Z')
    doc = preview(client, headers).json()
    assert confirm(client, headers, doc).status_code == 200
    with app.state.store.db() as db:
        rows = db.execute('SELECT * FROM snapshots').fetchall()
    assert len(rows) == 1
    assert rows[0]['source'] == 'Original'
    assert rows[0]['observed_at'] == '2026-10-25T12:00:00Z'
    assert rows[0]['last_observed_at'] is None


def test_source_observation_date_cannot_be_overridden_to_make_file_fresh(env):
    app, client, headers = env
    content = json.dumps({'players': [{'id': '42', 'name': 'Dated player'}], 'observed_at': '2026-10-01T00:00:00Z'}).encode()
    doc = preview(client, headers, content).json()
    assert doc['datasets'][0]['observed_at'].startswith('2026-10-01T00:00:00')
    assert confirm(client, headers, doc).status_code == 422
    result = confirm(client, headers, doc, [mapping(doc, observed_at='2026-10-01T00:00:00Z')])
    assert result.status_code == 200
    assert client.get('/api/state?team_id=72450').json()['squad_source']['observed_at'].startswith('2026-10-01')


def test_lost_mandate_permanently_invalidates_preview(env, monkeypatch):
    app, client, headers = env
    connect_selection(app)
    mandate(monkeypatch, manager='456')
    doc = preview(client, headers).json()
    rows = [mapping(doc, team_id='u20:9', cohort='selection')]
    assert confirm(client, headers, doc, rows).status_code == 422
    mandate(monkeypatch)
    assert confirm(client, headers, doc, rows).status_code == 404


def test_non_integral_source_game_date_is_rejected(env):
    app, client, headers = env
    content = json.dumps({'players': [{'id': '42', 'name': 'Dated player'}], 'gameDate': {'season': 62.8, 'round': 9, 'day': 5}}).encode()
    assert preview(client, headers, content).status_code == 422


def test_cache_byte_limit_evicts_oldest_preview(env, monkeypatch):
    import server.import_preview as module
    app, client, headers = env
    monkeypatch.setattr(module, 'MAX_CACHE_BYTES', 6000)
    content = json.dumps([{'id': str(i + 1), 'name': 'Synthetic ' + 'x' * 100} for i in range(15)]).encode()
    first = preview(client, headers, content).json()
    second = preview(client, headers, content).json()
    assert confirm(client, headers, first).status_code == 404
    assert confirm(client, headers, second).status_code == 200


def test_older_changed_file_cannot_replace_newer_current_roster(env):
    app, client, headers = env
    app.state.store.save_snapshot('72450', False, [{'id': '99', 'name': 'Newer player'}], 'Newer', '2026-10-25T12:00:00Z')
    doc = preview(client, headers).json()
    current = next(row for row in doc['destinations'] if row['team_id'] == '72450')['current']['seniors']
    assert current['count'] == 1
    assert current['observed_at'] == '2026-10-25T12:00:00Z'
    assert confirm(client, headers, doc).status_code == 422
    assert client.get('/api/state?team_id=72450').json()['squad'][0]['name'] == 'Newer player'


def test_storage_failure_rolls_back_entire_batch_and_token_can_retry(env, monkeypatch):
    app, client, headers = env
    doc = preview(client, headers, workbook(), 'rosters.ods').json()
    rows = [mapping(doc), {**mapping(doc, cohort='academy'), 'dataset_id': '1'}]
    original = type(app.state.store).save_snapshot
    count = 0
    def failing(store, *args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError('Synthetic storage failure')
        return original(store, *args, **kwargs)
    monkeypatch.setattr(type(app.state.store), 'save_snapshot', failing)
    with pytest.raises(RuntimeError, match='Synthetic storage failure'):
        confirm(client, headers, doc, rows)
    with app.state.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0
    monkeypatch.setattr(type(app.state.store), 'save_snapshot', original)
    assert confirm(client, headers, doc, rows).status_code == 200


def test_date_only_source_stays_visible_and_cannot_be_replaced_with_later_day(env):
    app, client, headers = env
    content = json.dumps({'players': [{'id': '42', 'name': 'Dated player'}], 'observed_at': '2026-10-01'}).encode()
    doc = preview(client, headers, content).json()
    assert doc['datasets'][0]['source_date_hint'] == '2026-10-01'
    assert doc['datasets'][0]['observed_at'] is None
    assert confirm(client, headers, doc).status_code == 422
    assert confirm(client, headers, doc, [mapping(doc, observed_at='2026-10-01T12:00:00Z')]).status_code == 200


@pytest.mark.parametrize('source_date', [
    '2020-01-01T12:00:00',
    '2099-01-01T12:00:00Z',
    '2099-01-01',
    '2020-02-30',
    'not-a-date',
    '2020-01-01Tgarbage',
    123,
    False,
])
def test_invalid_supplied_source_date_cannot_be_replaced_with_recent_mapping(env, source_date):
    app, client, headers = env
    app.state.store.save_snapshot('72450', False, [{'id': '99', 'name': 'Current player'}], 'Current', '2026-10-20T12:00:00Z')
    content = json.dumps({'players': [{'id': '42', 'name': 'Historical player'}], 'observed_at': source_date}).encode()
    response = preview(client, headers, content)
    if response.status_code == 200:
        # Reproduce the formerly successful 2020 -> 2026 false refresh through
        # the actual confirm endpoint before checking the intended refusal.
        replacement = confirm(client, headers, response.json(), [mapping(response.json(), observed_at='2026-10-21T12:00:00Z')])
        assert replacement.status_code == 422, replacement.text
    assert response.status_code == 422, response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad'][0]['name'] == 'Current player'
    assert state['squad_source']['observed_at'] == '2026-10-20T12:00:00Z'
