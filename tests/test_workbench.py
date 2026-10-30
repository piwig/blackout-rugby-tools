"""Workbench behavior against private stores; no Classic network calls."""
import importlib.util
import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    # Exercise real auth/context even before the coordinating integration lands.
    if not any(getattr(r, 'path', '') == '/api/workbench/daily' for r in app.routes):
        if importlib.util.find_spec('server.workbench'):
            from server.workbench import register_workbench
            endpoint = next(r for r in app.routes if getattr(r, 'path', '') == '/api/state')
            context = inspect.getclosurevars(endpoint.endpoint).nonlocals
            auth = endpoint.dependant.dependencies[0].call
            vacation = next(r for r in app.routes if getattr(r, 'path', '') == '/api/vacation/status')
            service = inspect.getclosurevars(vacation.endpoint).nonlocals['vacation_service']
            register_workbench(app, context['store'], auth, context['require_team'], endpoint.endpoint, app.state.accounts, service)
            app.router.routes.sort(key=lambda r: getattr(r, 'path', '') == '/{path:path}')
    return app


def login(client, name='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': name, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def event(**changes):
    return {'id': 'training-1', 'kind': 'training', 'title': 'Séance technique',
            'starts_at': '2026-11-02T18:30:00+01:00', 'timezone': 'Europe/Paris',
            'importance': 'normal', 'notes': 'Deux groupes', 'player_ids': [],
            'status': 'planned', 'source': 'manual', **changes}


def save_calendar(client, headers, events, revision=0):
    return client.post('/api/workbench/calendar', headers=headers,
                       json={'team_id': '72450', 'expected_revision': revision, 'events': events})


def test_workbench_requires_auth_csrf_and_private_club(app):
    with TestClient(app) as client:
        assert client.get('/api/workbench/daily').status_code == 401
        headers = login(client)
        assert save_calendar(client, {}, []).status_code == 403
        assert client.get('/api/workbench/calendar?team_id=9999999').status_code == 404
        assert client.get('/api/workbench/identity?team_id=bad').status_code == 422
        assert client.post('/api/workbench/calendar', headers=headers, json={
            'team_id': '72450', 'expected_revision': 0, 'events': [], 'user_id': 'primary'}).status_code == 422


def test_calendar_roundtrip_revision_and_rotation_validation(app):
    with TestClient(app) as client:
        headers = login(client)
        first = save_calendar(client, headers, [event()])
        assert first.status_code == 200, first.text
        assert first.json()['revision'] == 1
        assert first.json()['events'][0]['starts_at'] == '2026-11-02T18:30:00+01:00'
        assert save_calendar(client, headers, [event(title='Perte')]).status_code == 409
        assert client.get('/api/workbench/calendar?team_id=72450').json()['events'][0]['title'] == 'Séance technique'
        assert save_calendar(client, headers, [event(player_ids=['9999999'])], 1).status_code == 422
        assert save_calendar(client, headers, [], 1).json()['revision'] == 2


@pytest.mark.parametrize('change', [
    {'starts_at': '2026-11-02T18:30:00'}, {'starts_at': 'not-a-date'},
    {'starts_at': '2026-02-30T18:30:00Z'}, {'timezone': 'Mars/Base'},
    {'ends_at': '2026-11-01T12:00:00Z'}, {'title': 'x'*161},
    {'player_ids': ['42', '42']}, {'importance': 'extreme'},
])
def test_calendar_rejects_invalid_dates_and_documents(app, change):
    with TestClient(app) as client:
        headers = login(client)
        assert save_calendar(client, headers, [event(**change)]).status_code == 422


def test_managers_with_same_team_id_cannot_share_workbench_documents(app):
    with TestClient(app) as admin, TestClient(app) as other:
        ah = login(admin)
        admin.post('/api/admin/users', headers=ah, json={'username': 'alice', 'password': 'Another-password-5678'})
        oh = login(other, 'alice', 'Another-password-5678')
        other.post('/api/teams', headers=oh, json={'team_id': '72450', 'name': 'Private club', 'country': 'FR'})
        assert save_calendar(admin, ah, [event(title='Only admin')]).status_code == 200
        assert other.get('/api/workbench/calendar?team_id=72450').json()['events'] == []
        other.post('/api/workbench/identity', headers=oh, json={'team_id': '72450', 'expected_revision': 0,
                    'identity': {'palette': 'ocean', 'initials': 'AL', 'symbol': 'ball'}})
        assert admin.get('/api/workbench/identity?team_id=72450').json()['identity']['palette'] == 'forest'
        assert 'Only admin' not in other.get('/api/workbench/daily').text


def test_identity_is_finite_and_revisioned(app):
    with TestClient(app) as client:
        headers = login(client)
        body = {'team_id': '72450', 'expected_revision': 0, 'identity': {'palette': 'ocean', 'initials': 'RFC', 'symbol': 'ball'}}
        assert client.post('/api/workbench/identity', headers=headers, json=body).status_code == 200
        assert client.post('/api/workbench/identity', headers=headers, json=body).status_code == 409
        body.update(expected_revision=1, identity={'palette': 'url(evil)', 'initials': '<svg>', 'symbol': '<script>'})
        assert client.post('/api/workbench/identity', headers=headers, json=body).status_code == 422


def test_daily_fatigue_requires_explicit_scale_and_uses_private_notes(app):
    app.state.store.save_snapshot('72450', False, [{'id': '42', 'name': 'Player', 'energy': 5}], 'test',
                                 (datetime.now(timezone.utc)-timedelta(days=12)).isoformat())
    with TestClient(app) as client:
        headers = login(client)
        client.post('/api/notes', headers=headers, json={'team_id': '72450', 'player_id': '42', 'text': 'Review role', 'watch': True})
        before = client.get('/api/workbench/daily').json()
        club = next(c for c in before['clubs'] if c['team_id'] == '72450')
        assert club['fatigue']['low_count'] is None
        assert club['fatigue']['unknown_count'] == 1
        prefs = before['preferences']['preferences']
        prefs.update(energy_scale='level', energy_floor=6)
        response = client.post('/api/workbench/preferences', headers=headers,
                               json={'expected_revision': 0, 'preferences': prefs})
        assert response.status_code == 200, response.text
        after = client.get('/api/workbench/daily').json()
        club = next(c for c in after['clubs'] if c['team_id'] == '72450')
        assert club['fatigue']['low_count'] == 1
        kinds = {a['kind'] for a in after['actions'] if a['team_id'] == '72450'}
        assert {'fatigue', 'freshness', 'notes', 'followup'} <= kinds


def test_daily_overdue_and_done_calendar_priority(app):
    yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    with TestClient(app) as client:
        headers = login(client)
        assert save_calendar(client, headers, [event(kind='reminder', starts_at=yesterday),
                   event(id='finished', title='Already done', status='done', starts_at=yesterday)]).status_code == 200
        actions = client.get('/api/workbench/daily').json()['actions']
        assert any(a['kind'] == 'calendar' and a['event_id'] == 'training-1' and a['overdue'] for a in actions)
        assert not any(a.get('event_id') == 'finished' for a in actions)


def test_admin_feedback_requires_explicit_audience_and_status_revision(app):
    with TestClient(app) as admin, TestClient(app) as other:
        ah = login(admin)
        admin.post('/api/admin/users', headers=ah, json={'username': 'alice', 'password': 'Another-password-5678'})
        oh = login(other, 'alice', 'Another-password-5678')
        other.post('/api/teams', headers=oh, json={'team_id': '72450', 'name': 'Private club', 'country': 'FR'})
        private = {'team_id': '72450', 'expected_revision': 0, 'page': 'season', 'text': 'Private thought', 'rating': 3, 'audience': 'private'}
        assert other.post('/api/workbench/feedback', headers=oh, json=private).status_code == 200
        shared = {**private, 'expected_revision': 1, 'text': 'Please improve', 'audience': 'admin'}
        sent = other.post('/api/workbench/feedback', headers=oh, json=shared)
        assert sent.status_code == 200, sent.text
        assert other.get('/api/workbench/feedback/admin').status_code == 403
        inbox = admin.get('/api/workbench/feedback/admin')
        assert 'Private thought' not in inbox.text
        assert 'Private club' not in inbox.text
        item = inbox.json()['items'][0]
        assert item['text'] == 'Please improve'
        update = {'feedback_id': item['id'], 'status': 'reviewing', 'expected_revision': item['revision'], 'admin_view': True}
        assert admin.post('/api/workbench/feedback/status', headers=ah, json=update).status_code == 200
        assert admin.post('/api/workbench/feedback/status', headers=ah, json=update).status_code == 409
        assert any(x['status'] == 'reviewing' for x in other.get('/api/workbench/feedback').json()['items'])


def test_digest_and_exports_never_include_credentials(app):
    app.state.store.save_secrets('72450', {'m': '42', 'mk': 'SECRET-MANAGER', 'dk': 'SECRET-DEVELOPER', 'iv': 'SECRET-IV'})
    with TestClient(app) as client:
        headers = login(client)
        assert save_calendar(client, headers, [event()]).status_code == 200
        digest = client.get('/api/workbench/vacation-digest?team_id=72450&days=7')
        assert digest.status_code == 200, digest.text
        assert digest.json()['days'] == 7
        assert digest.json()['confirmed_count'] == 0
        assert 'SECRET' not in digest.text
        assert 'SECRET' not in client.get('/api/workbench/daily').text
        assert client.get('/api/workbench/vacation-digest?team_id=9999999').status_code == 404
        from server.workbench import export_workbench
        exported = export_workbench(app.state.store)
        assert 'Séance technique' in str(exported)
        assert 'SECRET' not in str(exported)


def test_calendar_concurrent_writers_do_not_overwrite_each_other(app):
    with TestClient(app) as first, TestClient(app) as second:
        h1, h2 = login(first), login(second)
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(save_calendar, first, h1, [event(title='First choice')]),
                    pool.submit(save_calendar, second, h2, [event(title='Second choice')])]
            responses = [job.result() for job in jobs]
        assert sorted(r.status_code for r in responses) == [200, 409]
        winner = next(r.json()['events'][0]['title'] for r in responses if r.status_code == 200)
        assert first.get('/api/workbench/calendar?team_id=72450').json()['events'][0]['title'] == winner


