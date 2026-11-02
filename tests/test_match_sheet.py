import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from server.classic import ClassicError
from server.match_sheet import SheetRequest, fetch_match_sheet, list_sheet_fixtures

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class Classic:
    def __init__(self):
        self.calls = []
        self.fixture = {'id': '90', 'hometeamid': '9', 'guestteamid': '8',
                        'matchstart': '2026-01-02T12:00:00+00:00', 'competition': 'Friendly'}
        self.lineups = {team: {'teamid': team, 'fixtureid': '90',
            **{f'p{i}': str(base+i) for i in range(1,16)},
            **{f'b{i}': str(base+15+i) for i in range(1,9)},
            'captain': str(base+1), 'kicker': str(base+10),
            'deadline': '2026-01-02T08:55:00+00:00', 'tacticsdeadline': 'ambiguous',
            'attack1': 'PRIVATE'} for team,base in [('9',100),('8',200)]}
        self.players = {str(i): {'id': str(i), 'name': f'Player {i}', 'csr': '10000',
            'weight': '100', 'height': '190', 'form': '7', 'experience': '7',
            'energy': '100', 'aggression': '3', 'discipline': '4', 'salary': 'PRIVATE'}
            for i in [*range(101,124),*range(201,224)]}

    async def request(self, resource, **params):
        self.calls.append((resource,params))
        if resource == 'f': return {'fixtures': {'90': deepcopy(self.fixture)}}
        if resource == 't': return {'teams': {t:{'id': t,'name': f'Team {t}'} for t in params['teamids'].split(',')}}
        if resource == 'lu':
            row = self.lineups[params['teamid']]
            return {'lineups': [deepcopy(row)] if row else []}
        if resource == 'p': return {'players': {p:deepcopy(self.players[p]) for p in params['playerids'].split(',') if p in self.players}}
        raise AssertionError('Only bounded reads are allowed')


def read(c=None, **args):
    return asyncio.run(fetch_match_sheet(c or Classic(), SheetRequest(team_id='9',match_type=0,reference='90',**args),now=NOW))


def metric(side, group, name):
    return next(g for g in side['groups'] if g['key']==group)['metrics'][name]


def test_complete_public_sheet_and_known_formula():
    c=Classic(); report=read(c)
    assert len(report['home']['players']) == len(report['guest']['players']) == 23
    assert report['home']['players'][0]['captain'] is True
    assert report['home']['players'][9]['kicker'] is True
    assert metric(report['home'],'pack','weight_total') == {'value':800,'known':8,'expected':8}
    assert metric(report['home'],'xv','adjusted_csr_average')['value'] == 10000
    assert report['home']['deadline_at'] == '2026-01-02T08:55:00+00:00'
    assert report['home']['tactics_deadline_at'] is None
    assert report['timing']['indicative']['lineup_at']=='2026-01-02T08:55:00+00:00'
    assert 'PRIVATE' not in str(report)
    assert [r for r,_ in c.calls] == ['f','t','lu','lu','p','p']
    assert all(len(p['playerids'].split(','))<=23 for r,p in c.calls if r=='p')


def test_missing_player_keeps_exact_slot_and_unknown_pack():
    c=Classic(); del c.players['103']; del c.lineups['9']['b8']
    s=read(c)['home']
    assert s['players'][2]['player_id']=='103' and s['players'][2]['status']=='missing_player'
    assert s['players'][3]['name']=='Player 104'
    assert s['players'][22]['player_id'] is None
    assert metric(s,'pack','weight_total')=={'value':None,'known':7,'expected':8}
    assert metric(s,'pack','csr_average')=={'value':10000,'known':7,'expected':8}


def test_unpublished_is_not_default_and_does_not_read_players():
    c=Classic(); c.lineups['8']=None
    s=read(c)['guest']
    assert s['lineup_state']=='not_provided' and len(s['players'])==23
    assert all(p['status']=='not_provided' for p in s['players'])
    assert len([1 for r,_ in c.calls if r=='p'])==1
    assert all(p.get('fixtureid')!='0' for _,p in c.calls)


@pytest.mark.parametrize('field,value',[('fixtureid','0'),('fixtureid','91'),('teamid','7'),('youth',1),('p2','101')])
def test_wrong_public_lineup_identity_or_duplicate_rejected(field,value):
    c=Classic(); c.lineups['9'][field]=value
    with pytest.raises(ClassicError): read(c)


