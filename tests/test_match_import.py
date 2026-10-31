"""Offline Classic and BRT match imports, using only synthetic source documents."""
import json

import pytest
from xml.etree import ElementTree as ET
from fastapi.testclient import TestClient

from server.classic import parse_commentary
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED', '0')
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)

    async def no_network(*args, **kwargs):
        pytest.fail('Offline imports must never call Classic.')

    monkeypatch.setattr('server.classic.ClassicClient.request', no_network)
    with TestClient(app) as client:
        response = client.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
        client.headers['X-CSRF-Token'] = response.json()['csrf']
        yield client


def source(**changes):
    return {'status': 'Ok', 'fixtureid': 123, 'brt': '2026-10-31T22:53:13+12:00',
            'gameDate': {'season': 62, 'round': 9, 'day': 6}, 'events': [
                {'id': '90', 'index': '0', 'commentary': '[b]Scrum won.[/b]', 'possession': '1',
                 'field': '2', 'gametime': '86', 'half': '1', 'homescore': '0', 'guestscore': '0',
                 'actualtime': '86', 'losttime': '0'},
                {'id': '91', 'index': '1', 'commentary': 'A takes the ball up strongly on the drive.',
                 'possession': '0', 'field': '2', 'gametime': '91', 'half': '1',
                 'homescore': '0', 'guestscore': '0', 'actualtime': '91', 'losttime': '0'},
            ], **changes}


def upload(client, doc, **options):
    return client.post('/api/matches/file', data={'type': '1', **options},
                       files={'file': ('match.json', json.dumps(doc).encode(), 'application/json')})


@pytest.mark.parametrize('method', ['paste', 'file'])
def test_classic_import_preserves_events_and_source_metadata_without_guessing_match_details(client, method):
    response = (client.post('/api/matches/import?type=1', json=source()) if method == 'paste'
                else upload(client, source()))
    assert response.status_code == 200, response.text
    assert response.json()['id'] == '123' and response.json()['type'] == 1
    match = client.get('/api/matches/1/123').json()
    assert len(match['events']) == 2
    assert match['home'] == 'Domicile (nom non fourni)'
    assert match['away'] == 'Extérieur (nom non fourni)'
    assert match['home_score'] is None and match['away_score'] is None
    assert match['season'] is None and match['round'] is None
    assert match['source_game_date'] == {'season': 62, 'round': 9, 'day': 6}
    assert match['source_observed_at'] == '2026-10-31T22:53:13+12:00'
    for key in ('id', 'index', 'commentary', 'actualtime', 'losttime', 'homescore', 'guestscore', 'half'):
        assert match['events'][1][key] == source()['events'][1][key]
    assert match['summary']['total_events'] == 2
    assert match['summary']['classified'] == 1 and match['summary']['inferred'] == 1


def test_json_classification_matches_existing_xml_rules_without_double_correction(client):
    document = source()
    document['events'].append({'commentary': '', 'possession': '0', 'field': '2', 'gametime': '92'})
    events = document['events']
    root = ET.Element('root')
    for event in events:
        node = ET.SubElement(root, 'event')
        for key, value in event.items():
            ET.SubElement(node, key).text = value
    expected = parse_commentary(root)
    assert client.post('/api/matches/import?type=1', json=document).status_code == 200
    imported = client.get('/api/matches/1/123').json()
    for actual, legacy in zip(imported['events'], expected):
        assert all(actual[key] == value for key, value in legacy.items())
    assert imported['events'][1]['possession'] == '1'
    assert imported['events'][1]['possession_reported'] == '0'
    assert client.post('/api/matches/import', json=imported | {'summary': None}).status_code == 422
    imported.pop('summary')
    assert client.post('/api/matches/import', json=imported).status_code == 200
    assert client.get('/api/matches/1/123').json()['events'] == imported['events']


@pytest.mark.parametrize('method', ['paste', 'file'])
def test_preview_validates_and_counts_without_writing(client, method):
    if method == 'paste':
        response = client.post('/api/matches/import?type=1&preview=true', json=source())
    else:
        response = client.post('/api/matches/file?preview=true', data={'type': '1'},
                               files={'file': ('match.json', json.dumps(source()).encode())})
    assert response.status_code == 200, response.text
    assert response.json()['match']['event_count'] == 2
    assert response.json()['match']['id'] == '123'
    assert response.json()['match']['summary']['inferred'] == 1
    assert 'events' not in response.json()['match']
    assert client.get('/api/state').json()['matches'] == []


def test_dictionary_events_use_explicit_numeric_indexes_without_sorting_halftime_clock(client):
    doc = source(events={
        '103': {'index': '10', 'half': '2', 'gametime': '10', 'commentary': 'Unknown passage', 'field': 'Unknown', 'possession': 'Unknown'},
        '102': {'index': '2', 'half': '1', 'gametime': '2400', 'commentary': 'Unknown passage', 'field': '2', 'possession': '1'},
    })
    assert upload(client, doc).status_code == 200
    match = client.get('/api/matches/1/123').json()
    assert [event['id'] for event in match['events']] == ['102', '103']
    assert [event['gametime'] for event in match['events']] == ['2400', '10']
    assert match['events'][1]['field'] == 'Unknown' and match['events'][1]['possession'] == 'Unknown'
    assert match['summary']['classified'] == 0


