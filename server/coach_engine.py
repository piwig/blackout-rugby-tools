"""Versioned, deterministic local coaching heuristics; no game action or win model."""
import calendar
from datetime import date

from .domain import SKILLS, number
from .optimization import ROLES, energy_of, injury_status, maximum_assignment, unique_players
from .bench_selection import select_bench
from .role_weights import default_weights

METHOD = 'coach-lab-v2'
ATTRIBUTES = (*SKILLS, 'height', 'weight', 'form', 'aggression', 'discipline', 'leadership', 'experience')


def defaults():
    refs = {key: {'min': 0, 'max': 21, 'direction': 'higher'} for key in SKILLS}
    refs.update({key: {'min': lo, 'max': hi, 'direction': direction} for key, lo, hi, direction in (
        ('height', 150, 220, 'higher'), ('weight', 60, 150, 'higher'), ('form', 0, 11, 'higher'),
        ('aggression', 0, 5, 'lower'), ('discipline', 0, 5, 'higher'),
        ('leadership', 0, 5, 'higher'), ('experience', 0, 21, 'higher'))})
    roles = default_weights()
    weights = {str(i): {key: roles[role].get(key, 0) for key in ATTRIBUTES} for i, role in enumerate(ROLES, 1)}
    weights['captain'] = {key: {'leadership': 4, 'experience': 2, 'discipline': 1}.get(key, 0) for key in ATTRIBUTES}
    weights['kicker'] = {key: {'kicking': 4, 'form': 1}.get(key, 0) for key in ATTRIBUTES}
    return {'weights': weights, 'references': refs, 'energy_scale': 'percent', 'energy_floor': 60,
            'energy_penalty': 0, 'mode': 'skills', 'rating_scale': '', 'position_scope': 'exact',
            'position_basis': 'observed', 'minimum_notes': 1, 'skill_share': 50,
            'locks': {}, 'excluded_ids': [], 'objective': 'balanced',
            'conditions': {'weather': 'unknown', 'wind': 'unknown'}, 'opponent': None}


def months_before(day, months):
    year, month = divmod(day.year*12+day.month-1-months, 12)
    return date(year, month+1, min(day.day, calendar.monthrange(year, month+1)[1]))


def attribute_score(player, weights, references):
    components, missing = [], []
    for key, weight in weights.items():
        if not weight:
            continue
        value = number(player.get(key))
        if value is None:
            missing.append(key)
            continue
        ref = references[key]
        normal = max(0, min(1, (value-ref['min'])/(ref['max']-ref['min'])))
        if ref['direction'] == 'lower':
            normal = 1-normal
        components.append({'attribute': key, 'value': value, 'weight': weight, 'normalized': round(normal*100, 4)})
    total = sum(weights.values())
    return {'score': None if missing or not total else sum(c['normalized']*c['weight'] for c in components)/total,
            'missing': missing, 'components': components}


def performance_index(rows, player_id, shirt, config, team_id, cohort, start, end):
    # A report start role (e.g. Pilier) is not proof of shirt 1 vs 3. Never use minutes as weights.
    position = str(shirt) if config['position_scope'] == 'exact' else ROLES[shirt-1]
    matches = [r for r in rows if str(r.get('player_id')) == player_id
               and r.get('team_id') == team_id and r.get('context') == cohort
               and r.get('rating_scale') == config['rating_scale']
               and r.get('position_basis', 'observed') == config['position_basis']
               and r.get('position') == position and start <= r.get('match_date', '') <= end
               and number(r.get('rating')) is not None]
    values = [number(r['rating']) for r in matches]
    bounds = {(r.get('scale_min'), r.get('scale_max')) for r in matches}
    lo, hi = next(iter(bounds)) if len(bounds) == 1 else (None, None)
    value = (max(values) if config['mode'] == 'best' else sum(values)/len(values)) if values else None
    if len(values) < config['minimum_notes']:
        value = None
    normalized = None
    if value is not None and number(lo) is not None and number(hi) is not None and hi > lo:
        normalized = 100*(value-lo)/(hi-lo)
    return {'score': value, 'normalized': normalized, 'count': len(values), 'small_sample': len(values)<5,
            'scale': config['rating_scale'], 'bounds': [lo, hi], 'position': position,
            'position_basis': config['position_basis'], 'evidence': matches}


def percentages(values):
    total = sum(values.values())
    raw = {key: value*100/total for key, value in values.items()}
    result = {key: int(value) for key, value in raw.items()}
    for key in sorted(raw, key=lambda k: -(raw[k]-result[k]))[:100-sum(result.values())]:
        result[key] += 1
    return result


