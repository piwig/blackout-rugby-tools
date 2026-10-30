import {useEffect,useState,useCallback,useRef} from 'react';
import {useNavigationGuard} from './navigation-guard';
import {PlayerDetail} from './player-detail';
import {LayoutDashboard,Sprout,Users,CalendarRange,BarChart3,Building2,Plug,BookOpen,LogOut,ArrowRight,RefreshCw,Menu,X,ShieldCheck,ArrowUpRight,Upload,ChevronRight,Sparkles,TrendingUp,UserRound,Info,MessageCircle} from 'lucide-react';
import {type State,type Player,fmt,date} from './types';
import {Pill} from './components';
import {Players,Training,Stadium,Matches,Settings} from './pages';
import {Onboarding} from './account';
import {Optimization} from './optimization';
import {Vacation} from './vacation';
import {SeasonPlanner,ClubIdentity,FeedbackWidget,VacationDigest,clubTheme,ClubBadge} from './workbench';
import {Tutorial,TutorialDialog,HelpButton} from './tutorial';
import {PhotoCredits,SectionPhoto} from './rugby';
import {Dashboard} from './dashboard';
import {Progression} from './progression';
import {RegistrationForm} from './registration';
import {AntiBot} from './antibot';
import {ContactForm,ContactPage} from './contact';
import {ProfileSettings,ProfileAvatar,defaultProfile,type ProfileDocument} from './profile';

const nav=[{id:'home',label:'Tableau de bord',icon:LayoutDashboard},{id:'optimization',label:'Optimisation',icon:Sparkles},{id:'season',label:'Saison & calendrier',icon:CalendarRange},{id:'progression',label:'Progression',icon:TrendingUp},{id:'academy',label:'Académie',icon:Sprout},{id:'squad',label:'Effectif & XV',icon:Users},{id:'matches',label:'Analyse des matchs',icon:BarChart3},{id:'training',label:'Entraînement',icon:CalendarRange},{id:'stadium',label:'Stade & finances',icon:Building2},{id:'vacation',label:'Mode vacances',icon:CalendarRange},{id:'profile',label:'Profil & affichage',icon:UserRound},{id:'settings',label:'Connexion & données',icon:Plug},{id:'contact',label:'Contact & idées',icon:MessageCircle},{id:'guide',label:'Tutoriel & aide',icon:BookOpen}];
const descriptions:Record<string,string>={contact:'Un bug à signaler, une idée à partager : échangez avec Pierig et suivez vos demandes.',home:'Vos repères, vos priorités et les progrès de votre club.',season:'Retrouvez vos prochaines échéances et préparez les rotations.',vacation:'Préparez le relais pendant votre absence et contrôlez les envois dans le jeu.',optimization:'Choisissez un objectif, comparez les propositions, puis enregistrez votre préparation.',academy:'Repérez les talents, fixez leurs objectifs et suivez les compétences dévoilées.',squad:'Consultez vos seniors et préparez la composition du XV.',matches:'Comparez les rencontres importées et construisez vos dossiers adversaires.',training:'Préparez les séances de l’académie sur les seize semaines de la saison.',stadium:'Comparez capacités et budgets avant de décider dans le jeu.',settings:'Connectez votre compte Classic, importez vos données et retrouvez vos accès.',guide:'Un parcours guidé, des exemples et les réponses à vos questions.',profile:'Votre profil, vos couleurs et un tableau de bord qui vous ressemble.',progression:'Ce qui a changé, quand et selon quelles observations.'};
const routeNotes:Record<string,string>={season:'Ajoutez un rendez-vous ou importez les rencontres Classic. Votre calendrier et vos intentions de rotation restent privés.',optimization:'Les propositions et scénarios sont enregistrés dans l’outil. Aucun changement n’est transmis à Classic depuis cet écran.',training:'Ce planning prépare vos séances. Vous devez ensuite les configurer dans le jeu.',settings:'Commencez par relier votre compte pour retrouver vos clubs. Vous pouvez aussi travailler à partir d’un fichier.',vacation:'Un envoi dans Classic exige un accès API adapté et votre validation, ou une règle datée que vous avez activée.'};
export async function request(path:string,body?:unknown,csrf?:string){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),120000);try{const r=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:{...(body instanceof FormData?{}:body!==undefined?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{})},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body),signal:controller.signal});let doc:any;try{doc=await r.json()}catch{throw new Error('Réponse du serveur indisponible. Réessayez.')}if(!r.ok){const e=new Error(typeof doc.detail==='string'?doc.detail:'Vérifiez les champs du formulaire.');Object.assign(e,{status:r.status});throw e}return doc}catch(e){if((e as Error).name==='AbortError')throw new Error('Le serveur a mis trop de temps à répondre. Les données conservées restent disponibles.');throw e}finally{clearTimeout(timer)}}
export type Actions={d:State;act:(path:string,body:unknown,message?:string)=>Promise<any>;openPlayer:(p:Player)=>void;go:(page:string)=>void;busy:boolean};