def test_calendar_disappeared_player_can_be_removed_one_event_at_a_time(app):
    app.state.store.save_snapshot('72450', False, [{'id': '42', 'name': 'Former player'}], 'test')
    with TestClient(app) as client:
        headers = login(client)
        first, second = event(player_ids=['42']), event(id='training-2', player_ids=['42'])
        assert save_calendar(client, headers, [first, second]).status_code == 200
        app.state.store.save_snapshot('72450', False, [], 'test')
        stale = client.get('/api/workbench/calendar?team_id=72450').json()
        assert stale['missing_player_ids'] == ['42']

        # Cleaning one event must not be blocked by the other retained reference.
        first['player_ids'] = []
        cleaned_first = save_calendar(client, headers, [first, second], 1)
        assert cleaned_first.status_code == 200, cleaned_first.text
        assert cleaned_first.json()['revision'] == 2
        assert cleaned_first.json()['missing_player_ids'] == ['42']
        assert client.get('/api/workbench/calendar?team_id=72450').json()['missing_player_ids'] == ['42']

        # A missing player cannot be introduced into another event or reintroduced.
        assert save_calendar(client, headers, [first, second, event(id='new-event', player_ids=['42'])], 2).status_code == 422
        assert save_calendar(client, headers, [{**first, 'player_ids': ['42']}, second], 2).status_code == 422
        assert save_calendar(client, headers, [first, {**second, 'player_ids': ['42', '999']}], 2).status_code == 422

        second['player_ids'] = []
        cleaned_second = save_calendar(client, headers, [first, second], 2)
        assert cleaned_second.status_code == 200, cleaned_second.text
        assert cleaned_second.json()['revision'] == 3
        assert cleaned_second.json()['missing_player_ids'] == []
        assert client.get('/api/workbench/calendar?team_id=72450').json()['missing_player_ids'] == []
        # An old revision cannot restore the stale reference after it was removed.
        assert save_calendar(client, headers, [first, {**second, 'player_ids': ['42']}], 1).status_code == 409


