import {useCallback, useEffect, useRef, useState} from 'react';
import {ArrowDown, ArrowUp, Check, CheckCircle2, Mail, Monitor, RefreshCw, Save, Shield, ShieldCheck, Shirt, Trophy, UserRound} from 'lucide-react';
import {request, type Actions} from './App';
import {rugbyClubs} from './rugby-clubs';
import './profile.css';

export const dashboardSections = ['priorities', 'metrics', 'progress', 'talents', 'actions', 'gallery'] as const;
export type DashboardSection = typeof dashboardSections[number];
export type FavoriteClub = 'none'|'toulouse'|'larochelle'|'leinster'|'racing92'|'toulon'|'clermont'|'munster'|'crusaders';
export type AvatarStyle = 'jersey'|'shield'|'trophy'|'rugby';
export const avatarChoices:{id:AvatarStyle;label:string}[] = [{id:'jersey',label:'Maillot'},{id:'shield',label:'Blason'},{id:'trophy',label:'Trophée'},{id:'rugby',label:'Rugby BRT'}];
export type ProfilePreferences = {
  display_name:string;initials:string;jersey_number:number;favorite_club:FavoriteClub;avatar_style:AvatarStyle;
  density:'comfortable'|'compact';text_size:'normal'|'large';motion:'system'|'reduced';
  start_page:'home'|'progression'|'academy'|'squad'|'season';banner:'matchday'|'clubhouse';
  dashboard_sections:DashboardSection[];
};
export type ProfileDocument = {revision:number;profile:ProfilePreferences;updated_at:string|null};
export const defaultProfile:ProfilePreferences = {
  display_name:'',initials:'BRT',jersey_number:15,favorite_club:'none',avatar_style:'jersey',density:'comfortable',
  text_size:'normal',motion:'system',start_page:'home',banner:'matchday',
  dashboard_sections:[...dashboardSections],
};
const sectionNames:Record<DashboardSection,string> = {priorities:'Priorités du jour',metrics:'Repères du club',progress:'Progression dans le temps',talents:'Talents à suivre',actions:'Prochaines étapes',gallery:'Inspirations rugby'};
const pageNames:Record<ProfilePreferences['start_page'],string> = {home:'Tableau de bord',progression:'Progression',academy:'Académie',squad:'Effectif & XV',season:'Saison & calendrier'};
const fieldNames:Record<keyof ProfilePreferences,string> = {display_name:'Nom affiché',initials:'Initiales',jersey_number:'Numéro de maillot',favorite_club:'Club favori',avatar_style:'Avatar',density:'Densité',text_size:'Taille du texte',motion:'Mouvements',start_page:'Page de départ',banner:'Bannière',dashboard_sections:'Rubriques d’accueil'};
const errorText = (error:unknown) => error instanceof Error ? error.message : 'Le profil n’a pas pu être chargé. Réessayez.';
const profileEqual = (left:ProfilePreferences,right:ProfilePreferences) => JSON.stringify(left)===JSON.stringify(right);
const updatedLabel = (value:string|null) => value ? new Date(value).toLocaleString('fr-FR',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : 'Réglages par défaut';

/** Pass username + CSRF to isolate reads across managers and replacement sessions. */
export function useProfile(scope:string|null) {
  const [state,setState]=useState<{scope:string|null;doc:ProfileDocument|null;error:string;loading:boolean}>({scope:null,doc:null,error:'',loading:false});
  const current=useRef(scope),mounted=useRef(false),ticket=useRef(0);current.current=scope;
  const reload=useCallback(async():Promise<ProfileDocument|null>=>{
    if(!scope)return null;
    const id=++ticket.current;
    setState(previous=>({scope,doc:previous.scope===scope?previous.doc:null,error:'',loading:true}));
    try {
      const document=await request('/profile') as ProfileDocument;
      if(mounted.current&&current.current===scope&&ticket.current===id){setState({scope,doc:document,error:'',loading:false});return document}
    } catch(error) {
      if(mounted.current&&current.current===scope&&ticket.current===id)setState(previous=>({...previous,scope,error:errorText(error),loading:false}));
    }
    return null;
  },[scope]);
  const accept=useCallback((document:ProfileDocument,capturedScope=scope)=>{
    if(mounted.current&&scope&&current.current===scope&&capturedScope===scope){ticket.current++;setState({scope,doc:document,error:'',loading:false})}
  },[scope]);
  useEffect(()=>{
    mounted.current=true;setState({scope,doc:null,error:'',loading:Boolean(scope)});
    if(scope)void reload();
    return()=>{mounted.current=false;ticket.current++};
  },[scope,reload]);
  const visible=state.scope===scope;
  return {doc:visible?state.doc:null,error:visible?state.error:'',loading:visible?state.loading:Boolean(scope),reload,accept};
}

export function ProfileAvatar({profile,username,small=false}:{profile?:ProfilePreferences|null;username:string;small?:boolean}) {
  const club=rugbyClubs.find(item=>item.id===profile?.favorite_club);
  const initials=profile?.initials||username.slice(0,2).toLocaleUpperCase('fr-FR')||'BRT';
  const number=profile?Number.isFinite(profile.jersey_number)?profile.jersey_number:'—':15;
  const style=profile?.avatar_style||'jersey',Icon=style==='shield'?Shield:style==='trophy'?Trophy:Shirt;
  return <span className={'profile-avatar'+(small?' small':'')} data-avatar={style} data-club={club?.id} role="img" aria-label={(profile?.display_name||username)+' · '+(avatarChoices.find(item=>item.id===style)?.label||'Maillot')+' · numéro '+number+(club?' · '+club.name:'')}>
    {style==='rugby'?<img className="profile-avatar-brt" src="/images/brt-logo-192.png" alt=""/>:<><Icon className="profile-avatar-shirt" aria-hidden="true"/><strong aria-hidden="true">{initials}</strong><small aria-hidden="true">{number}</small></>}
    {club&&<img className="profile-avatar-club" src={club.logo} alt=""/>}
  </span>;
}

export function AvatarChoices({value,onChange,profile=defaultProfile,name='avatar-style'}:{value:AvatarStyle;onChange:(style:AvatarStyle)=>void;profile?:ProfilePreferences;name?:string}) {
  return <div className="profile-avatars">{avatarChoices.map(choice=><label key={choice.id} className={'profile-avatar-choice'+(value===choice.id?' selected':'')}><input type="radio" name={name} value={choice.id} checked={value===choice.id} onChange={()=>onChange(choice.id)}/><ProfileAvatar profile={{...profile,avatar_style:choice.id}} username="Manager"/><strong>{choice.label}</strong></label>)}</div>;
}

function PrivateContact() {
  const [contact,setContact]=useState<{email:string|null}|null>(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;request('/account/contact').then(value=>{if(active)setContact(value)}).catch(()=>{if(active)setError('L’adresse d’inscription n’a pas pu être chargée.')});return()=>{active=false}},[]);
  return <div className="profile-contact"><Mail size={17} aria-hidden="true"/><div><strong>Adresse d’inscription privée</strong><p>{error||(!contact?'Chargement…':contact.email||'Aucune adresse renseignée pour ce compte.')}</p></div></div>;
}

