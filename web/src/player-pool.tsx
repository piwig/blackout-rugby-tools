import {useEffect,useRef,useState} from 'react';
import {Bookmark,ChevronLeft,ChevronRight,RefreshCw,Search,Users} from 'lucide-react';
import {request,type Actions} from './App';
import {tr} from './i18n';
import {date,fmt,labels,skills,type Player,type State} from './types';
import {useNavigationGuard,useUnsavedChanges} from './navigation-guard';
import './player-pool.css';

export interface PoolDocument {revision:number;watch:boolean;text:string;updated_at:string|null}
export interface PoolObservation {snapshot_id:number;team_id:string;team_name:string;kind:'club'|'u20'|'nt';cohort:'academy'|'squad';archive:boolean;source:string;observed_at:string;first_source:string;first_observed_at:string;imported_at:string;game_date:{season:number;round:number;day:number}|null;availability:'healthy'|'injured'|'unknown';quality:'partial'|'complete';player:Player}
export interface PoolSummary {player_id:string;names:string[];nationalities:string[];ages:number[];positions:string[];observation_count:number;archive_count:number;conflicts:Record<string,unknown[]>;document:PoolDocument}
export interface PoolDetail extends PoolSummary {observations:PoolObservation[]}
export interface PoolList {players:PoolSummary[];total:number;offset:number;limit:number;position_options:string[];limits:{contexts:number;observations:number;page_size:number;payload_bytes:number;total_bytes:number}}

const fieldLabels:Record<string,string>={name:'Nom',age:'Âge',age_decimal:'Âge décimal',birthday:'Anniversaire',nationality:'Nationalité',dualnationality:'Double nationalité',capped_for:'Sélection représentée',height:'Taille',weight:'Poids',injured:'Blessure déclarée',energy:'Énergie',form:'Forme',csr:'CSR',salary:'Salaire',stars:'Étoiles',leadership:'Leadership',experience:'Expérience',aggression:'Agressivité',discipline:'Discipline',jersey:'Maillot',WC:'WC (source)',delta_csr:'Évolution CSR',...labels};
const availabilityLabel=(value:PoolObservation['availability'])=>tr(value==='healthy'?'Sans blessure déclarée':value==='injured'?'Blessure déclarée':'Disponibilité inconnue');
const known=(value:unknown)=>value===null||value===undefined||value===''?'—':fmt(value);

/** PlayerDetail edits current-team notes: never pass a different or older context. */
export function playerForCurrentContext(o:PoolObservation,d:State):Player|undefined{
  if(o.team_id!==d.current_team.id)return undefined;
  const source=o.cohort==='academy'?d.academy_source:d.squad_source;
  if(source?.id!==o.snapshot_id)return undefined;
  return (o.cohort==='academy'?d.academy:d.squad).find(player=>player.id===o.player.id);
}

