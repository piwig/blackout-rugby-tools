"""Synthetic regression fixtures for import routing and observation integrity."""
import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from fastapi.testclient import TestClient

from server import imports, main
from server.progression import progression_series
from server.storage import Store


def ods(sheets):
    tables = []
    for name, rows in sheets.items():
        body = ''.join('<table:table-row>' + ''.join(
            '<table:table-cell><text:p>' + escape(str(value)) + '</text:p></table:table-cell>'
            for value in row) + '</table:table-row>' for row in rows)
        tables.append('<table:table table:name="' + name + '">' + body + '</table:table>')
    xml = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">' + ''.join(tables) + '</office:document-content>')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('content.xml', xml)
    return output.getvalue()


@pytest.fixture(autouse=True)
def observation_clock(monkeypatch):
    from server import storage
    monkeypatch.setattr(storage, 'now', lambda: '2026-11-02T10:00:00Z')
    monkeypatch.setattr(main, 'now', lambda: '2026-11-02T10:00:00Z')


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path, 'Testing-password-1234', seed=False)
    with store.db() as db:
        db.execute("INSERT INTO teams(id,name,country) VALUES('101','Synthetic affiliate','FR')")
    return store


def test_generic_ods_routes_players_metadata_plans_and_training_to_selected_club(store):
    result = imports.parse_import(ods({
        'players': [['id', 'name'], ['42', 'Synthetic player']],
        'team': [['name', 'date_maj'], ['Synthetic metadata', '2026-10-01']],
        'Academy': [['64', 'S1'], *[['', *(['FOR'] * 16)] for _ in range(4)]],
        'youth_training': [['id', 'teamid', 's1', 's2', 's3', 's4'], ['1', '72450', 'strength', 'speed', 'attack', 'defense']],
    }), 'generic.ods')
    assert store.import_result(result, '101', False, 'generic.ods') == 1
    with store.db() as db:
        assert [tuple(row) for row in db.execute('SELECT team_id,youth FROM snapshots')] == [('101', 0)]
        assert json.loads(db.execute("SELECT meta FROM teams WHERE id='101'").fetchone()[0])['name'] == 'Synthetic metadata'
        assert [row[0] for row in db.execute('SELECT team_id FROM plans')] == ['101']
        assert [row[0] for row in db.execute('SELECT id FROM teams')] == ['101']
    assert store.get('training:101') == ['strength', 'speed', 'attack', 'defense']
    assert store.get('training:72450') is None


def test_explicit_legacy_sheets_keep_distinct_destinations_and_generic_ancillaries_use_target(store):
    result = imports.parse_import(ods({
        'players': [['id', 'name'], ['42', 'Target player']],
        'moeskroen_ya': [['id', 'name'], ['43', 'Historical academy']],
        'latouff_players': [['id', 'name'], ['44', 'Historical senior']],
        'latouff_academy': [['id', 'name'], ['45', 'Historical academy']],
        'team': [['name'], ['Selected club metadata']],
        'Academy': [['64', 'S1'], *[['', *(['FOR'] * 16)] for _ in range(4)]],
    }), 'mixed.ods')
    store.import_result(result, '101', False, 'mixed.ods')
    with store.db() as db:
        rows = [tuple(row) for row in db.execute('SELECT team_id,youth FROM snapshots ORDER BY team_id,youth')]
        assert rows == [('101', 0), ('72444', 0), ('72444', 1), ('72450', 1)]
        assert json.loads(db.execute("SELECT meta FROM teams WHERE id='101'").fetchone()[0]) == {'name': 'Selected club metadata'}
        assert all(json.loads(row[0]) == {} for row in db.execute("SELECT meta FROM teams WHERE id!='101'"))
        assert [row[0] for row in db.execute('SELECT team_id FROM plans')] == ['101']


@pytest.fixture
def client(tmp_path):
    with TestClient(main.create_app(tmp_path, 'Testing-password-1234', secure=False)) as client:
        response = client.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
        client.headers.update({'X-CSRF-Token': response.json()['csrf']})
        yield client


