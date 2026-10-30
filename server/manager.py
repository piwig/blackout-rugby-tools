"""Import owned Classic clubs using the manager API key, without game writes."""
import asyncio,re
from urllib.parse import parse_qs,urlsplit
from .classic import ClassicClient,ClassicError
from .imports import parse_import
from .storage import pack,now

META_FIELDS=['region','stadium','members','contentment','stadium_capacity','stadium_standing','stadium_uncovered','stadium_covered','stadium_members','stadium_corporate','bank_balance','minor_sponsors','scouting_stars','average_top15_csr','total_salary','leagueid']

async def import_manager(store,shared,access_key,developer_id='',developer_key=''):
    value=access_key.strip().replace('&amp;','&')
    query=urlsplit(value).query if '://' in value else value.lstrip('?&')
    parsed=parse_qs(query)
    mid=parsed.get('m',[''])[0];key=parsed.get('mk',[''])[0]
    if not re.fullmatch(r'\d{1,15}',mid) or not re.fullmatch(r'[A-Za-z0-9_-]{3,200}',key):raise ClassicError('Copiez la clé complète « m=…&mk=… » depuis Moi → Mon compte dans Classic.')
    credentials={k:v for k,v in shared.items() if k in ['d','dk']}
    credentials.update({'m':mid,'mk':key})
    if developer_id:credentials['d']=developer_id
    if developer_key:credentials['dk']=developer_key
    client=ClassicClient(credentials)
    doc=await client.request('m',memberid=mid)
    member=doc.get('members',{}).get(mid)
    # email is only included in an authenticated member response. Never persist it.
    if not isinstance(member,dict) or 'email' not in member:raise ClassicError('Clé manager non validée. Vérifiez m et mk dans votre compte Classic.')
    tids=list(dict.fromkeys(str(x) for x in member.get('teams',[]) if re.fullmatch(r'\d{1,15}',str(x))))
    if not tids and str(member.get('teamid','')).isdigit():tids=[str(member['teamid'])]
    if not tids or len(tids)>30:raise ClassicError('Aucune équipe exploitable trouvée pour ce manager.')
    gate=asyncio.Semaphore(2)
    async def prepare(tid):
        async with gate:
            teamdoc=await client.request('t',teamid=tid);team=teamdoc.get('teams',{}).get(tid)
            if not isinstance(team,dict) or str(team.get('owner'))!=mid:raise ClassicError('Le club '+tid+' n’est pas rattaché à ce manager.')
            datasets=[]
            for youth in [True,False]:
                players=await client.request('p',teamid=tid,**({'youth':'1'} if youth else {}))
                if players.get('players') in ({},[]):result={'players':[],'game_date':players.get('gameDate')}
                else:result=parse_import(pack(players).encode(),'players.json')
                datasets.append((youth,result))
            return tid,team,datasets
    try:prepared=await asyncio.wait_for(asyncio.gather(*(prepare(tid) for tid in tids)),timeout=95)
    except TimeoutError:raise ClassicError('Synchronisation trop longue. Vos données précédentes sont conservées ; réessayez.') from None
    # All external reads and validation finish before any saved club is changed.
    result=[];observed=now()
    with store.db() as db:
        for tid,team,datasets in prepared:
            name=str(team.get('name',tid))[:100];country=str(team.get('country_iso','??'))[:2]
            meta={k:team[k] for k in META_FIELDS if k in team};meta['date_maj']=observed
            db.execute('INSERT INTO teams(id,name,country,meta) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,meta=excluded.meta',(tid,name,country,pack(meta)))
            counts={}
            for youth,players in datasets:
                store.save_snapshot(tid,youth,players['players'],'API Classic · compte manager',observed,players.get('game_date'),db)
                counts['academy' if youth else 'squad']=len(players['players'])
            result.append({'id':tid,'name':name,'country':country,**counts})
    for tid in tids:store.save_secrets(tid,credentials)
    account={'id':mid,'username':str(member.get('username',mid))[:100],'team_ids':tids,'imported_at':observed}
    store.set('classic_account',account)
    store.set('api_manager',store.cipher.encrypt(pack({'m':mid,'mk':key}).encode()).decode())
    if doc.get('gameDate'):store.set('game_date',doc['gameDate'])
    return {'ok':True,'account':account,'teams':result}
