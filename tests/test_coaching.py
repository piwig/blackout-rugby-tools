"""Synthetic private coaching imports; exercise routes and real SQLite storage."""
import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from server.accounts import PrivateStore, active_store
from server.classic import ClassicClient, ClassicError
from server.storage import Store


GAME_DATE = {'season': 62, 'round': 9, 'day': 7}


def instructions():
    return {'status': 'Ok', 'team training': {'teamid': '123', 's1': 'stamina', 's2': 'defense', 's3': 'none', 's4': 'none'},
            'individual training': [{'id': '31', 'playerid': '101', 'teamid': '123', 'skill': 'defense', 'sessions': '2',
                                     'player name': 'Synthetic One', 'trainer name': 'Private Trainer'}],
            'gameDate': GAME_DATE, 'brt': '2026-10-31T21:00:00+12:00'}


def report():
    return {'status': 'Ok', 'report': {'id': '800', 'teamid': '123', 'season': '61', 'round': '8', 'report': {
        'team': {'skills': ['stamina', 'defense'], 'players': {
            '101': {'id': '101', 'pops': [{'skill': 'defense', 'was': 7, 'is': 8}], 'drops': [],
                    'csr': {'was': '10000', 'is': 10100}}}},
        'individual': {'players': {'101': {'id': '101', 'skills': [{'skill': 'defense', 'sessions': '2', 'pops': [],
            'trainer': 'Private Trainer', 'trainerlevel': '5', 'trainertype': 'defense'}],
            'csr': {'was': 10100, 'is': '10150'}, 'energy': {'was': 105, 'is': 95}}}}
    }}, 'gameDate': GAME_DATE}


def stats():
    return {'status': 'Ok', 'player statistics': {
        '101': {'playerid': '101', 'tackles': '8', 'missedtackles': '2', 'tries': '0', 'balltime': '6',
                'leaguecaps': '3', 'metresgained': '110', 'totalpoints': '0'},
        '102': {'playerid': '102', 'tackles': '0', 'missedtackles': '0', 'balltime': '0'}}, 'gameDate': GAME_DATE}


@pytest.fixture
def env(tmp_path, monkeypatch):
    stores = {name: Store(tmp_path / name, 'Testing-password-1234', seed=False) for name in ('primary', 'second')}
    for value in stores.values():
        value.set('classic_account', {'id': '50', 'username': 'synthetic', 'team_ids': ['123', '124']})
        with value.db() as db:
            db.executemany('INSERT INTO teams(id,name,country) VALUES(?,?,?)', [('123', 'Example Club', 'FR'), ('124', 'Other Club', 'FR'), ('u20:9', 'Selection', 'FR')])
    state = SimpleNamespace(stores=stores, creds={name: {'d': '7', 'dk': 'synthetic-dev', 'm': '50', 'mk': 'synthetic-key'} for name in stores},
                            responses={'ti': instructions(), 'tr': report(), 'ps': stats()}, calls=[], failure=None, after_request=None)
    async def remote(self, resource, **params):
        state.calls.append((resource, params))
        if getattr(state, 'delay', 0):
            await asyncio.sleep(state.delay)
        if resource == state.failure:
            raise ClassicError('secret-upstream-body')
        if resource == 'm':
            result = {'status': 'Ok', 'members': {params['memberid']: {'id': params['memberid'], 'email': 'synthetic@example.invalid'}}}
        elif resource == 't':
            result = {'status': 'Ok', 'teams': {params['teamid']: {'id': params['teamid'], 'owner': '50'}}}
        elif resource == 'p':
            result = {'status': 'Ok', 'players': {str(i): {'id': str(i), 'name': f'Synthetic {i}', 'teamid': params['teamid']} for i in (101, 102, 103)}}
        else:
            result = copy.deepcopy(state.responses[resource])
        if resource in state.responses and resource in ('m', 't', 'p'):
            result = copy.deepcopy(state.responses[resource])
        if callable(result):
            result = result(params)
        if state.after_request:
            state.after_request(resource)
        return result
    monkeypatch.setattr(ClassicClient, 'request', remote)
    app = FastAPI()
    proxy = PrivateStore()
    async def auth(request: Request):
        if request.headers.get('X-Manager') not in stores:
            raise HTTPException(401)
        return {'user_id': request.headers['X-Manager']}
    @app.middleware('http')
    async def context(request, call_next):
        owner = request.headers.get('X-Manager', 'primary')
        token = active_store.set(stores.get(owner, stores['primary']))
        try:
            return await call_next(request)
        finally:
            active_store.reset(token)
    def require_team(tid):
        with proxy.db() as db:
            row = db.execute('SELECT * FROM teams WHERE id=?', (tid,)).fetchone()
        if not row:
            raise HTTPException(404)
        return dict(row)
    def credentials(tid):
        return state.creds[Path(proxy.path).parent.name].copy()
    try:
        from server.coaching import register_coaching
    except ImportError:
        register_coaching = None
    if register_coaching:
        register_coaching(app, proxy, auth, require_team, credentials, lambda key: None)
    with TestClient(app) as client:
        client.headers['X-Manager'] = 'primary'
        state.client = client
        yield state


def preview(env, kind='instructions', **params):
    return env.client.post('/api/clubs/123/coaching/preview', json={'kind': kind, **params})


def confirm(env, value, tid='123'):
    return env.client.post(f'/api/clubs/{tid}/coaching/confirm', json={key: value[key] for key in ('preview_id', 'expected_revision')})