export function ProfileSettings({d,act,busy,onSaved}:Actions&{onSaved:(document:ProfileDocument)=>void}) {
  const scope=d.user.username+':'+d.csrf,resource=useProfile(scope),current=useRef(scope);current.current=scope;
  const accept=(document:ProfileDocument)=>{if(current.current===scope){resource.accept(document,scope);onSaved(document)}};
  return <section className="profile-settings" aria-labelledby="profile-heading">
    <div className="profile-intro"><div><span className="eyebrow">VOTRE ESPACE, VOS REPÈRES</span><h2 id="profile-heading">Un atelier à votre image.</h2><p>Votre profil et vos préférences d’affichage vous suivent dans votre espace privé.</p></div><span className="profile-private"><ShieldCheck size={17}/> Profil privé</span></div>
    <PrivateContact key={scope}/>
    {resource.error&&<div className="notice error" role="alert"><span>{resource.error}</span><button type="button" className="button secondary" disabled={resource.loading} onClick={()=>void resource.reload()}><RefreshCw size={16}/>Réessayer</button></div>}
    {!resource.doc&&resource.loading&&<p role="status">Chargement de votre profil…</p>}
    {resource.doc&&<ProfileEditor key={scope} document={resource.doc} username={d.user.username} act={act} busy={busy} onSaved={accept} reload={resource.reload}/>}
  </section>;
}

