"""Direct Classic imports use synthetic data and never contact the game."""
import asyncio
import importlib.util
from datetime import datetime, timezone

import pytest

from server.classic import ClassicError


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def module():
    assert importlib.util.find_spec('server.match_direct'), 'The direct import module is missing'
    from server import match_direct
    return match_direct


class Client:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def request(self, resource, **params):
        self.calls.append((resource, params))
        assert resource in ('f', 't', 'me', 'ls'), 'Direct imports are read-only'
        return self.reply(resource, params)


def fixture(identifier='100', **overrides):
    return {'id': identifier, 'hometeamid': '9', 'guestteamid': '20',
            'matchstart': '2026-10-30T13:00:00+02:00',
            'matchfinish': '2026-10-30T15:00:00+02:00',
            'botmatch': '0', 'data_removed': '0', 'season': '62', 'round': '9',
            'competition': 'League', **overrides}


@pytest.mark.parametrize('value,kind,want', [
    (' 100 ', 0, '100'),
    ('https://classic-api.blackoutrugby.com/?r=me&fixtureid=100&u20=1&d=secret', 1, '100'),
    ('https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture=100&nat=1', 2, '100'),
])
def test_reference_extracts_only_fixture_identity(value, kind, want):
    assert module().parse_fixture_reference(value, kind) == want


@pytest.mark.parametrize('value,kind', [
    ('https://evil.invalid/?fixtureid=100&mk=secret', 0),
    ('https://www.blackoutrugby.com.evil.invalid/game/club.livematch.php?id=100', 0),
    ('https://secret@www.blackoutrugby.com/game/club.livematch.php?id=100', 0),
    ('https://www.blackoutrugby.com/game/me.account.php?id=100', 0),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&fixtureid=101', 0),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&id=101', 0),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&u20=1', 0),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&u20=1&nat=1', 1),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&youth=1', 1),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&youth=1', 0),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&youth=1', 2),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&youth=0', 3),
    ('https://classic-api.blackoutrugby.com/?fixtureid=100&youth=1&u20=1', 3),
    ('https://classic-api.blackoutrugby.com:444/?fixtureid=100', 0),
    ('https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture=100&nat=1&u20=1', 2),
    ('https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture=100&secret=PRIVATE', 0),
    ('https://www.blackoutrugby.com/game/tools.live.scoring.php?fixtureid=101#fixture=100', 0),
    ('0', 0), ('１２', 0), ('100', True), ('100', 4), (True, 0),
])
def test_reference_rejects_ambiguous_or_foreign_urls_without_echoing_input(value, kind):
    with pytest.raises(ClassicError) as error:
        module().parse_fixture_reference(value, kind)
    assert 'secret' not in str(error.value)
    assert 'https://' not in str(error.value)


@pytest.mark.parametrize('team_id,kind,flag', [('9', 0, {}), ('u20:9', 1, {'u20': '1'}), ('nt:9', 2, {'nat': '1'})])
def test_recent_fixtures_are_scoped_finished_sorted_and_public(team_id, kind, flag):
    rows = {'100': fixture(), '101': fixture('101', matchfinish='2026-10-31T11:00:00Z'),
            '102': fixture('102', matchfinish=None),
            '103': fixture('103', hometeamid='30', guestteamid='40'),
            '104': fixture('104', matchfinish='2026-11-01T11:00:00Z'),
            '105': fixture('105', matchfinish='2026-10-30T15:00:00'),
            '106': fixture('106', botmatch='1'), '107': fixture('107', data_removed='1')}

    def reply(resource, params):
        assert {key: params[key] for key in flag} == flag
        if resource == 'f':
            assert params == {'teamid': '9', 'last': '20', **flag}
            return {'status': 'Ok', 'fixtures': rows}
        assert resource == 't'
        return {'teams': {'9': {'id': '9', 'name': 'Home', 'owner': 'PRIVATE'},
                          '20': {'id': '20', 'name': 'Away'}}}

    result = asyncio.run(module().recent_matches(Client(reply), team_id, now=NOW))
    assert result['team_id'] == team_id and result['type'] == kind
    assert [item['id'] for item in result['fixtures']] == ['101', '100']
    assert result['excluded_count'] == 6
    first = result['fixtures'][0]
    assert (first['home'], first['away'], first['home_id'], first['away_id']) == ('Home', 'Away', '9', '20')
    assert first['home_score'] is None and first['away_score'] is None
    assert first['season'] == 62 and first['round'] == 9
    assert 'PRIVATE' not in str(result)