@pytest.mark.parametrize('kind,youth', [('academy', True), ('squad', False)])
@pytest.mark.parametrize('empty', [{}, []])
def test_explicit_empty_targeted_sync_clears_only_requested_roster(client, monkeypatch, kind, youth, empty):
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player'}]
    for team in ['72450', '72444']:
        for cohort in [True, False]:
            store.save_snapshot(team, cohort, players, 'synthetic')
    store.save_secrets('72450', {'mk': 'synthetic-manager-key'})

    async def request(self, resource, **params):
        return {'players': empty, 'gameDate': {'season': 64, 'round': 1, 'day': 2}}

    monkeypatch.setattr(main.ClassicClient, 'request', request)
    response = client.post('/api/sync', json={'team_id': '72450', 'kind': kind})
    assert response.status_code == 200, response.text
    assert response.json()['players'] == 0
    state = client.get('/api/state?team_id=72450').json()
    assert state[kind] == []
    assert len(state['squad' if youth else 'academy']) == 1
    other = client.get('/api/state?team_id=72444').json()
    assert len(other['squad']) == len(other['academy']) == 1


@pytest.mark.parametrize('document', [{}, {'players': None}, {'players': ''}, {'players': [None]}, {'players': {'42': None}}])
def test_missing_or_malformed_targeted_sync_preserves_previous_roster(client, monkeypatch, document):
    store = client.app.state.store
    store.save_snapshot('72450', True, [{'id': '42', 'name': 'Synthetic player'}], 'synthetic')
    store.save_secrets('72450', {'mk': 'synthetic-manager-key'})

    async def request(self, resource, **params):
        return document

    monkeypatch.setattr(main.ClassicClient, 'request', request)
    response = client.post('/api/sync', json={'team_id': '72450', 'kind': 'academy'})
    assert response.status_code == 422, response.text
    assert len(client.get('/api/state?team_id=72450').json()['academy']) == 1


def test_identical_reread_refreshes_source_without_rewriting_history_or_inventing_progress(client):
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player', 'strength': 7}]
    for cohort in [True, False]:
        store.save_snapshot('72450', cohort, players, 'First read', '2026-01-01T10:00:00Z', {'season': 64, 'round': 1, 'day': 1})
        store.save_snapshot('72450', cohort, players, 'Second read', '2026-11-01T10:00:00Z', {'season': 64, 'round': 2, 'day': 3})
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad_source']['observed_at'] == '2026-11-01T10:00:00Z'
    assert state['squad_source']['first_observed_at'] == '2026-01-01T10:00:00Z'
    assert state['squad_source']['source'] == 'Second read'
    assert state['squad_source']['first_source'] == 'First read'
    market = client.get('/api/market?team_id=72450').json()
    assert market['analysis']['squad']['observed_at'] == '2026-11-01T10:00:00Z'
    assert json.loads(state['squad_source']['game_date']) == {'season': 64, 'round': 2, 'day': 3}
    assert state['squad'][0]['changes'] == {}
    assert len(state['snapshots']) == 2
    series = progression_series(store, '72450', False)
    assert len(series['points']) == 1
    assert series['points'][0]['at'] == '2026-01-01T10:00:00+00:00'
    assert series['points'][0]['players']['42']['deltas'] == {}
    assert series['points'][0]['sources'][0]['source'] == 'First read'
    with store.db() as db:
        assert json.loads(db.execute("SELECT game_date FROM snapshots WHERE youth=0").fetchone()[0]) == {'season': 64, 'round': 1, 'day': 1}
    from server.workbench import build_daily, AlertPreferences
    daily = build_daily([state], {}, AlertPreferences().model_dump(), {}, generated_at='2026-11-02T10:00:00Z')
    assert not any(action['kind'] == 'freshness' for action in daily['actions'])


