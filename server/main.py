import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Request,Response,HTTPException,Depends,UploadFile,File,Form
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,ConfigDict
from .storage import Store,pack,now
from .domain import SKILLS,player_metrics,wc_projection,attack_summary,csv_export
from .imports import parse_import,normalize_player,read_csv,reject_constant
from .classic import ClassicClient,ClassicError
from .accounts import Accounts,PrivateStore,active_store
from .manager import import_manager

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Login(Model):
    username:str=Field(max_length=60)
    password:str=Field(max_length=128)
class NewUser(Model):
    username:str=Field(min_length=3,max_length=40)
    password:str=Field(min_length=12,max_length=128)
class PasswordChange(Model):
    current_password:str=Field(max_length=128)
    new_password:str=Field(min_length=12,max_length=128)
class ManagerImport(Model):
    access_key:str=Field(min_length=6,max_length=300)
    developer_id:str=Field(default='',max_length=30)
    developer_key:str=Field(default='',max_length=200)
class TeamRef(Model):
    team_id:str=Field(pattern=r'^\d{1,15}$')
class Team(TeamRef):
    name:str=Field(min_length=1,max_length=100)
    country:str=Field(default='BE',pattern=r'^[A-Z]{2}$')
class Settings(TeamRef):
    developer_id:str=Field(default='',max_length=30)
    developer_key:str=Field(default='',max_length=200)
    manager_id:str=Field(default='',max_length=30)
    manager_key:str=Field(default='',max_length=200)
class Note(TeamRef):
    player_id:str=Field(pattern=r'^\d{1,15}$')
    text:str=Field(default='',max_length=3000)
    watch:bool=False
class Plan(TeamRef):
    season:int=Field(ge=1,le=999)
    grid:list[list[str]]
class Lineup(TeamRef):
    slots:dict[str,str]
class Sync(TeamRef):
    kind:Literal['academy','squad','team','fixtures']='academy'
class FixtureSync(Model):
    id:str=Field(pattern=r'^\d{1,15}$')
    type:Literal[0,1,2]=0
class Match(FixtureSync):
    home:str=Field(default='Domicile',max_length=150)
    away:str=Field(default='Extérieur',max_length=150)
    home_score:int|None=Field(default=None,ge=0,le=999)
    away_score:int|None=Field(default=None,ge=0,le=999)
    events:list[dict]=Field(default_factory=list,max_length=20000)
    season:int|None=None
    round:int|None=None