export function PoolObservations({observations,conflicts,d,openPlayer}:{observations:PoolObservation[];conflicts:Record<string,unknown[]>;d:State;openPlayer:Actions['openPlayer']}){
  const fields=['age','nationality','dualnationality','birthday','capped_for','height','weight','energy','form','csr',...skills,...['age_decimal','injured','salary','stars','leadership','experience','aggression','discipline','jersey','WC','delta_csr'].filter(field=>observations.some(o=>o.player[field]!==undefined&&o.player[field]!==null&&o.player[field]!==''))];
  return <div className="pool-observations">
    <p className="notice">{tr('Chaque colonne conserve une observation entière. Des valeurs différentes peuvent refléter des dates ou des sources différentes ; aucune fusion automatique n’est effectuée.')}</p>
    <p className="tiny">{tr('L’âge et la nationalité ne confirment aucune éligibilité officielle. Le poste est une affinité estimée par BRT, calculée seulement avec les compétences nécessaires connues.')}</p>
    {Object.keys(conflicts).length>0&&<p className="pool-warning">{tr('Valeurs divergentes : {fields}',{fields:Object.keys(conflicts).map(field=>tr(fieldLabels[field]||field)).join(' · ')})}</p>}
    <div className="table-scroll pool-comparison" tabIndex={0} role="region" aria-label={tr('Comparaison des observations du joueur')}><table><caption className="sr-only">{tr('Sources conservées séparément')}</caption><thead><tr><th scope="col">{tr('Champ observé')}</th>{observations.map(o=><th scope="col" key={o.snapshot_id}>
      <strong>{o.team_name}</strong><small>{o.kind==='club'?tr('Club'):o.kind.toUpperCase()} · {tr(o.cohort==='academy'?'Académie':'Effectif')} · {o.team_id}</small>
      {o.archive&&<span className="pool-archive">{tr('Archive en pause')}</span>}
      <small>{tr('Observé le {date}',{date:date(o.observed_at)})}</small><small>{o.source}</small>
      <small>{tr('Première observation : {date}',{date:date(o.first_observed_at)})} · {o.first_source}</small>
      <small>{tr('Importé le {date}',{date:date(o.imported_at)})}</small>
      {o.game_date&&<small>{tr('Saison {season} · semaine {round} · jour {day}',o.game_date)}</small>}
    </th>)}</tr></thead><tbody>
      <tr><th scope="row">{tr('Nom')}</th>{observations.map(o=><td key={o.snapshot_id}>{o.player.name||'—'}</td>)}</tr>
      <tr><th scope="row">{tr('Disponibilité observée')}</th>{observations.map(o=><td key={o.snapshot_id}>{availabilityLabel(o.availability)}</td>)}</tr>
      {fields.map(field=><tr key={field} className={conflicts[field]?'pool-divergence':''}><th scope="row">{tr(fieldLabels[field]||field)}{conflicts[field]&&<span aria-label={tr('Valeurs divergentes')}> !</span>}</th>{observations.map(o=><td key={o.snapshot_id}>{known(o.player[field])}</td>)}</tr>)}
      <tr><th scope="row">{tr('Postes estimés')}</th>{observations.map(o=><td key={o.snapshot_id}>{o.player.metrics.roles.slice(0,3).map(r=><small key={r.name}>{tr(r.name)} · {fmt(r.score)}/21</small>)}{!o.player.metrics.roles.length&&'—'}</td>)}</tr>
      <tr><th scope="row">{tr('Compétences connues')}</th>{observations.map(o=><td key={o.snapshot_id}>{o.player.metrics.known_skills}/10</td>)}</tr>
      <tr><th scope="row">{tr('Fiche du joueur')}</th>{observations.map(o=>{const player=playerForCurrentContext(o,d);return <td key={o.snapshot_id}>{player?<button className="text-button" onClick={()=>openPlayer(player)}>{tr('Ouvrir la fiche de l’équipe sélectionnée')}</button>:<span className="tiny">{tr('Observation consultable dans ce tableau')}</span>}</td>})}</tr>
    </tbody></table></div>
    <p className="tiny">{tr('La disponibilité décrit la source à sa date d’observation. Une archive ancienne n’est pas une confirmation de la situation actuelle. Une valeur absente reste « — ».')}</p>
  </div>;
}

