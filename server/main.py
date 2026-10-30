import hashlib
import asyncio
from contextlib import asynccontextmanager, suppress
import json
import os
import secrets
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Request,Response,HTTPException,Depends,UploadFile,File,Form,Query
from fastapi.responses import JSONResponse,FileResponse,StreamingResponse
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,ConfigDict,field_validator
from fastapi.exceptions import RequestValidationError
from .storage import Store,pack,now
from .domain import SKILLS,player_metrics,wc_projection,attack_summary,csv_export
from .imports import parse_import,normalize_player,read_csv,reject_constant
from .classic import ClassicClient,ClassicError
from .accounts import Accounts,PrivateStore,active_store
from .manager import import_manager
from .optimization import build_report
from .vacation import VacationService,VacationRule,VacationError
from .lineup_lab import register_lineup_lab
from .insights import register_insights
from .workbench import register_workbench,identity_for
from .profile import register_profile,get_profile
from .progression import register_progression
from .registration import register_registration
from .contact import register_contact,contact_history
from .auth_security import init_login_security,consume_login
from .antibot import register_antibot,verify as verify_antibot
from .exports import export_chunks

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Login(Model):
    username:str=Field(max_length=60)
    password:str=Field(max_length=128)
    captcha_token:str=Field(default='',max_length=2048)
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
    developer_iv:str=Field(default='',max_length=64)
    manager_id:str=Field(default='',max_length=30)
    manager_key:str=Field(default='',max_length=200)
    @field_validator('developer_iv')
    @classmethod
    def validate_iv(cls,value):
        if value and len(value.encode('utf-8'))!=16:raise ValueError('Le paramètre IV Classic doit contenir exactement 16 octets.')
        return value
class NoteVersion(Model):
    text:str=Field(default='',max_length=3000)
    watch:bool=False
class Note(TeamRef):
    player_id:str=Field(pattern=r'^\d{1,15}$')
    text:str=Field(default='',max_length=3000)
    watch:bool=False
    expected_note:NoteVersion|None=None
class Plan(TeamRef):
    season:int=Field(ge=1,le=999)
    grid:list[list[str]]
    expected_grid:list[list[str]]|None=None
class Lineup(TeamRef):
    slots:dict[str,str]
    expected_slots:dict[str,str]|None=None
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

class VacationOptions(Model):
    objective:Literal['balanced','recovery','development']='balanced'
    energy_floor:float=Field(default=60,ge=0,le=110,allow_inf_nan=False)
    energy_scale:Literal['auto','percent','level']='auto'
    excluded_ids:list[str]=Field(default_factory=list,max_length=200)
    captain_id:str|None=Field(default=None,pattern=r'^\d{1,15}$')
    kicker_id:str|None=Field(default=None,pattern=r'^\d{1,15}$')
    @field_validator('excluded_ids')
    @classmethod
    def validate_exclusions(cls,value):
        if any(not x.isascii() or not x.isdigit() or not 1<=len(x)<=15 for x in value):raise ValueError('Identifiants de joueurs invalides.')
        return list(dict.fromkeys(value))

class VacationPreview(TeamRef):
    fixture_id:str=Field(default='0',pattern=r'^\d{1,15}$')
    source:Literal['optimized','saved']='optimized'
    options:VacationOptions=Field(default_factory=VacationOptions)