def test_older_identical_file_does_not_make_current_observation_older(client):
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player'}]
    store.save_snapshot('72450', False, players, 'First', '2026-10-20T10:00:00Z')
    store.save_snapshot('72450', False, players, 'New', '2026-11-01T10:00:00Z', {'season': 64, 'round': 2, 'day': 3})
    store.save_snapshot('72450', False, players, 'Old file', '2026-10-01T10:00:00Z', {'season': 63, 'round': 1, 'day': 1})
    source = client.get('/api/state?team_id=72450').json()['squad_source']
    assert source['observed_at'] == '2026-11-01T10:00:00Z'
    assert source['first_observed_at'] == '2026-10-20T10:00:00Z'
    assert source['source'] == 'New'
    assert json.loads(source['game_date']) == {'season': 64, 'round': 2, 'day': 3}

def test_overlapping_legacy_and_generic_sheets_are_rejected_atomically(store):
    result = imports.parse_import(ods({
        'players': [['id', 'name'], ['42', 'Chosen club player']],
        'latouff_players': [['id', 'name'], ['43', 'Legacy club player']],
        'team': [['name'], ['Must not replace metadata']],
    }), 'overlap.ods')
    with pytest.raises(ValueError, match='effectif|destination'):
        store.import_result(result, '72444', False, 'overlap.ods')
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM teams WHERE id='72444'").fetchone()[0] == 0

@pytest.mark.parametrize('stamp', ['not-a-date', '2026-11-03T10:00:00Z'])
def test_invalid_or_future_reread_cannot_replace_last_valid_observation(client, monkeypatch, stamp):
    from server import storage
    monkeypatch.setattr(storage, 'now', lambda: '2026-11-02T10:00:00Z')
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player'}]
    store.save_snapshot('72450', False, players, 'Original', '2026-10-01T10:00:00Z')
    store.save_snapshot('72450', False, players, 'Current', '2026-11-01T10:00:00Z')
    store.save_snapshot('72450', False, players, 'Invalid file', stamp)
    source = client.get('/api/state?team_id=72450').json()['squad_source']
    assert source['observed_at'] == '2026-11-01T10:00:00Z'
    assert source['source'] == 'Current'


def test_same_dated_historical_file_remains_stale_after_reread(client, monkeypatch):
    from server import storage
    from server.workbench import build_daily, AlertPreferences
    monkeypatch.setattr(storage, 'now', lambda: '2026-11-02T10:00:00Z')
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player'}]
    for cohort in [True, False]:
        store.save_snapshot('72450', cohort, players, 'Original file', '2026-10-01')
        store.save_snapshot('72450', cohort, players, 'Repeated file', '2026-10-01')
    state = client.get('/api/state?team_id=72450').json()
    daily = build_daily([state], {}, AlertPreferences().model_dump(), {}, generated_at='2026-11-02T10:00:00Z')
    assert any(action['kind'] == 'freshness' for action in daily['actions'])
    assert state['squad_source']['observed_at'] == '2026-10-01'
    assert state['squad_source']['first_observed_at'] == '2026-10-01'
    assert len(state['snapshots']) == 2

def test_valid_reread_recovers_from_future_legacy_observation(client, monkeypatch):
    from server import storage
    monkeypatch.setattr(storage, 'now', lambda: '2026-11-02T10:00:00Z')
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player'}]
    store.save_snapshot('72450', False, players, 'Future legacy', '2027-01-01T10:00:00Z')
    store.save_snapshot('72450', False, players, 'Real read', '2026-11-01T10:00:00Z')
    source = client.get('/api/state?team_id=72450').json()['squad_source']
    assert source['observed_at'] == '2026-11-01T10:00:00Z'
    assert source['first_observed_at'] == '2027-01-01T10:00:00Z'

