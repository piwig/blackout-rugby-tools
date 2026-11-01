import {groupedTeams,isSelectionTeam} from './team-context';
import {tr,getLocale,useLocale,LanguageSelect,normalizeLocale,type Locale} from './i18n';
import {useEffect,useState,useCallback,useRef} from 'react';
import {useNavigationGuard} from './navigation-guard';
import {PlayerDetail} from './player-detail';
import {ArrowRight,RefreshCw,Menu,X,ShieldCheck,Upload,ChevronRight,Info} from 'lucide-react';
import {type State,type Player,fmt,date} from './types';
import {Pill} from './components';
import {Players,Training,Stadium,Matches,Settings} from './pages';
import {Onboarding} from './account';
import {Optimization} from './optimization';
import {Vacation} from './vacation';
import {Market} from './market';
import {SeasonPlanner,ClubIdentity,FeedbackWidget,VacationDigest,clubTheme,ClubBadge} from './workbench';
import {Tutorial,TutorialDialog,HelpButton} from './tutorial';
import {PhotoCredits,SectionPhoto} from './rugby';
import {Dashboard} from './dashboard';
import {SelectionDashboard} from './selection-dashboard';
import {PlayerPool} from './player-pool';
import {PlayerPerformance} from './player-performance';
import {Progression} from './progression';
import {RegistrationForm} from './registration';
import {AntiBot} from './antibot';
import {Sidebar} from './sidebar';
import {navigationItems,isClubOnly} from './navigation';
import {ContactPage} from './contact';
import {ProfileSettings,ProfileAvatar,defaultProfile,type ProfileDocument} from './profile';

const nav=navigationItems;
const descriptions:Record<string,string>={pool:'Vos joueurs dans un même vestiaire de travail, avec toutes leurs observations.',performance:'Les faits du terrain, poste par poste : comparez les notes, les minutes connues et leur contexte.',market:'Comparez les renforts et les investissements sans perdre votre marge de manœuvre.',contact:'Un bug à signaler, une idée à partager : échangez avec Pierig et suivez vos demandes.',home:'Vos repères, vos priorités et les progrès de votre club.',season:'Retrouvez vos prochaines échéances et préparez les rotations.',vacation:'Préparez le relais pendant votre absence et contrôlez les envois dans le jeu.',optimization:'Choisissez un objectif, comparez les propositions, puis enregistrez votre préparation.',academy:'Repérez les talents, fixez leurs objectifs et suivez les compétences dévoilées.',squad:'Consultez vos seniors et préparez la composition du XV.',matches:'Comparez les rencontres importées et construisez vos dossiers adversaires.',training:'Préparez les séances de l’académie sur les seize semaines de la saison.',stadium:'Comparez capacités et budgets avant de décider dans le jeu.',settings:'Connectez votre compte Classic, importez vos données et retrouvez vos accès.',guide:'Un parcours guidé, des exemples et les réponses à vos questions.',profile:'Votre profil, vos couleurs et un tableau de bord qui vous ressemble.',progression:'Ce qui a changé, quand et selon quelles observations.'};
const routeNotes:Record<string,string>={season:'Ajoutez un rendez-vous ou importez les rencontres Classic. Votre calendrier et vos intentions de rotation restent privés.',optimization:'Les propositions et scénarios sont enregistrés dans l’outil. Aucun changement n’est transmis à Classic depuis cet écran.',training:'Ce planning prépare vos séances. Vous devez ensuite les configurer dans le jeu.',settings:'Commencez par relier votre compte pour retrouver vos clubs. Vous pouvez aussi travailler à partir d’un fichier.',vacation:'Un envoi dans Classic exige un accès API adapté et votre validation, ou une règle datée que vous avez activée.'};
export async function request(path:string,body?:unknown,csrf?:string){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),120000);try{const r=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:{'Accept-Language':getLocale(),...(body instanceof FormData?{}:body!==undefined?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{})},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body),signal:controller.signal});let doc:any;try{doc=await r.json()}catch{throw new Error('Réponse du serveur indisponible. Réessayez.')}if(!r.ok){const e=new Error(typeof doc.detail==='string'?doc.detail:'Vérifiez les champs du formulaire.');Object.assign(e,{status:r.status});throw e}return doc}catch(e){if((e as Error).name==='AbortError')throw new Error('Le serveur a mis trop de temps à répondre. Les données conservées restent disponibles.');throw e}finally{clearTimeout(timer)}}
export type Actions={d:State;act:(path:string,body:unknown,message?:string)=>Promise<any>;openPlayer:(p:Player)=>void;go:(page:string)=>void;busy:boolean};

