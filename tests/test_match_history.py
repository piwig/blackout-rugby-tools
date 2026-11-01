"""Historical statistics use isolated stores and synthetic matches only."""
import importlib.util

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from server.match_review import effective_match, register_match_review
from server.storage import Store, pack


def history_module():
    assert importlib.util.find_spec('server.match_history'), 'The historical match statistics module is missing'
    from server import match_history
    return match_history


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'manager', 'Testing-password-1234', seed=False)


def put(store, mid='1', **changes):
    doc = {'id': mid, 'type': 0, 'home': 'Home', 'away': 'Away', 'season': 62, 'round': 9,
           'home_score': None, 'away_score': None, 'events': [], **changes}
    with store.db() as db:
        db.execute('INSERT INTO matches VALUES(?,?,?,?)',
                   (doc['id'], doc['type'], pack(doc), '2026-10-31T12:00:00Z'))
    return doc


def client_for(store):
    app = FastAPI()

    async def auth(request: Request):
        if request.headers.get('X-Test-Session') != 'manager':
            raise HTTPException(401, 'Session requise')
        return {'user_id': 'manager'}

    history_module().register_match_history(app, store, auth)
    register_match_review(app, store, auth)
    return TestClient(app, headers={'X-Test-Session': 'manager'})


def test_history_counts_all_saved_matches_beyond_page_without_returning_events(store):
    for n in range(1, 102):
        put(store, str(n), events=[{'text': 'Private source event'}])
    with client_for(store) as client:
        result = client.get('/api/matches/history?offset=100&limit=20').json()
    assert result['total_stored'] == result['total_filtered'] == result['totals']['matches'] == 101
    assert result['totals']['events'] == 101
    assert len(result['matches']) == 1
    assert result['matches'][0]['event_count'] == 1
    assert 'events' not in result['matches'][0]
    assert 'Private source event' not in str(result)


def test_zero_scores_are_known_and_incomplete_scores_do_not_pollute_averages(store):
    put(store, '1', home_score=0, away_score=0)
    put(store, '2', home_score=20, away_score=10)
    put(store, '3', home_score=99)
    put(store, '4', season=None)
    with client_for(store) as client:
        result = client.get('/api/matches/history').json()
    assert result['totals']['scored_matches'] == 2
    assert result['totals']['points_total'] == 30
    assert result['totals']['points_per_match'] == 15
    assert result['totals']['coverage_pct'] is None
    assert result['by_season'] == [
        {'season': 62, 'matches': 3, 'scored_matches': 2, 'points_total': 30, 'classified': 0, 'events': 0, 'coverage_pct': None},
        {'season': None, 'matches': 1, 'scored_matches': 0, 'points_total': None, 'classified': 0, 'events': 0, 'coverage_pct': None},
    ]


def test_filter_options_keep_all_seasons_and_types_but_only_names_from_selected_type(store):
    put(store, '1', season=61, home='One')
    put(store, '2', season=62, home='one', type=1)
    put(store, '3', season=None, home='Domicile (nom non fourni)', away='Extérieur (nom non fourni)', type=2)
    with client_for(store) as client:
        result = client.get('/api/matches/history?type=0&season=61&team=One').json()
    assert result['total_stored'] == 3 and result['total_filtered'] == 1
    assert result['options']['seasons'] == [62, 61]
    assert set(result['options']['teams']) == {'One', 'Away'}
    assert result['options']['types'] == [0, 1, 2]


def test_team_options_are_independent_of_selected_team_season_and_page_within_a_type(store):
    for kind, name in [(0, 'Senior'), (1, 'U20'), (2, 'NT'), (3, 'Junior')]:
        put(store, '77', type=kind, home=name, away=name+' away', season=62)
    put(store, '78', type=3, home='Other junior', away='Junior away', season=61)
    with client_for(store) as client:
        result = client.get('/api/matches/history?type=3&team=Junior&season=62&offset=1&limit=1').json()
        assert result['total_filtered'] == 1 and result['totals']['matches'] == 1 and result['matches'] == []
        assert set(result['options']['teams']) == {'Junior', 'Junior away', 'Other junior'}
        assert result['options']['types'] == [0, 1, 2, 3]
        assert result['options']['seasons'] == [62, 61]
        unfiltered = client.get('/api/matches/history?offset=3&limit=1').json()
        assert unfiltered['total_filtered'] == 5 and len(unfiltered['matches']) == 1
        assert set(unfiltered['options']['teams']) == {'Senior', 'Senior away', 'U20', 'U20 away', 'NT', 'NT away', 'Junior', 'Junior away', 'Other junior'}