export default function App(){
  const {confirmLeave}=useNavigationGuard();
  const [d,setD]=useState<State|null>(null),[login,setLogin]=useState(false),[initial,setInitial]=useState(true),[page,setPage]=useState('home'),[team,setTeam]=useState(localStorage.getItem('brt-team')||'72450'),[busy,setBusy]=useState(false),[toast,setToast]=useState(''),[error,setError]=useState(''),[menu,setMenu]=useState(false),[help,setHelp]=useState(false),[player,setPlayer]=useState<Player|null>(null);
  const [mobile,setMobile]=useState(()=>window.matchMedia('(max-width:700px)').matches);
  const identity=useRef(''),sessionScope=useRef(''),actionTicket=useRef(0),requestedTeam=useRef(team),requestId=useRef(0),menuButton=useRef<HTMLButtonElement>(null);requestedTeam.current=team;
  const endSession=useCallback(()=>{sessionScope.current='';identity.current='';requestId.current++;actionTicket.current++;setBusy(false);setD(null);setLogin(true);setInitial(false);setHelp(false);setPlayer(null);setMenu(false);setToast('');setError('')},[]);
  const refresh=useCallback(async()=>{const ticket=++requestId.current;try{const doc=await request('/state?team_id='+encodeURIComponent(team));if(ticket!==requestId.current||team!==requestedTeam.current)return;
    const nextScope=doc.user.username+':'+doc.csrf;
    if(sessionScope.current!==nextScope){actionTicket.current++;setBusy(false);setError('');setToast('');setPlayer(null);setHelp(false);setPage(new URLSearchParams(window.location.search).get('page')==='contact'?'contact':doc.profile?.profile?.start_page||'home');setMenu(false);identity.current=doc.user.username;window.scrollTo({top:0,behavior:'instant'})}
    sessionScope.current=nextScope;
    if(doc.current_team&&doc.current_team.id!==team){requestedTeam.current=doc.current_team.id;setTeam(doc.current_team.id);localStorage.setItem('brt-team',doc.current_team.id)}setD(doc);setLogin(false)
  }catch(e){if(ticket!==requestId.current||team!==requestedTeam.current)return;if((e as any).status===401)endSession();else setError((e as Error).message)}finally{if(ticket===requestId.current&&team===requestedTeam.current)setInitial(false)}},[team,endSession]);
  useEffect(()=>{void refresh()},[refresh]);
  useEffect(()=>{if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{})},[]);
  useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),5000);return()=>clearTimeout(t)}},[toast]);
  useEffect(()=>{document.title=(nav.find(n=>n.id===page)?.label||'Votre atelier')+' · Blackout Rugby Tools'},[page]);
  useEffect(()=>{const query=window.matchMedia('(max-width:700px)'),change=()=>{setMobile(query.matches);if(!query.matches)setMenu(false)};query.addEventListener('change',change);return()=>query.removeEventListener('change',change)},[]);
  useEffect(()=>{if(!menu||!mobile)return;const aside=document.querySelector<HTMLElement>('.sidebar');aside?.querySelector<HTMLElement>('[aria-current="page"]')?.focus();const close=(e:KeyboardEvent)=>{
    if(e.key==='Escape'){e.preventDefault();setMenu(false);menuButton.current?.focus()}
    if(e.key==='Tab'&&aside){const items=Array.from(aside.querySelectorAll<HTMLElement>('button:not([disabled]),a[href]')),first=items[0],last=items[items.length-1];if(e.shiftKey&&(document.activeElement===first||!aside.contains(document.activeElement))){e.preventDefault();last?.focus()}else if(!e.shiftKey&&(document.activeElement===last||!aside.contains(document.activeElement))){e.preventDefault();first?.focus()}}
  };document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close)},[menu,mobile]);
  const profile=d?.profile?.profile??defaultProfile;
  const showPage=(next:string)=>{setPage(next);setMenu(false);setError('');const reduced=profile.motion==='reduced'||window.matchMedia('(prefers-reduced-motion: reduce)').matches;window.scrollTo({top:0,behavior:reduced?'instant':'smooth'});requestAnimationFrame(()=>document.getElementById('page-heading')?.focus({preventScroll:true}))};
  const go=(next:string)=>{if(!nav.some(n=>n.id===next)||next===page)return;if(busy){setToast('Une opération est en cours. Patientez avant de changer de rubrique.');return}if(!confirmLeave())return;showPage(next)};
  const act=async(path:string,body:unknown,message='Enregistré')=>{
    if(!d||(!d.setup_required&&d.current_team.id!==requestedTeam.current))throw new Error('Chargement du club en cours.');
    const scope=d.user.username+':'+d.csrf;
    if(scope!==sessionScope.current)throw new Error('La session a changé. Rechargez votre espace.');
    const ticket=++actionTicket.current;
    setBusy(true);setError('');
    try{const result=await request(path,body,d.csrf);
      if(scope!==sessionScope.current)throw new Error('Cette réponse appartient à une session terminée.');
      if(path==='/logout'){endSession();return result}
      await refresh();
      if(scope!==sessionScope.current)throw new Error('Cette réponse appartient à une session terminée.');
      if(message)setToast(message);return result;
    }catch(e){if(scope===sessionScope.current){if((e as any).status===401)endSession();else setError((e as Error).message)}throw e}
    finally{if(scope===sessionScope.current&&ticket===actionTicket.current)setBusy(false)}
  };
  const selectTeam=(id:string,next:string)=>{if(busy||(id===team&&next===page)||!d?.teams.some(t=>t.id===id)||!nav.some(n=>n.id===next)||!confirmLeave())return;requestedTeam.current=id;setTeam(id);if(id!==team)setD(null);setError('');localStorage.setItem('brt-team',id);setPlayer(null);showPage(next)};
  if(initial)return <div className="boot"><img src="/images/brt-logo-192.png" alt=""/><p>Ouverture de votre atelier…</p></div>;
  if(login)return <Login onLogin={refresh}/>;
  if(!d)return <div className="boot"><p>{error||'Chargement du club…'}</p><button onClick={refresh}>Réessayer</button></div>;
  if(d.setup_required)return <Onboarding d={d} act={act} busy={busy} error={error}/>;
  const props={d,act,openPlayer:setPlayer,go,busy,selectTeam};const current=nav.find(n=>n.id===page)??nav[0];
  const savedProfile=(doc:ProfileDocument)=>setD(current=>current&&current.user.username+':'+current.csrf===d.user.username+':'+d.csrf&&(current.profile?.revision??0)<=doc.revision?{...current,profile:doc}:current);
  const displayName=profile.display_name||d.user.username;
  return <div className="app-shell" style={clubTheme(d.workbench_identity)} data-density={profile.density} data-text-size={profile.text_size} data-motion={profile.motion}>
    <a className="skip-link" href="#page-heading">Aller au contenu</a>
    {menu&&<button className="nav-scrim" aria-label="Fermer le menu" onClick={()=>{setMenu(false);menuButton.current?.focus()}}/>}
    <aside className={'sidebar '+(menu?'is-open':'')} inert={mobile&&!menu} role={mobile&&menu?'dialog':undefined} aria-modal={mobile&&menu?true:undefined} aria-label={mobile&&menu?'Menu de navigation':undefined}>
      <button className="icon-button sidebar-close" aria-label="Fermer la navigation" onClick={()=>{setMenu(false);menuButton.current?.focus()}}><X size={20}/></button>
      <a className="brand" href="#" onClick={e=>{e.preventDefault();go('home')}}><img src="/images/brt-logo-192.png" alt=""/><span>BLACKOUT<small>RUGBY TOOLS</small></span></a>
      <div className="edition"><i/> CLASSIC EDITION <span>2.3</span></div><span className="nav-label">VOTRE CLUB-HOUSE</span>
      <nav id="main-navigation" aria-label="Navigation principale">{nav.map(n=><button key={n.id} aria-current={page===n.id?'page':undefined} className={(page===n.id?'active ':'')+(n.id==='profile'?'nav-separator':'')} onClick={()=>go(n.id)}><n.icon size={19}/><span>{n.label}</span>{page===n.id&&<span className="nav-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="club-mini"><button className="profile-nav" onClick={()=>go('profile')} aria-label="Ouvrir mon profil"><ProfileAvatar profile={profile} username={d.user.username} small/><span><strong>{displayName}</strong><small>Mon espace privé</small></span></button><button className="icon-button" aria-label="Se déconnecter" disabled={busy} onClick={()=>{if(confirmLeave())void act('/logout',{},'').catch(()=>{})}}><LogOut size={17}/></button></div></div>
    </aside>
    <div className="main-shell" inert={mobile&&menu}><header className="topbar"><div className="breadcrumbs"><button ref={menuButton} className="icon-button mobile-menu" aria-label={menu?'Fermer le menu':'Ouvrir le menu'} aria-controls="main-navigation" aria-expanded={menu} onClick={()=>setMenu(!menu)}><Menu/></button><span>Mon atelier</span><ChevronRight size={14}/><strong>{current.label}</strong></div>
      <div className="topbar-right">{d.game_date&&<span className="season" title="Dernier repère de saison importé depuis le jeu">S{d.game_date.season}<i/>Semaine {d.game_date.round}</span>}<label className="club-select"><ClubBadge identity={d.workbench_identity} name={d.current_team.name} small/><select aria-label="Choisir un club" disabled={busy} value={team} onChange={e=>selectTeam(e.target.value,page)}>{d.teams.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><button className="topbar-profile" aria-label="Personnaliser mon espace" onClick={()=>go('profile')}><ProfileAvatar profile={profile} username={d.user.username} small/></button></div>
    </header><main>
      <div className={'page-title '+(!['home','guide','profile'].includes(page)?'page-masthead':'')}><SectionPhoto page={page}/><div><div className="eyebrow">{page==='home'?'BONJOUR '+displayName.toUpperCase():d.current_team.name.toUpperCase()}</div><h1 id="page-heading" tabIndex={-1}>{current.label}</h1><p>{descriptions[page]}</p></div><div className="page-actions"><HelpButton onClick={()=>setHelp(true)}/>{!['settings','guide','profile','contact'].includes(page)&&<button className="button secondary" onClick={()=>go('settings')}><Upload size={16}/><span>Actualiser mes données</span></button>}</div></div>
      {error&&<div className="notice error" role="alert"><span>{error}</span><button className="icon-button" aria-label="Fermer l’erreur" onClick={()=>setError('')}><X size={17}/></button></div>}
      <div className="page-content" key={d.user.username+':'+d.csrf+':'+page}>{routeNotes[page]&&<div className="page-route-note"><Info size={17}/><span>{routeNotes[page]}</span></div>}
        {page==='contact'&&<ContactPage {...props}/>}
        {page==='home'&&<Dashboard {...props} profile={profile}/>}{page==='progression'&&<Progression key={team} {...props}/>}
        {page==='profile'&&<><ProfileSettings key={d.user.username} {...props} onSaved={savedProfile}/><ClubIdentity key={'identity-'+team} {...props}/></>}
        {page==='season'&&<SeasonPlanner key={team} {...props}/>}{page==='optimization'&&<Optimization key={team} {...props}/>}
        {page==='vacation'&&<><VacationDigest key={'digest-'+team} {...props}/><Vacation key={team} {...props}/></>}
        {(page==='academy'||page==='squad')&&<Players key={team+page} {...props} youth={page==='academy'}/>}{page==='training'&&<Training key={team} {...props}/>}{page==='stadium'&&<Stadium key={team} {...props}/>}{page==='matches'&&<Matches key={team} {...props}/>}{page==='settings'&&<Settings key={team} {...props}/>}{page==='guide'&&<Tutorial key={d.user.username} username={d.user.username} go={go}/>}
      </div>
      <FeedbackWidget key={team} {...props} page={page}/><footer className="footer"><span>BLACKOUT RUGBY TOOLS <i/> L’atelier du manager</span><span>Outil indépendant · Votre espace privé</span><PhotoCredits/></footer>
    </main></div>
    {toast&&<div role="status" className="toast"><ShieldCheck size={18}/>{toast}</div>}{busy&&<div className="busy" role="status"><RefreshCw size={16} className="spin"/> Opération en cours…</div>}
    {help&&<TutorialDialog username={d.user.username} page={page} onClose={()=>setHelp(false)} go={go}/>}{player&&<PlayerDetail key={d.user.username+':'+d.csrf+':'+d.current_team.id+':'+player.id} player={player} d={d} act={act} close={()=>setPlayer(null)}/>}
  </div>
}

function Login({onLogin}:{onLogin:()=>Promise<void>}){
  const [captchaToken,setCaptchaToken]=useState<string|null>(null),[captchaReset,setCaptchaReset]=useState(0);
  const [username,setUsername]=useState(localStorage.getItem('brt-username')||''),[password,setPassword]=useState(''),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  const [mode,setMode]=useState<'login'|'register'|'contact'>('login'),[registration,setRegistration]=useState<boolean|null>(null);
  useEffect(()=>{let active=true;request('/registration/options').then(result=>{if(active)setRegistration(result.enabled)}).catch(()=>{if(active)setRegistration(null)});return()=>{active=false}},[]);
  return <div className={'login-page '+(mode==='contact'?'login-contact':'')}><div className="login-story"><div className="brand"><img src="/images/brt-logo-192.png" alt=""/><span>BLACKOUT<small>RUGBY TOOLS</small></span></div><div><Pill>CLASSIC EDITION</Pill><h1>Le prochain avantage<br/>se prépare ici.</h1><p>Votre effectif, votre académie, votre lecture du jeu.<br/>Tout l’atelier du manager, au même endroit.</p><img className="login-emblem" src="/images/brt-logo-192.png" alt="Emblème Blackout Rugby Tools"/></div><span>UN OUTIL INDÉPENDANT POUR LES PASSIONNÉS DE CLASSIC.</span></div>
    <div className="login-form"><div>
      {mode==='register'?<RegistrationForm onRegistered={onLogin} onCancel={()=>setMode('login')}/>:mode==='contact'?<section aria-labelledby="public-contact-heading"><button type="button" className="registration-back" onClick={()=>setMode('login')}>Retour à la connexion</button><span className="eyebrow">CONTACT & IDÉES</span><h2 id="public-contact-heading">Échangeons avec Pierig.</h2><p>Un problème d’accès, un bug ou une idée pour l’atelier ?</p><ContactForm/></section>:<>
        <span className="eyebrow">BIENVENUE DANS VOTRE ATELIER</span><h2>À vous de jouer.</h2><p>Connectez-vous à votre espace privé.</p>
        <form onSubmit={async e=>{e.preventDefault();setBusy(true);setErr('');try{await request('/login',{username,password,captcha_token:captchaToken||''});localStorage.setItem('brt-username',username);setPassword('');await onLogin()}catch(e){setErr((e as Error).message)}finally{setBusy(false);setCaptchaToken(null);setCaptchaReset(value=>value+1)}}}>
          <label>Identifiant<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Mot de passe de l’outil<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{err&&<p className="text-error" role="alert">{err}</p>}<AntiBot action="login" onToken={setCaptchaToken} resetKey={captchaReset}/><button className="button primary" disabled={busy||captchaToken===null}>{busy?'Connexion…':'Entrer dans l’atelier'}<ArrowRight size={17}/></button>
        </form>
        <div className="login-foot"><ShieldCheck size={17}/><span>Les accès à cet outil sont distincts de ceux du jeu Blackout Rugby.</span></div>
        {registration===true?<div className="login-signup"><p>Première visite ? Votre espace privé vous attend.</p><button className="button secondary" disabled={busy} onClick={()=>{setPassword('');setErr('');setMode('register')}}>Créer mon compte</button></div>:registration===false?<p className="tiny">Les inscriptions sont momentanément fermées. Contactez Pierig pour ouvrir votre espace.</p>:<p className="tiny">Vérification de l’ouverture des inscriptions indisponible. Rechargez la page ou contactez Pierig.</p>}
        <button type="button" className="text-button login-contact-link" disabled={busy} onClick={()=>{setPassword('');setErr('');setMode('contact')}}><MessageCircle size={16}/>Contacter Pierig · bug ou idée</button>
      </>}
      <PhotoCredits/>
    </div></div>
  </div>
}
