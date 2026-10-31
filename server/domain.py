"""Explainable calculations. None of these functions issues game actions."""
import csv
import io
import math
import re
from .role_weights import default_weights, validate_weights

SKILLS = ['stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking']
SKILL_LABELS = dict(zip(SKILLS, ['Endurance','Dextérité','Attaque','Défense','Technique','Force','Saut','Vitesse','Agilité','Jeu au pied']))
ZONES = ['22','40','40A','22A']
ATTACKS = ['Percussion','Pick and go','Large','Créatif','Jeu au pied']

def number(value):
    try:
        if value is None or isinstance(value,bool) or not str(value).strip(): return None
        n=float(str(value).replace(',','.'))
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def wc_projection(player, game_date):
    """Franck's priority generation, NOT universal official eligibility."""
    try:
        age=int(player['age']); r,d=map(int,str(player['birthday']).split(':'))
        season,week,day=(int(game_date[k]) for k in ('season','round','day'))
        if not (0<=age<=20 and 1<=r<8 and 1<=d<=7 and season>0): return None
        target=season+20-age-int((r,d)>(week,day))
        return target if target%2==0 and target>=season else None
    except (KeyError,ValueError,TypeError): return None

def player_metrics(player, *, role_weights=None):
    skills={k:number(player.get(k)) for k in SKILLS}
    known=[v for v in skills.values() if v is not None]
    roles=default_weights() if role_weights is None else validate_weights(role_weights)
    scores=[]
    for name,weights in roles.items():
        weights={k:w for k,w in weights.items() if w>0}
        if all(skills[k] is not None for k in weights):
            scores.append({'name':name,'score':round(sum(skills[k]*w for k,w in weights.items())/sum(weights.values()),2)})
    scores.sort(key=lambda r:r['score'],reverse=True)
    return {'known_skills':len(known),'skill_total':round(sum(known),2),
      'estimated_csr':round(.42*sum(v**4 for v in known)) if len(known)==10 else None,
      'roles':scores}

def attack_label(value):
    aliases={'percu':'Percussion','percussion':'Percussion','driving':'Percussion','drive':'Percussion',
      'png':'Pick and go','pick and go':'Pick and go','pick&go':'Pick and go','pickngo':'Pick and go',
      'large':'Large','expansive':'Large','wide':'Large','crea':'Créatif','créatif':'Créatif','creative':'Créatif',
      'kick':'Jeu au pied','kicking':'Jeu au pied','jeu au pied':'Jeu au pied'}
    return aliases.get(str(value).strip().lower())

def attack_summary(events):
    result={side:{'total':0,'zones':{z:{a:0 for a in ATTACKS} for z in ZONES},'attacks':{a:0 for a in ATTACKS}} for side in ['home','away']}
    unknown=non_attack=missing_context=0
    provenance={'source':0,'commentary_rule':0,'manual':0}
    for event in events:
        if event.get('classification')=='non_attack':
            non_attack+=1
            continue
        attack=attack_label(event.get('att',''))
        try:
            possession=int(event.get('possession')); field=int(event.get('field'))
            valid_context=(str(event.get('possession')).strip() in ('0','1') and str(event.get('field')).strip() in tuple(map(str,range(6))))
        except (ValueError,TypeError): valid_context=False
        if attack is None or not valid_context:
            unknown+=1
            missing_context+=int(attack is not None)
            continue
        zone=(['22','22','40','40A','22A','22A'] if possession==0 else ['22A','22A','40A','40','22','22'])[field]
        side=result['home' if possession==0 else 'away']
        side['total']+=1;side['zones'][zone][attack]+=1;side['attacks'][attack]+=1
        origin='manual' if event.get('classification')=='attack' and event.get('att_origin')=='manual' else 'commentary_rule' if event.get('att_origin')=='commentary-rule' else 'source'
        provenance[origin]+=1
    return {**result,'unclassified':unknown,'classified':len(events)-unknown-non_attack,'total_events':len(events),
            'inferred':provenance['commentary_rule'],'inferred_events':sum(e.get('att_origin')=='commentary-rule' for e in events),
            'manual':provenance['manual'],'non_attack':non_attack,'attack_missing_context':missing_context,
            'suggested':sum(bool(e.get('suggestion')) for e in events),'provenance':provenance}

def stadium_plan(members,seats,multiplier=9):
    members=number(members); multiplier=number(multiplier)
    if members is None or multiplier is None or not 0<=members<=1_000_000 or not 1<=multiplier<=20: raise ValueError('Membres ou multiplicateur invalide.')
    ratios=[('standing','Debout',.22),('uncovered','Assis découvert',.39),('covered','Assis couvert',.30),('members','Abonnés',.08),('corporate','Loges',.01)]
    sections=[]
    for key,label,ratio in ratios:
        current=max(0,number(seats.get(key)) or 0); target=math.floor(members*multiplier*ratio+.5)
        sections.append({'key':key,'label':label,'ratio':ratio,'current':current,'target':target,'delta':target-current,'to_add':max(0,target-current)})
    return {'sections':sections,'target_total':sum(x['target'] for x in sections),'to_add':sum(x['to_add'] for x in sections)}

def csv_export(rows):
    if not rows: return '\ufeff'
    columns=list(dict.fromkeys(k for row in rows for k in row))
    out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=columns,delimiter=';',lineterminator='\r\n');writer.writeheader()
    for row in rows:
        safe={}
        for key,value in row.items():
            text=str(value) if value is not None else ''
            safe[key]="'"+text if re.match(r'^[\s]*[=+@\-\t\r]',text) else text
        writer.writerow(safe)
    return '\ufeff'+out.getvalue()
