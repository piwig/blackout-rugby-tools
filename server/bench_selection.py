"""Exact indicative bench coverage, given fixed starters and declared scores."""
from decimal import Decimal
import math


def select_bench(candidates, roles, limit=8):
    """Maximize filled coverage units, then known-score sum, then stable IDs.

    Two options sought for Pilier; one for every other role. A player's covers
    describe personal affinity, not qualification or simultaneous replacements.
    Unknown scores add no term; players with no established affinity are omitted.
    """
    if (type(limit) is not int or not 0 <= limit <= 8 or len(candidates) > 500
            or not 1 <= len(roles) <= 9 or len(set(roles)) != len(roles)):
        raise ValueError('Banc hors limites.')
    rows, seen = [], set()
    for row in candidates:
        identifier, covers, score = row['id'], row['covers'], row['score']
        if (not isinstance(identifier,str) or not identifier or identifier in seen
                or not isinstance(covers,(list,tuple,set,frozenset)) or not set(covers)<=set(roles)
                or score is not None and (type(score) not in (int,float) or not math.isfinite(score))):
            raise ValueError('Candidat au banc incohérent.')
        seen.add(identifier)
        if covers:
            rows.append((identifier,set(covers),Decimal(str(score)) if score is not None else Decimal(0)))
    rows.sort(key=lambda row:row[0])
    target=min(limit,len(rows))
    needs=tuple(2 if role=='Pilier' else 1 for role in roles)
    zero=(0,)*len(roles)
    dp={(0,zero):(Decimal(0),())}
    for identifier,covers,score in rows:
        next_dp=dict(dp)
        for (count,state),(total,ids) in dp.items():
            if count==target:continue
            updated=tuple(min(need,value+int(role in covers)) for role,need,value in zip(roles,needs,state))
            key=(count+1,updated);choice=(total+score,ids+(identifier,));old=next_dp.get(key)
            if old is None or choice[0]>old[0] or choice[0]==old[0] and choice[1]<old[1]:next_dp[key]=choice
        dp=next_dp
    finalists=[(-sum(state),-score,ids) for (count,state),(score,ids) in dp.items() if count==target]
    return list(min(finalists)[2])