@pytest.mark.parametrize('team,kind,flag',[('9',0,{}),('9',3,{'youth':'1'}),('u20:9',1,{'u20':'1'}),('nt:9',2,{'nat':'1'})])
def test_each_resource_has_exact_population_flags(team,kind,flag):
    c=Classic()
    result=asyncio.run(fetch_match_sheet(c,SheetRequest(team_id=team,match_type=kind,reference='90'),now=NOW))
    assert result['team_id']==team and result['match_type']==kind
    for r,p in c.calls:
        expected={} if r=='t' and kind==3 else flag
        assert {k:p[k] for k in ('youth','u20','nat') if k in p}==expected
    c.calls=[]
    calendar=asyncio.run(list_sheet_fixtures(c,team,kind,now=NOW))
    assert len(calendar['fixtures'])==1
    assert c.calls==[('f',{'future':'9',**flag})]


@pytest.mark.parametrize('team,kind',[('u20:9',0),('nt:9',1),('9',2)])
def test_incompatible_population_makes_no_calls(team,kind):
    c=Classic()
    with pytest.raises(ClassicError): asyncio.run(fetch_match_sheet(c,SheetRequest(team_id=team,match_type=kind,reference='90'),now=NOW))
    assert not c.calls


def test_unrelated_fixture_rejected_before_lineups():
    c=Classic(); c.fixture['hometeamid']='7'
    with pytest.raises(ClassicError): read(c)
    assert len(c.calls)==1


def test_energy_ambiguity_is_per_player_and_explicit_level_is_approximate():
    c=Classic(); c.players['101']['energy']='10'
    side=read(c)['home']
    assert side['players'][0]['adjusted_csr'] is None
    assert side['players'][1]['adjusted_csr']==10000
    assert side['players'][0]['energy_scale']=='unknown'
    side=read(c,home_energy_scale='level')['home']
    assert side['players'][0]['energy_percent']==100 and side['players'][0]['adjusted_csr']==10000
    assert side['players'][1]['energy_percent'] is None


@pytest.mark.parametrize('value',[None,'',True,'NaN','Infinity',-1,111])
def test_invalid_energy_is_unknown(value):
    c=Classic(); c.players['101']['energy']=value
    assert read(c)['home']['players'][0]['adjusted_csr'] is None


def test_percent_110_and_truncation_order():
    c=Classic(); c.players['101']['energy']=110
    assert read(c)['home']['players'][0]['adjusted_csr']==11000
    c.players['101'].update(csr=10001,form=8,experience=8,energy=100)
    c.players['102']['csr']=10002
    side=read(c)['home']
    assert side['players'][0]['adjusted_csr']==10915
    assert metric(side,'first_row','adjusted_csr_average')['value']==10305


@pytest.mark.parametrize('field,value',[('csr',True),('csr','nan'),('weight',0),('height',301),('form',12),('experience',22),('aggression',6),('discipline','Unknown')])
def test_invalid_attributes_are_unknown_not_zero(field,value):
    c=Classic(); c.players['101'][field]=value
    assert read(c)['home']['players'][0][field] is None


def test_upstream_errors_never_disclose_url_or_credentials():
    class Broken:
        async def request(self,*a,**k): raise ClassicError('https://example.invalid/?mk=SECRET')
    with pytest.raises(ClassicError) as e: read(Broken())
    assert 'SECRET' not in str(e.value) and 'example.invalid' not in str(e.value)


@pytest.mark.parametrize('resource',['f','t','lu','p'])
@pytest.mark.parametrize('team,kind',[('9',0),('9',3),('u20:9',1),('nt:9',2)])
def test_root_population_contradictions_are_rejected(resource,team,kind):
    class Contradiction(Classic):
        async def request(self,r,**params):
            doc=await super().request(r,**params)
            if r==resource: doc['nat' if kind!=2 else 'youth']='1'
            return doc
    with pytest.raises(ClassicError):
        asyncio.run(fetch_match_sheet(Contradiction(),SheetRequest(team_id=team,match_type=kind,reference='90'),now=NOW))


@pytest.mark.parametrize('team,kind',[('9',0),('9',3),('u20:9',1),('nt:9',2)])
def test_calendar_root_population_is_checked(team,kind):
    class Contradiction(Classic):
        async def request(self,r,**params):
            doc=await super().request(r,**params);doc['nat' if kind!=2 else 'youth']='1';return doc
    with pytest.raises(ClassicError): asyncio.run(list_sheet_fixtures(Contradiction(),team,kind,now=NOW))


@pytest.mark.parametrize('csr,form,xp,expected',[(100,1,7,58),(1000,2,1,572)])
def test_decimal_formula_truncates_only_after_exact_multiplication(csr,form,xp,expected):
    c=Classic();c.players['101'].update(csr=csr,form=form,experience=xp,energy=100)
    assert read(c)['home']['players'][0]['adjusted_csr']==expected