def match_client(*, change=None, events=None):
    documents = {
        'f': {'status': 'Ok', 'fixtures': {'100': fixture()}},
        't': {'teams': {'9': {'id': '9', 'name': 'Home'}, '20': {'id': '20', 'name': 'Away'}}},
        'me': {'status': 'Ok', 'fixtureid': '100', 'brt': '2026-10-31T11:00:00Z',
               'events': events if events is not None else [{'id': '1', 'commentary': 'A quiet passage.'},
                                                          {'id': '2', 'commentary': 'They go wide', 'field': 2, 'possession': 0}]},
        'ls': {'status': 'Ok', 'fixtureid': '100', 'match_has_finished': '1', 'homescore': '21', 'guestscore': '7'},
    }
    if change:
        change(documents)
    return Client(lambda resource, params: documents[resource])


def test_fetch_preserves_every_event_uses_real_metadata_and_checks_selection_flags():
    client = match_client()
    doc = asyncio.run(module().fetch_match(client, '100', 1, now=NOW))
    assert doc['id'] == '100' and doc['type'] == 1
    assert (doc['home'], doc['away'], doc['home_score'], doc['away_score']) == ('Home', 'Away', 21, 7)
    assert doc['season'] == 62 and doc['round'] == 9
    assert len(doc['events']) == 2 and doc['events'][0]['id'] == '1'
    assert doc['events'][1]['att_origin'] == 'commentary-rule'
    assert doc['source_observed_at'] == '2026-10-31T11:00:00Z'
    assert all(params.get('u20') == '1' for _, params in client.calls)


def test_absent_names_scores_and_season_remain_explicitly_unknown():
    def change(docs):
        docs['t'] = {'teams': {}}
        docs['ls'] = {'fixtureid': '100', 'match_has_finished': '1'}
        docs['f']['fixtures']['100'].pop('season')
        docs['me']['events'][0]['homescore'] = 99
    doc = asyncio.run(module().fetch_match(match_client(change=change), '100', 0, now=NOW))
    assert doc['home_score'] is None and doc['away_score'] is None and doc['season'] is None
    assert 'non fourni' in doc['home'] and 'non fourni' in doc['away']


@pytest.mark.parametrize('change', [
    lambda d: d.update(f={'status': 'Failed', 'error': 'PRIVATE'}),
    lambda d: d.update(f={'fixtures': {'100': fixture('999')}}),
    lambda d: d['f']['fixtures']['100'].update(matchfinish=None),
    lambda d: d['f']['fixtures']['100'].update(matchstart='2026-11-02T10:00:00Z'),
    lambda d: d['f']['fixtures']['100'].update(botmatch='1'),
    lambda d: d['f']['fixtures']['100'].update(data_removed='1'),
    lambda d: d['me'].update(fixtureid='999'),
    lambda d: d['me'].pop('events'),
    lambda d: d['me'].update(events='PRIVATE'),
    lambda d: d['ls'].update(fixtureid='999'),
    lambda d: d['ls'].update(match_has_finished='0'),
    lambda d: d['ls'].update(homescore=True),
    lambda d: d['t']['teams']['9'].update(id='999'),
])
def test_fetch_refuses_invalid_identity_or_incomplete_source_without_echoing(change):
    with pytest.raises(ClassicError) as error:
        asyncio.run(module().fetch_match(match_client(change=change), '100', 0, now=NOW))
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('error', [TimeoutError('PRIVATE'), ClassicError('API indisponible')])
def test_failed_reads_never_produce_an_import_document(error):
    def fail(resource, params):
        raise error
    with pytest.raises(ClassicError) as caught:
        asyncio.run(module().fetch_match(Client(fail), '100', 0, now=NOW))
    assert 'PRIVATE' not in str(caught.value)


