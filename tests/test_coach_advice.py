"""Behavioral checks for descriptive, private coaching advice."""
from copy import deepcopy
import importlib
import json

import pytest

from server.domain import SKILLS


OBSERVED = '2026-10-31T12:00:00+00:00'


def report(data):
    try:
        module = importlib.import_module('server.coach_advice')
    except ModuleNotFoundError:
        pytest.fail('The coaching advice module has not been implemented yet.')
    return module.build_coach_advice(data)


def player(identifier, value=10, **fields):
    return {'id': str(identifier), 'name': f'Joueur {identifier}',
            **dict.fromkeys(SKILLS, value), 'age': 24, 'energy': 80,
            'injured': False, 'form': 7, **fields}


def state(squad=None, academy=None, **fields):
    return {'current_team': {'id': 'club', 'name': 'Club'},
            'squad': squad or [], 'academy': academy or [],
            'squad_source': {'source': 'Test', 'observed_at': OBSERVED},
            'academy_source': {'source': 'Test', 'observed_at': OBSERVED},
            'notes': {}, **fields}


def test_missing_skills_do_not_lower_averages_and_coverage_is_explicit():
    data = state([player(1, attack=12), player(2, attack=18), player(3, attack=None)])
    group = report(data)['squad']
    attack = next(item for item in group['skills'] if item['skill'] == 'attack')
    assert attack['average'] == 15
    assert attack['known'] == 2
    assert attack['total'] == 3
    assert attack['coverage'] == 66.7
    assert group['known_skills'] == 29


def test_sparse_observations_cannot_be_presented_as_team_strengths_or_weaknesses():
    group = report(state([player(1, attack=18)]))['squad']
    assert group['strengths'] == []
    assert group['weaknesses'] == []
    hidden = report(state([player(1, value=None)]))['squad']
    assert hidden['known_skills'] == 0
    assert all(item['average'] is None for item in hidden['skills'])
    assert hidden['priorities'] == []
    assert hidden['observe'][0]['id'] == '1'


def test_senior_and_academy_profiles_are_separate_and_ties_are_not_defects():
    result = report(state([player(i, attack=15, kicking=4) for i in range(3)],
                          [player(10+i, value=3) for i in range(3)]))
    assert result['squad']['strengths'][0]['skill'] == 'attack'
    assert result['squad']['weaknesses'][0]['skill'] == 'kicking'
    assert result['academy']['strengths'] == []
    assert result['academy']['weaknesses'] == []
    assert result['academy']['skills'][0]['average'] == 3


def test_identical_fractional_averages_do_not_create_false_weaknesses():
    group = report(state([player(i, value=3.23) for i in range(3)]))['squad']
    assert group['strengths'] == []
    assert group['weaknesses'] == []


def test_csr_does_not_change_training_priorities():
    data = state([player(1, csr=999999), player(2, value=12, csr=1)])
    baseline = report(data)
    data['squad'][0]['csr'], data['squad'][1]['csr'] = 1, 999999
    assert report(data) == baseline


def test_age_29_and_33_do_not_exclude_training_profiles_or_invent_decline():
    group = report(state([player(1, age=29), player(2, age=33)]))['squad']
    assert {item['id'] for item in group['priorities']} == {'1', '2'}
    assert all(item['readiness'] == 'review' for item in group['priorities'])
    assert all(item['age_context'] for item in group['priorities'])
    assert all('decline' not in item for item in group['priorities'])


def test_academy_prefers_starred_profiles_but_needs_known_role_skills():
    group = report(state(academy=[player(1, value=None, age=16, stars=5),
                                        player(2, value=7, age=17, stars=5),
                                        player(3, value=8, age=18, stars=4)]))['academy']
    assert [item['id'] for item in group['priorities']] == ['2', '3']
    assert [item['id'] for item in group['observe']] == ['1']
    assert group['priorities'][0]['profile']['name']
    assert group['priorities'][0]['focus']['value'] == 7