export function PoolNoteEditor({playerId,document,csrf,busy,onSaved}:{playerId:string;document:PoolDocument;csrf:string;busy:boolean;onSaved:(doc:PoolDocument)=>void}){
  const [baseline,setBaseline]=useState(document),[text,setText]=useState(document.text),[watch,setWatch]=useState(document.watch),[pending,setPending]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false),[server,setServer]=useState<PoolDocument|null>(null),[message,setMessage]=useState('');
  const mounted=useRef(true),sending=useRef(false);
  const dirty=text!==baseline.text||watch!==baseline.watch;
  useUnsavedChanges(dirty||pending);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
  useEffect(()=>{if(!dirty&&!pending&&document.revision>baseline.revision){setBaseline(document);setText(document.text);setWatch(document.watch)}},[document,dirty,pending,baseline.revision]);
  const save=async()=>{
    if(sending.current||busy||!dirty||conflict)return;
    sending.current=true;setPending(true);setError('');setMessage('');
    try{const next:PoolDocument=await request('/player-pool/'+encodeURIComponent(playerId),{expected_revision:baseline.revision,watch,text},csrf);if(mounted.current){setBaseline(next);setServer(null);setMessage('Note du vivier enregistrée.');onSaved(next)}}
    catch(e){if(mounted.current){setError((e as Error).message);setConflict((e as {status?:number}).status===409)}}
    finally{sending.current=false;if(mounted.current)setPending(false)}
  };
  const compare=async()=>{
    if(sending.current||busy)return;sending.current=true;setPending(true);setError('');
    try{const next:PoolDetail=await request('/player-pool/'+encodeURIComponent(playerId),undefined,csrf);if(mounted.current)setServer(next.document)}catch(e){if(mounted.current)setError((e as Error).message)}finally{sending.current=false;if(mounted.current)setPending(false)}
  };
  return <form className="pool-note" aria-label={tr('Note privée du vivier')} aria-busy={pending} onSubmit={e=>{e.preventDefault();void save()}}>
    <h4><Bookmark size={18}/>{tr('Votre suivi privé')}</h4><p className="tiny">{tr('Cette note et ce suivi appartiennent au vivier. Les notes de chaque club restent indépendantes.')}</p>
    <label>{tr('Note privée du vivier')}<textarea rows={4} maxLength={3000} value={text} disabled={pending} onChange={e=>{setText(e.target.value);setMessage('')}}/></label>
    <label className="check"><input type="checkbox" checked={watch} disabled={pending} onChange={e=>{setWatch(e.target.checked);setMessage('')}}/>{tr('Garder dans ma liste de suivi')}</label>
    {error&&<p className="notice error" role="alert">{tr(error)}</p>}
    {conflict&&<button type="button" className="button secondary" disabled={pending||busy} onClick={()=>void compare()}>{tr('Comparer la note enregistrée')}</button>}
    {server&&<div className="pool-conflict"><h4>{tr('Version enregistrée · révision {revision}',{revision:server.revision})}</h4><p className="pool-note-text">{server.text||'—'}</p><p>{tr(server.watch?'Dans la liste de suivi':'Hors de la liste de suivi')}</p>
      <button type="button" className="button secondary" disabled={pending||busy} onClick={()=>{setBaseline(server);setText(server.text);setWatch(server.watch);setConflict(false);setServer(null);setError('')}}>{tr('Utiliser la version enregistrée')}</button>
      <button type="button" className="button secondary" disabled={pending||busy} onClick={()=>{setBaseline(server);setConflict(false);setServer(null);setError('')}}>{tr('Conserver mon brouillon sur cette révision')}</button>
    </div>}
    <div className="pool-note-actions"><button className="button primary" disabled={pending||busy||!dirty||conflict}>{tr(pending?'Enregistrement en cours…':'Enregistrer la note du vivier')}</button><span className="tiny" role="status">{message?tr(message):dirty?tr('Modifications non enregistrées.'):tr('Révision {revision}',{revision:baseline.revision})}</span></div>
  </form>;
}

export function PlayerPool(props:Actions){return <PoolPanel key={props.d.user.username+':'+props.d.csrf+':'+props.d.current_team.id} {...props}/>}