def create_app(directory=None,password=None,secure=None):
    directory=Path(directory or os.getenv('BRT_DATA_DIR','data'))
    primary=Store(directory,password or os.getenv('BRT_PASSWORD'));accounts=Accounts(directory,primary);store=PrivateStore()
    secure=secure if secure is not None else os.getenv('BRT_SECURE','1')=='1'
    public_url=os.getenv('BRT_PUBLIC_URL','https://brt.bordebat.fr').rstrip('/')
    app=FastAPI(title='Blackout Rugby Tools',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=primary;app.state.accounts=accounts;attempts={};sync_times={}

    @app.middleware('http')
    async def security(request,call_next):
        if request.method not in ['GET','HEAD','OPTIONS']:
            if int(request.headers.get('content-length','0'))>8_200_000:return JSONResponse({'detail':'Fichier limité à 8 Mo.'},status_code=413)
            origin=request.headers.get('origin')
            allowed={public_url}
            if not secure:allowed.update({'http://localhost:5173','http://localhost:3042','http://127.0.0.1:3042','http://testserver'})
            if origin and origin.rstrip('/') not in allowed:return JSONResponse({'detail':'Origine non autorisée.'},status_code=403)
        session=accounts.session(request.cookies.get('brt_session'))
        request.state.session=session
        token=active_store.set(accounts.store(session['user_id'])) if session else None
        try:response=await call_next(request)
        finally:
            if token is not None:active_store.reset(token)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Permissions-Policy':'camera=(), microphone=(), geolocation=()',
          'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response

    async def auth(request:Request):
        session=request.state.session
        if not session:raise HTTPException(401,'Connexion requise.')
        if request.method not in ['GET','HEAD'] and not secrets.compare_digest(request.headers.get('x-csrf-token',''),session['csrf']):raise HTTPException(403,'Session à actualiser (protection CSRF).')
        return session

    def require_team(tid):
        with store.db() as db:r=db.execute('SELECT * FROM teams WHERE id=?',(tid,)).fetchone()
        if not r:raise HTTPException(404,'Club introuvable.')
        return dict(r)

    @app.get('/api/health')
    def health():return {'ok':True,'version':'2.0.0'}

    @app.post('/api/login')
    def login(body:Login,request:Request,response:Response):
        ip=request.client.host if request.client else 'unknown';clock=time.time()
        for key in list(attempts):
            attempts[key]=[t for t in attempts[key] if t>clock-900]
            if not attempts[key]:attempts.pop(key)
        history=attempts.setdefault(ip,[])
        if len(history)>=10:raise HTTPException(429,'Trop de tentatives. Patientez 15 minutes.')
        history.append(clock)
        user=accounts.user(body.username);valid=accounts.verify(user,body.password)
        if not valid:raise HTTPException(401,'Identifiant ou mot de passe incorrect.')
        attempts.pop(ip,None);token,csrf=accounts.start_session(user['id'])
        response.set_cookie('brt_session',token,httponly=True,secure=secure,samesite='strict',max_age=604800,path='/')
        return {'ok':True,'csrf':csrf,'username':user['username']}

    @app.post('/api/logout')
    def logout(response:Response,session=Depends(auth)):
        accounts.logout(session['token'])
        response.delete_cookie('brt_session',path='/');return {'ok':True}

    def admin(session=Depends(auth)):
        if not session['admin']:raise HTTPException(403,'Réservé à l’administrateur.')
        return session

    @app.get('/api/admin/users',dependencies=[Depends(admin)])
    def users():return accounts.list_users()

    @app.post('/api/admin/users',dependencies=[Depends(admin)])
    def create_user(body:NewUser):
        try:return accounts.create(body.username,body.password)
        except ValueError as e:raise HTTPException(422,str(e)) from None

    @app.post('/api/account/password')
    def change_password(body:PasswordChange,response:Response,session=Depends(auth)):
        if not accounts.verify(accounts.user(session['username']),body.current_password):raise HTTPException(403,'Mot de passe actuel incorrect.')
        accounts.change_password(session['user_id'],body.new_password)
        response.delete_cookie('brt_session',path='/')
        return {'ok':True}

    def credentials(tid=''):
        shared={k:v for k,v in primary.secrets('').items() if k in ['d','dk']}
        return {**shared,**store.secrets(tid)}

    @app.post('/api/classic/import',dependencies=[Depends(auth)])
    async def classic_import(body:ManagerImport):
        throttle('manager-import')
        try:return await import_manager(store,credentials(),body.access_key,body.developer_id,body.developer_key)
        except ValueError as e:raise HTTPException(422,str(e)[:250]) from None

    @app.post('/api/classic/sync',dependencies=[Depends(auth)])
    async def classic_sync():
        throttle('manager-import')
        raw=store.get('api_manager')
        if not raw:raise HTTPException(422,'Importez d’abord votre compte Classic.')
        keys=json.loads(store.cipher.decrypt(raw.encode()))
        try:return await import_manager(store,credentials(),'m='+keys['m']+'&mk='+keys['mk'])
        except ValueError as e:raise HTTPException(422,str(e)[:250]) from None

    def snapshot_data(tid,youth):
        with store.db() as db:rows=db.execute('SELECT * FROM snapshots WHERE team_id=? AND youth=? ORDER BY id DESC LIMIT 2',(tid,int(youth))).fetchall()
        if not rows:return [],None
        latest=dict(rows[0]);players=json.loads(latest.pop('payload'));previous={p['id']:p for p in json.loads(rows[1]['payload'])} if len(rows)>1 else {}
        game_date=json.loads(latest['game_date']) if latest['game_date'] else store.get('game_date',{})
        for p in players:
            p['metrics']=player_metrics(p);p['wc_projection']=wc_projection(p,game_date)
            old=previous.get(p['id'],{});p['changes']={k:{'before':old[k],'after':p[k]} for k in SKILLS if k in old and k in p and old[k]!=p[k]}
        return players,latest

    @app.get('/api/state')
    def state(team_id:str='',session=Depends(auth)):
        user={'username':session['username'],'admin':bool(session['admin'])}
        with store.db() as db:
            available=[dict(r) for r in db.execute('SELECT id,name,country FROM teams ORDER BY name')]
        if not available:return {'setup_required':True,'teams':[],'user':user,'csrf':session['csrf'],'classic_account':store.get('classic_account'),'settings':{'developer_ready':bool(credentials().get('dk')),'manager_ready':False}}
        if team_id not in [t['id'] for t in available]:team_id='72450' if any(t['id']=='72450' for t in available) else available[0]['id']
        current=require_team(team_id);academy,asnap=snapshot_data(team_id,True);squad,ssnap=snapshot_data(team_id,False)
        with store.db() as db:
            teams=[dict(r) for r in db.execute('SELECT id,name,country FROM teams ORDER BY name')]
            notes={r['player_id']:{'text':r['text'],'watch':bool(r['watch'])} for r in db.execute('SELECT * FROM notes WHERE team_id=?',(team_id,))}
            plans={str(r['season']):json.loads(r['grid']) for r in db.execute('SELECT * FROM plans WHERE team_id=?',(team_id,))}
            snapshots=[dict(r) for r in db.execute('SELECT id,youth,source,observed_at,imported_at FROM snapshots WHERE team_id=? ORDER BY id DESC LIMIT 40',(team_id,))]
            matches=[{**json.loads(r['payload']),'updated_at':r['updated_at']} for r in db.execute('SELECT * FROM matches ORDER BY updated_at DESC LIMIT 100')]
        for m in matches:m['summary']=attack_summary(m['events']);m['event_count']=len(m.pop('events'))
        creds=credentials(team_id)
        return {'user':user,'setup_required':False,'classic_account':store.get('classic_account'),'teams':teams,'current_team':{**current,'meta':json.loads(current['meta'])},'academy':academy,'squad':squad,'academy_source':asnap,'squad_source':ssnap,'snapshots':snapshots,'notes':notes,'plans':plans,'matches':matches,'game_date':store.get('game_date'),
          'lineup':store.get('lineup:'+team_id,{}),'training':store.get('training:'+team_id,[]),'settings':{'developer_ready':bool(creds.get('d') and creds.get('dk')),'manager_ready':bool(creds.get('m') and creds.get('mk'))},'csrf':session['csrf']}

    @app.post('/api/teams',dependencies=[Depends(auth)])
    def add_team(body:Team):
        with store.db() as db:db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country',(body.team_id,body.name,body.country))
        return {'ok':True}

    @app.post('/api/settings',dependencies=[Depends(auth)])
    def settings(body:Settings):
        require_team(body.team_id)
        store.save_secrets(body.team_id,{'d':body.developer_id,'dk':body.developer_key,'m':body.manager_id,'mk':body.manager_key})
        return {'ok':True}

    @app.post('/api/import',dependencies=[Depends(auth)])
    async def upload(file:UploadFile=File(...),team_id:str=Form('72450'),youth:bool=Form(True)):
        require_team(team_id);data=await file.read(8_000_001)
        try:result=parse_import(data,file.filename or '');count=store.import_result(result,team_id,youth,Path(file.filename or 'import').name)
        except ValueError as e:raise HTTPException(422,str(e)) from None
        return {'ok':True,'players':count,'datasets':len(result['datasets']) or 1}

    @app.post('/api/notes',dependencies=[Depends(auth)])
    def notes(body:Note):
        require_team(body.team_id)
        with store.db() as db:db.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?)',(body.team_id,body.player_id,body.text,int(body.watch)))
        return {'ok':True}

    @app.post('/api/plans',dependencies=[Depends(auth)])
    def plans(body:Plan):
        require_team(body.team_id)
        if len(body.grid)!=4 or any(len(row)!=16 or any(s not in SKILLS+[''] for s in row) for row in body.grid):raise HTTPException(422,'Planning attendu : 4 créneaux × 16 semaines.')
        with store.db() as db:db.execute('INSERT OR REPLACE INTO plans VALUES(?,?,?)',(body.team_id,body.season,pack(body.grid)))
        return {'ok':True}

    @app.post('/api/lineup',dependencies=[Depends(auth)])
    def lineup(body:Lineup):
        require_team(body.team_id);selected=[v for v in body.slots.values() if v]
        if len(selected)!=len(set(selected)) or any(k not in [str(i) for i in range(1,24)] for k in body.slots) or any(not v.isdigit() or len(v)>15 for v in selected):raise HTTPException(422,'Un joueur ne peut occuper qu’un poste, de 1 à 23.')
        store.set('lineup:'+body.team_id,body.slots);return {'ok':True}

    def save_match(doc):
        with store.db() as db:db.execute('INSERT OR REPLACE INTO matches VALUES(?,?,?,?)',(doc['id'],doc['type'],pack(doc),now()))

    @app.post('/api/matches/import',dependencies=[Depends(auth)])
    def import_match(body:Match):
        doc=body.model_dump();doc['events']=[{k:str(v)[:2000] for k,v in e.items() if k in ['att','field','possession','text','commentary','comment','time','minute','att_origin','possession_reported','gametime','half','rule_version']} for e in doc['events']]
        save_match(doc);return {'ok':True,'summary':attack_summary(doc['events'])}

    @app.post('/api/matches/file',dependencies=[Depends(auth)])
    async def match_file(file:UploadFile=File(...),id:str=Form(...),type:int=Form(0),home:str=Form('Domicile'),away:str=Form('Extérieur')):
        raw=await file.read(8_000_001)
        if len(raw)>8_000_000:raise HTTPException(413,'Fichier limité à 8 Mo.')
        try:
            name=(file.filename or '').lower()
            if name.endswith('.csv'):
                rows=read_csv(raw)
                if not rows or not {'field','possession'}.issubset(rows[0]):raise ValueError('CSV : colonnes field et possession requises ; att et text conseillées.')
                doc={'id':id,'type':type,'home':home,'away':away,'events':rows}
            elif name.endswith('.json'):doc=json.loads(raw.decode('utf-8-sig'),parse_constant=reject_constant)
            else:raise ValueError('Format CSV ou JSON attendu.')
            body=Match.model_validate(doc)
        except (ValueError,TypeError,UnicodeError):raise HTTPException(422,'Import invalide : vérifier les colonnes, l’identifiant, le type et les événements.') from None
        return {**import_match(body),'id':body.id,'type':body.type}

    @app.get('/api/matches/{kind}/{mid}',dependencies=[Depends(auth)])
    def match_detail(kind:int,mid:str):
        with store.db() as db:r=db.execute('SELECT payload FROM matches WHERE id=? AND type=?',(mid,kind)).fetchone()
        if not r:raise HTTPException(404,'Match introuvable.')
        doc=json.loads(r['payload']);return {**doc,'summary':attack_summary(doc['events'])}

    @app.get('/api/history/{team_id}/{player_id}',dependencies=[Depends(auth)])
    def history(team_id:str,player_id:str):
        require_team(team_id);found=[]
        with store.db() as db:rows=db.execute('SELECT id,observed_at,source,payload FROM snapshots WHERE team_id=? ORDER BY id DESC LIMIT 100',(team_id,)).fetchall()
        for row in rows:
            for p in json.loads(row['payload']):
                if p['id']==player_id:found.append({'observed_at':row['observed_at'],'source':row['source'],'player':p})
        return found

    @app.get('/api/export',dependencies=[Depends(auth)])
    def export(team_id:str='72450',kind:str='all'):
        if kind in ['academy','squad']:
            require_team(team_id)
            players,_=snapshot_data(team_id,kind=='academy')
            flat=[{k:v for k,v in p.items() if not isinstance(v,(list,dict))} for p in players]
            return Response(csv_export(flat),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="brt-{team_id}-{kind}.csv"'})
        with store.db() as db:
            export={table:[dict(r) for r in db.execute('SELECT * FROM '+table)] for table in ['teams','snapshots','notes','plans','matches']}
        export['lineups']={team['id']:store.get('lineup:'+team['id'],{}) for team in export['teams']}
        export['training']={team['id']:store.get('training:'+team['id'],[]) for team in export['teams']}
        export['game_date']=store.get('game_date');export['exported_at']=now()
        return Response(pack(export),media_type='application/json',headers={'Content-Disposition':'attachment; filename="brt-backup.json"'})

    def throttle(key):
        key=str(store.path)+':'+key;t=time.monotonic()
        if t-sync_times.get(key,0)<10:raise HTTPException(429,'Patientez 10 secondes entre deux synchronisations.')
        sync_times[key]=t

    @app.post('/api/sync',dependencies=[Depends(auth)])
    async def sync(body:Sync):
        require_team(body.team_id);throttle(body.team_id+body.kind);client=ClassicClient(credentials(body.team_id))
        try:
            if body.kind in ['academy','squad']:
                if not client.credentials.get('mk'):raise ClassicError('Ajoutez la clé manager autorisant la lecture des compétences de ce club.')
                doc=await client.request('p',teamid=body.team_id,**({'youth':'1'} if body.kind=='academy' else {}))
                result=parse_import(pack(doc).encode(),'players.json');count=store.import_result(result,body.team_id,body.kind=='academy','API Classic',now())
                return {'ok':True,'players':count}
            doc=await client.request('t',teamid=body.team_id);team=doc.get('teams',{}).get(body.team_id)
            if not isinstance(team,dict):raise ClassicError('Club absent de la réponse Classic.')
            if body.kind=='team':
                # Allowlist prevents credentials or unexpected API fields leaking to the browser.
                keys=['region','stadium','members','contentment','stadium_capacity','stadium_standing','stadium_uncovered','stadium_covered','stadium_members','stadium_corporate','bank_balance','minor_sponsors','scouting_stars','average_top15_csr','total_salary','leagueid']
                meta={k:team[k] for k in keys if k in team};meta['date_maj']=now()
                with store.db() as db:db.execute('UPDATE teams SET meta=? WHERE id=?',(pack(meta),body.team_id))
                return {'ok':True}
            leagueid=team.get('leagueid')
            if not leagueid:raise ClassicError('Championnat du club non disponible.')
            doc=await client.request('f',latest=str(leagueid));fixtures=doc.get('fixtures',{})
            if not isinstance(fixtures,dict):raise ClassicError('Liste des rencontres non reconnue.')
            return {'ok':True,'fixtures':[{k:v for k,v in f.items() if k in ['id','season','round','hometeamid','guestteamid','competition','weather']} for f in fixtures.values() if isinstance(f,dict)]}
        except ValueError as e:raise HTTPException(422,str(e)) from None

    @app.post('/api/matches/sync',dependencies=[Depends(auth)])
    async def sync_match(body:FixtureSync):
        throttle('match:'+str(body.type)+body.id);client=ClassicClient(credentials());flags={1:{'u20':'1'},2:{'nat':'1'}}.get(body.type,{})
        try:
            doc=await client.request('f',fixtureid=body.id,**flags);fixture=doc.get('fixtures',{}).get(body.id)
            if not isinstance(fixture,dict):raise ClassicError('Rencontre introuvable pour ce type de match.')
            names=[]
            for key in ['hometeamid','guestteamid']:
                tid=str(fixture.get(key,''));tdoc=await client.request('t',teamid=tid,**flags);names.append(tdoc.get('teams',{}).get(tid,{}).get('name',tid))
            commentary=await client.request('me',fixtureid=body.id,**flags)
            score=await client.request('ls',fixtureid=body.id,**flags)
            match=Match(id=body.id,type=body.type,home=names[0],away=names[1],home_score=score.get('homescore'),away_score=score.get('guestscore'),season=fixture.get('season'),round=fixture.get('round'),events=commentary['events'])
            save_match(match.model_dump());return {'ok':True,'summary':attack_summary(match.events)}
        except ValueError as e:raise HTTPException(422,str(e)[:300]) from None

    dist=Path(__file__).resolve().parents[1]/'web'/'dist'
    if dist.exists():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        if (dist/'images').exists():app.mount('/images',StaticFiles(directory=dist/'images'),name='images')
        @app.get('/{path:path}')
        def frontend(path:str):
            if path.startswith('api/'):raise HTTPException(404,'Route inconnue.')
            if path in ['manifest.webmanifest','sw.js','icon.svg','image-credits.json']:return FileResponse(dist/path)
            return FileResponse(dist/'index.html',headers={'Cache-Control':'no-cache'})
    return app

def app_factory():return create_app()
