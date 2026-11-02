"""Four latest finished fixtures per participant, with observed reporter data.

No estimates, storage, external URL fetching or game writes. Missing reports
keep their chronological slot rather than being replaced by an older match.
"""
import math
import re

from .classic import ClassicError
from .match_direct import _check_flags, _flags, _identifier, _names, parse_fixture_reference
from .match_prep import _date, _fixture, _now, _rows
from .match_sheet import _context, _fixture_row, _read

HISTORY_LIMIT=20
MATCH_LIMIT=4
RATINGS=('scrum','lineout','kicking','ruck','maul','handling','attack','defense','stamina',
         'pickandgo','driving','expansive','creative')
INVALID='Rapport Classic incohérent. Aucune donnée du jeu modifiée.'
CONTEXTS={0:'club',1:'u20',2:'nt',3:'youth'}


def _number(value, maximum, *, integer=False):
    if type(value) not in (int,float,str) or not re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,6})?',str(value)):
        return None
    parsed=float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= maximum or integer and not parsed.is_integer():
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _summary(document, fixture, kind):
    if not isinstance(document,dict) or document.get('status') not in (None,'Ok') or document.get('error') or document.get('errors'):
        raise ClassicError(INVALID)
    _check_flags(document,kind)
    if 'fixtureid' in document and _identifier(document['fixtureid'])!=fixture['id']:
        raise ClassicError(INVALID)
    for side,team in (('home',fixture['home_id']),('guest',fixture['guest_id'])):
        values=document.get(side)
        if not isinstance(values,dict) or _identifier(values.get('teamid'))!=team:
            raise ClassicError(INVALID)
        _check_flags(values,kind)
    return document


def _observations(document,fixture,kind,team):
    summary=_summary(document,fixture,kind)
    own=summary['home' if fixture['home_id']==team else 'guest']
    result={'report_state':'available',
            'home_score':_number(summary['home'].get('points'),100000,integer=True),
            'guest_score':_number(summary['guest'].get('points'),100000,integer=True),
            'ratings':{key:_number(own.get(key),1000) for key in RATINGS},
            'pack_weight':_number(own.get('scrum weight'),30000),
            'xv_weight':_number(own.get('weight'),30000),
            'starting_csr':_number(own.get('starting_csr'),1_000_000_000)}
    result['score_source']='reporter' if result['home_score'] is not None or result['guest_score'] is not None else None
    return result


def _missing(state):
    return {'report_state':state,'home_score':None,'guest_score':None,'score_source':None,
            'ratings':dict.fromkeys(RATINGS),'pack_weight':None,'xv_weight':None,'starting_csr':None}


async def _finished_score(client,fid,kind):
    try:
        doc=await _read(client,'ls',fixtureid=fid,**_flags(kind))
        _check_flags(doc,kind)
        if 'fixtureid' in doc and _identifier(doc['fixtureid'])!=fid:raise ClassicError(INVALID)
        if type(doc.get('match_has_finished')) not in (int,str) or str(doc['match_has_finished'])!='1':return None
        scores=(_number(doc.get('homescore'),100000,integer=True),_number(doc.get('guestscore'),100000,integer=True))
        return scores if all(v is not None for v in scores) else None
    except (ClassicError,TimeoutError):return None


async def compare_recent_matches(client,request,*,now=None):
    team,kind=_context(request.team_id,request.match_type)
    fid=parse_fixture_reference(request.reference,kind)
    current,flags=_now(now),_flags(kind)
    target_doc=await _read(client,'f',fixtureid=fid,**flags)
    _check_flags(target_doc,kind)
    target_rows=_rows(target_doc,1)
    if fid not in target_rows:raise ClassicError(INVALID)
    target=_fixture_row(target_rows[fid],team,kind)
    participants=(target['home_id'],target['guest_id'])
    groups=[];ids=set(participants)
    for participant in participants:
        doc=await _read(client,'f',teamid=participant,last=str(HISTORY_LIMIT),**flags)
        _check_flags(doc,kind)
        rows=_rows(doc,HISTORY_LIMIT);finished=[]
        for raw in rows.values():
            _check_flags(raw,kind)
            item=_fixture(raw,participant)
            finish,start=_date(raw.get('matchfinish')),_date(raw.get('matchstart'))
            if item is None or finish is None or finish>current or start is not None and start>finish:
                continue
            weather=raw.get('weather')
            weather=str(weather) if type(weather) in (str,int) and re.fullmatch(r'[0-9]{1,2}',str(weather)) else None
            # No unverified mapping from weather codes to a sunny/rainy icon.
            finished.append({**item,'type':kind,'weather_code':weather,'botmatch':str(raw.get('botmatch',''))=='1'})
        finished.sort(key=lambda f:(f['finish_at'],int(f['id'])),reverse=True)
        chosen=finished[:MATCH_LIMIT]
        for match in chosen:ids.update((match['home_id'],match['guest_id']))
        groups.append({'team_id':participant,'matches':chosen,'history_count':len(rows),
                       'excluded_count':len(rows)-len(finished),'eligible_count':len(finished)})
    names=await _names(client,sorted(ids,key=int),kind)
    summaries={};scores={}
    for group in groups:
        group['name']=names.get(group['team_id'])
        for match in group['matches']:
            match['home_name']=names.get(match['home_id'])
            match['guest_name']=names.get(match['guest_id'])
            if match.pop('botmatch'):
                match.update(_missing('not_played'))
            else:
                if match['id'] not in summaries:
                    try:
                        doc=await client.read_reporter_summary(match['id'],CONTEXTS[kind])
                    except (ClassicError,TimeoutError):
                        summaries[match['id']]=None
                    else:
                        summaries[match['id']]=doc
                doc=summaries[match['id']]
                if doc is None:
                    match.update(_missing('unavailable'))
                else:
                    try:observed=_observations(doc,match,kind,group['team_id'])
                    except ClassicError:observed=_missing('inconsistent')
                    match.update(observed)
            if match['home_score'] is None and match['guest_score'] is None:
                if match['id'] not in scores:scores[match['id']]=await _finished_score(client,match['id'],kind)
                confirmed=scores[match['id']]
                if confirmed is not None:
                    match.update(home_score=confirmed[0],guest_score=confirmed[1],score_source='match_score')
    return {'team_id':request.team_id,'match_type':kind,'fixture_id':fid,
            'retrieved_at':current.isoformat(timespec='seconds'),'sides':groups,
            'history_limit':HISTORY_LIMIT,'match_limit':MATCH_LIMIT,
            'methodology':[
                'Les 20 dernières rencontres de chaque équipe sont examinées ; les 4 dernières terminées sont conservées, même si leur rapport manque.',
                'Scores et notes proviennent du reporter Classic ; un score absent peut être complété par le relevé de score Classic après confirmation de fin. Le poids du pack, du XV et le CSR sont ceux du rapport historique, pas des fiches actuelles.',
                'Une note collective est une observation du reporter, pas une fréquence tactique ni une probabilité de victoire. Aucune échelle maximale n’est supposée.',
                'La météo conserve son code Classic lorsque son libellé n’a pas été vérifié. Une donnée manquante ne vaut jamais zéro.',
            ]}
