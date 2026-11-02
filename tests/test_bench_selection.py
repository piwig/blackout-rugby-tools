from itertools import combinations
import math
import random
import pytest
from server.bench_selection import select_bench


def oracle(rows,roles,limit):
    rows=[r for r in rows if r['covers']]
    n=min(len(rows),limit)
    def key(chosen):
        count=sum(min(2 if role=='Pilier' else 1,sum(role in r['covers'] for r in chosen)) for role in roles)
        score=sum(r['score'] for r in chosen if r['score'] is not None)
        return -count,-score,tuple(sorted(r['id'] for r in chosen))
    return sorted(r['id'] for r in min(combinations(rows,n),key=key))


def test_global_coverage_keeps_rare_specialist_and_versatile_cover():
    rows=[{'id':'a','covers':['A'],'score':100},{'id':'b','covers':['A','B'],'score':90},
          {'id':'c','covers':['C'],'score':80}]
    assert select_bench(rows,['A','B','C'],limit=2)==['b','c']


def test_coverage_precedes_score_and_missing_data_does_not_create_aptitude():
    rows=[{'id':'a','covers':['Pilier'],'score':100},{'id':'b','covers':['Arrière'],'score':None},
          {'id':'c','covers':[],'score':10000}]
    assert select_bench(rows,['Pilier','Arrière'],limit=2)==['a','b']


def test_small_exhaustive_oracle_and_permutations():
    rng=random.Random(713)
    roles=['Pilier','Talonneur','Arrière']
    for _ in range(60):
        rows=[{'id':str(i),'covers':[r for r in roles if rng.randrange(2)],'score':rng.choice([None,0,2,8,11])} for i in range(7)]
        expected=oracle(rows,roles,3)
        assert select_bench(rows,roles,limit=3)==expected
        rng.shuffle(rows)
        assert select_bench(rows,roles,limit=3)==expected


@pytest.mark.parametrize('score',[True,math.nan,math.inf,-math.inf])
def test_invalid_scores_are_rejected(score):
    with pytest.raises(ValueError):select_bench([{'id':'a','covers':['Pilier'],'score':score}],['Pilier'])


def test_limits_and_duplicate_ids_are_rejected():
    row={'id':'1','covers':['Pilier'],'score':10}
    for rows,roles,limit in [([row,row],['Pilier'],8),([row],['Pilier'],9),([row],['Arrière'],8),
                            ([{**row,'id':str(i)} for i in range(501)],['Pilier'],8)]:
        with pytest.raises(ValueError):select_bench(rows,roles,limit)