def test_team_record_orients_home_and_away_and_excludes_unscored_matches(store):
    put(store, '1', home='Target', home_score=20, away_score=10)
    put(store, '2', away='Target', home_score=30, away_score=10)
    put(store, '3', away='Target', home_score=0, away_score=0)
    put(store, '4', home='Target')
    put(store, '5', home='Other', home_score=90, away_score=0)
    with client_for(store) as client:
        result = client.get('/api/matches/history?type=0&team=Target').json()
    assert result['team_record'] == {'played': 4, 'scored_matches': 3, 'won': 1, 'drawn': 1, 'lost': 1,
                                     'points_for': 30, 'points_against': 40, 'win_pct': 33.33}


def test_manual_review_changes_historical_counts_but_not_persisted_events(store):
    doc = put(store, events=[{'id': 'event-1', 'text': 'A runner attacks.'},
                            {'text': 'A stop in play.'},
                            {'att': 'kick', 'field': '3', 'possession': '1', 'att_origin': 'commentary-rule'}])
    review = effective_match(store, doc, include_review=True)
    with client_for(store) as client:
        response = client.post('/api/matches/0/1/annotations', json={
            'expected_revision': review['review']['revision'],
            'expected_source_digest': review['review']['source_digest'],
            'changes': [
                {'event_key': review['events'][0]['event_key'], 'classification': 'attack', 'att': 'percu', 'possession': 0, 'field': 2},
                {'event_key': review['events'][1]['event_key'], 'classification': 'non_attack', 'possession': None, 'field': None},
            ],
        })
        assert response.status_code == 200, response.text
        result = client.get('/api/matches/history?type=0').json()
    totals = result['totals']
    assert (totals['events'], totals['classified'], totals['non_attack'], totals['unclassified']) == (3, 2, 1, 0)
    assert totals['manual'] == totals['inferred'] == 1
    assert totals['coverage_pct'] == 66.67
    assert next(item for item in result['attacks'] if item['name'] == 'Percussion') == {'name': 'Percussion', 'count': 1, 'percent': 50}
    assert next(item for item in result['zones'] if item['name'] == '40')['count'] == 2
    with store.db() as db:
        assert 'manual' not in db.execute('SELECT payload FROM matches').fetchone()['payload']


def test_history_requires_auth_and_isolated_managers_never_share_records(store, tmp_path):
    put(store, home='Private team')
    other = Store(tmp_path / 'other', 'Testing-password-1234', seed=False)
    with client_for(store) as owner, client_for(other) as outsider:
        assert owner.get('/api/matches/history', headers={'X-Test-Session': ''}).status_code == 401
        assert owner.get('/api/matches/history').json()['total_stored'] == 1
        assert outsider.get('/api/matches/history').json()['total_stored'] == 0
        assert 'Private team' not in outsider.get('/api/matches/history').text


@pytest.mark.parametrize('query', ['type=4', 'type=-1', 'offset=-1', 'limit=0', 'limit=101', 'season=-1', 'team='])
def test_bad_filters_are_rejected(store, query):
    with client_for(store) as client:
        assert client.get('/api/matches/history?' + query).status_code == 422


def test_same_team_name_across_match_types_requires_explicit_type_for_record(store):
    put(store, '1', type=0, home='Target', home_score=10, away_score=0)
    put(store, '2', type=1, home='Target', home_score=0, away_score=20)
    with client_for(store) as client:
        assert client.get('/api/matches/history?team=Target').status_code == 422
        filtered = client.get('/api/matches/history?team=Target&type=1').json()
    assert filtered['team_record']['lost'] == 1 and filtered['team_record']['won'] == 0