@pytest.mark.parametrize('unique_history', [False, True])
def test_existing_database_migration_and_export_preserve_original_and_latest_observations(client, unique_history):
    store = client.app.state.store
    players = [{'id': '42', 'name': 'Synthetic player'}]
    store.save_snapshot('72450', False, players, 'Legacy first', '2026-10-01T10:00:00Z')
    # Synthetic old schema, including the obsolete global digest uniqueness rule.
    with store.db() as db:
        db.execute('ALTER TABLE snapshots RENAME TO fixture_snapshots')
        db.execute('DROP INDEX snapshots_latest')
        constraint = ',UNIQUE(team_id,youth,digest)' if unique_history else ''
        db.execute('CREATE TABLE snapshots(id INTEGER PRIMARY KEY,team_id TEXT NOT NULL,youth INTEGER NOT NULL,source TEXT NOT NULL,observed_at TEXT NOT NULL,imported_at TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL,game_date TEXT' + constraint + ')')
        db.execute('INSERT INTO snapshots SELECT id,team_id,youth,source,observed_at,imported_at,digest,payload,game_date FROM fixture_snapshots')
        db.execute('DROP TABLE fixture_snapshots')
    reopened = Store(store.path.parent, seed=False)
    reopened.save_snapshot('72450', False, players, 'Latest read', '2026-11-01T10:00:00Z', {'season': 64, 'round': 2, 'day': 3})
    response = client.get('/api/export')
    assert response.status_code == 200
    exported = response.json()['snapshots']
    assert len(exported) == 1
    assert exported[0]['observed_at'] == '2026-10-01T10:00:00Z'
    assert exported[0]['source'] == 'Legacy first'
    assert exported[0]['last_observed_at'] == '2026-11-01T10:00:00Z'
    assert exported[0]['last_source'] == 'Latest read'
    assert json.loads(exported[0]['last_game_date']) == {'season': 64, 'round': 2, 'day': 3}
    assert client.get('/api/state?team_id=72450').json()['squad_source']['observed_at'] == '2026-11-01T10:00:00Z'

def test_reimported_older_json_does_not_rewind_game_date(client):
    store = client.app.state.store
    for stamp, game_date in [
        ('2026-10-01T10:00:00Z', {'season': 63, 'round': 15, 'day': 6}),
        ('2026-11-01T10:00:00Z', {'season': 64, 'round': 2, 'day': 3}),
        ('2026-10-15T10:00:00Z', {'season': 64, 'round': 1, 'day': 6}),
    ]:
        result = imports.parse_import(json.dumps({'players': [{'id': '42', 'name': 'Synthetic player'}], 'gameDate': game_date}).encode(), 'players.json')
        store.import_result(result, '72450', False, 'players.json', stamp)
    state = client.get('/api/state?team_id=72450').json()
    assert state['game_date'] == {'season': 64, 'round': 2, 'day': 3}
    assert json.loads(state['squad_source']['game_date']) == {'season': 64, 'round': 2, 'day': 3}

@pytest.mark.parametrize('reread_format', ['older-json', 'undated-json', 'undated-csv'])
def test_public_unchanged_import_preserves_latest_game_context(client, monkeypatch, reread_format):
    from server import storage
    player = {'id': '42', 'name': 'Synthetic player', 'age': 18, 'birthday': '1:1'}
    old_date = {'season': 63, 'round': 1, 'day': 1}
    current_date = {'season': 64, 'round': 1, 'day': 1}

    def upload(filename, raw):
        response = client.post('/api/import', data={'team_id': '72450', 'youth': 'true'},
                               files={'file': (filename, raw)})
        assert response.status_code == 200, response.text

    monkeypatch.setattr(storage, 'now', lambda: '2026-10-01T10:00:00Z')
    upload('first.json', json.dumps({'players': [player], 'gameDate': old_date}).encode())
    monkeypatch.setattr(storage, 'now', lambda: '2026-11-01T10:00:00Z')
    upload('latest.json', json.dumps({'players': [player], 'gameDate': current_date}).encode())
    before = client.get('/api/state?team_id=72450').json()
    assert before['academy'][0]['wc_projection'] == 66

    monkeypatch.setattr(storage, 'now', lambda: '2026-11-02T10:00:00Z')
    if reread_format == 'older-json':
        upload('old-file.json', json.dumps({'players': [player], 'gameDate': old_date}).encode())
    elif reread_format == 'undated-json':
        upload('undated.json', json.dumps({'players': [player]}).encode())
    else:
        upload('undated.csv', b'id,name,age,birthday\n42,Synthetic player,18,1:1')
    after = client.get('/api/state?team_id=72450').json()
    assert json.loads(after['academy_source']['game_date']) == current_date
    assert after['academy'][0]['wc_projection'] == 66
    assert after['game_date'] == current_date
    assert after['academy_source']['first_observed_at'] == '2026-10-01T10:00:00Z'
    assert len(after['snapshots']) == 1
    assert after['academy'][0]['changes'] == {}
    if reread_format == 'older-json':
        assert after['academy_source']['observed_at'] == before['academy_source']['observed_at']
        assert after['academy_source']['source'] == 'latest.json'
    exported = client.get('/api/export').json()['snapshots'][0]
    assert exported['observed_at'] == '2026-10-01T10:00:00Z'
    assert json.loads(exported['game_date']) == old_date