def test_recent_limit_rejects_oversized_collection_before_reading_names():
    client = Client(lambda resource, params: {'fixtures': {str(n): fixture(str(n)) for n in range(1, 22)}})
    with pytest.raises(ClassicError):
        asyncio.run(module().recent_matches(client, '9', now=NOW))
    assert len(client.calls) == 1


def test_recent_names_use_bounded_groups_and_preserve_missing_names():
    rows = {str(i): fixture(str(i), guestteamid=str(20+i)) for i in range(1, 21)}

    def reply(resource, params):
        if resource == 'f':
            return {'fixtures': rows}
        ids = params['teamids'].split(',')
        assert len(ids) <= 10
        return {'teams': {identifier: {'id': identifier, 'name': 'Team ' + identifier}
                          for identifier in ids if identifier != '40'}}

    client = Client(reply)
    result = asyncio.run(module().recent_matches(client, '9', now=NOW))
    assert len(result['fixtures']) == 20
    assert len(client.calls) == 4
    assert result['fixtures'][0]['away'] == 'Extérieur (nom non fourni)'


@pytest.mark.parametrize('team_id', ['0', 'u20:0', 'nt:9/../../', 'youth:9', True])
def test_invalid_team_never_triggers_network(team_id):
    client = Client(lambda resource, params: pytest.fail('Invalid teams must not trigger a read'))
    with pytest.raises(ClassicError):
        asyncio.run(module().recent_matches(client, team_id, now=NOW))


def test_unverified_score_is_unknown_even_when_live_score_is_zero():
    def change(docs):
        docs['ls'] = {'fixtureid': '100', 'homescore': '0', 'guestscore': '0'}
    doc = asyncio.run(module().fetch_match(match_client(change=change), '100', 2, now=NOW))
    assert doc['home_score'] is None and doc['away_score'] is None


def test_excess_commentary_events_fail_without_silent_truncation():
    with pytest.raises(ClassicError):
        asyncio.run(module().fetch_match(match_client(events=[{}] * 20001), '100', 0, now=NOW))


@pytest.mark.parametrize('field', ['botmatch', 'data_removed'])
def test_absent_report_flags_do_not_hide_finished_matches(field):
    row = fixture()
    del row[field]
    client = Client(lambda resource, params: {'fixtures': {'100': row}} if resource == 'f' else {'teams': {}})
    result = asyncio.run(module().recent_matches(client, '9', now=NOW))
    assert [match['id'] for match in result['fixtures']] == ['100']
    assert result['excluded_count'] == 0


def test_u20_without_optional_availability_flags_can_be_listed_and_imported():
    def change(documents):
        row = documents['f']['fixtures']['100']
        row.pop('botmatch')
        row.pop('data_removed')
        row.update(matchstart='2026-10-31T03:35:00+12:00', matchfinish='2026-10-31T05:15:00+12:00')
    client = match_client(change=change)
    recent = asyncio.run(module().recent_matches(client, 'u20:9', now=NOW))
    assert [item['id'] for item in recent['fixtures']] == ['100']
    imported = asyncio.run(module().fetch_match(client, '100', 1, now=NOW))
    assert imported['type'] == 1 and len(imported['events']) == 2
    assert ('me', {'fixtureid': '100', 'u20': '1'}) in client.calls


@pytest.mark.parametrize('field', ['botmatch', 'data_removed'])
@pytest.mark.parametrize('value', [True, False, None, '', 'unknown', 2, [], {}])
def test_present_unrecognised_availability_flags_are_rejected(field, value):
    client = match_client(change=lambda documents: documents['f']['fixtures']['100'].update({field: value}))
    with pytest.raises(ClassicError):
        asyncio.run(module().fetch_match(client, '100', 1, now=NOW))


def test_absent_flags_do_not_hide_commentary_failure():
    def change(documents):
        documents['f']['fixtures']['100'].pop('botmatch')
        documents['f']['fixtures']['100'].pop('data_removed')
        documents['me'] = {'status': 'Failed', 'error': 'PRIVATE unavailable commentary'}
    client = match_client(change=change)
    with pytest.raises(ClassicError) as error:
        asyncio.run(module().fetch_match(client, '100', 1, now=NOW))
    assert ('me', {'fixtureid': '100', 'u20': '1'}) in client.calls
    assert 'PRIVATE' not in str(error.value)