def propose_tactics(players, config):
    refs = config['references']
    skills = {}
    unknown = []
    for key in ('strength', 'technique', 'handling', 'attack', 'speed', 'agility', 'kicking', 'defense', 'discipline'):
        values = [attribute_score(p, {key: 1}, refs)['score'] for p in players]
        known = [v for v in values if v is not None]
        skills[key] = sum(known)/len(known) if known else None
        if len(known) < 15:
            unknown.append(key)
    # Neutral 50 is a declared tactic fallback only, never a player selection score.
    value = lambda key: skills[key] if skills[key] is not None else 50
    attacks = {'driving': 10+value('strength'), 'pickandgo': 10+value('technique'),
               'expansive': 10+(value('speed')+value('handling'))/2,
               'creative': 10+(value('agility')+value('attack'))/2}
    wet = config['conditions']['weather'] == 'wet'
    wind = config['conditions']['wind'] == 'strong'
    if wet:
        attacks['creative'] *= .7
        attacks['expansive'] *= .8
    opponent = config.get('opponent')
    # Manager-declared defensive exposure is only a bounded preference (+10%), not a proven counter.
    if opponent:
        attacks[opponent['exposure']] *= 1.1
    intensity = {'balanced': 65, 'recovery': 40, 'development': 50}[config['objective']]
    energies = [energy_of(p, config['energy_scale']) for p in players]
    known_energy = [v for v in energies if v is not None]
    if known_energy and sum(known_energy)/len(known_energy) < 75:
        intensity = max(30, intensity-15)
    frequency = round(max(10, min(55, 20+(value('kicking')-50)/5+(10 if wet else 0)-(10 if wind else 0))))
    base = {'attacks': percentages(attacks), 'kick_frequency': frequency,
            'kick_types': percentages({'touch': 50+(20 if wind else 0), 'territory': 30, 'contestable': 20-(10 if wind else 0)}),
            'defense': 'drift' if value('speed') >= value('strength') else 'man',
            'intensity': intensity, 'discipline': 'cautious' if wet or value('discipline') < 50 else 'balanced'}
    cautious = {**base, 'intensity': max(20, intensity-15), 'discipline': 'cautious', 'kick_frequency': min(70, frequency+10)}
    possession = {**base, 'kick_frequency': max(0, frequency-10), 'attacks': percentages({**attacks, 'pickandgo': attacks['pickandgo']*1.2})}
    return {**base, 'base_plan': not bool(opponent), 'selected_count': len(players), 'known_means': skills,
            'unknown_attributes': unknown, 'conditions': config['conditions'], 'opponent': opponent,
            'objective': config['objective'], 'fallback': 'neutral-50-for-tactics-only',
            'variants': [{'name': name, 'plan': plan, 'reason': reason} for name, plan, reason in (
                ('base', base, 'Forces du XV retenu et conditions déclarées.'),
                ('cautious', cautious, 'Intensité réduite et davantage de territoire ; moins de possession.'),
                ('possession', possession, 'Plus de pick and go, moins de pied ; davantage de phases et de fatigue.'))]}


