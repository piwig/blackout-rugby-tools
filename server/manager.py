"""Import owned Classic clubs using the manager API key, without game writes."""
import asyncio,json,re
from urllib.parse import parse_qs,urlsplit
from .classic import ClassicClient,ClassicError
from .imports import parse_import
from .storage import pack,now
from .national import authenticated_member,prepare_linked_selections,persist_selections,selection_ids

META_FIELDS=['region','stadium','members','contentment','stadium_capacity','stadium_standing','stadium_uncovered','stadium_covered','stadium_members','stadium_corporate','bank_balance','minor_sponsors','scouting_stars','average_top15_csr','total_salary','leagueid']

async def import_manager(store,shared,access_key,developer_id='',developer_key=''):
    previous_account=store.get('classic_account')
    value=access_key.strip().replace('&amp;','&')
    query=urlsplit(value).query if '://' in value else value.lstrip('?&')
    parsed=parse_qs(query)
    mid=parsed.get('m',[''])[0];key=parsed.get('mk',[''])[0]
    if not re.fullmatch(r'\d{1,15}',mid) or not re.fullmatch(r'[A-Za-z0-9_-]{3,200}',key):raise ClassicError('Copiez la clé complète « m=…&mk=… » depuis Moi → Mon compte dans Classic.')
    credentials={k:v for k,v in shared.items() if k in ['d','dk','iv']}
    credentials.update({'m':mid,'mk':key})
    if (developer_id and developer_id!=credentials.get('d')) or (developer_key and developer_key!=credentials.get('dk')):credentials.pop('iv',None)
    if developer_id:credentials['d']=developer_id
    if developer_key:credentials['dk']=developer_key
    client=ClassicClient(credentials)
    member,doc=await authenticated_member(client,mid)
    teams=member.get('teams',[])
    if isinstance(teams,dict):teams=teams.values()
    tids=list(dict.fromkeys(str(x) for x in teams if re.fullmatch(r'\d{1,15}',str(x))))
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
    linked=previous_account if isinstance(previous_account,dict) and str(previous_account.get('id'))==mid else {'id':mid}
    async def collect():
        clubs=await asyncio.gather(*(prepare(tid) for tid in tids))
        selections=await prepare_linked_selections(store,client,linked)
        return clubs,selections
    try:prepared,selections=await asyncio.wait_for(collect(),timeout=110)
    except TimeoutError:raise ClassicError('Synchronisation trop longue. Vos données précédentes sont conservées ; réessayez.') from None
    # All external reads and validation finish before any saved club is changed.
    result=[];observed=now()
    account={'id':mid,'username':str(member.get('username',mid))[:100],'team_ids':tids,
             'selection_ids':selection_ids(linked),'selection_revision':linked.get('selection_revision',0),'imported_at':observed}
    if selections:account['selections_imported_at']=observed
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT value FROM kv WHERE key='classic_account'").fetchone()
        if (json.loads(row['value']) if row else None)!=previous_account:
            raise ClassicError('Le compte Classic a changé pendant la lecture. Relancez la synchronisation.')
        for tid,team,datasets in prepared:
            name=str(team.get('name',tid))[:100];country=str(team.get('country_iso','??'))[:2]
            meta={k:team[k] for k in META_FIELDS if k in team};meta['date_maj']=observed
            db.execute('INSERT INTO teams(id,name,country,meta) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,meta=excluded.meta',(tid,name,country,pack(meta)))
            counts={}
            for youth,players in datasets:
                store.save_snapshot(tid,youth,players['players'],'API Classic · compte manager',observed,players.get('game_date'),db)
                counts['academy' if youth else 'squad']=len(players['players'])
            result.append({'id':tid,'name':name,'country':country,**counts})
        result.extend(persist_selections(store,db,selections,observed))
        db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('classic_account',pack(account)))
    for tid in tids:store.save_secrets(tid,credentials)
    store.set('api_manager',store.cipher.encrypt(pack({'m':mid,'mk':key}).encode()).decode())
    if doc.get('gameDate'):store.set('game_date',doc['gameDate'])
    return {'ok':True,'account':account,'teams':result}
