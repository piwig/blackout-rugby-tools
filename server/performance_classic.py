"""Observed per-fixture Classic JSON, established from official rs/fs docs.

Reported positions are lineup slots, not a history of repositioning. Fixture
statistics' `minutes played` are total player minutes, never minutes in a role.
Neither rating scale bounds nor missing bench positions are inferred.
"""
import math
import re
from datetime import datetime, timezone

from .classic import ClassicError
from .match_prep import _date
from .team_identity import team_identity

INVALID = 'Observations de match Classic incohérentes ou non reconnues. Aucune observation enregistrée.'
POSITION_WARNING = 'Les postes Classic sont ceux du rapport de départ ; les minutes sont le total du match, sans répartition après changement de poste. Le poste réel des remplaçants reste inconnu.'
BOUNDS_WARNING = 'Les bornes de l’échelle Classic ne sont pas documentées ici. Les notes actuelles et anciennes restent séparées.'
MINUTES_WARNING = 'Minutes Classic indisponibles pour ce relevé ; aucune durée n’est déduite.'
ROLES = {1:'Pilier',2:'Talonneur',3:'Pilier',4:'Deuxième ligne',5:'Deuxième ligne',6:'Troisième ligne',7:'Troisième ligne',8:'Troisième ligne',9:'Demi de mêlée',10:'Demi d’ouverture',11:'Ailier',12:'Centre',13:'Centre',14:'Ailier',15:'Arrière'}


def bad():
    raise ClassicError(INVALID)


def identifier(value):
    if type(value) not in (int, str) or not re.fullmatch(r'[1-9][0-9]{0,14}', str(value)):
        bad()
    return str(value)


def number(value, maximum=1000):
    if value is None:
        return None
    if type(value) not in (int,float,str) or not re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,6})?',str(value)):
        bad()
    parsed=float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= maximum:
        bad()
    return parsed


def flags(context):
    return {'youth':{'youth':'1'}, 'u20':{'u20':'1'}, 'nt':{'nat':'1'}}.get(context,{})


def check_context(document, context):
    if not isinstance(document,dict) or document.get('status') not in (None,'Ok') or document.get('error') or document.get('errors'):
        bad()
    for key,expected in (('youth',context=='youth'),('u20',context=='u20'),('nat',context=='nt')):
        if key in document:
            value=document[key]
            if type(value) not in (int,str) or str(value) not in ('0','1') or (str(value)=='1') != expected:
                bad()


def exact_fixture(document, fixture_id, context):
    check_context(document,context)
    fixtures=document.get('fixtures')
    if not isinstance(fixtures,dict) or set(fixtures)!={fixture_id} or not isinstance(fixtures[fixture_id],dict):
        bad()
    result=fixtures[fixture_id]
    check_context(result,context)
    if 'id' in result and identifier(result['id'])!=fixture_id:
        bad()
    return result


async def read_match_observations(client, team_id, context, fixture_id, *, names=None, current=None):
    try:
        identity=team_identity(team_id)
    except ValueError:
        bad()
    if context not in (('club','youth') if identity['kind']=='club' else (identity['kind'],)):
        bad()
    fixture_id=identifier(fixture_id)
    current=current or datetime.now(timezone.utc)
    if current.tzinfo is None:
        bad()
    requested=flags(context)
    fixture=exact_fixture(await client.request('f',fixtureid=fixture_id,**requested),fixture_id,context)
    home,guest=identifier(fixture.get('hometeamid')),identifier(fixture.get('guestteamid'))
    if home==guest or identity['classic_id'] not in (home,guest):
        bad()
    start,finish=_date(fixture.get('matchstart')),_date(fixture.get('matchfinish'))
    if start is None or finish is None or not start <= finish <= current:
        raise ClassicError('Cette rencontre Classic doit être terminée et datée avant de lire ses observations.')
    competition=fixture.get('competition')
    if not isinstance(competition,str) or not 1 <= len(competition.strip()) <= 160:
        bad()
    summary=await client.read_reporter_summary(fixture_id,context)
    check_context(summary,context)
    if 'fixtureid' in summary and identifier(summary['fixtureid'])!=fixture_id:
        bad()
    for key,expected in (('home',home),('guest',guest)):
        if not isinstance(summary.get(key),dict) or identifier(summary[key].get('teamid'))!=expected:
            bad()
    side='home' if identity['classic_id']==home else 'guest'
    players=summary[side].get('players')
    if not isinstance(players,dict) or not 1 <= len(players) <= 23:
        bad()
    parsed=[];seen=set()
    for key,player in players.items():
        if not isinstance(player,dict) or not re.fullmatch(r'(?:[1-9]|1[0-9]|2[0-3])',str(key)):
            bad()
        player_id=identifier(player.get('playerid'))
        position=player.get('position')
        if type(position) not in (int,str) or not re.fullmatch(r'(?:[1-9]|1[0-9]|2[0-3])',str(position)) or player_id in seen:
            bad()
        seen.add(player_id)
        parsed.append((player_id,int(position),player))
    warnings=[POSITION_WARNING,BOUNDS_WARNING]
    minutes={}
    # fs documents no context selector. Until primary support is established,
    # avoid requesting ambiguous youth/international statistics.
    if context=='club':
        try:
            stats_doc=await client.request('fs',fixtureid=fixture_id,playersonly='1')
        except ClassicError:
            warnings.append(MINUTES_WARNING)
        else:
            check_context(stats_doc,context)
            if stats_doc.get('fixtures') == {}:
                stats = {}
                warnings.append(MINUTES_WARNING)
            else:
                stats=exact_fixture(stats_doc,fixture_id,context)
            if len(stats)>50:
                bad()
            for key,player in stats.items():
                if not re.fullmatch(side+r' player (?:[1-9]|1[0-9]|2[0-3])',key):
                    continue
                if not isinstance(player,dict):
                    bad()
                player_id=identifier(player.get('id'))
                if player_id in minutes or player_id not in seen:
                    bad()
                minutes[player_id]=number(player.get('minutes played'),240)
    else:
        warnings.append(MINUTES_WARNING)
    rows=[]
    names=names or {}
    stadium=str(fixture.get('stadium',''))
    venue=('home' if side=='home' else 'away') if stadium=='0' else 'unknown'
    for player_id,position,player in parsed:
        methods=[key for key in ('rating','rating_old') if key in player] or ['rating']
        for method in methods:
            row={'team_id':team_id,'context':context,'match_id':fixture_id,'match_date':start.date().isoformat(),
                 'competition':competition.strip(),'opponent':'#'+(guest if side=='home' else home),'venue':venue,
                 'player_id':player_id,'player_name':names.get(player_id,'#'+player_id),
                 'position':ROLES.get(position,'Poste inconnu'),'position_basis':'report_start' if position<=15 else 'report_bench_unknown',
                 'rating':number(player.get(method)),'rating_scale':'Classic-rs-legacy' if method=='rating_old' else 'Classic-rs-current',
                 'scale_min':None,'scale_max':None,'minutes':minutes.get(player_id),
                 'source':f'Classic API r=rs fixture={fixture_id} context={context} slot={position}; '+('r=fs minutes played (total match)' if minutes.get(player_id) is not None else 'minutes unknown')}
            rows.append(row)
    if not any(row['minutes'] is not None for row in rows) and MINUTES_WARNING not in warnings:
        warnings.append(MINUTES_WARNING)
    return {'observations':rows,'warnings':warnings,'fixture_id':fixture_id,'context':context,'team_id':team_id}