export default function App(){
  const {locale,setLocale}=useLocale();
  const [languageBusy,setLanguageBusy]=useState(false);
  const {confirmLeave}=useNavigationGuard();
  const [d,setD]=useState<State|null>(null),[login,setLogin]=useState(false),[initial,setInitial]=useState(true),[page,setPage]=useState('home'),[team,setTeam]=useState(localStorage.getItem('brt-team')||'72450'),[busy,setBusy]=useState(false),[toast,setToast]=useState(''),[error,setError]=useState(''),[menu,setMenu]=useState(false),[help,setHelp]=useState(false),[player,setPlayer]=useState<Player|null>(null);
  const [mobile,setMobile]=useState(()=>window.matchMedia('(max-width:700px)').matches);
  const identity=useRef(''),sessionScope=useRef(''),actionTicket=useRef(0),requestedTeam=useRef(team),requestId=useRef(0),menuButton=useRef<HTMLButtonElement>(null);requestedTeam.current=team;
  const endSession=useCallback(()=>{sessionScope.current='';identity.current='';requestId.current++;actionTicket.current++;setBusy(false);setD(null);setLogin(true);setInitial(false);setHelp(false);setPlayer(null);setMenu(false);setToast('');setError('')},[]);
  const refresh=useCallback(async()=>{const ticket=++requestId.current;try{const doc=await request('/state?team_id='+encodeURIComponent(team));if(ticket!==requestId.current||team!==requestedTeam.current)return;
    const nextScope=doc.user.username+':'+doc.csrf;
    setLocale(normalizeLocale(doc.profile?.profile?.language));
    if(sessionScope.current!==nextScope){actionTicket.current++;setBusy(false);setError('');setToast('');setPlayer(null);setHelp(false);setPage(new URLSearchParams(window.location.search).get('page')==='contact'?'contact':doc.profile?.profile?.start_page||'home');setMenu(false);identity.current=doc.user.username;window.scrollTo({top:0,behavior:'instant'})}
    sessionScope.current=nextScope;
    if(doc.current_team&&doc.current_team.id!==team){requestedTeam.current=doc.current_team.id;setTeam(doc.current_team.id);localStorage.setItem('brt-team',doc.current_team.id)}setD(doc);setLogin(false)
  }catch(e){if(ticket!==requestId.current||team!==requestedTeam.current)return;if((e as any).status===401)endSession();else setError((e as Error).message)}finally{if(ticket===requestId.current&&team===requestedTeam.current)setInitial(false)}},[team,endSession,setLocale]);
  useEffect(()=>{void refresh()},[refresh]);
  useEffect(()=>{if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{})},[]);
  useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),5000);return()=>clearTimeout(t)}},[toast]);
  useEffect(()=>{document.title=tr(nav.find(n=>n.id===page)?.label||'Votre atelier')+' · Blackout Rugby Tools'},[page,locale]);
  useEffect(()=>{const query=window.matchMedia('(max-width:700px)'),change=()=>{setMobile(query.matches);if(!query.matches)setMenu(false)};query.addEventListener('change',change);return()=>query.removeEventListener('change',change)},[]);
  useEffect(()=>{if(!menu||!mobile)return;const previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';const aside=document.querySelector<HTMLElement>('.sidebar');const currentRoute=aside?.querySelector<HTMLElement>('[aria-current="page"]');const focusTarget=currentRoute?.getClientRects().length?currentRoute:currentRoute?.closest('section')?.querySelector<HTMLElement>('.sidebar-group-toggle')??aside?.querySelector<HTMLElement>('button');focusTarget?.focus();const close=(e:KeyboardEvent)=>{
    if(e.key==='Escape'){e.preventDefault();setMenu(false);menuButton.current?.focus()}
    if(e.key==='Tab'&&aside){const items=Array.from(aside.querySelectorAll<HTMLElement>('button:not([disabled]),a[href]')).filter(item=>item.getClientRects().length>0),first=items[0],last=items[items.length-1];if(e.shiftKey&&(document.activeElement===first||!aside.contains(document.activeElement))){e.preventDefault();last?.focus()}else if(!e.shiftKey&&(document.activeElement===last||!aside.contains(document.activeElement))){e.preventDefault();first?.focus()}}
  };document.addEventListener('keydown',close);return()=>{document.removeEventListener('keydown',close);document.body.style.overflow=previousOverflow}},[menu,mobile]);
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
  const chooseLanguage=async(next:Locale)=>{
    if(!d||busy||languageBusy||next===locale)return;
    const capturedScope=sessionScope.current;
    setLanguageBusy(true);setError('');
    try{
      const latest=await request('/profile') as ProfileDocument;
      if(capturedScope!==sessionScope.current)return;
      await act('/profile',{expected_revision:latest.revision,profile:{...latest.profile,language:next}},'Langue enregistrée');
    }catch(caught){if(capturedScope===sessionScope.current)setError((caught as Error).message);}
    finally{setLanguageBusy(false);}
  };
  const selectTeam=(id:string,next:string)=>{if(busy||(id===team&&next===page)||!d?.teams.some(t=>t.id===id)||!nav.some(n=>n.id===next)||!confirmLeave())return;requestedTeam.current=id;setTeam(id);if(id!==team)setD(null);setError('');localStorage.setItem('brt-team',id);setPlayer(null);showPage(next)};
  if(initial)return <div className="boot"><img src="/images/brt-logo-192.png" alt=""/><p>{tr("Ouverture de votre atelier…")}</p></div>;
  if(login)return <Login onLogin={refresh}/>;
  if(!d)return <div className="boot"><p>{tr(error||'Chargement du club…')}</p><button onClick={refresh}>{tr("Réessayer")}</button></div>;
  if(d.setup_required)return <Onboarding d={d} act={act} busy={busy} error={error}/>;
  const selection=isSelectionTeam(d.current_team);
  const blockedPage=selection&&isClubOnly(page);
  const props={d,act,openPlayer:setPlayer,go,busy,selectTeam};const current=nav.find(n=>n.id===page)??nav[0];
  const savedProfile=(doc:ProfileDocument)=>setD(current=>current&&current.user.username+':'+current.csrf===d.user.username+':'+d.csrf&&(current.profile?.revision??0)<=doc.revision?{...current,profile:doc}:current);
  const displayName=profile.display_name||d.user.username;
  return <div className="app-shell" style={clubTheme(d.workbench_identity)} data-density={profile.density} data-text-size={profile.text_size} data-motion={profile.motion}>
    <a className="skip-link" href="#page-heading">{tr("Aller au contenu")}</a>
    {menu&&<button className="nav-scrim" aria-label={tr("Fermer le menu")} onClick={()=>{setMenu(false);menuButton.current?.focus()}}/>}
    <Sidebar key={d.user.username} page={page} selection={selection} username={d.user.username} profile={profile} displayName={displayName} busy={busy} mobile={mobile} open={menu} onClose={()=>{setMenu(false);menuButton.current?.focus()}} go={go} onLogout={()=>{if(confirmLeave())void act('/logout',{},'').catch(()=>{})}}/>
    <div className="main-shell" inert={mobile&&menu}><header className="topbar"><div className="breadcrumbs"><button ref={menuButton} className="icon-button mobile-menu" aria-label={tr(menu?'Fermer le menu':'Ouvrir le menu')} aria-controls="main-navigation" aria-expanded={menu} onClick={()=>setMenu(!menu)}><Menu/></button><span>{tr("Mon atelier")}</span><ChevronRight size={14}/><strong>{tr(current.label)}</strong></div>
      <div className="topbar-right"><LanguageSelect compact disabled={busy||languageBusy} onChange={next=>void chooseLanguage(next)}/>{d.game_date&&<span className="season" title={tr("Dernier repère de saison importé depuis le jeu")}>{tr("S")}{d.game_date.season}<i/>{tr("Semaine ")}{d.game_date.round}</span>}<label className="club-select"><ClubBadge identity={d.workbench_identity} name={d.current_team.name} small/><select aria-label={tr("Choisir une équipe")} disabled={busy} value={team} onChange={e=>selectTeam(e.target.value,page)}>{groupedTeams(d).map(group=><optgroup key={group.label} label={group.label}>{group.teams.map(t=><option key={t.id} value={t.id}>{t.name}{t.kind==='u20'?' · U20':t.kind==='nt'?tr(' · Nationale'):''}</option>)}</optgroup>)}</select></label><button className="topbar-profile" aria-label={tr("Personnaliser mon espace")} onClick={()=>go('profile')}><ProfileAvatar profile={profile} username={d.user.username} small/></button></div>
    </header><main>
      <div className={'page-title '+(!['home','guide','profile'].includes(page)?'page-masthead':'')}><SectionPhoto page={page}/><div><div className="eyebrow">{page==='home'?tr('BONJOUR {name}',{name:displayName.toUpperCase()}):['pool','performance'].includes(page)?tr('MON RÉSEAU PRIVÉ'):d.current_team.name.toUpperCase()}</div><h1 id="page-heading" tabIndex={-1}>{tr(current.label)}</h1><p>{tr(descriptions[page])}</p></div><div className="page-actions"><HelpButton onClick={()=>setHelp(true)}/>{!['settings','guide','profile','contact'].includes(page)&&<button className="button secondary" onClick={()=>go('settings')}><Upload size={16}/><span>{tr("Actualiser mes données")}</span></button>}</div></div>
      {error&&<div className="notice error" role="alert"><span>{tr(error)}</span><button className="icon-button" aria-label={tr("Fermer l’erreur")} onClick={()=>setError('')}><X size={17}/></button></div>}
      <div className="page-content" key={d.user.username+':'+d.csrf+':'+page}>{routeNotes[page]&&<div className="page-route-note"><Info size={17}/><span>{selection&&page==='season'?tr("Ajoutez les rendez-vous de votre sélection dans le calendrier manuel. Votre calendrier et vos intentions de rotation restent privés."):tr(routeNotes[page])}</span></div>}
        {blockedPage&&<section className="card prose"><h2>{tr("Cette rubrique concerne les clubs.")}</h2><p>{tr("Pour cette sélection, retrouvez l’effectif, les compositions, les matchs et la progression.")}</p><button className="button primary" onClick={()=>go('home')}>{tr("Ouvrir le tableau de bord de la sélection")}</button></section>}
        {page==='contact'&&<ContactPage {...props}/>}
        {page==='pool'&&<PlayerPool {...props}/>}
        {page==='performance'&&<PlayerPerformance {...props}/>}
        {page==='home'&&(selection?<SelectionDashboard {...props}/>:<Dashboard {...props} profile={profile}/>)}{page==='progression'&&<Progression key={team} {...props}/>}
        {page==='profile'&&<><ProfileSettings key={d.user.username} {...props} onSaved={savedProfile}/><ClubIdentity key={'identity-'+team} {...props}/></>}
        {page==='season'&&<SeasonPlanner key={team} {...props}/>}{page==='optimization'&&<Optimization key={team} {...props}/>}
        {page==='vacation'&&!selection&&<><VacationDigest key={'digest-'+team} {...props}/><Vacation key={team} {...props}/></>}
        {page==='market'&&!selection&&<Market {...props} onRefresh={refresh}/>}
        {(page==='squad'||(page==='academy'&&!selection))&&<Players key={team+page} {...props} youth={page==='academy'}/>}{page==='training'&&!selection&&<Training key={team} {...props}/>}{page==='stadium'&&!selection&&<Stadium key={team} {...props}/>}{page==='matches'&&<Matches key={team} {...props}/>}{page==='settings'&&<Settings key={team} {...props}/>}{page==='guide'&&<Tutorial key={d.user.username} username={d.user.username} go={go}/>}
      </div>
      <FeedbackWidget key={team} {...props} page={page}/><footer className="footer"><span>{tr("BLACKOUT RUGBY TOOLS ")}<i/>{tr(" L’atelier du manager")}</span><span>{tr("Outil indépendant · Votre espace privé")}</span><PhotoCredits/></footer>
    </main></div>
    {toast&&<div role="status" className="toast"><ShieldCheck size={18}/>{tr(toast)}</div>}{busy&&<div className="busy" role="status"><RefreshCw size={16} className="spin"/>{tr(" Opération en cours…")}</div>}
    {help&&<TutorialDialog username={d.user.username} page={page} onClose={()=>setHelp(false)} go={go}/>}{player&&<PlayerDetail key={d.user.username+':'+d.csrf+':'+d.current_team.id+':'+player.id} player={player} d={d} act={act} close={()=>setPlayer(null)}/>}
  </div>
}