def calculate(roster, observations, config, team_id, cohort, generated_at, *, manual=None, captain=None, kicker=None, tactics=None):
    roster = unique_players(roster)
    if len(roster)>500:
        raise ValueError('Effectif limité à 500 joueurs.')
    players = {str(p['id']): p for p in roster}
    locks, exclusions = config['locks'], set(config['excluded_ids'])
    if not (set(locks.values())|exclusions) <= set(players) or len(set(locks.values())) != len(locks) or set(locks.values()) & exclusions:
        raise ValueError('Verrouillages ou exclusions incompatibles avec cet effectif.')
    eligible, unknown_energy, unknown_injury = [], [], []
    for pid, p in players.items():
        energy = energy_of(p, config['energy_scale'])
        injury = injury_status(p.get('injured'), generated_at)
        if energy is None: unknown_energy.append(pid)
        if injury is None: unknown_injury.append(pid)
        if pid not in exclusions and injury is not True and (energy is None or energy >= config['energy_floor']):
            eligible.append(pid)
    if not set(locks.values()) <= set(eligible):
        raise ValueError('Un joueur verrouillé est exclu, blessé ou sous le seuil d’énergie.')
    end = date.fromisoformat(generated_at[:10]); start = months_before(end, 4)
    edges = {}
    for shirt in range(1, 16):
        for pid in eligible:
            skill = attribute_score(players[pid], config['weights'][str(shirt)], config['references'])
            perf = performance_index(observations, pid, shirt, config, team_id, cohort, start.isoformat(), end.isoformat())
            score = skill['score'] if config['mode']=='skills' else perf['score']
            if config['mode']=='hybrid':
                score = None if skill['score'] is None or perf['normalized'] is None else (config['skill_share']*skill['score']+(100-config['skill_share'])*perf['normalized'])/100
            energy = energy_of(players[pid], config['energy_scale'])
            if score is not None and config['energy_penalty']:
                score = None if energy is None else score-abs(score)*config['energy_penalty']/100*(110-energy)/110
            edges[(shirt, pid)] = {'score': score, 'skills': skill, 'performance': perf, 'energy': energy}
    role_names=list(dict.fromkeys(ROLES))
    affinities={pid:{role:max((edges[(s,pid)]['skills']['score'] for s in range(1,16)
                              if ROLES[s-1]==role and edges[(s,pid)]['skills']['score'] is not None),default=None)
                     for role in role_names} for pid in eligible}
    coverable={pid:[role for role,value in values.items() if value is not None and
                   value>=.8*max(v for v in values.values() if v is not None)]
               for pid,values in affinities.items()}
    if manual is not None:
        slots = {k:v for k,v in manual.items() if v}
        if len(set(slots.values()))!=len(slots) or not set(slots.values())<=set(eligible) or any(slots.get(k)!=v for k,v in locks.items()):
            raise ValueError('Feuille manuelle incompatible : doublon, effectif, disponibilité ou verrouillage.')
    else:
        slots = dict(locks)
        shirts = [i for i in range(1,16) if str(i) not in locks]
        candidates = [pid for pid in eligible if pid not in locks.values()]
        assignments = maximum_assignment([[edges[(shirt,pid)]['score'] for pid in candidates] for shirt in shirts])
        slots.update({str(shirt): candidates[index] for shirt,index in zip(shirts,assignments) if index is not None})
        remaining = [pid for pid in eligible if pid not in slots.values()
                     and any(edges[(s,pid)]['score'] is not None for s in range(1,16))]
        bench = select_bench([{'id':pid, 'covers':coverable[pid],
                               'score':max((edges[(s,pid)]['score'] for s in range(1,16)
                                            if edges[(s,pid)]['score'] is not None),default=None)}
                              for pid in remaining],role_names)
        slots.update({str(i):pid for i,pid in enumerate(bench,16)})
    starter_ids = {pid for slot,pid in slots.items() if int(slot)<=15}
    ranked_roles = {}
    for role, chosen in (('captain',captain),('kicker',kicker)):
        ranking = [{'id':pid,'name':players[pid].get('name',pid), **attribute_score(players[pid],config['weights'][role],config['references']), 'starter':pid in starter_ids} for pid in eligible]
        ranking.sort(key=lambda row: (row['score'] is None,-(row['score'] or 0),row['id']))
        if chosen and chosen not in starter_ids:
            raise ValueError('Le capitaine et le buteur doivent appartenir au XV titulaire.')
        suggested = next((r['id'] for r in ranking if r['starter'] and r['score'] is not None),None)
        primary = chosen or suggested
        ranked_roles[role] = {'selected':primary,'manual':bool(chosen),'ranking':ranking,
                              'backups':[r['id'] for r in ranking if r['id']!=primary and r['id'] in slots.values() and r['score'] is not None][:3]}
    selected = [{'slot':int(slot),'id':pid,'name':players[pid].get('name',pid),
                 **(edges[(int(slot),pid)] if int(slot)<=15 else {'score':None})} for slot,pid in sorted(slots.items(),key=lambda item:int(item[0]))]
    coverage = {role:[pid for slot,pid in slots.items() if int(slot)>15 and role in coverable[pid]]
                for role in role_names}
    needed = {role:2 if role=='Pilier' else 1 for role in role_names}
    plan = propose_tactics([players[pid] for pid in sorted(starter_ids)],config)
    if tactics:
        plan.update(tactics);plan['manual']=True
    warnings = []
    if unknown_energy: warnings.append('Certaines énergies sont inconnues ; vérifier avant application.')
    if unknown_injury: warnings.append('Certaines disponibilités médicales sont inconnues.')
    if config['mode']!='skills' and any(p.get('performance',{}).get('small_sample') for p in selected if p['slot']<=15): warnings.append('Petit échantillon : moins de cinq notes par poste.')
    unfilled = [i for i in range(1,16) if str(i) not in slots]
    if unfilled: warnings.append('XV incomplet : certains postes restent vacants.')
    if any(p['score'] is None for p in selected if p['slot']<=15): warnings.append('Une sélection manuelle possède un score incomplet.')
    return {'method':METHOD,'generated_at':generated_at,'window':{'start':start.isoformat(),'end':end.isoformat()},
            'slots':slots,'players':selected,'unfilled':unfilled,'responsibles':ranked_roles,'tactics':plan,
            'bench':{'coverage':coverage,'needed':needed,'method':'exact-indicative-coverage-v1','gaps':[role for role,pids in coverage.items() if len(pids)<needed[role]]},'warnings':warnings,
            'unknown_energy':unknown_energy,'unknown_injury':unknown_injury}