@pytest.mark.parametrize('changes,query', [
    ({}, ''), ({'status': 'Error'}, '?type=1'), ({'events': [None]}, '?type=1'),
    ({'events': 'not-a-collection'}, '?type=1'), ({'events': {'x': []}}, '?type=1'),
    ({'fixtureid': True}, '?type=1'), ({'fixtureid': '12/3'}, '?type=1'),
    ({'type': True}, ''), ({'type': 3}, ''), ({'type': 0}, '?type=1'),
    ({'u20': 1}, '?type=0'), ({'u20': 1, 'nat': 1}, '?type=1'),
    ({}, '?type=1&id=456'), ({'id': '456'}, '?type=1'),
])
def test_invalid_or_conflicting_identity_and_events_are_rejected_atomically(client, changes, query):
    response = client.post('/api/matches/import' + query, json=source(**changes))
    assert response.status_code == 422
    assert client.get('/api/state').json()['matches'] == []


def test_explicit_normalized_metadata_and_preclassified_events_are_preserved(client):
    doc = {'id': '123', 'type': 0, 'home': 'Home side', 'away': 'Away side', 'home_score': 12,
           'away_score': 9, 'season': 61, 'round': 4,
           'events': [{'att': 'large', 'possession': '0', 'field': '2', 'text': 'On the drive.'}]}
    assert client.post('/api/matches/import', json=doc).status_code == 200
    assert upload(client, source()).status_code == 200
    assert client.get('/api/matches/0/123').json()['events'][0]['att'] == 'large'
    assert client.get('/api/matches/0/123').json()['home_score'] == 12
    assert client.get('/api/matches/0/123').json()['season'] == 61
    assert len(client.get('/api/state').json()['matches']) == 2
    with TestClient(client.app) as other:
        assert other.get('/api/matches/1/123').status_code == 401
        client.app.state.accounts.create('other', 'Another-password-1234')
        assert other.post('/api/login', json={'username': 'other', 'password': 'Another-password-1234'}).status_code == 200
        assert other.get('/api/matches/1/123').status_code == 404


def test_match_csv_retains_comments_and_accepts_more_than_player_file_limit(client):
    rows = 'field;possession;att;text\n' + '2;0;large;"Two; parts"\n' * 4001
    response = client.post('/api/matches/file', data={'id': '77', 'type': '2', 'home': 'Home side', 'away': 'Away side'},
                           files={'file': ('match.csv', rows.encode())})
    assert response.status_code == 200, response.text
    match = client.get('/api/matches/2/77').json()
    assert len(match['events']) == 4001 and match['events'][0]['text'] == 'Two; parts'


@pytest.mark.parametrize('method', ['paste', 'file'])
def test_event_count_limit_rejects_without_partial_save(client, method):
    doc = source(events=[{'text': 'unknown'}] * 20001)
    response = client.post('/api/matches/import?type=1', json=doc) if method == 'paste' else upload(client, doc)
    assert response.status_code == 422
    assert client.get('/api/state').json()['matches'] == []


@pytest.mark.parametrize('method', ['paste', 'file'])
def test_eight_megabyte_limit_is_identical_for_pasted_and_uploaded_json(client, method):
    raw = json.dumps(source(events=[])).encode() + b' ' * 8_000_000
    if method == 'paste':
        response = client.post('/api/matches/import?type=1', content=raw, headers={'Content-Type': 'application/json'})
    else:
        response = client.post('/api/matches/file', data={'type': '1'}, files={'file': ('match.json', raw)})
    assert response.status_code == 413
    assert client.get('/api/state').json()['matches'] == []


def test_classic_document_missing_events_does_not_create_an_empty_match(client):
    doc = source()
    del doc['events']
    assert client.post('/api/matches/import?type=1', json=doc).status_code == 422
    assert client.get('/api/state').json()['matches'] == []


def test_csv_parser_limit_is_reported_without_saving_or_echoing_source(client):
    raw = ('field;possession;att;text\n2;0;large;' + 'private-source-' * 11000).encode()
    response = client.post('/api/matches/file', data={'id': '77', 'type': '2'},
                           files={'file': ('match.csv', raw)})
    assert response.status_code == 422
    assert 'private-source' not in response.text
    assert client.get('/api/state').json()['matches'] == []


def test_unknown_possession_is_retained_even_when_attack_is_inferred(client):
    doc = source()
    doc['events'][1]['possession'] = 'Unknown'
    assert client.post('/api/matches/import?type=1', json=doc).status_code == 200
    result = client.get('/api/matches/1/123').json()
    assert result['events'][1]['possession'] == 'Unknown'
    assert result['events'][1]['att_origin'] == 'commentary-rule'
    assert result['summary']['classified'] == 0
