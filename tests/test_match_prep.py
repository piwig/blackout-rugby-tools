import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from server import match_prep
from server.classic import ClassicClient, ClassicError

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def fixture(identifier, *, home='9', guest='20', start=None, finish=None, bot='0'):
    start = start or ('2026-01-01T12:00:00Z' if finish else '2026-11-01T12:00:00Z')
    return {'id': str(identifier), 'hometeamid': home, 'guestteamid': guest, 'matchstart': start,
            'matchfinish': finish, 'botmatch': bot, 'competition': 'League'}


def stats(*, home=10, guest=20, possession=40, opposing_possession=60):
    return {'home team stats': {'total points': home, 'tries': 0, 'possession': possession,
                               'missed tackles': '', 'handling errors': None},
            'guest team stats': {'total points': guest, 'tries': 2, 'possession': opposing_possession}}


class Client:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    async def request(self, resource, **params):
        self.calls.append((resource, params))
        assert resource in ('f', 'fs'), 'Scouting may only read fixtures and team statistics'
        return self.replies(resource, params)


def test_calendar_only_keeps_future_club_fixtures_and_sorts_by_utc():
    assert callable(getattr(match_prep, 'list_upcoming_fixtures', None))
    client = Client(lambda resource, params: {'fixtures': {
        '2': fixture(2, start='2026-11-01T13:00:00+02:00'),
        '1': fixture(1, start='2026-11-01T10:30:00Z'),
        '3': fixture(3, home='70', guest='80'),
        '4': fixture(4, start='2026-10-30T12:00:00Z'),
        '5': fixture(5, start='2026-11-01T12:00:00'),
        '6': fixture(6, finish='2026-10-31T11:00:00Z'),
    }})
    result = asyncio.run(match_prep.list_upcoming_fixtures(client, '9', now=NOW))
    assert client.calls == [('f', {'future': '9'})]
    assert [item['id'] for item in result['fixtures']] == ['1', '2']
    assert result['fixtures'][0]['opponent_id'] == '20'
    assert result['fixtures'][0]['side'] == 'home'
    assert result['fixtures'][1]['start_at'] == '2026-11-01T11:00:00+00:00'
    assert result['excluded_count'] == 4


def test_scout_finds_five_recent_documented_non_bot_matches_and_uses_the_opponents_side():
    assert callable(getattr(match_prep, 'scout_opponent', None))
    history = {str(i): fixture(i, home='20' if i % 2 else '30', guest='30' if i % 2 else '20',
                              start=(NOW-timedelta(days=i-99, hours=2)).isoformat(),
                              finish=(NOW-timedelta(days=i-99)).isoformat()) for i in range(100, 110)}
    history['199'] = fixture(199, home='20', guest='30', finish='2026-10-31T11:00:00Z', bot='1')
    history['198'] = fixture(198, home='20', guest='30', finish='2026-11-01T11:00:00Z')
    history['197'] = fixture(197, home='20', guest='30')
    history['196'] = fixture(196, home='70', guest='80', finish='2026-10-31T10:00:00Z')

    def replies(resource, params):
        if params == {'fixtureid': '900'}:
            return {'fixtures': {'900': fixture(900)}}
        if params == {'teamid': '20', 'last': '20'}:
            return {'fixtures': history}
        assert resource == 'fs'
        ids = params['fixtureids'].split(',')
        assert len(ids) <= 5
        return {'fixtures': {identifier: stats() for identifier in ids if identifier != '100'}}

    client = Client(replies)
    result = asyncio.run(match_prep.scout_opponent(client, '9', '900', now=NOW))
    assert [item['id'] for item in result['matches']] == ['101', '102', '103', '104', '105']
    assert result['matches'][0]['side'] == 'home'
    assert result['matches'][0]['metrics']['points_for'] == 10
    assert result['matches'][1]['side'] == 'guest'
    assert result['matches'][1]['metrics']['points_for'] == 20
    assert result['matches'][0]['metrics']['possession_pct'] == 40
    assert result['matches'][1]['metrics']['possession_pct'] == 60
    assert result['matches'][0]['metrics']['tries'] == 0
    assert result['matches'][0]['metrics']['missed_tackles'] is None
    assert result['missing_stats'][0]['id'] == '100'
    summary = {item['key']: item for item in result['summary']}
    assert summary['points_for']['average'] == 14
    assert summary['points_for']['sample_count'] == 5
    assert summary['missed_tackles']['average'] is None
    assert summary['missed_tackles']['sample_count'] == 0
    assert len(client.calls) == 4
    assert result['excluded_count'] == 4


@pytest.mark.parametrize('selected', [fixture(900, home='70', guest='80'),
                                      fixture(900, finish='2026-10-31T11:00:00Z'),
                                      fixture(900, start='2026-10-30T12:00:00Z')])
def test_unrelated_or_non_future_fixture_is_refused_before_reading_an_opponent(selected):
    assert callable(getattr(match_prep, 'scout_opponent', None))
    client = Client(lambda resource, params: {'fixtures': {'900': selected}})
    with pytest.raises(ClassicError):
        asyncio.run(match_prep.scout_opponent(client, '9', '900', now=NOW))
    assert len(client.calls) == 1