@pytest.mark.parametrize('endpoint', ['import', 'sync'])
@pytest.mark.parametrize('legacy_at', ['2027-01-01T10:00:00Z', 'invalid-legacy-date'])
def test_public_read_recovers_invalid_legacy_game_context(client, monkeypatch, endpoint, legacy_at):
    from server import storage
    monkeypatch.setattr(storage, 'now', lambda: '2026-11-01T12:00:00Z')
    monkeypatch.setattr(main, 'now', lambda: '2026-11-01T12:00:00Z')
    player = imports.normalize_player({'id': '42', 'name': 'Synthetic player', 'age': 18, 'birthday': '1:1'})
    legacy_game = {'season': 65, 'round': 2, 'day': 3}
    current_game = {'season': 64, 'round': 2, 'day': 3}
    store = client.app.state.store
    store.save_snapshot('72450', True, [player], 'Invalid legacy source', legacy_at, legacy_game)
    document = {'players': [player], 'gameDate': current_game}
    if endpoint == 'import':
        response = client.post('/api/import', data={'team_id': '72450', 'youth': 'true'},
                               files={'file': ('current.json', json.dumps(document).encode())})
    else:
        store.save_secrets('72450', {'mk': 'synthetic-manager-key'})

        async def request(self, resource, **params):
            return document

        monkeypatch.setattr(main.ClassicClient, 'request', request)
        response = client.post('/api/sync', json={'team_id': '72450', 'kind': 'academy'})
    assert response.status_code == 200, response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['academy_source']['observed_at'] == '2026-11-01T12:00:00Z'
    assert state['academy_source']['source'] == ('current.json' if endpoint == 'import' else 'API Classic')
    assert json.loads(state['academy_source']['game_date']) == current_game
    assert state['game_date'] == current_game
    assert state['academy'][0]['wc_projection'] == 66
    assert state['academy_source']['first_observed_at'] == legacy_at
    assert len(state['snapshots']) == 1
    exported = client.get('/api/export').json()['snapshots'][0]
    assert exported['observed_at'] == legacy_at
    assert exported['source'] == 'Invalid legacy source'
    assert json.loads(exported['game_date']) == legacy_game
    assert json.loads(exported['last_game_date']) == current_game


@pytest.mark.parametrize('youth', [False, True])
@pytest.mark.parametrize('file_format', ['ods', 'json'])
def test_legacy_changed_older_import_cannot_rewind_roster_or_progression(client, monkeypatch, youth, file_format):
    from server import storage
    cohort = 'academy' if youth else 'squad'

    def upload(value, observed, game_date, clock):
        monkeypatch.setattr(storage, 'now', lambda: clock)
        if file_format == 'ods':
            raw = ods({
                'moeskroen_ya' if youth else 'players': [['id', 'name', 'strength'], ['42', 'Synthetic player', value]],
                'team': [['date_maj'], [observed]],
            })
        else:
            raw = json.dumps({'players': [{'id': '42', 'name': 'Synthetic player', 'strength': value}],
                              'gameDate': game_date}).encode()
        return client.post('/api/import', data={'team_id': '72450', 'youth': str(youth).lower()},
                           files={'file': ('players.' + file_format, raw)})

    assert upload(12, '2026-10-31T12:00:00Z', {'season': 64, 'round': 2, 'day': 3}, '2026-10-31T12:00:00Z').status_code == 200
    before = client.get('/api/state?team_id=72450').json()
    history = client.get('/api/progression?team_id=72450').json()
    rejected = upload(5, '2026-10-01T12:00:00Z', {'season': 63, 'round': 15, 'day': 1}, '2026-11-01T12:00:00Z')
    assert rejected.status_code == 422, rejected.text
    assert client.get('/api/state?team_id=72450').json() == before
    assert client.get('/api/progression?team_id=72450').json() == history
    advice = client.get('/api/coach-advice?team_id=72450').json()
    assert next(skill['average'] for skill in advice[cohort]['skills'] if skill['skill'] == 'strength') == 12


