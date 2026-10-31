import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Check,Download,RefreshCw,Search} from 'lucide-react';
import {request,type Actions} from './App';
import {Pill} from './components';
import {tr} from './i18n';
import {useUnsavedChanges} from './navigation-guard';
import type {Match} from './types';
import './match-review.css';

type DirectPreview={match:Match;source_token:string;expected_revision:number;expected_source_digest:string|null};
type Fixture={id:string;type?:number;home?:string;away?:string;season?:number;round?:number;date?:string;home_score?:number|null;away_score?:number|null};

export function MatchDirect({d,act,busy,go,onImported}:Pick<Actions,'d'|'act'|'busy'|'go'>&{onImported:(match:Match)=>void}) {
  const [reference,setReference]=useState(''),[kind,setKind]=useState(d.current_team.kind==='u20'?1:d.current_team.kind==='nt'?2:0);
  const [fixtures,setFixtures]=useState<Fixture[]|null>(null),[preview,setPreview]=useState<DirectPreview|null>(null),[pending,setPending]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false),[message,setMessage]=useState('');
  const generation=useRef(0),working=useRef(false),scope=d.user.username+':'+d.csrf+':'+d.current_team.id,current=useRef(scope);current.current=scope;
  useEffect(()=>()=>{generation.current++},[]);
  useUnsavedChanges(pending||Boolean(preview));
  const disabled=busy||pending;
  const invalidate=()=>{generation.current++;setPreview(null);setError('');setConflict(false);setMessage('')};
  const run=async(operation:()=>Promise<void>)=>{
    if(busy||working.current)return;
    working.current=true;setPending(true);setError('');setMessage('');
    try{await operation()}catch(e){if(current.current===scope){setError((e as Error).message);setConflict((e as {status?:number}).status===409)}}finally{working.current=false;if(current.current===scope)setPending(false)}
  };
  const recent=()=>void run(async()=>{
    const ticket=++generation.current,result=await request('/matches/recent',{team_id:d.current_team.id},d.csrf);
    if(ticket===generation.current&&current.current===scope)setFixtures(result.fixtures??[]);
  });
  const inspect=(value=reference,type=kind)=>void run(async()=>{
    const ticket=++generation.current;
    setPreview(null);setConflict(false);
    const result=await request('/matches/direct/preview',{reference:value.trim(),type},d.csrf) as DirectPreview;
    if(ticket===generation.current&&current.current===scope)setPreview(result);
  });
  const confirm=()=>void run(async()=>{
    if(!preview)return;
    const ticket=++generation.current;
    const result=await act('/matches/direct/confirm',{source_token:preview.source_token,expected_revision:preview.expected_revision,expected_source_digest:preview.expected_source_digest},tr("Match importé"));
    if(ticket!==generation.current||current.current!==scope)return;
    setPreview(null);setConflict(false);setMessage(tr("Match ajouté à votre bibliothèque. Vous pouvez maintenant classer ses événements."));onImported(result.match);
  });
  const m=preview?.match;
  return <section className="card match-direct" aria-labelledby="match-direct-title">
    <div className="card-heading"><div><span className="eyebrow">{tr("DEPUIS BLACKOUT RUGBY CLASSIC")}</span><h2 id="match-direct-title">{tr("Importez un match, puis affinez sa lecture.")}</h2><p>{tr("Choisissez une rencontre récente ou collez son lien. Vérifiez l’aperçu avant de l’ajouter à votre bibliothèque privée.")}</p></div><Pill tone={d.classic_account?'green':'amber'}>{d.classic_account?tr("Compte Classic lié"):tr("Compte Classic à relier")}</Pill></div>
    {(!d.classic_account||!d.settings.developer_ready)&&<div className="notice"><span>{tr("Reliez votre compte Classic dans Connexion & données pour retrouver vos rencontres.")}</span><button className="text-button" disabled={disabled} onClick={()=>go('settings')}>{tr("Connexion & données")}<ArrowRight size={15}/></button></div>}
    <div className="match-direct-route"><div><h3>{tr("1. Retrouvez la rencontre")}</h3><p className="tiny">{tr('Rencontres de {club}',{club:d.current_team.name})}</p></div><button className="button secondary" disabled={disabled||!d.settings.developer_ready} onClick={recent}><RefreshCw size={16}/>{pending&&!preview?tr("Lecture en cours…"):tr("Afficher les rencontres récentes")}</button></div>
    {fixtures&&<div className="match-recent" aria-label={tr("Rencontres récentes")}>{fixtures.length?fixtures.map(f=><button className="match-recent-item" key={(f.type??kind)+':'+f.id} disabled={disabled} onClick={()=>{setReference(String(f.id));setKind(f.type??kind);inspect(String(f.id),f.type??kind)}}><strong>{f.home||tr("Équipe à domicile inconnue")} — {f.away||tr("Équipe à l’extérieur inconnue")}</strong><span>{tr('#{id} · S{season} / Tour {round}',{id:f.id,season:f.season??'—',round:f.round??'—'})}</span><span>{tr("Voir l’aperçu")}<ArrowRight size={14}/></span></button>):<p role="status">{tr("Aucune rencontre retournée. Vous pouvez aussi coller son identifiant ou son lien ci-dessous.")}</p>}</div>}
    <form className="match-reference-form" onSubmit={e=>{e.preventDefault();inspect()}}>
      <label>{tr("Lien officiel ou identifiant du match")}<input value={reference} onChange={e=>{setReference(e.target.value);invalidate()}} disabled={disabled} required maxLength={2000} placeholder={tr("Collez le lien du match ou son numéro")} autoComplete="off"/></label>
      <label>{tr("Type du match")}<select value={kind} disabled={disabled} onChange={e=>{setKind(Number(e.target.value));invalidate()}}><option value={0}>{tr("Club")}</option><option value={1}>{tr("U20")}</option><option value={2}>{tr("Sélection nationale")}</option></select></label>
      <button className="button primary" disabled={disabled||!reference.trim()||!d.settings.developer_ready}><Search size={16}/>{tr("Voir l’aperçu")}</button>
    </form>
    {error&&<p className="notice error" role="alert">{tr(error)}</p>}
    {conflict&&<div className="notice"><span>{tr("Le match a changé ou l’aperçu a expiré. Relisez un nouvel aperçu avant de confirmer.")}</span><button className="button secondary" disabled={disabled} onClick={()=>inspect()}>{tr("Réactualiser l’aperçu")}</button></div>}
    {m&&<section className="match-import-preview" aria-label={tr("Aperçu du match à importer")}>
      <div className="card-heading"><div><span className="eyebrow">{tr("2. VÉRIFIEZ LE MATCH")}</span><h3>{m.home} — {m.away}</h3><p>{tr('{type} · #{id} · Score fourni : {home} : {away}',{type:tr(['Club','U20','Sélection nationale'][m.type]),id:m.id,home:m.home_score??'—',away:m.away_score??'—'})}</p></div><Pill tone="neutral">{tr('{count} événements',{count:m.event_count??m.events?.length??0})}</Pill></div>
      <p>{tr('{classified} attaques exploitables · {unknown} événements à relire',{classified:m.summary.classified??0,unknown:m.summary.unclassified??0})}</p>
      <p className="tiny">{tr("Les estimations restent à vérifier. Les commentaires d’origine sont conservés ; aucune suggestion n’est validée automatiquement.")}</p>
      {preview.expected_source_digest!==null&&<p className="notice">{tr("Ce match est déjà présent. Les corrections des événements identiques sont conservées ; celles des événements disparus restent signalées à part.")}</p>}
      <div className="match-review-actions"><button className="button primary" disabled={disabled||conflict} onClick={confirm}><Download size={16}/>{pending?tr("Import en cours…"):tr("Confirmer l’import")}</button><button className="text-button" disabled={disabled} onClick={invalidate}>{tr("Annuler cet aperçu")}</button></div>
    </section>}
    {message&&<p className="notice success" role="status"><Check size={16}/>{message}</p>}
  </section>;
}