def bundle(env, query=''):
    return env.client.get('/api/clubs/123/coaching' + query)


def import_mail(env, body=None, team='123', filename='training.html'):
    if body is None:
        body = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_bytes()
    return env.client.post(f'/api/clubs/{team}/coaching/import-preview', files={'file': (filename, body)})


def test_local_mail_import_needs_no_classic_credentials_and_persists_only_normalized_report(env):
    store = env.stores['primary']
    with store.db() as db:
        db.execute("DELETE FROM kv WHERE key='classic_account'")
    env.creds.clear()
    store.save_snapshot('123', False, [{'id': '101', 'name': 'Camille Démo'}], 'Synthetic snapshot')
    response = import_mail(env, filename='private-name.html')
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['kind'] == 'report' and value['expected_revision'] == 0 and not value['already_imported']
    assert value['data']['provenance']['source'] == 'Classic email'
    assert value['data']['provenance']['source_format'] == 'html'
    assert value['identity'] == {'club_name': 'Example Club', 'club_id': None, 'player_count': 2,
                                 'roster_match_count': 1, 'missing_player_ids': ['102']}
    assert 'Certains joueurs du rapport ne figurent pas dans l’effectif actuel du club.' in value['warnings']
    assert 'L’identité déclarée dans le fichier ne certifie pas son expéditeur.' in value['warnings']
    assert bundle(env).json()['report_total'] == 0
    saved = confirm(env, value)
    assert saved.status_code == 200, saved.text
    assert saved.json()['imported'] and saved.json()['bundle']['revision'] == 1
    assert bundle(env).json()['reports'] == [dict(value['data'], source_disagreement=False)]
    with store.db() as db:
        row = db.execute("SELECT key,value FROM kv WHERE key LIKE 'coaching:123:report:%'").fetchone()
        assert row['key'].startswith('coaching:123:report:061:08:mail:')
        assert 'private-name.html' not in row['value'] and '<table>' not in row['value']
    assert env.calls == []


def test_local_mail_rejects_wrong_destination_and_explicit_club_id(env):
    synthetic = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    assert import_mail(env, team='999').status_code == 404
    assert import_mail(env, team='u20:9').status_code == 422
    assert import_mail(env, team='124').status_code == 422
    assert import_mail(env, synthetic.replace('page=training', 'clubid=124').encode()).status_code == 422
    assert import_mail(env, synthetic.replace('Example Club', 'example Club').encode()).status_code == 422
    assert bundle(env).json()['report_total'] == 0
    assert env.calls == []


def test_local_mail_matches_unicode_and_space_normalized_club_name(env):
    synthetic = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    with env.stores['primary'].db() as db:
        db.execute("UPDATE teams SET name=? WHERE id='123'", ('  Cafe\u0301    Imaginaire ',))
    response = import_mail(env, synthetic.replace('Example Club', 'Café&nbsp;Imaginaire').encode())
    assert response.status_code == 200, response.text
    assert response.json()['identity']['club_name'] == 'Café Imaginaire'


