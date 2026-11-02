"""Synthetic contracts: unknown values, unique XVs and evidence separation."""
from datetime import date
import pytest


def engine():
    from server import coach_engine
    return coach_engine


def player(identifier='1', **changes):
    return {'id': identifier, 'name': 'Synthetic '+identifier, 'energy':100, 'injured':False,
            **{key:10 for key in ('stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking')}, **changes}


def test_bench_coverage_requires_relative_affinity_and_not_just_complete_attributes():
    e=engine();config=e.defaults();config['locks']={str(i):str(i) for i in range(1,16)}
    for shirt in range(1,16):
        config['weights'][str(shirt)]={key:0 for key in e.ATTRIBUTES}
        config['weights'][str(shirt)]['kicking' if shirt==15 else 'strength']=1
    roster=[player(str(i),strength=21,kicking=1) for i in range(1,24)]
    result=e.calculate(roster,[],config,'9','club','2026-11-02T00:00:00+00:00')
    assert result['bench']['coverage']['Arrière']==[]
    assert 'Arrière' in result['bench']['gaps']
    assert result['bench']['needed']['Pilier']==2
    assert len([s for s in result['slots'] if int(s)>15])==8


def observation(**changes):
    return {'team_id':'72450','context':'club','player_id':'1','match_date':'2026-10-01',
            'position':'1','position_basis':'observed','rating_scale':'observer','rating':8,
            'scale_min':0,'scale_max':10,'source':'synthetic notebook','match_id':'1', **changes}


def test_required_unknown_attribute_is_incomplete_but_zero_is_valid():
    e=engine(); config=e.defaults(); weights={k:0 for k in e.ATTRIBUTES};weights['strength']=1
    assert e.attribute_score(player(strength=None),weights,config['references'])['score'] is None
    assert e.attribute_score(player(strength=0),weights,config['references'])['score']==0
    weights['height']=1
    assert e.attribute_score(player(height=None),weights,config['references'])['missing']==['height']


def test_calendar_window_clamps_month_end_and_performance_separates_evidence():
    e=engine();assert e.months_before(date(2026,6,30),4)==date(2026,2,28)
    config=e.defaults();config.update(mode='mean',rating_scale='observer',minimum_notes=1)
    rows=[observation(),observation(context='youth',rating=100),observation(position_basis='report_start',rating=100),observation(match_date='2026-06-30',rating=100)]
    result=e.calculate([player()],rows,config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['slots']=={'1':'1'}
    assert result['players'][0]['score']==8
    assert result['players'][0]['performance']['count']==1
    assert result['players'][0]['performance']['small_sample'] is True


def test_hybrid_unknown_bounds_never_invents_a_scale():
    e=engine();config=e.defaults();config.update(mode='hybrid',rating_scale='observer')
    result=e.calculate([player()],[observation(scale_min=None,scale_max=None)],config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['slots']=={}
    assert result['unfilled']==list(range(1,16))


def test_exact_assignment_respects_locks_exclusions_injury_and_energy():
    e=engine();config=e.defaults();config['locks']={'1':'2'};config['excluded_ids']=['3']
    result=e.calculate([player(str(i),injured=i==4,energy=20 if i==5 else 100) for i in range(1,20)],[],config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['slots']['1']=='2'
    assert len(set(result['slots'].values()))==len(result['slots'])
    assert not {'3','4','5'}&set(result['slots'].values())
    assert len(result['unfilled'])==0
    config['locks']={'1':'4'}
    with pytest.raises(ValueError):e.calculate([player('4',injured=True)],[],config,'72450','club','2026-11-01T00:00:00+00:00')


def test_manual_sheet_requires_unique_eligible_players_and_responsibles_in_xv():
    e=engine();config=e.defaults()
    with pytest.raises(ValueError):e.calculate([player()],[],config,'72450','club','2026-11-01T00:00:00+00:00',manual={'1':'1','2':'1'})
    with pytest.raises(ValueError):e.calculate([player(),player('2')],[],config,'72450','club','2026-11-01T00:00:00+00:00',manual={'1':'1'},captain='2')


def test_tactics_are_numeric_balanced_and_depend_on_actual_xv_conditions_objective():
    e=engine();config=e.defaults()
    result=e.calculate([player(str(i)) for i in range(1,16)],[],config,'72450','club','2026-11-01T00:00:00+00:00')
    tactics=result['tactics'];assert sum(tactics['attacks'].values())==100;assert sum(tactics['kick_types'].values())==100
    assert tactics['base_plan'] is True
    config.update(objective='recovery',conditions={'weather':'wet','wind':'strong'})
    changed=e.calculate([player(str(i)) for i in range(1,16)],[],config,'72450','club','2026-11-01T00:00:00+00:00')['tactics']
    assert changed['intensity'] < tactics['intensity']
    assert changed['attacks'] != tactics['attacks']
    assert len(changed['variants'])==3


def test_known_hybrid_scale_and_minimum_sample_are_applied_without_minute_weights():
    e=engine();config=e.defaults();config.update(mode='hybrid',rating_scale='observer',minimum_notes=2)
    for key in ('stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking'):config['references'][key]['max']=20
    rows=[observation(rating=8,minutes=1),observation(match_id='2',rating=10,minutes=80)]
    result=e.calculate([player()],rows,config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['players'][0]['score']==70
    result=e.calculate([player()],rows[:1],config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['slots']=={}


def test_report_start_broad_role_can_compare_only_when_explicitly_selected():
    e=engine();config=e.defaults();config.update(mode='best',rating_scale='observer',position_scope='role',position_basis='report_start')
    result=e.calculate([player()],[observation(position='Pilier',position_basis='report_start',rating=-2,scale_min=None,scale_max=None)],config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['slots']=={'1':'1'}
    assert result['players'][0]['score']==-2


def test_penalty_requires_known_energy_and_manual_roles_recompute_with_selected_xv():
    e=engine();config=e.defaults();config['energy_penalty']=20
    result=e.calculate([player(energy=None)],[],config,'72450','club','2026-11-01T00:00:00+00:00')
    assert result['slots']=={}
    config['energy_penalty']=0
    result=e.calculate([player('1',leadership=5,experience=21,discipline=5,form=11),player('2',leadership=1,experience=1,discipline=1,form=1)],[],config,'72450','club','2026-11-01T00:00:00+00:00',manual={'1':'2','16':'1'})
    assert result['responsibles']['captain']['selected']=='2'
    assert result['responsibles']['captain']['backups']==['1']