def test_utc_finish_order_wins_over_local_clock_and_naive_dates_are_excluded():
    assert callable(getattr(match_prep, 'scout_opponent', None))
    def replies(resource, params):
        if params == {'fixtureid': '900'}:
            return {'fixtures': {'900': fixture(900)}}
        if resource == 'f':
            return {'fixtures': {'1': fixture(1, home='20', guest='30', finish='2026-10-30T13:00:00+02:00'),
                                 '2': fixture(2, home='20', guest='30', finish='2026-10-30T12:00:00Z'),
                                 '3': fixture(3, home='20', guest='30', finish='2026-10-30T14:00:00')}}
        return {'fixtures': {'1': stats(), '2': stats()}}
    result = asyncio.run(match_prep.scout_opponent(Client(replies), '9', '900', now=NOW))
    assert [row['id'] for row in result['matches']] == ['2', '1']
    assert result['excluded_count'] == 1
    assert result['summary'][0]['sample_count'] == 2


def test_scout_is_bounded_when_every_statistic_is_missing():
    assert callable(getattr(match_prep, 'scout_opponent', None))
    def replies(resource, params):
        if params == {'fixtureid': '900'}:
            return {'fixtures': {'900': fixture(900)}}
        if resource == 'f':
            return {'fixtures': {str(i): fixture(i, home='20', guest='30', finish=(NOW-timedelta(days=i)).isoformat()) for i in range(1, 21)}}
        return {'fixtures': {}}
    client = Client(replies)
    result = asyncio.run(match_prep.scout_opponent(client, '9', '900', now=NOW))
    assert len(client.calls) == 6
    assert len(result['missing_stats']) == 20
    assert result['matches'] == []
    assert all(row['average'] is None for row in result['summary'])


@pytest.mark.parametrize('team_id', ['u20:9', 'nt:9', 'invalid', '0'])
def test_unsupported_team_identifiers_never_call_classic(team_id):
    assert callable(getattr(match_prep, 'list_upcoming_fixtures', None))
    client = Client(lambda *_: pytest.fail('Unexpected call'))
    with pytest.raises(ClassicError):
        asyncio.run(match_prep.list_upcoming_fixtures(client, team_id, now=NOW))
    assert client.calls == []


def test_missing_opposing_time_and_invalid_numeric_stats_never_become_zero_percentages():
    assert callable(getattr(match_prep, 'scout_opponent', None))
    def replies(resource, params):
        if params == {'fixtureid': '900'}:
            return {'fixtures': {'900': fixture(900)}}
        if resource == 'f':
            return {'fixtures': {'1': fixture(1, home='20', guest='30', finish='2026-10-30T12:00:00Z')}}
        return {'fixtures': {'1': {'home team stats': {'tries': 0, 'possession': 50, 'tackles': True, 'total points': -1}}}}
    result = asyncio.run(match_prep.scout_opponent(Client(replies), '9', '900', now=NOW))
    row = result['matches'][0]['metrics']
    assert row['possession_pct'] is None
    assert row['points_for'] is None
    assert row['tries'] == 0


def test_classic_fixture_stats_are_read_with_get_and_existing_write_parameters_stay_forbidden(monkeypatch):
    calls = []
    async def send(self, method, query, data=None, before_send=None):
        calls.append((method, query))
        return b'{"status":"Ok","fixtures":{}}'
    monkeypatch.setattr(ClassicClient, '_send', send)
    client = ClassicClient({'d':'test-developer','dk':'test-key'})
    result = asyncio.run(client.request('fs', fixtureids='1,2'))
    assert result['fixtures'] == {}
    assert calls[0][0] == 'GET'
    assert calls[0][1]['r'] == 'fs'
    with pytest.raises(ClassicError):
        asyncio.run(client.request('fs', update='1'))
    assert len(calls) == 1


def test_future_match_start_cannot_be_reclassified_as_completed_by_a_contradictory_finish():
    def replies(resource, params):
        if params == {'fixtureid': '900'}:
            return {'fixtures': {'900': fixture(900)}}
        if resource == 'f':
            return {'fixtures': {'1': fixture(1, home='20', guest='30', start='2026-11-01T12:00:00Z', finish='2026-10-30T12:00:00Z')}}
        return {'fixtures': {'1': stats()}}
    client = Client(replies)
    result = asyncio.run(match_prep.scout_opponent(client, '9', '900', now=NOW))
    assert result['matches'] == []
    assert result['excluded_count'] == 1
    assert len(client.calls) == 2


def test_ratio_averages_round_once_after_averaging_each_match():
    def replies(resource, params):
        if params == {'fixtureid': '900'}:
            return {'fixtures': {'900': fixture(900)}}
        if resource == 'f':
            return {'fixtures': {str(n): fixture(n, home='20', guest='30', finish=f'2026-10-{28+n}T12:00:00Z') for n in (1, 2)}}
        return {'fixtures': {str(n): {
            'home team stats': {'possession': 1, 'territory': 1, 'lineouts won': 1,
                                'lineouts lost': other, 'scrums won': 1, 'scrums lost': other},
            'guest team stats': {'possession': other, 'territory': other},
        } for n, other in ((1, 5), (2, 1))}}
    result = asyncio.run(match_prep.scout_opponent(Client(replies), '9', '900', now=NOW))
    summary = {row['key']: row for row in result['summary']}
    for key in ('possession_pct', 'territory_pct', 'lineouts_pct', 'scrums_pct'):
        # (100 * 1/6 + 100 * 1/2) / 2 = 100/3, rather than a mean of rounded displays.
        assert summary[key]['average'] == 33.33
        assert summary[key]['sample_count'] == 2