def test_academy_keeps_cumulative_scouting_stars_above_five():
    group = report(state(academy=[player(1, stars=100), player(2, stars=20),
                                  player(3, stars=5), player(4, stars=-1)]))['academy']
    assert [item['id'] for item in group['priorities']] == ['1', '2', '3', '4']
    assert [item['stars'] for item in group['priorities']] == [100, 20, 5, None]


def test_academy_uses_stars_then_existing_generation_then_profile_not_age():
    group = report(state(academy=[
        player('later', value=15, age=16, stars=20, wc_projection=68),
        player('sooner', value=8, age=19, stars=20, wc_projection=64),
        player('stronger', value=10, age=20, stars=20, wc_projection=64),
        player('more-stars', value=7, age=18, stars=21, wc_projection=None),
        player('unknown', value=18, age=15, stars=20, wc_projection=None),
    ]))['academy']
    assert [item['id'] for item in group['priorities']] == ['more-stars', 'stronger', 'sooner', 'later', 'unknown']
    assert [item['wc_projection'] for item in group['priorities']] == [None, 64, 64, 68, None]


@pytest.mark.parametrize('projection', [None, 0, -1, True, 'NaN', 64.5])
def test_invalid_generation_remains_unknown_instead_of_being_guessed(projection):
    group = report(state(academy=[player(1, age=16, wc_projection=projection)]))['academy']
    assert group['priorities'][0]['wc_projection'] is None


def test_injury_dates_use_the_observation_date_and_unknown_is_not_healthy():
    group = report(state([player(1, injured='2026-11-02T00:00:00+00:00'),
                          player(2, injured='2026-10-30T00:00:00+00:00'),
                          player(3, injured=None)]))['squad']
    by_id = {item['id']: item for item in group['priorities']}
    assert by_id['1']['readiness'] == 'recovery'
    assert by_id['2']['injured'] is False
    assert by_id['3']['injured'] is None
    assert group['availability']['injured'] == 1
    assert group['availability']['unknown_injury'] == 1
    assert group['priorities'][-1]['id'] == '1'


def test_ambiguous_energy_scale_never_creates_a_fatigue_alert():
    group = report(state([player(1, energy=4), player(2, energy=9)]))['squad']
    assert group['availability']['energy_scale'] == 'ambiguous'
    assert group['availability']['low_energy'] == 0
    assert group['availability']['unknown_energy'] == 2
    assert all(item['energy'] is None for item in group['priorities'])
    known = report(state([player(1, energy=0), player(2, energy=90)]))['squad']
    assert known['availability']['low_energy'] == 1
    assert known['availability']['unknown_energy'] == 0
    assert known['priorities'][-1]['id'] == '1'


def test_known_zero_form_is_preserved_without_inventing_a_scale():
    group = report(state([player(1, form=0), player(2, form=None)]))['squad']
    assert group['availability']['unknown_form'] == 1
    assert next(item for item in group['priorities'] if item['id'] == '1')['form'] == 0
    assert next(item for item in group['priorities'] if item['id'] == '2')['form'] is None


def test_deduplication_immutability_and_json_serialization():
    data = state([player(1), player(1, value=0), player(2, stamina=float('nan'), attack=-1)])
    data['squad'][2]['stamina'] = 'NaN'
    before = deepcopy(data)
    result = report(data)
    assert data == before
    assert result['squad']['count'] == 2
    assert result['squad']['known_skills'] == 18
    assert result['warnings']
    json.dumps(result, allow_nan=False)


def test_explicit_watch_notes_are_visible_without_inventing_goals():
    result = report(state([player(1)], notes={'1': {'watch': True, 'text': 'Préparer la relève.'}}))
    item = result['squad']['priorities'][0]
    assert item['watch'] is True
    assert item['note'] == 'Préparer la relève.'
    assert report(state([player(1)]))['squad']['priorities'][0]['note'] is None


def test_empty_state_is_an_honest_empty_report():
    result = report({})
    assert result['squad']['count'] == result['academy']['count'] == 0
    assert result['squad']['coverage'] is None
    assert result['squad']['priorities'] == result['academy']['priorities'] == []
    assert result['team'] == {'id': None, 'name': None}
