"""Junior match files remain local and distinct from all verified Classic contexts."""
import json

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.match_import import normalize_match_document


def document(kind=3, **changes):
    return {'id': '77', 'type': kind, 'home': 'Synthetic home', 'away': 'Synthetic away',
            'home_score': kind, 'away_score': 0, 'season': 62,
            'events': [{'id': '1', 'text': 'Synthetic action', 'att': 'kick', 'possession': '0', 'field': '2'}], **changes}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED', '0')
    async def no_network(*args, **kwargs):
        pytest.fail('Local junior imports must not contact Classic.')
    monkeypatch.setattr('server.classic.ClassicClient._send', no_network)
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with TestClient(app) as c:
        c.headers['X-CSRF-Token'] = c.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'}).json()['csrf']
        yield c


@pytest.mark.parametrize('flag', [True, 1, '1'])
def test_junior_flag_is_explicitly_represented_by_local_type_three(flag):
    normalized = normalize_match_document(document(youth=flag, u20=0, nat=0))
    assert normalized['type'] == 3
    assert normalized['events'][0]['att'] == 'kick'


@pytest.mark.parametrize('changes', [
    {'type': 0, 'youth': True}, {'type': 1, 'youth': True}, {'type': 2, 'youth': True},
    {'youth': False}, {'youth': '0'}, {'youth': 0}, {'youth': 'true'}, {'youth': 1.0},
    {'youth': True, 'u20': True}, {'youth': True, 'nat': True},
])
def test_contradictory_or_invalid_youth_flags_are_rejected(changes):
    with pytest.raises(ValueError, match='[Jj]unior|youth'):
        normalize_match_document(document(**changes))


def test_youth_flag_without_explicit_type_requires_a_choice_instead_of_defaulting_to_seniors():
    raw = document(youth=True); raw.pop('type')
    with pytest.raises(ValueError, match='[Jj]unior'):
        normalize_match_document(raw)


@pytest.mark.parametrize('file', [False, True])
def test_junior_preview_does_not_write_and_csv_or_json_import_retains_type(client, file):
    if file:
        def send(preview):
            return client.post('/api/matches/file' + ('?preview=true' if preview else ''),
                               data={'id': '77', 'type': '3'}, files={'file': ('junior.csv', b'field,possession,att,text\n2,0,kick,Synthetic\n')})
    else:
        def send(preview):
            return client.post('/api/matches/import' + ('?preview=true' if preview else ''), json=document(youth=True))
    preview = send(True)
    assert preview.status_code == 200, preview.text
    assert preview.json()['match']['type'] == 3
    assert client.get('/api/matches/history').json()['total_stored'] == 0
    saved = send(False)
    assert saved.status_code == 200, saved.text
    assert client.get('/api/matches/3/77').json()['summary']['classified'] == 1


def test_same_number_across_four_contexts_keeps_annotations_statistics_links_and_exports_separate(client):
    for kind in (0, 1, 2, 3):
        result = client.post('/api/matches/import', json=document(kind))
        assert result.status_code == 200, result.text
    junior = client.get('/api/matches/3/77').json()
    changed = client.post('/api/matches/3/77/annotations', json={
        'expected_revision': 0, 'expected_source_digest': junior['review']['source_digest'],
        'changes': [{'event_key': junior['events'][0]['event_key'], 'classification': 'attack',
                     'att': 'percu', 'possession': 1, 'field': 3}],
    })
    assert changed.status_code == 200, changed.text
    for kind in (0, 1, 2):
        sibling = client.get(f'/api/matches/{kind}/77').json()
        assert sibling['events'][0]['att'] == 'kick' and sibling['review']['revision'] == 0
    for kind in (0, 1, 2, 3):
        history = client.get(f'/api/matches/history?type={kind}').json()
        assert history['total_filtered'] == 1 and history['matches'][0]['type'] == kind
        assert history['totals']['points_total'] == kind
        assert history['totals']['manual'] == (1 if kind == 3 else 0)
    links = [{'match_id': '77', 'match_type': kind, 'club_side': 'home', 'opponent': 'Synthetic opponent', 'season': 62} for kind in (0, 1, 2, 3)]
    saved = client.post('/api/insights/72450', json={'expected_revision': 0, 'document': {'match_links': links}})
    assert saved.status_code == 200, saved.text
    report = client.get('/api/insights/72450/opponents?match_type=3').json()
    assert report['match_count'] == 1 and report['opponent_actions'] == 1
    assert report['matches'][0]['match_type'] == 3
    assert client.get('/api/insights/72450/opponents?match_type=0').json()['opponent_actions'] == 0
    backup = client.get('/api/export').json()
    exported = [json.loads(row['payload']) for row in backup['matches']]
    assert {(row['id'], row['type']) for row in exported} == {('77', kind) for kind in (0, 1, 2, 3)}
    assert backup['manager_documents']['match_review:3:77']['revision'] == 1
    for row in exported:
        assert client.post('/api/matches/import', json=row).status_code == 200
    reread = client.get('/api/matches/3/77').json()
    assert reread['events'][0]['att'] == 'percu' and reread['review']['orphaned_count'] == 0
    assert client.get('/api/matches/history').json()['total_stored'] == 4