def test_preferences_reject_boolean_as_numeric_energy(app):
    with TestClient(app) as client:
        headers = login(client)
        response = client.post('/api/workbench/preferences', headers=headers,
                               json={'expected_revision': 0, 'preferences': {'energy_scale': 'percent', 'energy_floor': True}})
        assert response.status_code == 422


def test_vacation_digest_counts_confirmed_results_only_in_period_and_sanitizes_diagnostics():
    from server.workbench import vacation_digest
    clock = datetime.now(timezone.utc)
    timestamp = (clock-timedelta(days=1)).isoformat()
    status = {'rules': [{'team_id': '7', 'enabled': True, 'mode': 'automatic', 'paused_reason': 'mk=SECRET'}],
              'previews': [{'team_id': '7', 'status': 'uncertain', 'payload': {'mk': 'SECRET'}}, {'team_id': '8', 'status': 'uncertain'}],
              'events': [{'id': 1, 'team_id': '7', 'kind': 'sending', 'created_at': timestamp, 'message': 'mk=SECRET'},
                         {'id': 2, 'team_id': '7', 'kind': 'confirmed', 'created_at': timestamp, 'message': 'mk=SECRET'},
                         {'id': 3, 'team_id': '7', 'kind': 'confirmed', 'created_at': (clock-timedelta(days=8)).isoformat()},
                         {'id': 4, 'team_id': '8', 'kind': 'confirmed', 'created_at': timestamp}]}
    digest = vacation_digest(status, '7', 7)
    assert digest['confirmed_count'] == 1
    assert digest['unresolved_count'] == 1
    assert digest['rules'][0]['paused'] is True
    assert len(digest['events']) == 2
    assert 'SECRET' not in str(digest)