class VacationSend(Model):
    preview_id:str=Field(min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
class VacationReconcile(VacationSend):
    accept_current:bool=False
class VacationSave(Model):
    rule:VacationRule
    expected_revision:int=Field(default=0,ge=0)
class VacationStop(Model):
    team_id:str|None=Field(default=None,pattern=r'^\d{1,15}$')

def create_app(directory=None,password=None,secure=None):
    directory=Path(directory or os.getenv('BRT_DATA_DIR','data'))
    primary=Store(directory,password or os.getenv('BRT_PASSWORD'));accounts=Accounts(directory,primary);store=PrivateStore()
    secure=secure if secure is not None else os.getenv('BRT_SECURE','1')=='1'
    public_url=os.getenv('BRT_PUBLIC_URL','https://brt.bordebat.fr').rstrip('/')
    vacation_services={}
    worker_enabled=os.getenv('BRT_VACATION_WORKER','0')=='1'
    worker_health={'worker_enabled':worker_enabled,'worker_last_run':None,'worker_error':None}
    manager_worker_health={}

    def vacation_service(user_id):
        shared={k:v for k,v in primary.secrets('').items() if k in ['d','dk','iv']}
        if user_id not in vacation_services:
            vacation_services[user_id]=VacationService(accounts.store(user_id),shared_credentials=shared)
        service=vacation_services[user_id]
        service.shared_credentials=shared
        return service

    async def vacation_cycle():
        # Each manager gets an explicit Store; no request ContextVar is inherited.
        with accounts.db() as db:identifiers=[row['id'] for row in db.execute('SELECT id FROM users ORDER BY id')]
        for user_id in identifiers:
            error=None
            try:await vacation_service(user_id).tick()
            except asyncio.CancelledError:raise
            except Exception:
                # Exceptions may contain upstream transport details. Never log secrets.
                error='Votre suivi nécessite un contrôle ; consultez le journal du mode vacances.'
            manager_worker_health[user_id]={'worker_last_run':now(),'worker_error':error}
        worker_health.update(worker_last_run=now(),worker_error=None)

    async def vacation_worker():
        while True:
            try:await vacation_cycle()
            except asyncio.CancelledError:raise
            except Exception:worker_health['worker_error']='Le suivi automatique a rencontré une erreur. Nouvelle vérification au prochain passage.'
            await asyncio.sleep(900)

    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(vacation_worker()) if worker_enabled else None
        try:yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):await task

    app=FastAPI(title='Blackout Rugby Tools',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=primary;app.state.accounts=accounts;sync_times={}
    init_login_security(accounts)
    register_antibot(app,public_url,secure)
    app.state.vacations=vacation_services;app.state.vacation_cycle=vacation_cycle

    @app.exception_handler(VacationError)
    async def vacation_error(request,exc):
        return JSONResponse({'detail':str(exc),'code':exc.code},status_code=exc.status_code)

    @app.exception_handler(ClassicError)
    async def classic_error(request,exc):
        return JSONResponse({'detail':str(exc),'code':'classic_unavailable'},status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Pydantic's default response echoes submitted values, including secret fields.
        return JSONResponse({'detail':'Vérifiez les champs du formulaire.','fields':[{'loc':e['loc'],'type':e['type']} for e in exc.errors()]},status_code=422)

    @app.middleware('http')
    async def security(request,call_next):
        if request.method not in ['GET','HEAD','OPTIONS']:
            try:content_length=int(request.headers.get('content-length','0'))
            except ValueError:return JSONResponse({'detail':'Requête invalide.'},status_code=400)
            if content_length<0:return JSONResponse({'detail':'Requête invalide.'},status_code=400)
            if content_length>8_200_000:return JSONResponse({'detail':'Fichier limité à 8 Mo.'},status_code=413)
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
          'Content-Security-Policy':"default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
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
    def health():return {'ok':True,'version':'2.3.0'}

    @app.post('/api/login')
    def login(body:Login,request:Request,response:Response):
        consume_login(accounts,request.client.host if request.client else 'unknown',body.username)
        verify_antibot(request,body.captcha_token,'login')
        user=accounts.user(body.username);valid=accounts.verify(user,body.password)
        if not valid:raise HTTPException(401,'Identifiant ou mot de passe incorrect.')
        token,csrf=accounts.start_session(user['id'])
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
        shared={k:v for k,v in primary.secrets('').items() if k in ['d','dk','iv']}
        own=store.secrets(tid)
        if any(own.get(k) and own[k]!=shared.get(k) for k in ['d','dk']):shared.pop('iv',None)
        return {**shared,**own}

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

    @app.get('/api/vacation/status')
    def vacation_status(team_id:str=Query(default='',pattern=r'^(\d{1,15})?$'),session=Depends(auth)):
        if team_id:require_team(team_id)
        creds=credentials(team_id)
        ready=bool(creds.get('d') and creds.get('m') and creds.get('mk') and len(creds.get('iv','').encode())==16 and len(creds.get('dk','').encode()) in (16,24,32))
        return {**vacation_service(session['user_id']).status(team_id or None),**worker_health,**manager_worker_health.get(session['user_id'],{}),
                'write_ready':ready,'write_blocked_reason':None if ready else 'Pour envoyer dans Classic, renseignez les clés manager et les paramètres développeur d, dk et IV dans Connexion & données.'}

    @app.get('/api/vacation/fixtures')
    async def vacation_fixtures(team_id:str=Query(pattern=r'^\d{1,15}$'),session=Depends(auth)):
        require_team(team_id)
        return await vacation_service(session['user_id']).fixtures(team_id)

    @app.post('/api/vacation/rules')
    def vacation_rules(body:VacationSave,session=Depends(auth)):
        require_team(body.rule.team_id)
        return vacation_service(session['user_id']).save_rule(body.rule,body.expected_revision)

    @app.post('/api/vacation/preview')
    async def vacation_preview(body:VacationPreview,session=Depends(auth)):
        require_team(body.team_id)
        return await vacation_service(session['user_id']).preview(body.team_id,body.fixture_id,body.source,body.options.model_dump())

    @app.post('/api/vacation/send')
    async def vacation_send(body:VacationSend,session=Depends(auth)):
        return await vacation_service(session['user_id']).send(body.preview_id)

    @app.post('/api/vacation/reconcile')
    async def vacation_reconcile(body:VacationReconcile,session=Depends(auth)):
        return await vacation_service(session['user_id']).reconcile(body.preview_id,body.accept_current)

    @app.post('/api/vacation/stop')
    def vacation_stop(body:VacationStop,session=Depends(auth)):
        if body.team_id:require_team(body.team_id)
        return vacation_service(session['user_id']).stop(body.team_id)

    def snapshot_data(tid,youth):
        with store.db() as db:rows=db.execute('SELECT id,team_id,youth,substr(source,1,500) AS source,substr(observed_at,1,80) AS observed_at,substr(imported_at,1,80) AS imported_at,digest,payload,game_date FROM snapshots WHERE team_id=? AND youth=? ORDER BY id DESC LIMIT 2',(tid,int(youth))).fetchall()
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
        if not available:return {'setup_required':True,'teams':[],'user':user,'profile':get_profile(store),'csrf':session['csrf'],'classic_account':store.get('classic_account'),'settings':{'developer_ready':bool(credentials().get('dk')),'manager_ready':False}}
        if team_id not in [t['id'] for t in available]:team_id='72450' if any(t['id']=='72450' for t in available) else available[0]['id']
        current=require_team(team_id);academy,asnap=snapshot_data(team_id,True);squad,ssnap=snapshot_data(team_id,False)
        with store.db() as db:
            teams=[dict(r) for r in db.execute('SELECT id,name,country FROM teams ORDER BY name')]
            notes={r['player_id']:{'text':r['text'],'watch':bool(r['watch'])} for r in db.execute('SELECT * FROM notes WHERE team_id=?',(team_id,))}
            plans={str(r['season']):json.loads(r['grid']) for r in db.execute('SELECT * FROM plans WHERE team_id=?',(team_id,))}
            snapshots=[dict(r) for r in db.execute('SELECT id,youth,substr(source,1,500) AS source,substr(observed_at,1,80) AS observed_at,substr(imported_at,1,80) AS imported_at FROM snapshots WHERE team_id=? ORDER BY id DESC LIMIT 40',(team_id,))]
            matches=[]
            for row in db.execute('SELECT * FROM matches ORDER BY updated_at DESC LIMIT 100'):
                match=json.loads(row['payload']);events=match.pop('events')
                match.update(updated_at=row['updated_at'],summary=attack_summary(events),event_count=len(events))
                matches.append(match)
        creds=credentials(team_id)
        return {'user':user,'profile':get_profile(store),'setup_required':False,'classic_account':store.get('classic_account'),'workbench_identity':identity_for(store,team_id),'teams':teams,'current_team':{**current,'meta':json.loads(current['meta'])},'academy':academy,'squad':squad,'academy_source':asnap,'squad_source':ssnap,'snapshots':snapshots,'notes':notes,'plans':plans,'matches':matches,'game_date':store.get('game_date'),
          'lineup':store.get('lineup:'+team_id,{}),'training':store.get('training:'+team_id,[]),'settings':{'developer_ready':bool(creds.get('d') and creds.get('dk')),'manager_ready':bool(creds.get('m') and creds.get('mk'))},'csrf':session['csrf']}

    @app.get('/api/optimization')
    def optimization(team_id:str=Query(default='',pattern=r'^(\d{1,15})?$'),
                     objective:Literal['balanced','recovery','development']='balanced',
                     energy_floor:float=Query(default=60,ge=0,le=110),
                     energy_scale:Literal['auto','percent','level']='auto',
                     season:int|None=Query(default=None,ge=1,le=999),
                     scope:Literal['current','all']='current',session=Depends(auth)):
        # Validate an explicitly selected club before state() can choose a fallback.
        if team_id:require_team(team_id)
        with store.db() as db:
            available=[r['id'] for r in db.execute('SELECT id FROM teams ORDER BY name,id')]
        if not available:return {'reports':[]}
        selected=team_id or ('72450' if '72450' in available else available[0])
        targets=available if scope=='all' else [selected]
        generated=now()
        return {'reports':[build_report(state(tid,session),objective,energy_floor,season,generated_at=generated,energy_scale=energy_scale) for tid in targets]}

    @app.post('/api/teams',dependencies=[Depends(auth)])
    def add_team(body:Team):
        with store.db() as db:db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country',(body.team_id,body.name,body.country))
        return {'ok':True}

    @app.post('/api/settings',dependencies=[Depends(auth)])
    def settings(body:Settings):
        require_team(body.team_id)
        store.save_secrets(body.team_id,{'d':body.developer_id,'dk':body.developer_key,'iv':body.developer_iv,'m':body.manager_id,'mk':body.manager_key})
        return {'ok':True}

    @app.post('/api/import',dependencies=[Depends(auth)])
    async def upload(file:UploadFile=File(...),team_id:str=Form('72450'),youth:bool=Form(True)):
        require_team(team_id);data=await file.read(8_000_001)
        try:
            result=await run_in_threadpool(parse_import,data,file.filename or '')
            count=await run_in_threadpool(store.import_result,result,team_id,youth,Path(file.filename or 'import').name)
        except ValueError as e:raise HTTPException(422,str(e)) from None
        return {'ok':True,'players':count,'datasets':len(result['datasets']) or 1}

    @app.post('/api/notes',dependencies=[Depends(auth)])
    def notes(body:Note):
        require_team(body.team_id)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if body.expected_note is not None:
                row=db.execute('SELECT text,watch FROM notes WHERE team_id=? AND player_id=?',(body.team_id,body.player_id)).fetchone()
                current={'text':row['text'],'watch':bool(row['watch'])} if row else {'text':'','watch':False}
                if current!=body.expected_note.model_dump():raise HTTPException(409,'Cette note a changé dans une autre session. Votre brouillon est conservé ; relisez la note enregistrée avant de continuer.')
            db.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?)',(body.team_id,body.player_id,body.text,int(body.watch)))
        return {'ok':True}

    @app.post('/api/plans',dependencies=[Depends(auth)])
    def plans(body:Plan):
        require_team(body.team_id)
        if len(body.grid)!=4 or any(len(row)!=16 or any(s not in SKILLS+[''] for s in row) for row in body.grid):raise HTTPException(422,'Planning attendu : 4 créneaux × 16 semaines.')
        with store.db() as db:
            # Reserve the write lock before reading so a competing preview cannot
            # pass the same comparison and overwrite a change from this session.
            db.execute('BEGIN IMMEDIATE')
            if body.expected_grid is not None:
                row=db.execute('SELECT grid FROM plans WHERE team_id=? AND season=?',(body.team_id,body.season)).fetchone()
                current=json.loads(row['grid']) if row else [['']*16 for _ in range(4)]
                if current!=body.expected_grid:raise HTTPException(409,'Données modifiées dans une autre session. Rechargez la page avant de recalculer.')
            db.execute('INSERT OR REPLACE INTO plans VALUES(?,?,?)',(body.team_id,body.season,pack(body.grid)))
        return {'ok':True}

    @app.post('/api/lineup',dependencies=[Depends(auth)])
    def lineup(body:Lineup):
        require_team(body.team_id);selected=[v for v in body.slots.values() if v]
        if len(selected)!=len(set(selected)) or any(k not in [str(i) for i in range(1,24)] for k in body.slots) or any(not v.isdigit() or len(v)>15 for v in selected):raise HTTPException(422,'Un joueur ne peut occuper qu’un poste, de 1 à 23.')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            key='lineup:'+body.team_id
            if body.expected_slots is not None:
                row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
                current=json.loads(row['value']) if row else {}
                if current!=body.expected_slots:raise HTTPException(409,'Données modifiées dans une autre session. Rechargez la page avant de recalculer.')
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key,pack(body.slots)))
        return {'ok':True}

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
        with store.db() as db:
            for row in db.execute('SELECT id,substr(observed_at,1,80) AS observed_at,substr(source,1,500) AS source,payload FROM snapshots WHERE team_id=? ORDER BY id DESC LIMIT 100',(team_id,)):
                for p in json.loads(row['payload']):
                    if p['id']==player_id:
                        found.append({'observed_at':row['observed_at'],'source':row['source'],'player':p});break
        return found

    @app.get('/api/export',dependencies=[Depends(auth)])
    def export(team_id:str='72450',kind:str='all',session=Depends(auth)):
        if kind in ['academy','squad']:
            require_team(team_id)
            players,_=snapshot_data(team_id,kind=='academy')
            flat=[{k:v for k,v in p.items() if not isinstance(v,(list,dict))} for p in players]
            return Response(csv_export(flat),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="brt-{team_id}-{kind}.csv"'})
        private=accounts.store(session['user_id'])
        return StreamingResponse(export_chunks(private,accounts,session['user_id']),media_type='application/json',headers={'Content-Disposition':'attachment; filename="brt-backup.json"'})

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

    register_lineup_lab(app,store,auth,require_team,state)
    register_insights(app,store,auth,require_team,state)
    register_workbench(app,store,auth,require_team,state,accounts,vacation_service)
    register_profile(app,store,auth)
    register_progression(app,store,auth,require_team)
    register_registration(app,accounts,auth,secure)
    register_contact(app,accounts,auth,secure)

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
