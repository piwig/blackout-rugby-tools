"""Synthetic contracts for bounded recent-match comparisons; no live requests."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from server.classic import ClassicError
from server.match_sheet import SheetRequest
from server.match_recent import compare_recent_matches

NOW=datetime(2026,1,15,tzinfo=timezone.utc)

def fixture(i,home='9',guest='8',day=10):
    return {'id':str(i),'hometeamid':home,'guestteamid':guest,'competition':'Friendly','botmatch':'0',
            'weather':'3','matchstart':f'2026-01-{day:02}T12:00:00Z','matchfinish':f'2026-01-{day:02}T14:00:00Z'}

class Classic:
    def __init__(self):
        self.calls=[]
        self.target=fixture(900,day=20);self.target['matchfinish']=None
        self.history={t:{str(base+i):fixture(base+i,t,other,i+1) for i in range(6)} for t,base,other in [('9',100,'20'),('8',200,'21')]}
        self.shared=fixture(300)
        for rows in self.history.values():rows['300']=deepcopy(self.shared)
        self.summaries={};self.scores={}
        for rows in self.history.values():
            for fid,f in rows.items():
                self.summaries[fid]={'status':'Ok','fixtureid':fid,'home':{'teamid':f['hometeamid'],'points':'0','scrum':'11','scrum weight':850,'weight':1450},
                                    'guest':{'teamid':f['guestteamid'],'points':'0','scrum':'9'},'private_tactics':'DO NOT COPY'}
                self.scores[fid]={'fixtureid':fid,'match_has_finished':'1','homescore':'0','guestscore':'0'}
    async def request(self,resource,**params):
        self.calls.append((resource,params))
        if resource=='f':return {'fixtures':{'900':deepcopy(self.target)} if 'fixtureid' in params else deepcopy(self.history[params['teamid']])}
        if resource=='t':return {'teams':{t:{'id':t,'name':f'Team {t}'} for t in params['teamids'].split(',')}}
        if resource=='ls':
            result=self.scores[params['fixtureid']]
            if isinstance(result,Exception):raise result
            return deepcopy(result)
        raise AssertionError('Only bounded f/t reads and reporter summaries permitted')
    async def read_reporter_summary(self,fid,context):
        self.calls.append(('rs',{'fixtureid':fid,'context':context}))
        result=self.summaries[fid]
        if isinstance(result,Exception):raise result
        return deepcopy(result)

def read(c=None,team='9',kind=0):
    return asyncio.run(compare_recent_matches(c or Classic(),SheetRequest(team_id=team,match_type=kind,reference='900'),now=NOW))

def test_last_four_for_each_team_with_scores_weather_ratings_and_deduplicated_reads():
    c=Classic();r=read(c)
    assert r['team_id']=='9' and r['fixture_id']=='900'
    assert [[m['id'] for m in s['matches']] for s in r['sides']]==[['300','105','104','103'],['300','205','204','203']]
    assert len([1 for resource,_ in c.calls if resource=='rs'])==7
    m=r['sides'][0]['matches'][0]
    assert m['home_score']==m['guest_score']==0 and m['weather_code']=='3'
    assert m['ratings']['scrum']==11 and m['pack_weight']==850 and m['xv_weight']==1450
    assert r['sides'][1]['matches'][0]['ratings']['scrum']==9
    assert 'DO NOT COPY' not in str(r)

def test_missing_recent_report_is_kept_in_position_and_not_replaced_by_older_match():
    c=Classic();c.summaries['105']=ClassicError('https://example.invalid/?mk=PRIVATE')
    c.scores['105']=ClassicError('Unavailable score')
    r=read(c);rows=r['sides'][0]['matches']
    assert rows[1]['id']=='105' and rows[1]['report_state']=='unavailable'
    assert rows[1]['home_score'] is None and all(v is None for v in rows[1]['ratings'].values())
    assert len(rows)==4 and rows[-1]['id']=='103'
    assert 'PRIVATE' not in str(r) and 'example.invalid' not in str(r)

@pytest.mark.parametrize('team,kind,flag,context',[('9',0,{},'club'),('9',3,{'youth':'1'},'youth'),('u20:9',1,{'u20':'1'},'u20'),('nt:9',2,{'nat':'1'},'nt')])
def test_population_is_explicit_for_histories_names_and_every_report(team,kind,flag,context):
    c=Classic();c.summaries['105']=ClassicError('Missing report');r=read(c,team,kind)
    assert r['match_type']==kind
    for resource,params in c.calls:
        if resource=='rs':assert params['context']==context
        else:
            expected={} if resource=='t' and kind==3 else flag
            assert {k:params[k] for k in ('nat','u20','youth') if k in params}==expected

@pytest.mark.parametrize('mutation',[lambda s:s.update(fixtureid='999'),lambda s:s['home'].update(teamid='7'),lambda s:s.update(nat='1')])
def test_incoherent_report_never_leaks_wrong_team_or_population(mutation):
    c=Classic();c.summaries['300']['home']['points']='1234';mutation(c.summaries['300']);m=read(c)['sides'][0]['matches'][0]
    assert m['report_state']=='inconsistent' and m['home_score']==0 and m['score_source']=='match_score'
    assert all(v is None for v in m['ratings'].values())

def test_future_naive_dates_and_unrelated_fixture_are_excluded_without_invented_results():
    c=Classic();c.history['9']['401']=fixture(401,day=16)
    c.history['9']['402']={**fixture(402),'matchfinish':'2026-01-12T14:00:00'}
    c.history['9']['403']=fixture(403,'70','71',12)
    r=read(c);assert r['sides'][0]['excluded_count']==3
    assert [m['id'] for m in r['sides'][0]['matches']]==['300','105','104','103']

def test_unrelated_target_and_oversized_history_are_rejected_before_reports():
    c=Classic();c.target['hometeamid']='7'
    with pytest.raises(ClassicError):read(c)
    assert len(c.calls)==1
    c=Classic();c.history['9']={str(i):fixture(i) for i in range(100,121)}
    with pytest.raises(ClassicError):read(c)
    assert not any(resource=='rs' for resource,_ in c.calls)

def test_absent_scores_and_invalid_numbers_remain_unknown_instead_of_zero():
    c=Classic();c.summaries['300']['home'].update(points=None,scrum=True,weight='Unknown')
    m=read(c)['sides'][0]['matches'][0]
    assert m['report_state']=='available' and m['home_score'] is None and m['guest_score']==0
    assert m['ratings']['scrum'] is None and m['xv_weight'] is None

def test_finished_bot_fixture_is_visible_but_has_no_invented_report():
    c=Classic();c.history['9']['300']['botmatch']='1'
    m=read(c)['sides'][0]['matches'][0]
    assert m['report_state']=='not_played' and m['home_score']==0 and m['guest_score']==0
    assert m['score_source']=='match_score' and all(v is None for v in m['ratings'].values())


def test_missing_shared_report_uses_one_verified_score_read_for_both_histories():
    c=Classic();c.summaries['300']=ClassicError('Missing report')
    c.scores['300'].update(homescore='23',guestscore='14')
    r=read(c)
    for side in r['sides']:
        m=side['matches'][0]
        assert (m['home_score'],m['guest_score'],m['score_source'])==(23,14,'match_score')
        assert m['report_state']=='unavailable' and all(v is None for v in m['ratings'].values())
    assert len([1 for resource,params in c.calls if resource=='ls' and params['fixtureid']=='300'])==1


@pytest.mark.parametrize('override',[{'fixtureid':'999'},{'match_has_finished':'0'},{'nat':'1'},{'homescore':False}])
def test_wrong_or_unconfirmed_score_never_becomes_a_final_result(override):
    c=Classic();c.summaries['300']=ClassicError('Missing report');c.scores['300'].update(override)
    m=read(c)['sides'][0]['matches'][0]
    assert m['home_score'] is None and m['guest_score'] is None and m['score_source'] is None