def test_daily_senior_notes_and_follows_open_the_squad_only():
    from server.workbench import AlertPreferences, build_daily
    data = {'current_team': {'id': '7', 'name': 'Club'}, 'squad': [{'id': '42'}], 'academy': [],
            'notes': {'42': {'watch': True, 'text': 'Senior note'},
                      '99': {'watch': True, 'text': 'Former player note'}}}
    report = build_daily([data], {}, AlertPreferences().model_dump(), {})
    notes = [a for a in report['actions'] if a['kind'] in ('notes', 'followup')]
    assert {(a['kind'], a['page']) for a in notes} == {('notes', 'squad'), ('followup', 'squad')}
    assert all(a['count'] == 1 for a in notes)
    club = report['clubs'][0]
    assert club['note_count'] == club['watch_count'] == 1
    assert club['stale_note_count'] == club['stale_watch_count'] == 1


def test_daily_notes_and_follows_have_distinct_cohort_actions():
    from server.workbench import AlertPreferences, build_daily
    data = {'current_team': {'id': '7', 'name': 'Club'}, 'squad': [{'id': '42'}], 'academy': [{'id': '43'}],
            'notes': {'42': {'watch': True, 'text': 'Senior note'}, '43': {'watch': True, 'text': 'Youth note'}}}
    report = build_daily([data], {}, AlertPreferences().model_dump(), {})
    notes = [a for a in report['actions'] if a['kind'] in ('notes', 'followup')]
    assert {(a['kind'], a['page']) for a in notes} == {('notes', 'squad'), ('followup', 'squad'),
                                                     ('notes', 'academy'), ('followup', 'academy')}
    assert len({a['id'] for a in notes}) == 4
    assert all(a['cohort'] == a['page'] and a['count'] == 1 for a in notes)
    assert report['clubs'][0]['note_count'] == report['clubs'][0]['watch_count'] == 2