def test_legacy_older_sheet_rejects_whole_workbook_before_rosters_and_annexes_change(client):
    store = client.app.state.store
    store.save_snapshot('72450', False, [{'id': '42', 'name': 'Earlier senior'}], 'Existing', '2026-10-01T10:00:00Z')
    store.save_snapshot('72444', True, [{'id': '43', 'name': 'Latest junior'}], 'Existing', '2026-10-31T10:00:00Z')
    before = client.get('/api/export').json()
    raw = ods({
        'players': [['id', 'name'], ['44', 'Must not become senior']],
        'latouff_academy': [['id', 'name'], ['45', 'Older junior']],
        'team': [['date_maj', 'name'], ['2026-10-15T10:00:00Z', 'Must not replace metadata']],
        'Academy': [['64', 'S1'], *[['', *(['FOR'] * 16)] for _ in range(4)]],
        'youth_training': [['s1', 's2', 's3', 's4'], ['strength', 'speed', 'attack', 'defense']],
    })
    response = client.post('/api/import', data={'team_id': '72450'}, files={'file': ('batch.ods', raw)})
    assert response.status_code == 422, response.text
    after = client.get('/api/export').json()
    for key in ('snapshots', 'teams', 'plans'):
        assert after[key] == before[key]
    assert store.get('training:72450') is None


@pytest.mark.parametrize('field', ['observed_at', 'date_maj'])
@pytest.mark.parametrize('stamp,expected', [('2026-10-01T14:00:00+02:00', '2026-10-01T12:00:00+00:00'), ('2026-10-01', '2026-10-01')])
def test_legacy_json_preserves_explicit_source_date_and_precision(client, field, stamp, expected):
    raw = json.dumps({'players': [{'id': '42', 'name': 'Dated player'}], field: stamp}).encode()
    response = client.post('/api/import', data={'team_id': '72450', 'youth': 'false'}, files={'file': ('dated.json', raw)})
    assert response.status_code == 200, response.text
    source = client.get('/api/state?team_id=72450').json()['squad_source']
    assert source['observed_at'] == expected


@pytest.mark.parametrize('stamp', ['2020-01-01T12:00:00', '2099-01-01T12:00:00Z', '2099-01-01', '2020-02-30', 'not-a-date', 123, False])
def test_legacy_supplied_invalid_date_is_rejected_without_false_freshness(client, stamp):
    raw = json.dumps({'players': [{'id': '42', 'name': 'Historical player'}], 'observed_at': stamp}).encode()
    response = client.post('/api/import', data={'team_id': '72450'}, files={'file': ('invalid.json', raw)})
    assert response.status_code == 422, response.text
    assert client.get('/api/state?team_id=72450').json()['academy'] == []


@pytest.mark.parametrize('game_date', [{'season': 62.8, 'round': 9, 'day': 5}, {'season': 64, 'round': 17, 'day': 1}])
def test_legacy_invalid_game_date_is_rejected_before_chronology_comparison(client, game_date):
    raw = json.dumps({'players': [{'id': '42', 'name': 'Historical player'}], 'gameDate': game_date}).encode()
    response = client.post('/api/import', data={'team_id': '72450'}, files={'file': ('invalid.json', raw)})
    assert response.status_code == 422, response.text
    assert client.get('/api/state?team_id=72450').json()['academy'] == []