def test_upload_is_private_and_bounded(env):
    response = import_mail(env, b'x' * (2 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert bundle(env).json()['report_total'] == 0
    env.client.headers.pop('X-Manager')
    assert import_mail(env).status_code == 401


def test_identical_mail_from_eml_after_html_confirms_unchanged(env):
    from email.message import EmailMessage

    first = import_mail(env).json()
    assert confirm(env, first).status_code == 200
    email = EmailMessage()
    synthetic = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    email.set_content(synthetic, subtype='html', cte='base64')
    second = import_mail(env, email.as_bytes(), filename='forward.eml').json()
    assert second['already_imported'] and second['data']['key'] == first['data']['key']
    result = confirm(env, second).json()
    assert result['unchanged'] and result['bundle']['revision'] == 1
    assert result['bundle']['reports'][0]['provenance']['source_format'] == 'html'


def test_mail_keeps_distinct_sources_and_warns_only_on_shared_conflicts(env):
    phases = env.responses['tr']['report']['report']
    api_skill = phases['individual']['players']['101']['skills'][0]
    api_skill['trainer'] = 'Coach Émile'
    for phase in ('team', 'individual'):
        phases[phase]['players']['102'] = {'id': '102'}
    assert confirm(env, preview(env, 'report').json()).status_code == 200
    matching = import_mail(env).json()
    warning = 'Des rapports enregistrés pour cette période diffèrent sur des valeurs communes.'
    assert warning not in matching['warnings']
    assert confirm(env, matching).status_code == 200
    synthetic = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    different = import_mail(env, synthetic.replace('10,150', '10,160').encode()).json()
    assert warning in different['warnings'] and not different['already_imported']
    result = confirm(env, different).json()
    assert result['imported'] and result['bundle']['report_total'] == 3
    reports = result['bundle']['reports']
    assert len({report['key'] for report in reports}) == 3
    assert [report['provenance']['source'] for report in reports].count('Classic email') == 2
    assert warning in preview(env, 'report').json()['warnings']
    assert bundle(env, '?report_offset=2').json()['reports'][0]['provenance']['source'] == 'Classic API'


def test_changed_sessions_skill_is_visible_as_a_report_disagreement(env):
    first = import_mail(env).json()
    assert confirm(env, first).status_code == 200
    synthetic = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    modified = synthetic.replace('<b>Defense</b><br><span>2 sessions', '<b>Kicking</b><br><span>2 sessions')
    second = import_mail(env, modified.encode()).json()
    assert 'Des rapports enregistrés pour cette période diffèrent sur des valeurs communes.' in second['warnings']


@pytest.mark.parametrize('sessions,mail_change,api_lists,disagrees', [
    (True, '3:4', [['3:4']], False),
    (False, '3:4', [['4:5']], True),
    (False, '3:4', [['3:4'], ['4:5']], True),
    (False, '3:4', [['3:4'], ['3:4']], False),
    (False, 'Fair:Good', [['3:4']], False),
    (False, 'none', [['3:4']], True),
    (False, '3:4', [[]], True),
    (False, '3:4', [None], False),
    (False, '3:4', [[], None], False),
    (False, 'unknown', [['4:5']], False),
])
def test_individual_transition_agreement_in_preview_and_saved_history(env, sessions, mail_change, api_lists, disagrees):
    phases = env.responses['tr']['report']['report']
    phases['team'] = None
    entries = []
    for trained_skill, values in zip(('speed', 'defense'), api_lists):
        entry = {'skill': trained_skill, 'sessions': 1}
        if values is not None:
            entry['pops'] = [{'skill': 'handling', 'was': item.split(':')[0], 'is': item.split(':')[1]} for item in values]
        entries.append(entry)
    phases['individual']['players'] = {'101': {'id': '101'}, '102': {'id': '102', 'skills': entries}}
    assert confirm(env, preview(env, 'report').json()).status_code == 200

    html = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    heading = '<span><b>Skills Trained</b></span>\n          <ul><li><b>Handling</b><br><span>1 session</span></li></ul>'
    html = html.replace(heading, heading.replace('Handling', 'Speed') if sessions else '')
    change = '<b>Handling</b> popped from <b>Fair</b> to <b>Good</b>'
    if mail_change in ('none', 'unknown'):
        html = html.replace(change, 'No pops' if mail_change == 'none' else '')
    else:
        before, after = mail_change.split(':')
        html = html.replace(change, change.replace('Fair', before).replace('Good', after))
    mail = import_mail(env, html.encode()).json()
    warning = 'Des rapports enregistrés pour cette période diffèrent sur des valeurs communes.'
    preview_disagrees = warning in mail['warnings']
    assert confirm(env, mail).status_code == 200
    reports = bundle(env).json()['reports']
    assert [preview_disagrees, *(item['source_disagreement'] for item in reports)] == [disagrees] * 3


@pytest.mark.parametrize('roster,matches,missing', [
    (None, None, None),
    ([], 0, ['101', '102']),
    ([{'id': '102'}], 1, ['101']),
])
def test_mail_identity_uses_only_a_recorded_senior_roster(env, roster, matches, missing):
    store = env.stores['primary']
    store.save_snapshot('123', True, [{'id': '101'}], 'Synthetic youth roster')
    if roster is not None:
        store.save_snapshot('123', False, roster, 'Synthetic senior roster')
    mail = import_mail(env).json()
    assert mail['identity']['player_count'] == 2
    assert mail['identity']['roster_match_count'] == matches
    assert mail['identity']['missing_player_ids'] == missing
    assert ('Certains joueurs du rapport ne figurent pas dans l’effectif actuel du club.' in mail['warnings']) == bool(missing)
    assert confirm(env, mail).status_code == 200


def test_confirm_old_report_returns_its_history_page_including_on_duplicate(env):
    html = (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')
    for season in range(62, 82):
        newer = import_mail(env, html.replace('season 61', f'season {season}').encode()).json()
        assert confirm(env, newer).status_code == 200
    for unchanged in (False, True):
        old = import_mail(env).json()
        saved = confirm(env, old).json()
        assert saved['unchanged'] is unchanged
        page = saved['bundle']
        assert page['report_offset'] == 20 and page['report_total'] == 21
        assert [item['key'] for item in page['reports']] == [old['data']['key']]
        assert bundle(env, '?report_offset=20').json() == page
    assert len(bundle(env).json()['reports']) == 20


def test_saved_report_disagreement_includes_sources_outside_the_requested_page(env):
    assert confirm(env, preview(env, 'report').json()).status_code == 200
    original = import_mail(env).json()
    assert confirm(env, original).status_code == 200
    with env.stores['primary'].db() as db:
        sql = "SELECT key,value FROM kv WHERE key LIKE 'coaching:123:report:%' ORDER BY key"
        before = [tuple(row) for row in db.execute(sql)]
        assert all('source_disagreement' not in value for _, value in before)

    next_page = bundle(env, '?report_offset=1').json()['reports']
    assert len(next_page) == 1
    assert next_page[0]['provenance']['source'] == 'Classic API'
    assert next_page[0]['source_disagreement'] is True
    assert bundle(env).json()['reports'][0]['source_disagreement'] is True
    with env.stores['primary'].db() as db:
        assert [tuple(row) for row in db.execute(sql)] == before


@pytest.mark.parametrize('reported, warns', [(True, True), (False, False)])
def test_phase_participants_disagree_only_when_both_lists_are_supplied(env, reported, warns):
    phases = env.responses['tr']['report']['report']
    phases['individual'] = None
    if reported:
        phases['team']['players'] = {}
    else:
        phases['team'].pop('players')
    assert confirm(env, preview(env, 'report').json()).status_code == 200
    result = import_mail(env).json()
    warning = 'Des rapports enregistrés pour cette période diffèrent sur des valeurs communes.'
    assert (warning in result['warnings']) == warns


def test_mail_confirmation_rejects_other_owner_wrong_team_wrong_revision_and_expiry(env, monkeypatch):
    first = import_mail(env).json()
    env.client.headers['X-Manager'] = 'second'
    assert confirm(env, first).status_code == 409
    assert bundle(env).json()['report_total'] == 0
    env.client.headers['X-Manager'] = 'primary'
    assert confirm(env, first, '124').status_code == 409
    assert confirm(env, dict(first, expected_revision=1)).status_code == 409
    assert confirm(env, first).status_code == 200
    second = import_mail(env).json()
    import server.coaching as coaching
    monkeypatch.setattr(coaching.time, 'monotonic', lambda: float('inf'))
    assert confirm(env, second).status_code == 409


def test_mail_confirmation_rejects_changed_club_name_and_stale_revision(env):
    first = import_mail(env).json()
    with env.stores['primary'].db() as db:
        db.execute("UPDATE teams SET name='Renamed Club' WHERE id='123'")
    assert confirm(env, first).status_code == 409
    with env.stores['primary'].db() as db:
        db.execute("UPDATE teams SET name='Example Club' WHERE id='123'")
    first, second = import_mail(env).json(), import_mail(env).json()
    assert confirm(env, first).status_code == 200
    assert confirm(env, second).status_code == 409
    assert bundle(env).json()['report_total'] == 1


def test_new_api_reports_keep_numeric_energy_and_trainer_metadata(env):
    response = preview(env, 'report')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['schema_version'] == 2
    player = data['individual']['players'][0]
    assert player['energy'] == {'kind': 'numeric', 'scale': 'unreported', 'before': 105, 'after': 95}
    assert (player['energy_before'], player['energy_after']) == (105, 95)
    assert player['skills'][0]['trainer'] == {'name': 'Private Trainer', 'level': 5, 'type': 'defense'}


def test_rereading_legacy_optional_absence_and_null_keeps_the_original_api_report(env):
    legacy = preview(env, 'report').json()['data']
    legacy.pop('schema_version', None)
    player = legacy['individual']['players'][0]
    player.pop('energy', None)
    player.pop('player_name', None)
    player['skills'][0]['trainer'] = None
    with env.stores['primary'].db() as db:
        db.execute('INSERT INTO kv VALUES(?,?)', ('coaching:123:report:061:08', json.dumps(legacy)))
    response = preview(env, 'report')
    assert response.status_code == 200, response.text
    assert response.json()['already_imported']
    assert confirm(env, response.json()).json()['unchanged']
    assert bundle(env).json()['reports'] == [dict(legacy, source_disagreement=False)]
    env.responses['tr']['report']['report']['individual']['players']['101']['csr']['is'] = 600
    assert preview(env, 'report').status_code == 409


@pytest.mark.parametrize('old_name,new_name', [(None, 'Example Player'), ('Example Player', None)])
def test_api_player_name_available_from_one_read_keeps_legacy_proof_bytes(env, old_name, new_name):
    legacy = preview(env, 'report').json()['data']
    legacy.pop('schema_version')
    legacy['team']['players'][0]['player_name'] = old_name
    if old_name is None:
        legacy['team']['players'][0].pop('player_name')
    original = json.dumps(legacy, indent=2)
    with env.stores['primary'].db() as db:
        db.execute('INSERT INTO kv VALUES(?,?)', ('coaching:123:report:061:08', original))
    env.responses['tr']['report']['report']['team']['players']['101']['name'] = new_name
    response = preview(env, 'report')
    assert response.status_code == 200, response.text
    assert response.json()['already_imported']
    assert confirm(env, response.json()).json()['unchanged']
    with env.stores['primary'].db() as db:
        assert db.execute("SELECT value FROM kv WHERE key='coaching:123:report:061:08'").fetchone()['value'] == original


def test_api_two_known_conflicting_player_names_cannot_replace_original_proof(env):
    raw_player = env.responses['tr']['report']['report']['team']['players']['101']
    raw_player['name'] = 'Example First'
    assert confirm(env, preview(env, 'report').json()).status_code == 200
    raw_player['name'] = 'Example Second'
    assert preview(env, 'report').status_code == 409
    assert bundle(env).json()['reports'][0]['team']['players'][0]['player_name'] == 'Example First'


def test_known_conflicting_api_trainer_cannot_replace_original_proof(env):
    assert confirm(env, preview(env, 'report').json()).status_code == 200
    env.responses['tr']['report']['report']['individual']['players']['101']['skills'][0]['trainerlevel'] = '6'
    assert preview(env, 'report').status_code == 409
    assert bundle(env).json()['reports'][0]['individual']['players'][0]['skills'][0]['trainer']['level'] == 5


def test_preview_preserves_unknown_youth_and_does_not_save_before_confirm(env):
    response = preview(env)
    assert response.status_code == 200, response.text
    p = response.json()
    assert p['data']['team_skills'] == ['stamina', 'defense', None, None]
    assert p['data']['youth_skills'] is None
    assert p['data']['individual'] == [{'player_id': '101', 'player_name': 'Synthetic One', 'skill': 'defense', 'sessions': 2}]
    assert 'Private Trainer' not in response.text
    assert bundle(env).json()['instructions'] is None
    saved = confirm(env, p)
    assert saved.status_code == 200, saved.text
    assert saved.json()['imported'] and not saved.json()['unchanged']
    assert saved.json()['bundle']['revision'] == 1
    assert confirm(env, p).status_code == 409


def test_equivalent_read_is_idempotent_despite_new_source_clock(env):
    confirm(env, preview(env).json())
    env.responses['ti']['brt'] = '2026-11-01T21:00:00+12:00'
    env.responses['ti']['gameDate'] = {'season': 62, 'round': 10, 'day': 1}
    p = preview(env).json()
    assert p['already_imported'] is True
    result = confirm(env, p).json()
    assert result['unchanged'] and not result['imported']
    assert result['bundle']['revision'] == 1


def test_statistical_scope_names_and_unknown_counts_survive_import(env):
    response = preview(env, 'statistics', scope='league', season=61)
    assert response.status_code == 200, response.text
    value = response.json()['data']
    assert value['scope'] == 'league' and value['season'] == 61
    assert value['requested_count'] == 3 and value['missing_player_ids'] == ['103']
    assert value['players'][0]['player_name'] == 'Synthetic 101'
    assert value['players'][0]['counters']['carries'] == 6
    assert value['players'][0]['counters']['tries'] == 0
    assert value['players'][0]['counters']['yellow_cards'] is None
    assert value['players'][0]['tackle_success_rate'] == 80.0
    assert value['players'][1]['tackle_success_rate'] is None
    assert value['provenance']['source_resource'] == 'ps'
    assert value['provenance']['requested_scope'] == 'league'
    assert ('ps', {'playerids': '101,102,103', 'league': '1', 'season': '61'}) in env.calls
    assert all('minutes' not in player for player in value['players'])
    assert confirm(env, response.json()).status_code == 200


def test_report_uses_report_period_not_current_metadata_and_keeps_phases_separate(env):
    response = preview(env, 'report', season=61, round=8)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert (data['season'], data['round']) == (61, 8)
    assert data['team']['players'][0]['csr_after'] == 10100
    assert data['individual']['players'][0]['csr_before'] == 10100
    assert data['team']['players'][0]['energy_before'] is None
    assert data['team']['players'][0]['pops'] == [{'skill': 'defense', 'before': 7, 'after': 8}]
    assert data['provenance']['requested_period'] == {'season': 61, 'round': 8}
    assert confirm(env, response.json()).json()['bundle']['report_total'] == 1


def test_divergent_same_report_period_cannot_overwrite_saved_observation(env):
    confirm(env, preview(env, 'report', season=61, round=8).json())
    env.responses['tr']['report']['report']['team']['players']['101']['csr']['is'] = 99999
    assert preview(env, 'report', season=61, round=8).status_code == 409
    assert bundle(env).json()['reports'][0]['team']['players'][0]['csr_after'] == 10100


@pytest.mark.parametrize('resource', ['m', 't', 'ti', 'tr', 'p', 'ps'])
def test_failed_read_is_safe_and_preserves_previous_bundle(env, resource):
    confirm(env, preview(env).json())
    env.failure = resource
    kind = {'m': 'instructions', 't': 'instructions', 'ti': 'instructions', 'tr': 'report', 'p': 'statistics', 'ps': 'statistics'}[resource]
    response = preview(env, kind)
    assert response.status_code == 502
    assert 'secret-upstream-body' not in response.text
    assert bundle(env).json()['revision'] == 1


def test_failed_report_envelope_never_becomes_empty_report(env):
    env.responses['tr'] = {'status': 'Failed', 'error': 'private error token'}
    response = preview(env, 'report')
    assert response.status_code == 502 and 'private error' not in response.text
    assert bundle(env).json()['report_total'] == 0


@pytest.mark.parametrize('where', ['owner', 'private_member', 'instructions_team', 'instruction_team', 'roster_team', 'stats_player', 'report_team', 'report_period'])
def test_wrong_identity_or_scope_is_rejected_without_data(env, where):
    kind, args = 'instructions', {}
    if where == 'owner':
        env.responses['t'] = {'status': 'Ok', 'teams': {'123': {'id': '123', 'owner': '999'}}}
    elif where == 'private_member':
        env.responses['m'] = {'status': 'Ok', 'members': {'50': {'id': '50'}}}
    elif where == 'instructions_team':
        env.responses['ti']['team training']['teamid'] = '124'
    elif where == 'instruction_team':
        env.responses['ti']['individual training'][0]['teamid'] = '124'
    elif where == 'roster_team':
        kind = 'statistics'; env.responses['p'] = {'status': 'Ok', 'players': {'101': {'id': '101', 'teamid': '124', 'name': 'Other'}}}
    elif where == 'stats_player':
        kind = 'statistics'; env.responses['ps']['player statistics']['999'] = {'playerid': '999', 'tries': '2'}
    elif where == 'report_team':
        kind = 'report'; env.responses['tr']['report']['teamid'] = '124'
    else:
        kind, args = 'report', {'season': 62, 'round': 8}
    assert preview(env, kind, **args).status_code in (403, 502)
    assert bundle(env).json()['revision'] == 0


@pytest.mark.parametrize('body', [
    {'kind': 'statistics', 'scope': 'league'}, {'kind': 'statistics', 'scope': 'career', 'season': 62},
    {'kind': 'instructions', 'season': 62}, {'kind': 'report', 'season': 62},
    {'kind': 'report', 'season': 62, 'round': 17}, {'kind': 'report', 'season': True, 'round': 1},
    {'kind': 'report', 'season': '62', 'round': 1}, {'kind': 'statistics', 'playerids': ['101']},
    {'kind': 'statistics', 'scope': 'league', 'season': 1000}, {'kind': 'statistics', 'scope': 'league', 'season': 0},
])
def test_request_scope_rejects_extra_or_ambiguous_filters(env, body):
    response = env.client.post('/api/clubs/123/coaching/preview', json=body)
    assert response.status_code == 422
    assert env.calls == []


def test_local_and_remote_club_scope_do_not_accept_national_or_unknown_teams(env):
    assert env.client.get('/api/clubs/u20:9/coaching').status_code == 422
    assert env.client.post('/api/clubs/u20:9/coaching/preview', json={'kind': 'instructions'}).status_code == 422
    assert env.client.post('/api/clubs/999/coaching/preview', json={'kind': 'instructions'}).status_code == 404
    assert env.calls == []


def test_private_preview_rejects_other_manager_or_club_without_consuming_owner_token(env):
    p = preview(env).json()
    env.client.headers['X-Manager'] = 'second'
    assert confirm(env, p).status_code == 409
    assert bundle(env).json()['instructions'] is None
    env.client.headers['X-Manager'] = 'primary'
    assert confirm(env, p, '124').status_code == 409
    assert confirm(env, p).status_code == 200


@pytest.mark.parametrize('change', ['key', 'account'])
def test_reconnection_invalidates_existing_preview(env, change):
    p = preview(env).json()
    if change == 'key':
        env.creds['primary']['mk'] = 'new-manager-key'
    else:
        env.stores['primary'].set('classic_account', {'id': '50', 'team_ids': ['123', '124'], 'imported_at': 'later'})
    assert confirm(env, p).status_code == 409
    assert bundle(env).json()['revision'] == 0


def test_account_change_during_network_read_never_exposes_preview(env):
    def changed(resource):
        if resource == 'ti':
            env.creds['primary']['mk'] = 'changed-during-await'
    env.after_request = changed
    assert preview(env).status_code == 409


def test_two_previews_use_optimistic_club_revision(env):
    first, second = preview(env).json(), preview(env, 'statistics').json()
    assert confirm(env, first).status_code == 200
    assert confirm(env, second).status_code == 409
    assert bundle(env).json()['statistics_total'] == 0


def test_expired_preview_and_wrong_revision_cannot_save(env, monkeypatch):
    p = preview(env).json()
    bad = {**p, 'expected_revision': 99}
    assert confirm(env, bad).status_code == 409
    import server.coaching as coaching
    clock = coaching.time.monotonic()
    monkeypatch.setattr(coaching.time, 'monotonic', lambda: clock + 601)
    assert confirm(env, p).status_code == 409


def test_only_three_previews_per_manager_are_retained(env):
    values = [preview(env).json() for _ in range(4)]
    assert confirm(env, values[0]).status_code == 409
    assert confirm(env, values[-1]).status_code == 200


@pytest.mark.parametrize('value', ['-1', '1.5', 'NaN', True, '10000000000000000000'])
def test_malformed_counter_is_not_coerced_to_zero(env, value):
    env.responses['ps']['player statistics']['101']['tackles'] = value
    assert preview(env, 'statistics').status_code == 502


def test_absent_or_zero_tackle_denominator_stays_unknown(env):
    del env.responses['ps']['player statistics']['101']['missedtackles']
    data = preview(env, 'statistics').json()['data']
    assert all(row['tackle_success_rate'] is None for row in data['players'])


def test_report_missing_phases_and_changes_are_unknown_not_empty(env):
    raw = env.responses['tr']['report']['report']
    del raw['individual']
    del raw['team']['players']['101']['pops']
    data = preview(env, 'report').json()['data']
    assert data['individual'] is None
    assert data['team']['players'][0]['pops'] is None


def test_history_retains_more_than_one_page_and_paginates(env):
    for index in range(23):
        env.responses['ps']['player statistics']['101']['tries'] = str(index)
        assert confirm(env, preview(env, 'statistics').json()).status_code == 200
    first = bundle(env).json()
    assert first['statistics_total'] == 23 and len(first['statistics']) == 20
    last = bundle(env, '?statistics_offset=20').json()
    assert len(last['statistics']) == 3 and last['statistics_offset'] == 20
    assert bundle(env, '?statistics_offset=-1').status_code == 422
    assert bundle(env, '?report_offset=1000001').status_code == 422


def test_routes_require_authentication(env):
    del env.client.headers['X-Manager']
    assert bundle(env).status_code == 401
    assert preview(env).status_code == 401


def test_oversized_preview_never_evicts_previous_valid_preview(env, monkeypatch):
    import server.coaching as coaching
    saved = preview(env).json()
    old_limit = coaching.MAX_PREVIEW_BYTES
    monkeypatch.setattr(coaching, 'MAX_PREVIEW_BYTES', 1)
    assert preview(env, 'statistics').status_code == 413
    monkeypatch.setattr(coaching, 'MAX_PREVIEW_BYTES', old_limit)
    assert confirm(env, saved).status_code == 200


def test_preview_budget_evicts_oldest_before_exceeding_bytes(env, monkeypatch):
    import server.coaching as coaching
    first = preview(env).json()
    length = len(json.dumps(first['data'], ensure_ascii=False, separators=(',', ':')).encode())
    monkeypatch.setattr(coaching, 'MAX_PREVIEW_BYTES', length * 2 + 10)
    preview(env)
    third = preview(env).json()
    assert confirm(env, first).status_code == 409
    assert confirm(env, third).status_code == 200


def test_preview_global_limit_spans_private_managers(env):
    first = preview(env).json()
    root = env.stores['primary'].path.parent.parent
    for index in range(6):
        name = 'manager' + str(index)
        store = Store(root / name, 'Testing-password-1234', seed=False)
        store.set('classic_account', {'id': '50', 'team_ids': ['123']})
        with store.db() as db:
            db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?)', ('123', 'Example', 'FR'))
        env.stores[name] = store
        env.creds[name] = env.creds['primary'].copy()
        env.client.headers['X-Manager'] = name
        for _ in range(3):
            assert preview(env).status_code == 200
    env.client.headers['X-Manager'] = 'primary'
    assert confirm(env, first).status_code == 409


def test_timeout_is_safe_and_preserves_previous_history(env, monkeypatch):
    import server.coaching as coaching
    confirm(env, preview(env).json())
    env.delay = .05
    monkeypatch.setattr(coaching, 'READ_TIMEOUT', .001)
    assert preview(env).status_code == 502
    assert bundle(env).json()['revision'] == 1


def test_statistics_batches_use_only_the_verified_current_roster(env):
    env.responses['p'] = {'status': 'Ok', 'players': {str(i): {'id': str(i), 'name': 'Synthetic', 'teamid': '123'} for i in range(101, 152)}}
    env.responses['ps'] = lambda params: {'status': 'Ok', 'player statistics': {
        pid: {'playerid': pid, 'tackles': '2', 'missedtackles': '0'} for pid in params['playerids'].split(',')}, 'gameDate': GAME_DATE}
    p = preview(env, 'statistics').json()
    assert len(p['data']['players']) == 51 and p['data']['missing_player_ids'] == []
    calls = [params for resource, params in env.calls if resource == 'ps']
    assert len(calls) == 2 and len(calls[0]['playerids'].split(',')) == 50
    assert calls[1]['playerids'] == '151'


def test_statistics_batch_period_change_is_rejected(env):
    env.responses['p'] = {'status': 'Ok', 'players': {str(i): {'id': str(i), 'name': 'Synthetic', 'teamid': '123'} for i in range(101, 152)}}
    env.responses['ps'] = lambda params: {'status': 'Ok', 'player statistics': {}, 'gameDate': {
        'season': 62, 'round': 10 if params['playerids'] == '151' else 9, 'day': 1}}
    assert preview(env, 'statistics').status_code == 502


def test_oversized_roster_is_rejected_before_statistics_fetch(env):
    env.responses['p'] = {'status': 'Ok', 'players': {str(i): {'id': str(i), 'teamid': '123'} for i in range(1, 202)}}
    assert preview(env, 'statistics').status_code == 502
    assert not any(resource == 'ps' for resource, _ in env.calls)


def test_report_period_cannot_be_after_source_game_date(env):
    env.responses['tr']['report'].update(season='62', round='10')
    assert preview(env, 'report').status_code == 502


def test_new_instructions_revision_keeps_the_prior_observation(env):
    confirm(env, preview(env).json())
    env.responses['ti']['team training']['s1'] = 'strength'
    confirm(env, preview(env).json())
    assert bundle(env).json()['instructions']['team_skills'][0] == 'strength'
    with env.stores['primary'].db() as db:
        rows = db.execute("SELECT value FROM kv WHERE key LIKE 'coaching:123:instructions:%'").fetchall()
    assert len(rows) == 2
    assert {json.loads(row['value'])['team_skills'][0] for row in rows} == {'stamina', 'strength'}


@pytest.mark.parametrize('skill', ['Stamina', 'ENDURANCE', 'none', 1])
def test_individual_skill_codes_are_not_guessed(env, skill):
    env.responses['ti']['individual training'][0]['skill'] = skill
    assert preview(env).status_code == 502


def test_latest_reimport_of_older_instruction_makes_it_current_without_erasing_history(env):
    initial = copy.deepcopy(env.responses['ti'])
    confirm(env, preview(env).json())
    env.responses['ti']['team training']['s1'] = 'strength'
    confirm(env, preview(env).json())
    env.responses['ti'] = initial
    confirm(env, preview(env).json())
    assert bundle(env).json()['instructions']['team_skills'][0] == 'stamina'
    with env.stores['primary'].db() as db:
        rows = db.execute("SELECT value FROM kv WHERE key LIKE 'coaching:123:instructions:%'").fetchall()
    assert len({json.loads(row['value'])['key'] for row in rows}) == 3


def test_older_statistics_values_can_be_observed_again_without_hiding_latest_scope(env):
    initial = copy.deepcopy(env.responses['ps'])
    confirm(env, preview(env, 'statistics').json())
    env.responses['ps']['player statistics']['101']['tries'] = '3'
    confirm(env, preview(env, 'statistics').json())
    env.responses['ps'] = initial
    confirm(env, preview(env, 'statistics').json())
    history = bundle(env).json()['statistics']
    assert [item['players'][0]['counters']['tries'] for item in history] == [0, 3, 0]
    assert len({item['key'] for item in history}) == 3


def test_unreported_instruction_slot_is_distinct_from_explicit_empty_setting(env):
    del env.responses['ti']['team training']['s3']
    data = preview(env).json()['data']
    assert data['team_skills'] == ['stamina', 'defense', 'unreported', None]
    assert data['youth_skills'] is None


def test_simultaneous_confirmations_cannot_commit_the_same_revision_twice(env):
    from concurrent.futures import ThreadPoolExecutor
    first, second = preview(env).json(), preview(env, 'statistics').json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(confirm, env, first), pool.submit(confirm, env, second)
        assert sorted([one.result().status_code, two.result().status_code]) == [200, 409]
    assert bundle(env).json()['revision'] == 1


def test_malformed_local_account_binding_is_rejected_before_api_reads(env):
    env.stores['primary'].set('classic_account', {'id': '50', 'team_ids': None})
    assert preview(env).status_code == 403
    assert env.calls == []


@pytest.mark.parametrize('case', ['duplicate_skill', 'too_many_skills', 'duplicate_pop', 'reversed_pop', 'reversed_drop'])
def test_report_rejects_incoherent_or_repeated_skill_changes(env, case):
    phases = env.responses['tr']['report']['report']
    player = phases['team']['players']['101']
    trained = phases['individual']['players']['101']['skills']
    if case == 'duplicate_skill':
        trained.append(copy.deepcopy(trained[0]))
    elif case == 'too_many_skills':
        trained.extend(copy.deepcopy(trained[0]) for _ in range(10))
    elif case == 'duplicate_pop':
        player['pops'].append(copy.deepcopy(player['pops'][0]))
    elif case == 'reversed_pop':
        player['pops'][0].update(was=8, **{'is': 7})
    else:
        player['drops'] = [{'skill': 'defense', 'was': 7, 'is': 8}]
    assert preview(env, 'report').status_code == 502


def test_repeated_team_skill_slots_remain_valid_training_instructions(env):
    env.responses['tr']['report']['report']['team']['skills'] = ['stamina'] * 4
    assert preview(env, 'report').json()['data']['team']['skills'] == ['stamina'] * 4


def test_large_normalized_document_is_refused_before_storage(env):
    skill_names = ['stamina', 'handling', 'attack', 'defense', 'technique', 'strength', 'jumping', 'speed', 'agility', 'kicking']
    pops = [{'skill': skill, 'was': 7, 'is': 8} for skill in skill_names]
    entries = [{'skill': skill, 'sessions': '2', 'pops': pops} for skill in skill_names]
    env.responses['tr']['report']['report']['individual']['players'] = {
        str(i): {'id': str(i), 'skills': entries, 'csr': {'was': 10000, 'is': 10500}} for i in range(1, 201)}
    response = preview(env, 'report')
    assert response.status_code == 413
    assert bundle(env).json()['report_total'] == 0


def test_legacy_oversized_stored_document_is_rejected_before_json_decoding(env, monkeypatch):
    import server.coaching as coaching
    encoded = json.dumps({'oversized_marker': 'x' * 512001})
    with env.stores['primary'].db() as db:
        db.execute('INSERT INTO kv VALUES(?,?)', ('coaching:123:report:061:08', encoded))
    original = coaching.json.loads
    def guarded_loads(value, *args, **kwargs):
        assert 'oversized_marker' not in value, 'Oversized saved observation reached the JSON decoder'
        return original(value, *args, **kwargs)
    monkeypatch.setattr(coaching.json, 'loads', guarded_loads)
    assert bundle(env).status_code == 413
    with env.stores['primary'].db() as db:
        assert db.execute("SELECT COUNT(*) FROM kv WHERE key='coaching:123:report:061:08'").fetchone()[0] == 1


def test_confirmation_rechecks_individual_document_size(env, monkeypatch):
    import server.coaching as coaching
    p = preview(env).json()
    monkeypatch.setattr(coaching, 'MAX_DOCUMENT_BYTES', 1, raising=False)
    assert confirm(env, p).status_code == 413
    assert bundle(env).json()['revision'] == 0


def test_maximum_roster_and_documented_counters_fit_document_budget(env):
    source_fields = ('tackles missedtackles tries totalpoints metresgained balltime linebreaks tryassists turnoverswon '
        'penaltiesconceded handlingerrors yellowcards redcards kicks leaguecaps friendlycaps cupcaps conversions dropgoals '
        'penalties intercepts knockons forwardpasses beatendefenders injuries fights kickingmetres undertwentycaps nationalcaps '
        'othercaps avkickingmetres kicksoutonthefull penaltytime missedconversions misseddropgoals missedpenalties goodupandunders '
        'badupandunders upandunders goodkicks badkicks lineoutssecured lineoutsconceded lineoutsstolen successfullineoutthrows '
        'unsuccessfullineoutthrows worldcupcaps undertwentyworldcupcaps').split()
    ids = [str(i) for i in range(100000000000001, 100000000000201)]
    env.responses['p'] = {'status': 'Ok', 'players': {pid: {'id': pid, 'teamid': '123', 'name': '🏉' * 120} for pid in ids}}
    env.responses['ps'] = lambda params: {'status': 'Ok', 'player statistics': {
        pid: {'playerid': pid, **{field: '1000000000000' for field in source_fields}} for pid in params['playerids'].split(',')}, 'gameDate': GAME_DATE}
    response = preview(env, 'statistics')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert len(data['players']) == 200
    assert len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()) <= 512000