function ProfileEditor({document,username,act,busy,onSaved,reload}:{document:ProfileDocument;username:string;act:Actions['act'];busy:boolean;onSaved:(document:ProfileDocument)=>void;reload:()=>Promise<ProfileDocument|null>}) {
  const [base,setBase]=useState(document),[form,setForm]=useState<ProfilePreferences>(document.profile);
  const [error,setError]=useState(''),[saved,setSaved]=useState(false),[saving,setSaving]=useState(false),[conflict,setConflict]=useState(false),[latest,setLatest]=useState<ProfileDocument|null>(null),[comparing,setComparing]=useState(false);
  const mounted=useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
  const dirty=!profileEqual(form,base.profile),club=rugbyClubs.find(item=>item.id===form.favorite_club);
  const locked=busy||saving||comparing;
  const change=<K extends keyof ProfilePreferences>(key:K,value:ProfilePreferences[K])=>{setForm(previous=>({...previous,[key]:value}));setSaved(false)};
  const loadLatest=async()=>{
    setComparing(true);
    const result=await reload();
    if(mounted.current){setLatest(result);setComparing(false)}
  };
  const submit=async()=>{
    if(locked||conflict||!dirty)return;
    setSaving(true);setError('');setSaved(false);
    try {
      const result=await act('/profile',{expected_revision:base.revision,profile:form},'Profil et affichage enregistrés') as ProfileDocument;
      if(mounted.current){setBase(result);setForm(result.profile);setLatest(null);setSaved(true);onSaved(result)}
    } catch(caught) {
      if(mounted.current){
        setError(errorText(caught));
        if((caught as {status?:number}).status===409){setConflict(true);await loadLatest()}
      }
    } finally {if(mounted.current)setSaving(false)}
  };
  const toggleSection=(section:DashboardSection)=>change('dashboard_sections',form.dashboard_sections.includes(section)?form.dashboard_sections.filter(item=>item!==section):[...form.dashboard_sections,section]);
  const moveSection=(section:DashboardSection,offset:number)=>{
    const items=[...form.dashboard_sections],index=items.indexOf(section),next=index+offset;
    if(index<0||next<0||next>=items.length)return;
    [items[index],items[next]]=[items[next],items[index]];change('dashboard_sections',items);
  };
  const comparedFields=latest?(Object.keys(fieldNames) as (keyof ProfilePreferences)[]).filter(key=>JSON.stringify(form[key])!==JSON.stringify(latest.profile[key])):[];
  const fieldValue=(profile:ProfilePreferences,key:keyof ProfilePreferences):string=>{
    if(key==='dashboard_sections')return profile.dashboard_sections.map(item=>sectionNames[item]).join(', ')||'Aucune rubrique';
    if(key==='favorite_club')return rugbyClubs.find(item=>item.id===profile.favorite_club)?.name||'Aucun';
    if(key==='avatar_style')return avatarChoices.find(item=>item.id===profile.avatar_style)?.label||'Maillot';
    if(key==='start_page')return pageNames[profile.start_page];
    const labels:Record<string,string>={comfortable:'Confortable',compact:'Compacte',normal:'Normale',large:'Grande',system:'Selon mon appareil',reduced:'Réduits',matchday:'Jour de match',clubhouse:'Vie du club'};
    const value=profile[key];
    return labels[String(value)]||String(value===''?'Non renseigné':value);
  };
  return <form className="profile-form" onSubmit={event=>{event.preventDefault();void submit()}}>
    <div className="profile-grid">
      <aside className="card profile-preview"><span className="eyebrow">APERÇU DU MANAGER</span><ProfileAvatar profile={form} username={username}/><h3>{form.display_name.trim()||username}</h3><p>@{username}</p><span className="profile-preview-number">Maillot n° {Number.isFinite(form.jersey_number)?form.jersey_number:'—'}</span>{club&&<div className="profile-favorite-preview" data-club={club.id}><img src={club.logo} alt=""/><span>Club de cœur<strong>{club.name}</strong></span></div>}<span className="profile-preview-note">Visible dans votre atelier privé.</span></aside>
      <fieldset className="card profile-panel" disabled={locked}><legend><UserRound size={19}/> Mon profil</legend><div className="profile-fields"><label className="profile-wide">Nom affiché<input autoComplete="nickname" maxLength={60} value={form.display_name} placeholder={username} onChange={event=>change('display_name',event.target.value)}/><small>Votre identifiant de connexion reste @{username}.</small></label><label>Initiales<input required maxLength={3} pattern="[A-Z0-9À-ÖØ-Þ]{1,3}" value={form.initials} onChange={event=>change('initials',event.target.value.toLocaleUpperCase('fr-FR'))}/><small>1 à 3 lettres ou chiffres.</small></label><label>Numéro de maillot<input required type="number" inputMode="numeric" min={0} max={99} step={1} value={Number.isFinite(form.jersey_number)?form.jersey_number:''} onChange={event=>change('jersey_number',event.target.valueAsNumber)}/><small>De 0 à 99.</small></label></div></fieldset>
    </div>
    <fieldset className="card profile-panel" disabled={locked}><legend><UserRound size={19}/> Mon avatar</legend><p>Choisissez votre emblème. Votre club de cœur reste un repère distinct.</p><AvatarChoices value={form.avatar_style} onChange={style=>change('avatar_style',style)} profile={form}/></fieldset>
    <fieldset className="card profile-panel" disabled={locked}><legend><Shirt size={19}/> Mon club de cœur</legend><p>Choisissez un grand club pour accompagner votre avatar.</p><div className="profile-clubs"><label className={'profile-club'+(form.favorite_club==='none'?' selected':'')}><input type="radio" name="favorite-club" value="none" checked={form.favorite_club==='none'} onChange={()=>change('favorite_club','none')}/><span className="profile-no-club"><Shirt size={27}/></span><strong>Aucun club</strong>{form.favorite_club==='none'&&<Check size={15} className="profile-choice-check" aria-hidden="true"/>}</label>{rugbyClubs.map(item=><label className={'profile-club'+(form.favorite_club===item.id?' selected':'')} data-club={item.id} key={item.id}><input type="radio" name="favorite-club" value={item.id} checked={form.favorite_club===item.id} onChange={()=>change('favorite_club',item.id as FavoriteClub)}/><img src={item.logo} alt="" loading="lazy"/><strong>{item.shortName}</strong>{form.favorite_club===item.id&&<Check size={15} className="profile-choice-check" aria-hidden="true"/>}</label>)}</div><p className="profile-credit">Les marques restent celles de leurs clubs respectifs. BRT est un outil indépendant.{club&&<> <a href={club.source} target="_blank" rel="noreferrer">Source du logo de {club.name}</a>.</>}</p></fieldset>
    <fieldset className="card profile-panel" disabled={locked}><legend><Monitor size={19}/> Mon affichage</legend><p>Ces réglages s’appliquent après enregistrement.</p><div className="profile-fields"><label>Densité<select value={form.density} onChange={event=>change('density',event.target.value as ProfilePreferences['density'])}><option value="comfortable">Confortable · plus d’espace</option><option value="compact">Compacte · plus de repères à l’écran</option></select></label><label>Taille du texte<select value={form.text_size} onChange={event=>change('text_size',event.target.value as ProfilePreferences['text_size'])}><option value="normal">Normale</option><option value="large">Grande</option></select></label><label>Mouvements<select value={form.motion} onChange={event=>change('motion',event.target.value as ProfilePreferences['motion'])}><option value="system">Suivre les préférences de mon appareil</option><option value="reduced">Réduire les mouvements</option></select></label><label>Page après connexion<select value={form.start_page} onChange={event=>change('start_page',event.target.value as ProfilePreferences['start_page'])}>{Object.entries(pageNames).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><label>Bannière d’accueil<select value={form.banner} onChange={event=>change('banner',event.target.value as ProfilePreferences['banner'])}><option value="matchday">Jour de match</option><option value="clubhouse">Vie du club</option></select></label></div></fieldset>
    <fieldset className="card profile-panel" disabled={locked}><legend>Mes rubriques d’accueil</legend><p>Affichez vos repères utiles et choisissez leur ordre avec les flèches.</p><ol className="profile-sections">{[...form.dashboard_sections,...dashboardSections.filter(item=>!form.dashboard_sections.includes(item))].map(section=>{
      const index=form.dashboard_sections.indexOf(section),enabled=index>=0;
      return <li key={section} className={enabled?'':'profile-section-hidden'}><label><input type="checkbox" checked={enabled} onChange={()=>toggleSection(section)}/><span>{sectionNames[section]}<small>{enabled?'Position '+(index+1):'Masquée sur l’accueil'}</small></span></label><div className="profile-reorder"><button type="button" className="icon-button" disabled={!enabled||index===0} aria-label={'Monter « '+sectionNames[section]+' »'} onClick={()=>moveSection(section,-1)}><ArrowUp size={18}/></button><button type="button" className="icon-button" disabled={!enabled||index===form.dashboard_sections.length-1} aria-label={'Descendre « '+sectionNames[section]+' »'} onClick={()=>moveSection(section,1)}><ArrowDown size={18}/></button></div></li>;
    })}</ol>{form.dashboard_sections.length===0&&<p className="profile-empty-hint">Votre accueil affichera la bannière et les accès principaux. Toutes les rubriques restent accessibles depuis le menu.</p>}</fieldset>
    {error&&!conflict&&<p className="notice error" role="alert">{error}</p>}
    {conflict&&<section className="profile-conflict" role="alert" aria-labelledby="profile-conflict-title"><h3 id="profile-conflict-title">Une autre version a été enregistrée.</h3><p>Votre brouillon est conservé ci-dessus. Comparez les changements avant de choisir la version à garder.</p>{comparing?<p role="status">Lecture de la version enregistrée…</p>:latest?<><div className="profile-comparison">{comparedFields.length?<dl>{comparedFields.map(key=><div key={key}><dt>{fieldNames[key]}</dt><dd><span>Enregistré</span>{fieldValue(latest.profile,key)}</dd><dd><span>Votre brouillon</span>{fieldValue(form,key)}</dd></div>)}</dl>:<p>Votre brouillon correspond déjà à la version enregistrée.</p>}</div><div className="profile-buttons"><button className="button secondary" type="button" disabled={locked} onClick={()=>{setBase(latest);setForm(latest.profile);setConflict(false);setError('');setSaved(false);onSaved(latest)}}>Utiliser la version enregistrée</button><button className="button secondary" type="button" disabled={locked} onClick={()=>{setBase(latest);setConflict(false);setError('');setSaved(false)}}>Garder mon brouillon pour l’enregistrer</button></div></>:<button type="button" className="button secondary" disabled={locked} onClick={()=>void loadLatest()}><RefreshCw size={16}/>Relire la version enregistrée</button>}</section>}
    <div className="profile-save"><div role="status" aria-live="polite">{saved?<><CheckCircle2 size={18}/><span>Profil enregistré.</span></>:dirty?<span>Modifications à enregistrer</span>:<span>{base.updated_at?'Dernière sauvegarde : ':''}{updatedLabel(base.updated_at)}</span>}</div><div className="profile-buttons"><button className="button secondary" type="button" disabled={locked||!dirty||conflict} onClick={()=>{setForm(base.profile);setError('');setSaved(false)}}>Annuler les modifications</button><button className="button primary" disabled={locked||!dirty||conflict||!Number.isInteger(form.jersey_number)}><Save size={16}/>{saving?'Enregistrement…':'Enregistrer mon profil'}</button></div></div>
  </form>;
}