def test_legacy_dated_identical_reread_refreshes_provenance_without_inventing_progress(client):
    for stamp in ['2026-10-01T12:00:00Z', '2026-10-31T12:00:00Z']:
        raw = json.dumps({'players': [{'id': '42', 'name': 'Unchanged player', 'strength': 12}], 'observed_at': stamp}).encode()
        response = client.post('/api/import', data={'team_id': '72450', 'youth': 'false'}, files={'file': ('same.json', raw)})
        assert response.status_code == 200, response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad_source']['observed_at'] == '2026-10-31T12:00:00+00:00'
    assert state['squad_source']['first_observed_at'] == '2026-10-01T12:00:00+00:00'
    assert len(state['snapshots']) == 1
    assert state['squad'][0]['changes'] == {}
    points = client.get('/api/progression?team_id=72450').json()['seniors']['points']
    assert len(points) == 1
    assert points[0]['players']['42']['deltas'] == {}


@pytest.mark.parametrize('filename,raw', [
    ('undated.json', b'{"players":[{"id":"42","name":"Updated player","strength":12}]}'),
    ('undated.csv', b'id,name,strength\n42,Updated player,12'),
])
def test_legacy_undated_file_keeps_import_time_compatibility(client, filename, raw):
    client.app.state.store.save_snapshot('72450', False, [{'id': '42', 'name': 'Earlier player', 'strength': 5}],
                                         'Earlier file', '2026-10-01T12:00:00Z')
    response = client.post('/api/import', data={'team_id': '72450', 'youth': 'false'}, files={'file': (filename, raw)})
    assert response.status_code == 200, response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad'][0]['strength'] == 12
    assert state['squad_source']['observed_at'] == '2026-11-02T10:00:00Z'
    assert len(state['snapshots']) == 2


@pytest.mark.parametrize('current,incoming,status', [
    ('2026-10-31T23:00:00Z', '2026-11-01T00:30:00+02:00', 422),
    ('2026-11-01T00:30:00+02:00', '2026-10-31T23:00:00Z', 200),
    ('2026-10-31T12:00:00Z', '2026-10-31', 200),
])
def test_legacy_chronology_compares_instants_without_inventing_time_for_date_only(client, current, incoming, status):
    client.app.state.store.save_snapshot('72450', False, [{'id': '42', 'name': 'Current player'}], 'Current', current)
    raw = json.dumps({'players': [{'id': '42', 'name': 'Incoming player'}], 'observed_at': incoming}).encode()
    response = client.post('/api/import', data={'team_id': '72450', 'youth': 'false'}, files={'file': ('dated.json', raw)})
    assert response.status_code == status, response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad'][0]['name'] == ('Incoming player' if status == 200 else 'Current player')


def test_changed_file_cannot_precede_last_successful_identical_read(client):
    for strength, stamp in [(12, '2026-10-01T12:00:00Z'), (12, '2026-10-31T12:00:00Z'), (5, '2026-10-15T12:00:00Z')]:
        raw = json.dumps({'players': [{'id': '42', 'name': 'Synthetic player', 'strength': strength}], 'observed_at': stamp}).encode()
        response = client.post('/api/import', data={'team_id': '72450', 'youth': 'false'}, files={'file': ('dated.json', raw)})
        assert response.status_code == (422 if strength == 5 else 200), response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['squad'][0]['strength'] == 12
    assert len(state['snapshots']) == 1