def test_junior_import_and_annotations_remain_private_and_csrf_protected(client):
    assert client.post('/api/matches/import', json=document(), headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post('/api/matches/import', json=document()).status_code == 200
    junior = client.get('/api/matches/3/77').json()
    body = {'expected_revision': 0, 'expected_source_digest': junior['review']['source_digest'],
            'changes': [{'event_key': junior['events'][0]['event_key'], 'reset': True}]}
    assert client.post('/api/matches/3/77/annotations', json=body, headers={'X-CSRF-Token': ''}).status_code == 403
    client.app.state.accounts.create('other', 'Another-password-1234')
    with TestClient(client.app) as other:
        assert other.get('/api/matches/3/77').status_code == 401
        other.headers['X-CSRF-Token'] = other.post('/api/login', json={'username': 'other', 'password': 'Another-password-1234'}).json()['csrf']
        assert other.get('/api/matches/3/77').status_code == 404
        assert other.post('/api/matches/3/77/annotations', json=body).status_code == 404
        assert other.get('/api/matches/history?type=3').json()['total_filtered'] == 0
        assert other.get('/api/export').json()['matches'] == []


def classic_documents():
    return {
        'f': {'fixtures': {'77': {'id': '77', 'hometeamid': '72450', 'guestteamid': '888',
                                'matchstart': '2020-01-01T13:00:00Z', 'matchfinish': '2020-01-01T15:00:00Z',
                                'botmatch': '0', 'data_removed': '0', 'youth': '1'}}},
        't': {'teams': {'72450': {'id': '72450', 'name': 'Synthetic home', 'youth': '0'},
                        '888': {'id': '888', 'name': 'Synthetic away'}}},
        'me': {'fixtureid': '77', 'youth': '1', 'events': document()['events']},
        'ls': {'fixtureid': '77', 'youth': '1', 'match_has_finished': '1', 'homescore': '0', 'guestscore': '5'},
    }


def synthetic_classic(monkeypatch, documents):
    calls = []
    async def request(self, resource, **params):
        calls.append((resource, params))
        assert resource in ('f', 't', 'me', 'ls')
        assert 'type' not in params
        assert 'u20' not in params and 'nat' not in params
        if resource == 't':
            assert 'youth' not in params  # Junior clubs share senior club identity, not a youth namespace.
        else:
            assert params['youth'] == '1'
        return documents[resource]
    monkeypatch.setattr('server.classic.ClassicClient.request', request)
    return calls


def test_direct_junior_preview_uses_youth_flag_and_confirmation_preserves_annotations_and_sibling(client, monkeypatch):
    calls = synthetic_classic(monkeypatch, classic_documents())
    for kind in (0, 3):
        assert client.post('/api/matches/import', json=document(kind)).status_code == 200
    junior = client.get('/api/matches/3/77').json()
    body = {'expected_revision': 0, 'expected_source_digest': junior['review']['source_digest'],
            'changes': [{'event_key': junior['events'][0]['event_key'], 'classification': 'attack', 'att': 'percu', 'possession': 1, 'field': 3, 'learn': False}]}
    assert client.post('/api/matches/3/77/annotations', json=body).status_code == 200
    response = client.post('/api/matches/direct/preview', json={'reference': 'https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture=77&youth=1', 'type': 3})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert [resource for resource, _ in calls] == ['f', 't', 'me', 'ls']
    assert preview['match']['type'] == 3 and preview['match']['home_score'] == 0
    assert client.get('/api/matches/3/77').json()['home_score'] == 3  # Preview has not written the new score.
    confirm = {key: preview[key] for key in ('source_token', 'expected_revision', 'expected_source_digest')}
    client.app.state.accounts.create('other', 'Another-password-1234')
    with TestClient(client.app) as other:
        other.headers['X-CSRF-Token'] = other.post('/api/login', json={'username': 'other', 'password': 'Another-password-1234'}).json()['csrf']
        assert other.post('/api/matches/direct/confirm', json=confirm).status_code == 409
        assert other.get('/api/matches/3/77').status_code == 404
    saved = client.post('/api/matches/direct/confirm', json=confirm)
    assert saved.status_code == 200, saved.text
    assert saved.json()['match']['events'][0]['att'] == 'percu'
    assert saved.json()['match']['home_score'] == 0
    assert client.get('/api/matches/0/77').json()['events'][0]['att'] == 'kick'
    assert client.get('/api/matches/history').json()['total_stored'] == 2
    assert client.post('/api/matches/direct/confirm', json=confirm).status_code == 409


def test_recent_junior_selection_is_explicit_and_uses_club_names(client, monkeypatch):
    calls = synthetic_classic(monkeypatch, classic_documents())
    client.post('/api/matches/import', json=document(0))
    response = client.post('/api/matches/recent', json={'team_id': '72450', 'type': 3})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['type'] == 3 and result['fixtures'][0]['type'] == 3
    assert result['fixtures'][0]['already_imported'] is False
    assert result['fixtures'][0]['home'] == 'Synthetic home'
    assert calls[0] == ('f', {'teamid': '72450', 'last': '20', 'youth': '1'})


@pytest.mark.parametrize('change,expected_calls', [
    (lambda d: d['f']['fixtures']['77'].update(data_removed='1'), ['f']),
    (lambda d: d['f']['fixtures']['77'].update(matchfinish=None), ['f']),
    (lambda d: d['me'].update(youth='0'), ['f', 't', 'me']),
    (lambda d: d.update(me={'status': 'Failed', 'error': 'PRIVATE'}), ['f', 't', 'me']),
    (lambda d: d['ls'].update(match_has_finished='0'), ['f', 't', 'me', 'ls']),
])
def test_unavailable_or_conflicting_junior_source_never_saves(client, monkeypatch, change, expected_calls):
    documents = classic_documents(); change(documents)
    calls = synthetic_classic(monkeypatch, documents)
    response = client.post('/api/matches/direct/preview', json={'reference': '77', 'type': 3})
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text
    assert [resource for resource, _ in calls] == expected_calls
    assert client.get('/api/matches/history').json()['total_stored'] == 0


@pytest.mark.parametrize('team_id,kind', [('u20:9', 3), ('nt:9', 3), ('9', 1), ('9', 2)])
def test_recent_type_cannot_change_team_namespace(team_id, kind):
    import asyncio
    from server.classic import ClassicError
    from server.match_direct import recent_matches
    class UnusedClient:
        async def request(self, *args, **kwargs):
            pytest.fail('A conflicting namespace must fail before any Classic request.')
    with pytest.raises(ClassicError):
        asyncio.run(recent_matches(UnusedClient(), team_id, match_type=kind))


def test_junior_sync_uses_the_same_verified_youth_mapping(client, monkeypatch):
    calls = synthetic_classic(monkeypatch, classic_documents())
    response = client.post('/api/matches/sync', json={'id': '77', 'type': 3})
    assert response.status_code == 200, response.text
    assert response.json()['type'] == 3
    assert [resource for resource, _ in calls] == ['f', 't', 'me', 'ls']