function Login({onLogin}:{onLogin:()=>Promise<void>}){
  const [captchaToken,setCaptchaToken]=useState<string|null>(null),[captchaReset,setCaptchaReset]=useState(0);
  const [username,setUsername]=useState(localStorage.getItem('brt-username')||''),[password,setPassword]=useState(''),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  const [mode,setMode]=useState<'login'|'register'>('login'),[registration,setRegistration]=useState<boolean|null>(null);
  useEffect(()=>{let active=true;request('/registration/options').then(result=>{if(active)setRegistration(result.enabled)}).catch(()=>{if(active)setRegistration(null)});return()=>{active=false}},[]);
  return <div className="login-page"><div className="login-story"><div className="brand"><img src="/images/brt-logo-192.png" alt=""/><span>{tr("BLACKOUT")}<small>{tr("RUGBY TOOLS")}</small></span></div><div><Pill>{tr("CLASSIC EDITION")}</Pill><h1>{tr("Le prochain avantage")}<br/>{tr("se prépare ici.")}</h1><p>{tr("Votre effectif, votre académie, votre lecture du jeu.")}<br/>{tr("Tout l’atelier du manager, au même endroit.")}</p><img className="login-emblem" src="/images/brt-logo-192.png" alt={tr("Emblème Blackout Rugby Tools")}/></div><span>{tr("UN OUTIL INDÉPENDANT POUR LES PASSIONNÉS DE CLASSIC.")}</span></div>
    <div className="login-form"><div><LanguageSelect disabled={busy}/>
      {mode==='register'?<RegistrationForm onRegistered={onLogin} onCancel={()=>setMode('login')}/>:<>
        <span className="eyebrow">{tr("BIENVENUE DANS VOTRE ATELIER")}</span><h2>{tr("Entrez dans votre vestiaire.")}</h2><p>{tr("Créez votre compte ou connectez-vous pour préparer la suite avec BRT.")}</p>
        <form onSubmit={async e=>{e.preventDefault();setBusy(true);setErr('');try{await request('/login',{username,password,captcha_token:captchaToken||''});localStorage.setItem('brt-username',username);setPassword('');await onLogin()}catch(e){setErr((e as Error).message)}finally{setBusy(false);setCaptchaToken(null);setCaptchaReset(value=>value+1)}}}>
          <label>{tr("Identifiant")}<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>{tr("Mot de passe de l’outil")}<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{err&&<p className="text-error" role="alert">{tr(err)}</p>}<AntiBot action="login" onToken={setCaptchaToken} resetKey={captchaReset}/><button className="button primary" disabled={busy||captchaToken===null}>{tr(busy?'Connexion…':'Entrer dans l’atelier')}<ArrowRight size={17}/></button>
        </form>
        <div className="login-foot"><ShieldCheck size={17}/><span>{tr("Les accès à cet outil sont distincts de ceux du jeu Blackout Rugby.")}</span></div>
        {registration===true?<div className="login-signup"><p>{tr("Première visite ? Votre espace privé vous attend.")}</p><button className="button secondary" disabled={busy} onClick={()=>{setPassword('');setErr('');setMode('register')}}>{tr("Créer mon compte")}</button></div>:registration===false?<p className="tiny">{tr("Les inscriptions sont momentanément fermées. Contactez Pierig pour ouvrir votre espace.")}</p>:<p className="tiny">{tr("Vérification de l’ouverture des inscriptions indisponible. Rechargez la page ou contactez Pierig.")}</p>}
      </>}
      <PhotoCredits/>
    </div></div>
  </div>
}