@pytest.mark.parametrize('endpoint', ['import', 'sync'])
@pytest.mark.parametrize('legacy_at', ['2027-01-01T10:00:00Z', 'invalid-legacy-date'])
def test_changed_current_read_can_replace_invalid_legacy_chronology(client, monkeypatch, endpoint, legacy_at):
    store = client.app.state.store
    store.save_snapshot('72450', True, [{'id': '42', 'name': 'Legacy player', 'strength': 5}],
                        'Invalid legacy source', legacy_at, {'season': 65, 'round': 2, 'day': 3})
    document = {'players': [{'id': '42', 'name': 'Current player', 'strength': 12}],
                'gameDate': {'season': 64, 'round': 2, 'day': 3}}
    if endpoint == 'import':
        response = client.post('/api/import', data={'team_id': '72450', 'youth': 'true'},
                               files={'file': ('current.json', json.dumps(document).encode())})
    else:
        store.save_secrets('72450', {'mk': 'synthetic-manager-key'})

        async def request(self, resource, **params):
            return document

        monkeypatch.setattr(main.ClassicClient, 'request', request)
        response = client.post('/api/sync', json={'team_id': '72450', 'kind': 'academy'})
    assert response.status_code == 200, response.text
    state = client.get('/api/state?team_id=72450').json()
    assert state['academy'][0]['strength'] == 12
    assert state['academy_source']['observed_at'] == '2026-11-02T10:00:00Z'
    assert len(state['snapshots']) == 2


@pytest.mark.parametrize('youth', [False, True])
def test_identical_roster_does_not_allow_older_workbook_to_overwrite_annexes(client, youth):
    def upload(stamp, skill):
        raw = ods({
            'moeskroen_ya' if youth else 'players': [['id', 'name', 'strength'], ['42', 'Synthetic player', 12]],
            'team': [['date_maj', 'bank_balance'], [stamp, '1000']],
            'youth_training': [['id', 's1'], ['1', skill]],
        })
        return client.post('/api/import', data={'team_id': '72450'}, files={'file': ('dated.ods', raw)})

    assert upload('2026-10-31T12:00:00Z', 'strength').status_code == 200
    before = client.get('/api/state?team_id=72450').json()
    response = upload('2026-10-01T12:00:00Z', 'speed')
    assert response.status_code == 422, response.text
    assert client.get('/api/state?team_id=72450').json() == before
    assert client.app.state.store.get('training:72450') == ['strength', '', '', '']
    # An actual later reread remains usable, including its new instructions.
    assert upload('2026-11-01T12:00:00Z', 'speed').status_code == 200
    after = client.get('/api/state?team_id=72450').json()
    assert client.app.state.store.get('training:72450') == ['speed', '', '', '']
    assert len(after['snapshots']) == 1


def test_older_legacy_annexes_use_their_own_team_destination_and_reject_whole_batch(client):
    store = client.app.state.store
    raw = ods({
        'players': [['id', 'name'], ['42', 'Chosen club player']],
        'latouff_yatt': [['id', 's1'], ['1', 'speed']],
    })
    result = imports.parse_import(raw, 'training.ods')
    # The named training targets another club, independently of the generic roster.
    store.save_snapshot('72444', True, [{'id': '43', 'name': 'Latest affiliate junior'}],
                        'Current affiliate source', '2026-10-31T12:00:00Z')
    store.set('training:72444', ['strength', '', '', ''])
    with pytest.raises(ValueError, match='ancien'):
        store.import_result(result, '72450', False, 'training.ods', '2026-10-01T12:00:00Z')
    assert store.get('training:72444') == ['strength', '', '', '']
    assert client.get('/api/state?team_id=72450').json()['squad'] == []


def test_older_identical_roster_can_add_missing_historical_plan_without_overwrite(client):
    store = client.app.state.store
    raw = ods({
        'players': [['id', 'name'], ['42', 'Synthetic player']],
        'Academy': [['64', 'S1'], *[['', *(['FOR'] * 16)] for _ in range(4)]],
    })
    result = imports.parse_import(raw, 'historical-plan.ods')
    store.save_snapshot('72450', False, result['players'], 'Current source', '2026-10-31T12:00:00Z')
    store.import_result(result, '72450', False, 'historical-plan.ods', '2026-10-01T12:00:00Z')
    state = client.get('/api/state?team_id=72450').json()
    assert state['plans']['64'][0] == ['strength'] * 16
    assert state['squad_source']['observed_at'] == '2026-10-31T12:00:00Z'
    result['plans']['64'][0][0] = 'speed'
    store.import_result(result, '72450', False, 'historical-plan.ods', '2026-10-01T12:00:00Z')
    assert client.get('/api/state?team_id=72450').json()['plans']['64'][0][0] == 'strength'