export function PoolPanel({d,busy,openPlayer}:Actions){
  const {confirmLeave}=useNavigationGuard();
  const [filters,setFilters]=useState({q:'',nationality:'',age_min:'',age_max:'',position:'',availability:'',quality:'',watch:false}),[offset,setOffset]=useState(0),[reload,setReload]=useState(0),[bundle,setBundle]=useState<PoolList|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[selected,setSelected]=useState('');
  const params=new URLSearchParams({q:filters.q,nationality:filters.nationality,position:filters.position,availability:filters.availability,quality:filters.quality,watch:String(filters.watch),offset:String(offset),limit:'25'});
  if(filters.age_min)params.set('age_min',filters.age_min);if(filters.age_max)params.set('age_max',filters.age_max);
  const query=params.toString();
  useEffect(()=>{let active=true;setLoading(true);setError('');request('/player-pool?'+query,undefined,d.csrf).then((next:PoolList)=>{if(active){const last=Math.max(0,Math.ceil(next.total/25)-1)*25;if(offset>last)setOffset(last);else setBundle(next)}}).catch((e:Error)=>{if(active){setError(e.message);setBundle(null)}}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[query,reload,d.csrf]);
  const filter=(key:keyof typeof filters,value:string|boolean)=>{setFilters(previous=>({...previous,[key]:value}));setOffset(0)};
  const invalidAge=filters.age_min!==''&&filters.age_max!==''&&Number(filters.age_min)>Number(filters.age_max);
  return <section className="card pool-panel" aria-label={tr('Vivier de joueurs')}>
    <div className="card-heading"><div><span className="eyebrow">{tr('LE CARNET DU RECRUTEUR')}</span><h2><Users size={24}/>{tr('Votre vivier privé')}</h2><p>{tr('Retrouvez les joueurs observés dans vos clubs, académies et sélections, avec chaque source et sa date.')}</p></div><button className="button secondary" disabled={busy||loading} onClick={()=>setReload(n=>n+1)}><RefreshCw size={16}/>{tr('Relire le vivier')}</button></div>
    <div className="pool-body"><p className="notice">{tr('Le vivier utilise les derniers effectifs enregistrés de chaque équipe et cohorte. Les sélections en pause restent visibles comme archives. Les filtres portent sur une même observation, sans recomposer un joueur à partir de sources différentes.')}</p>
      <div className="pool-filters">
        <label><span><Search size={15}/>{tr('Rechercher un joueur')}</span><input type="search" maxLength={120} value={filters.q} onChange={e=>filter('q',e.target.value)} placeholder={tr('Nom ou identifiant')}/></label>
        <label>{tr('Nationalité')}<input value={filters.nationality} maxLength={100} onChange={e=>filter('nationality',e.target.value)} placeholder={tr('Code ou valeur de la source')}/></label>
        <label>{tr('Âge minimum')}<input type="number" min={0} max={100} step="any" value={filters.age_min} onChange={e=>filter('age_min',e.target.value)}/></label>
        <label>{tr('Âge maximum')}<input type="number" min={0} max={100} step="any" value={filters.age_max} onChange={e=>filter('age_max',e.target.value)}/></label>
        <label>{tr('Poste estimé')}<select value={filters.position} onChange={e=>filter('position',e.target.value)}><option value="">{tr('Tous les postes')}</option>{bundle?.position_options.map(role=><option key={role} value={role}>{tr(role)}</option>)}</select></label>
        <label>{tr('Disponibilité observée')}<select value={filters.availability} onChange={e=>filter('availability',e.target.value)}><option value="">{tr('Toutes les disponibilités')}</option><option value="healthy">{tr('Sans blessure déclarée')}</option><option value="injured">{tr('Blessure déclarée')}</option><option value="unknown">{tr('Disponibilité inconnue')}</option></select></label>
        <label>{tr('Qualité des données')}<select value={filters.quality} onChange={e=>filter('quality',e.target.value)}><option value="">{tr('Toutes les observations')}</option><option value="partial">{tr('Données partielles')}</option><option value="complete">{tr('Dix compétences, âge et nationalité connus')}</option><option value="conflicting">{tr('Valeurs divergentes')}</option></select></label>
        <label className="check"><input type="checkbox" checked={filters.watch} onChange={e=>filter('watch',e.target.checked)}/>{tr('Ma liste de suivi')}</label>
      </div>
      {invalidAge&&<p role="alert" className="notice error">{tr('L’âge minimum doit être inférieur ou égal à l’âge maximum.')}</p>}
      {error&&<p role="alert" className="notice error">{tr(error)}</p>}{loading&&<p role="status">{tr('Lecture du vivier…')}</p>}
      {!loading&&bundle&&<>
        <div className="pool-result-heading"><h3>{tr(bundle.total===1?'{count} joueur dans cette recherche':'{count} joueurs dans cette recherche',{count:bundle.total})}</h3><span className="tiny">{tr('25 joueurs par page')}</span></div>
        {bundle.players.length?<div className="pool-results">{bundle.players.map(player=><article className={selected===player.player_id?'pool-player selected':'pool-player'} key={player.player_id}>
          <div><span className="eyebrow">#{player.player_id} {player.document.watch&&<Bookmark size={14} aria-label={tr('Dans la liste de suivi')}/>}</span><h4>{player.names.join(' / ')||tr('Joueur #{id}',{id:player.player_id})}</h4><p>{player.nationalities.join(' / ')||'—'} · {player.ages.map(age=>fmt(age)).join(' / ')||'—'} {tr('ans')}</p><p className="tiny">{player.positions.map(role=>tr(role)).join(' · ')||tr('Poste inconnu')}</p></div>
          <div className="pool-source-count"><span>{tr(player.observation_count===1?'{count} observation':'{count} observations',{count:player.observation_count})}</span>{player.archive_count>0&&<span className="pool-archive">{tr(player.archive_count===1?'{count} archive en pause':'{count} archives en pause',{count:player.archive_count})}</span>}{Object.keys(player.conflicts).length>0&&<span className="pool-warning">{tr('Valeurs divergentes')}</span>}</div>
          <button className="button secondary" aria-expanded={selected===player.player_id} disabled={busy} onClick={()=>{if(selected!==player.player_id&&confirmLeave())setSelected(player.player_id)}}>{tr('Comparer et suivre')}</button>
        </article>)}</div>:<div className="pool-empty"><Users size={30}/><p>{tr('Aucun joueur observé ne correspond à ces filtres.')}</p><p className="tiny">{tr('Importez un effectif ou ajustez les filtres pour commencer votre vivier.')}</p></div>}
        <nav className="pool-pagination" aria-label={tr('Pagination du vivier')}><span>{tr('{from}–{to} sur {count}',{from:bundle.total?Math.min(offset+1,bundle.total):0,to:Math.min(offset+25,bundle.total),count:bundle.total})}</span><button className="button secondary" disabled={busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}><ChevronLeft size={16}/>{tr('Précédent')}</button><button className="button secondary" disabled={busy||offset+25>=bundle.total} onClick={()=>setOffset(offset+25)}>{tr('Suivant')}<ChevronRight size={16}/></button></nav>
        <p className="tiny">{tr('Plafonds : {contexts} contextes, {observations} observations. Une lecture dépassant ces limites est refusée sans troncature.',bundle.limits)}</p>
      </>}
      {selected&&<PoolSelected key={selected} playerId={selected} d={d} busy={busy} openPlayer={openPlayer} reload={reload} onSaved={()=>setReload(n=>n+1)}/>}
    </div>
  </section>;
}

function PoolSelected({playerId,d,busy,openPlayer,onSaved,reload}:{playerId:string;d:State;busy:boolean;openPlayer:Actions['openPlayer'];onSaved:()=>void;reload:number}){
  const [detail,setDetail]=useState<PoolDetail|null>(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;setError('');request('/player-pool/'+encodeURIComponent(playerId),undefined,d.csrf).then((next:PoolDetail)=>{if(active)setDetail(next)}).catch((e:Error)=>{if(active)setError(e.message)});return()=>{active=false}},[playerId,d.csrf,reload]);
  return <section className="pool-selected" aria-label={tr('Dossier privé du joueur')}>
    {error&&<p role="alert" className="notice error">{tr(error)}</p>}{!detail&&!error&&<p role="status">{tr('Lecture des observations…')}</p>}
    {detail&&<><h3>{detail.names.join(' / ')||tr('Joueur #{id}',{id:playerId})} <small>#{playerId}</small></h3><PoolNoteEditor playerId={playerId} document={detail.document} csrf={d.csrf} busy={busy} onSaved={document=>{setDetail(previous=>previous?{...previous,document}:previous);onSaved()}}/><PoolObservations observations={detail.observations} conflicts={detail.conflicts} d={d} openPlayer={openPlayer}/></>}
  </section>;
}
