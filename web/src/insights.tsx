import {localeTag,tr} from './i18n';
import {useEffect, useReducer, useRef, useState} from 'react';
import {BookOpen, Plus, RefreshCw, Save, Sprout, Trash2} from 'lucide-react';
import {request, type Actions} from './App';
import {date, fmt, labels, skills} from './types';
import {useUnsavedChanges} from './navigation-guard';
import './insights.css';

type Props = Pick<Actions, 'd' | 'act' | 'busy'>;
type Goal = {player_id:string; text:string; skill:string|null; target:number|null; due_season:number|null};
type Session = {id:string; season:number; week:number; slot:number; skill:string; performed_at:string; note:string};
type PlannedSlot = {season:number; week:number; slot:number; skill:string; declared:boolean};
type Link = {match_id:string; match_type:number; club_side:'home'|'away'; opponent:string; season:number|null};
const categories = [['standing','Debout'],['uncovered','Assis découvert'],['covered','Assis couvert'],['members','Abonnés'],['corporate','Loges']] as const;
type Category = typeof categories[number][0];
type Values = Record<Category, number|null>;
type Scenario = {id:string; name:string; current:Values; target:Values; unit_costs:Values; treasury:number|null; reserve:number|null; note:string};
type Doc = {version:1; revision:number; updated_at:string|null; goals:Goal[]; sessions:Session[]; match_links:Link[]; stadium_scenarios:Scenario[]};
type Progress = {player_id:string; name:string; skill:string; before:number|null; after:number; delta:number|null; kind:string; observed_at:string; source:string; values?:(number|null)[]};
type GenerationPlayer = {id:string; name:string; age:number|null; goal:Goal|null; current_value:number|null; target_gap:number|null};
type Academy = {generations:Record<string,GenerationPlayer[]>; timeline:Progress[]; snapshot_count:number; history_truncated:boolean; undated_snapshots:number; stale_goal_ids:string[]; sessions:(Session&{comparison:string; provenance:string; planned_skill:string|null})[]; planned_slots:PlannedSlot[]; planned_count:number; unrecorded_count:number; latest_training_observation:string[]};
type Opponents = {match_count:number; total_events:number; classified:number; inferred:number; opponent_actions:number; attacks:Record<string,number>; zones:Record<string,number>; zone_attacks:Record<string,Record<string,number>>; coverage_pct:number|null; unlinked_count:number; missing_matches:number; matches:(Link&{home:string; away:string; total_events:number; classified:number; opponent_actions:number})[]};
type Stadium = {id:string; name:string; construction_cost:number|null; remaining_available:number|null; known_subtotal:number; missing_categories:Category[]; reduction_categories:Category[]; target_capacity:number|null};
type Bundle = {team_id:string; document:Doc; academy:Academy; opponents:Opponents; stadium:Stadium[]};
const optionalNumber = (value:string) => value === '' ? null : Number(value);
const uuid = () => crypto.randomUUID();

function useInsights(d:Props['d']) {
  const [bundle,setBundle] = useState<Bundle|null>(null);
  const [error,setError] = useState('');
  const [message,setMessage] = useState('');
  const [pending,setPending] = useState(false);
  const live = useRef(true), operation = useRef(false), sequence = useRef(0);
  const path = '/insights/' + d.current_team.id;
  const reload = async () => {
    const serial = ++sequence.current;
    try {
      const result = await request(path) as Bundle;
      if(live.current && serial === sequence.current) {setBundle(result);setError('');}
    } catch(e) {if(live.current && serial === sequence.current)setError((e as Error).message);}
  };
  useEffect(() => {live.current=true;void reload();return () => {live.current=false;sequence.current++;};}, [path]);
  useEffect(() => {void reload();}, [d.academy_source?.id, JSON.stringify(d.plans), JSON.stringify(d.matches)]);
  const save = async (changes:Partial<Doc>) => {
    if(!bundle || operation.current)return false;
    operation.current=true;setPending(true);setError('');setMessage('');
    const {revision,updated_at,...document}=bundle.document;
    try {
      await request(path,{expected_revision:revision,document:{...document,...changes}},d.csrf);
      if(live.current){await reload();setMessage('Suivi enregistré dans votre espace privé.');}
      return true;
    } catch(e) {if(live.current)setError((e as Error).message);return false;}
    finally {operation.current=false;if(live.current)setPending(false);}
  };
  return {bundle,error,message,pending,save,reload};
}

function Status({model}:{model:ReturnType<typeof useInsights>}) {
  return <>{model.error&&<div className="notice error" role="alert">{tr(model.error)}<button className="text-button" disabled={model.pending} onClick={()=>void model.reload()}><RefreshCw size={15}/>{tr("Recharger les suivis")}</button></div>}{model.message&&<p className="insights-status" role="status">{tr(model.message)}</p>}{!model.bundle&&!model.error&&<p role="status">{tr("Chargement des suivis privés…")}</p>}</>;
}

type SessionDraft = {season:string; week:string; slot:string; skill:string; performed:string; note:string};
type SessionDraftState = {draft:SessionDraft; baseline:SessionDraft};
type SessionDraftAction = {type:'edit'|'saved'|'reset'; draft:SessionDraft};
const blankSessionDraft = (season:string):SessionDraft => ({season,week:'1',slot:'1',skill:'strength',performed:'',note:''});

export function plannedSessionDraft(slot:PlannedSlot):SessionDraft {
  return {season:String(slot.season),week:String(slot.week),slot:String(slot.slot),skill:slot.skill,performed:'',note:''};
}

export function validateSessionDate(value:string,latest=Date.now()):{performedAt:string|null;error:string} {
  const performed=new Date(value);
  if(!value.trim()||!Number.isFinite(performed.getTime()))return {performedAt:null,error:'Renseignez une date réelle valide (date et heure), puis réessayez. Aucune séance n’a été enregistrée.'};
  if(performed.getTime()>latest)return {performedAt:null,error:'La date réelle ne peut pas être dans le futur. Indiquez la date et l’heure auxquelles la séance a eu lieu. Aucune séance n’a été enregistrée.'};
  return {performedAt:performed.toISOString(),error:''};
}

export function sessionDraftReducer(state:SessionDraftState, action:SessionDraftAction):SessionDraftState {
  if(action.type==='reset')return {draft:action.draft,baseline:action.draft};
  if(action.type==='saved')return {...state,baseline:action.draft};
  return {...state,draft:action.draft};
}

function TrainingDeclaration({model,season}:{model:ReturnType<typeof useInsights>;season:string}) {
  const {bundle,pending,save}=model;
  const [state,dispatch]=useReducer(sessionDraftReducer,season,value=>{
    const draft=blankSessionDraft(value);return {draft,baseline:draft};
  });
  const draft=state.draft, dirty=JSON.stringify(draft)!==JSON.stringify(state.baseline);
  const [planSeason,setPlanSeason]=useState(''),[planWeek,setPlanWeek]=useState('');
  const [dateError,setDateError]=useState('');
  const performedInput=useRef<HTMLInputElement>(null);
  useUnsavedChanges(dirty||pending);
  if(!bundle)return null;
  const planned=bundle.academy.planned_slots;
  const seasonSlots=planned.filter(item=>!planSeason||item.season===Number(planSeason));
  const slots=seasonSlots.filter(item=>!planWeek||item.week===Number(planWeek));
  const update=(key:keyof SessionDraft,value:string)=>{
    if(key==='performed')setDateError('');
    dispatch({type:'edit',draft:{...draft,[key]:value}});
  };
  const canReplace=()=>!pending&&(!dirty||window.confirm('Abandonner les modifications de cette déclaration ?'));
  const choose=(item:PlannedSlot)=>{
    if(!canReplace())return;
    setDateError('');
    dispatch({type:'edit',draft:plannedSessionDraft(item)});
    performedInput.current?.focus();
  };
  const submit=async()=>{
    if(pending)return;
    const submitted={...draft};
    const {performedAt,error}=validateSessionDate(submitted.performed);
    if(!performedAt){
      setDateError(error);
      performedInput.current?.focus();
      return;
    }
    setDateError('');
    const existing=bundle.document.sessions.find(item=>item.season===Number(submitted.season)&&item.week===Number(submitted.week)&&item.slot===Number(submitted.slot));
    const session={id:existing?.id||uuid(),season:Number(submitted.season),week:Number(submitted.week),slot:Number(submitted.slot),skill:submitted.skill,performed_at:performedAt,note:submitted.note};
    if(await save({sessions:[...bundle.document.sessions.filter(item=>item.id!==existing?.id),session]}))dispatch({type:'saved',draft:submitted});
  };
  return <div className="insights-training">
    <h3>{tr("Partir d’un créneau planifié")}</h3>
    <p className="muted">{tr("Choisissez une case renseignée du planning, puis indiquez la date réelle et vérifiez la compétence réalisée. Le planning ne prouve pas qu’une séance a eu lieu.")}</p>
    <div className="insights-grid">
      <label>{tr("Saison du planning")}<select value={planSeason} onChange={e=>{setPlanSeason(e.target.value);setPlanWeek('');}}><option value="">{tr("Toutes les saisons")}</option>{[...new Set(planned.map(item=>item.season))].map(value=><option key={value}>{value}</option>)}</select></label>
      <label>{tr("Semaine du planning")}<select value={planWeek} onChange={e=>setPlanWeek(e.target.value)}><option value="">{tr("Toutes les semaines")}</option>{[...new Set(seasonSlots.map(item=>item.week))].sort((a,b)=>a-b).map(value=><option key={value}>{value}</option>)}</select></label>
    </div>
    {slots.length?<ul className="insights-planned-slots">{slots.map(item=><li key={`${item.season}:${item.week}:${item.slot}`}>
      <div><strong>{tr("S")}{item.season}{tr(" · semaine ")}{item.week}{tr(" · créneau ")}{item.slot}</strong><span>{tr(labels[item.skill])} · {item.declared?tr("Déjà déclaré"):tr("Sans déclaration")}</span></div>
      <button className="button secondary" type="button" disabled={pending} onClick={()=>choose(item)} aria-label={`${item.declared?'Corriger':'Déclarer'} la séance saison ${item.season} semaine ${item.week} créneau ${item.slot}`}>{item.declared?tr("Corriger la déclaration"):tr("Déclarer la séance")}</button>
    </li>)}</ul>:<p className="muted">{tr("Aucun créneau renseigné pour ce filtre. Vous pouvez compléter le planning ou déclarer une séance manuellement ci-dessous.")}</p>}
    <form className="insights-form" onSubmit={e=>{e.preventDefault();void submit();}} aria-busy={pending}>
      <h3>{tr("Déclarer ou corriger un créneau réalisé")}</h3>
      {dateError&&<p className="notice error" role="alert">{dateError}</p>}
      <fieldset disabled={pending} className="insights-session-fields"><legend className="sr-only">{tr("Déclaration manuelle d’une séance réalisée")}</legend><div className="insights-grid">
        <label>{tr("Saison")}<input required type="number" min="1" max="999" value={draft.season} onChange={e=>update('season',e.target.value)}/></label>
        <label>{tr("Semaine")}<input required type="number" min="1" max="16" value={draft.week} onChange={e=>update('week',e.target.value)}/></label>
        <label>{tr("Créneau")}<input required type="number" min="1" max="4" value={draft.slot} onChange={e=>update('slot',e.target.value)}/></label>
        <label>{tr("Compétence réalisée")}<select value={draft.skill} onChange={e=>update('skill',e.target.value)}>{skills.map(value=><option key={value} value={value}>{tr(labels[value])}</option>)}</select></label>
        <label>{tr("Date réelle (heure locale)")}<input ref={performedInput} required type="datetime-local" aria-invalid={Boolean(dateError)} value={draft.performed} onChange={e=>update('performed',e.target.value)}/></label>
        <label>{tr("Source / note manuelle")}<input maxLength={1000} value={draft.note} onChange={e=>update('note',e.target.value)}/></label>
      </div><div className="insights-actions"><button className="button secondary"><Save size={16}/>{pending?tr("Enregistrement…"):tr("Enregistrer ce créneau réalisé")}</button><button className="text-button" type="button" disabled={!dirty} onClick={()=>{if(canReplace()){setDateError('');dispatch({type:'reset',draft:blankSessionDraft(season)});}}}>{tr("Annuler la saisie")}</button></div></fieldset>
      <p className="tiny">{tr("Une nouvelle déclaration pour la même saison, semaine et créneau remplace la précédente. La date réelle est obligatoire et reste vide lors du choix d’un créneau. Aucun entraînement n’est envoyé dans Classic.")}</p>
    </form>
  </div>;
}

const attackNames=['Percussion','Pick and go','Large','Créatif','Jeu au pied'];
const zoneNames=['22','40','40A','22A'];
export function zoneAttackValue(count:number,total:number):string {
  return total ? `${count} · ${new Intl.NumberFormat(localeTag(),{maximumFractionDigits:1}).format(100*count/total)} %` : '—';
}

export function ZoneAttackMatrix({matrix}:{matrix:Record<string,Record<string,number>>}) {
  return <div className="table-scroll insights-zone-scroll" role="region" aria-label={tr("Matrice des attaques adverses par zone")} tabIndex={0}><table className="insights-zone-matrix">
    <caption>{tr("Attaques par zone relative à l’adversaire. Chaque cellule indique le nombre et le pourcentage parmi les actions adverses classées de cette zone. Une zone vide ne permet aucune tendance.")}</caption>
    <thead><tr><th scope="col">{tr("Zone")}</th>{attackNames.map(name=><th key={name} scope="col">{tr(name)}</th>)}<th scope="col">{tr("Actions classées de la zone")}</th></tr></thead>
    <tbody>{zoneNames.map(zone=>{
      const counts=matrix[zone], total=attackNames.reduce((sum,name)=>sum+(counts?.[name]||0),0);
      return <tr key={zone}><th scope="row">{zone}</th>{attackNames.map(name=><td key={name}>{zoneAttackValue(counts?.[name]||0,total)}</td>)}<td>{total>0?<><strong>{total}</strong>{tr(" actions")}</>:<span className="insights-empty-zone">{tr("Aucune observation")}</span>}</td></tr>;
    })}</tbody>
  </table></div>;
}

export function AcademyInsights(props:Props) {return <AcademyPanel key={props.d.current_team.id} {...props}/>;}
function AcademyPanel({d}:Props) {
  const model=useInsights(d), {bundle,save,pending}=model;
  const [generation,setGeneration]=useState('all'),[playerId,setPlayerId]=useState(''),[text,setText]=useState(''),[skill,setSkill]=useState(''),[target,setTarget]=useState(''),[due,setDue]=useState('');
  const choosePlayer=(id:string)=>{setPlayerId(id);const goal=bundle?.document.goals.find(g=>g.player_id===id);setText(goal?.text||'');setSkill(goal?.skill||'');setTarget(goal?.target==null?'':String(goal.target));setDue(goal?.due_season==null?'':String(goal.due_season));};
  const report=bundle?.academy;
  const players=report?Object.entries(report.generations).filter(([key])=>generation==='all'||generation===key).flatMap(([,rows])=>rows):[];
  const timeline=report?.timeline.filter(event=>!playerId||event.player_id===playerId)||[];
  return <section className="card insights-card" aria-label={tr("Objectifs et suivi de l’académie")}>
    <div className="card-heading"><div><span className="eyebrow">{tr("ACADÉMIE / U20")}</span><h2><Sprout size={21}/>{tr("Chaque jeune, un objectif.")}</h2></div><span className="insights-tag">{tr("Suivi privé")}</span></div>
    <div className="insights-body"><Status model={model}/>{bundle&&report&&<>
      <p className="muted">{tr("Générations selon le repère personnel de Franck. Un dévoilement révèle une valeur ; seule la comparaison de deux valeurs numériques décrit une variation, sans en attribuer la cause.")}</p>
      <label className="insights-filter">{tr("Liste par génération")}<select value={generation} onChange={e=>setGeneration(e.target.value)}><option value="all">{tr("Toutes les générations (")}{d.academy.length})</option>{Object.entries(report.generations).map(([key,rows])=><option key={key} value={key}>{key==='unknown'?tr("Génération non déterminée"):tr("Saison ")+key} ({rows.length})</option>)}</select></label>
      <div className="insights-player-list">{players.length?players.map(p=><button type="button" className={'insights-player '+(playerId===p.id?'selected':'')} key={p.id} onClick={()=>choosePlayer(p.id)}><strong>{p.name}</strong><small>{p.age==null?tr("Âge inconnu"):p.age+tr(" ans")} · {p.goal?.text||tr("Objectif à définir")}</small>{p.goal?.skill&&<small>{tr(labels[p.goal.skill])} : {fmt(p.current_value)} → {fmt(p.goal.target)}{p.target_gap!==null?tr(" · écart ")+fmt(p.target_gap):''}</small>}</button>):<p className="muted">{tr("Aucun jeune observé dans cette génération.")}</p>}</div>
      <form className="insights-form" onSubmit={e=>{e.preventDefault();if(!playerId)return;void save({goals:[...bundle.document.goals.filter(g=>g.player_id!==playerId),{player_id:playerId,text,skill:skill||null,target:skill?optionalNumber(target):null,due_season:optionalNumber(due)}]});}}>
        <h3>{tr("Objectif individuel")}</h3><div className="insights-grid"><label>{tr("Jeune")}<select required value={playerId} onChange={e=>choosePlayer(e.target.value)}><option value="">{tr("Choisir un jeune")}</option>{d.academy.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label>{tr("Compétence ciblée")}<select value={skill} onChange={e=>setSkill(e.target.value)}><option value="">{tr("Objectif général")}</option>{skills.map(s=><option key={s} value={s}>{tr(labels[s])}</option>)}</select></label><label>{tr("Valeur cible (facultative)")}<input disabled={!skill} type="number" min="0" max="21" step="0.1" value={target} onChange={e=>setTarget(e.target.value)}/></label><label>{tr("Échéance, saison (facultative)")}<input type="number" min="1" max="999" value={due} onChange={e=>setDue(e.target.value)}/></label></div><label>{tr("Objectif et points à vérifier")}<textarea required maxLength={1000} value={text} onChange={e=>setText(e.target.value)} placeholder={tr("Ex. Dévoiler la défense puis comparer son profil au poste de centre.")}/></label><div className="insights-actions"><button className="button primary" disabled={pending||!playerId}><Save size={16}/>{tr("Enregistrer l’objectif")}</button>{bundle.document.goals.some(g=>g.player_id===playerId)&&<button className="text-button" type="button" disabled={pending} onClick={()=>void save({goals:bundle.document.goals.filter(g=>g.player_id!==playerId)}).then(ok=>{if(ok){setText('');setSkill('');setTarget('');setDue('');}})}>{tr("Retirer cet objectif")}</button>}</div>
      </form>
      {report.stale_goal_ids.length>0&&<div className="notice">{report.stale_goal_ids.length}{tr(" objectif(s) conservé(s) pour des jeunes absents du dernier effectif.")}{bundle.document.goals.filter(g=>report.stale_goal_ids.includes(g.player_id)).map(g=><p key={g.player_id}>#{g.player_id} · {g.text} <button className="text-button" disabled={pending} onClick={()=>void save({goals:bundle.document.goals.filter(x=>x.player_id!==g.player_id)})}>{tr("Retirer")}</button></p>)}</div>}
      <details className="insights-details" open><summary>{tr("Évolutions datées · ")}{report.snapshot_count}{tr(" observations")}{playerId?tr(" · joueur sélectionné"):''}</summary>{playerId&&<button className="text-button" onClick={()=>choosePlayer('')}>{tr("Voir tous les jeunes")}</button>}{report.history_truncated&&<p className="notice">{tr("Historique limité aux observations récentes et aux 500 dernières variations retenues. Les lots trop volumineux ou incomplets sont exclus ; aucune évolution n’est calculée à travers une lacune.")}</p>}{report.undated_snapshots>0&&<p className="notice">{report.undated_snapshots}{tr(" observation(s) sans date exploitable exclue(s) de la comparaison.")}</p>}{timeline.length?<div className="table-scroll insights-history"><table><thead><tr><th>{tr("Date et source")}</th><th>{tr("Jeune / compétence")}</th><th>{tr("Observation")}</th></tr></thead><tbody>{[...timeline].reverse().map((event,i)=><tr key={i}><td>{date(event.observed_at)}<small className="sub-cell">{event.source}</small></td><td>{event.name}<small className="sub-cell">{tr(labels[event.skill])}</small></td><td>{event.kind==='conflicting_observation'?<><span className="insights-tag">{tr("Observations contradictoires")}</span> {(event.values||[event.before,event.after]).map(value=>fmt(value)).join(' / ')}{tr(" · même date, aucun progrès calculé")}</>:event.kind==='revealed'?<><span className="insights-tag">{tr("Dévoilement")}</span> ? → {fmt(event.after)}</>:<><span className="insights-tag">{tr("Variation numérique")}</span> {fmt(event.before)} → {fmt(event.after)} ({(event.delta||0)>0?'+':''}{fmt(event.delta)})</>}</td></tr>)}</tbody></table></div>:<p className="muted">{tr("Pas encore de changement comparable. Deux observations datées sont nécessaires.")}</p>}</details>
      <details className="insights-details"><summary>{tr("Séances planifiées et réalisées")}</summary><p>{report.planned_count}{tr(" créneaux planifiés · ")}{report.sessions.length}{tr(" déclarations manuelles · ")}{report.unrecorded_count}{tr(" créneaux sans déclaration. L’absence de déclaration ne prouve pas l’absence d’entraînement.")}</p><p className="muted">{tr("Dernier export : ")}{report.latest_training_observation.length?report.latest_training_observation.map(s=>labels[s]||'Non renseigné').join(' · '):tr("aucune séance renseignée")}{tr(". Cette dernière observation n’est pas un historique.")}</p>
        <TrainingDeclaration model={model} season={String(d.game_date?.season||'')}/>
        {report.sessions.length>0&&<div className="table-scroll"><table><thead><tr><th>{tr("Créneau")}</th><th>{tr("Date déclarée")}</th><th>{tr("Prévu → réalisé")}</th><th>{tr("Rapprochement")}</th><th>{tr("Action")}</th></tr></thead><tbody>{report.sessions.map(s=><tr key={s.id}><td>{tr("S")}{s.season}{tr(" · sem. ")}{s.week} · {s.slot}</td><td>{date(s.performed_at)}<small className="sub-cell">{tr("Déclaration manuelle · ")}{s.note||tr("sans note")}</small></td><td>{s.planned_skill?labels[s.planned_skill]:tr("Sans plan")} → {tr(labels[s.skill])}</td><td>{{matches_plan:'Conforme au plan actuel',differs_from_plan:'Différent du plan actuel',unplanned:'Non planifié'}[s.comparison]}</td><td><button className="icon-button" aria-label={tr("Retirer la déclaration saison ")+s.season+tr(" semaine ")+s.week+tr(" créneau ")+s.slot} disabled={pending} onClick={()=>void save({sessions:bundle.document.sessions.filter(item=>item.id!==s.id)})}><Trash2 size={16}/></button></td></tr>)}</tbody></table></div>}
      </details>
    </>}</div>
  </section>;
}

export function OpponentInsights(props:Props) {return <OpponentPanel key={props.d.current_team.id} {...props}/>;}
function OpponentPanel({d}:Props) {
  const model=useInsights(d),{bundle,save,pending}=model;
  const [matchKey,setMatchKey]=useState(''),[side,setSide]=useState(''),[opponent,setOpponent]=useState(''),[season,setSeason]=useState('');
  const [filterOpponent,setFilterOpponent]=useState(''),[filterSeason,setFilterSeason]=useState(''),[filterType,setFilterType]=useState(''),[filterSide,setFilterSide]=useState('');
  const [filtered,setFiltered]=useState<Opponents|null>(null),[filterError,setFilterError]=useState('');
  useEffect(()=>{
    let active=true;setFiltered(null);setFilterError('');
    const query=new URLSearchParams();if(filterOpponent)query.set('opponent',filterOpponent);if(filterSeason)query.set('season',filterSeason);if(filterType)query.set('match_type',filterType);if(filterSide)query.set('club_side',filterSide);
    request('/insights/'+d.current_team.id+'/opponents?'+query.toString()).then(value=>{if(active)setFiltered(value);}).catch(e=>{if(active)setFilterError((e as Error).message);});
    return()=>{active=false;};
  },[d.current_team.id,bundle?.document.revision,filterOpponent,filterSeason,filterType,filterSide,JSON.stringify(d.matches)]);
  const chooseMatch=(key:string)=>{setMatchKey(key);const link=bundle?.document.match_links.find(m=>m.match_type+':'+m.match_id===key);setSide(link?.club_side||'');setOpponent(link?.opponent||'');setSeason(link?.season==null?'':String(link.season));};
  return <section className="card insights-card" aria-label={tr("Dossiers adversaires")}><div className="card-heading"><div><span className="eyebrow">{tr("PRÉPARER UNE RENCONTRE")}</span><h2><BookOpen size={21}/>{tr("Les dossiers adversaires")}</h2></div><span className="insights-tag">{tr("Plusieurs matchs, mêmes repères")}</span></div><div className="insights-body"><Status model={model}/>{bundle&&<>
    <p className="muted">{tr("Rattachez explicitement chaque rencontre à ")}{d.current_team.name}{tr(", à son côté et à l’adversaire. La bibliothèque est commune à vos clubs privés : aucun rattachement n’est deviné.")}</p>
    <form className="insights-form" onSubmit={e=>{e.preventDefault();const [type,id]=matchKey.split(':');void save({match_links:[...bundle.document.match_links.filter(m=>!(m.match_type===Number(type)&&m.match_id===id)),{match_id:id,match_type:Number(type),club_side:side as 'home'|'away',opponent,season:optionalNumber(season)}]});}}><div className="insights-grid"><label>{tr("Rencontre de la bibliothèque")}<select required value={matchKey} onChange={e=>chooseMatch(e.target.value)}><option value="">{tr("Choisir une rencontre")}</option>{d.matches.map(m=><option key={m.type+':'+m.id} value={m.type+':'+m.id}>{['Club','U20','NT'][m.type]} #{m.id} · {m.home} / {m.away}</option>)}</select></label><label>{tr("Côté de ")}{d.current_team.name}<select required value={side} onChange={e=>setSide(e.target.value)}><option value="">{tr("Choisir explicitement")}</option><option value="home">{tr("Domicile")}</option><option value="away">{tr("Extérieur")}</option></select></label><label>{tr("Nom du dossier adversaire")}<input required maxLength={150} value={opponent} onChange={e=>setOpponent(e.target.value)} placeholder={tr("Même nom pour regrouper ses matchs")}/></label><label>{tr("Saison (facultative)")}<input type="number" min="1" max="999" value={season} onChange={e=>setSeason(e.target.value)}/></label></div><button className="button primary" disabled={pending||!d.matches.length}><Plus size={16}/>{tr("Enregistrer le rattachement")}</button></form>
    {!d.matches.length&&<p className="muted">{tr("Importez d’abord une rencontre dans la bibliothèque ci-dessus.")}</p>}
    <div className="insights-grid insights-filters"><label>{tr("Adversaire")}<select value={filterOpponent} onChange={e=>setFilterOpponent(e.target.value)}><option value="">{tr("Tous les dossiers")}</option>{[...new Set(bundle.document.match_links.map(m=>m.opponent))].sort().map(name=><option key={name}>{name}</option>)}</select></label><label>{tr("Saison")}<select value={filterSeason} onChange={e=>setFilterSeason(e.target.value)}><option value="">{tr("Toutes les saisons")}</option>{[...new Set(bundle.document.match_links.map(m=>m.season).filter(s=>s!==null))].sort((a,b)=>a-b).map(s=><option key={s}>{s}</option>)}</select></label><label>{tr("Type")}<select value={filterType} onChange={e=>setFilterType(e.target.value)}><option value="">{tr("Tous")}</option><option value="0">{tr("Club")}</option><option value="1">{tr("U20")}</option><option value="2">{tr("NT")}</option></select></label><label>{tr("Côté du club")}<select value={filterSide} onChange={e=>setFilterSide(e.target.value)}><option value="">{tr("Tous")}</option><option value="home">{tr("Domicile")}</option><option value="away">{tr("Extérieur")}</option></select></label></div>
    {filterError&&<p role="alert" className="notice error">{filterError}</p>}{!filtered&&!filterError&&<p role="status">{tr("Calcul des volumes filtrés…")}</p>}{filtered&&<><div className="insights-summary"><div><strong>{filtered.match_count}</strong><span>{tr("rencontre(s) du filtre")}</span></div><div><strong>{filtered.classified} / {filtered.total_events}</strong><span>{tr("événements classés, deux côtés · ")}{fmt(filtered.coverage_pct)} %</span></div><div><strong>{filtered.opponent_actions}</strong><span>{tr("actions de l’adversaire classées")}</span></div><div><strong>{filtered.inferred}</strong><span>{tr("événements inférés des commentaires")}</span></div></div><p className="tiny">{filtered.unlinked_count}{tr(" rencontre(s) de la bibliothèque sans rattachement à ce club. Les pourcentages ci-dessous portent uniquement sur les actions adverses classées ; la couverture porte sur tous les événements des matchs retenus. Aucun pronostic n’en est déduit.")}</p>{filtered.missing_matches>0&&<p className="notice">{filtered.missing_matches}{tr(" rencontre(s) rattachée(s) ne sont plus dans la bibliothèque.")}</p>}{filtered.match_count>0?<><div className="insights-comparison"><div><h3>{tr("Types d’attaque adverses")}</h3>{Object.entries(filtered.attacks).map(([name,count])=><div className="insights-bar" key={name}><span>{tr(name)}</span><div><i style={{width:(filtered.opponent_actions?100*count/filtered.opponent_actions:0)+'%'}}/></div><b>{count} / {filtered.opponent_actions}</b></div>)}</div><div><h3>{tr("Zones relatives à l’adversaire")}</h3>{Object.entries(filtered.zones).map(([zone,count])=><div className="insights-bar" key={zone}><span>{zone}</span><div><i style={{width:(filtered.opponent_actions?100*count/filtered.opponent_actions:0)+'%'}}/></div><b>{count} / {filtered.opponent_actions}</b></div>)}</div></div><ZoneAttackMatrix matrix={filtered.zone_attacks}/><div className="table-scroll"><table><thead><tr><th>{tr("Rencontre")}</th><th>{tr("Dossier")}</th><th>{tr("Club / saison")}</th><th>{tr("Couverture")}</th><th>{tr("Action")}</th></tr></thead><tbody>{filtered.matches.map(m=><tr key={m.match_type+':'+m.match_id}><td>{['Club','U20','NT'][m.match_type]} #{m.match_id}<small className="sub-cell">{m.home} / {m.away}</small></td><td>{m.opponent}</td><td>{m.club_side==='home'?tr("Domicile"):tr("Extérieur")} · {m.season===null?tr("saison inconnue"):tr("S")+m.season}</td><td>{m.classified} / {m.total_events}</td><td><button className="text-button" disabled={pending} onClick={()=>void save({match_links:bundle.document.match_links.filter(link=>!(link.match_type===m.match_type&&link.match_id===m.match_id))})}>{tr("Détacher")}</button></td></tr>)}</tbody></table></div></>:<p className="muted">{tr("Aucune rencontre rattachée ne correspond au filtre. Ajoutez un rattachement ou élargissez les filtres.")}</p>}</>}
  </>}</div></section>;
}

const blankValues=():Values=>({standing:null,uncovered:null,covered:null,members:null,corporate:null});
const stadiumMaximumTotal=2_564_103;
const stadiumRatios=[22,39,30,8,1];

export function stadiumCapacityTarget(value:string):{target:Record<Category,number>|null;error:string} {
  const total=Number(value);
  if(!/^\d+$/.test(value.trim())||!Number.isSafeInteger(total)||total<0||total>stadiumMaximumTotal)
    return {target:null,error:'Saisissez une capacité totale entière entre 0 et 2 564 103 places.'};
  const parts=categories.map(([key],index)=>({key,index,seats:Math.floor(total*stadiumRatios[index]/100),remainder:total*stadiumRatios[index]%100}));
  const remaining=total-parts.reduce((sum,part)=>sum+part.seats,0);
  const ranked=[...parts].sort((a,b)=>b.remainder-a.remainder||a.index-b.index);
  for(let index=0;index<remaining;index++)ranked[index].seats++;
  return {target:Object.fromEntries(parts.map(part=>[part.key,part.seats])) as Record<Category,number>,error:''};
}

type StadiumObservation = Pick<Scenario,'current'|'treasury'>;
type StadiumDraftState = {draft:Scenario;observation:StadiumObservation;dirty:boolean;stale:boolean};
type StadiumDraftAction = {type:'observe';observation:StadiumObservation}|{type:'edit';draft:Scenario}|{type:'replace';draft:Scenario;observation:StadiumObservation;dirty:boolean}|{type:'use_latest'};
const sameObservation=(a:StadiumObservation,b:StadiumObservation)=>a.treasury===b.treasury&&categories.every(([key])=>a.current[key]===b.current[key]);

export function stadiumDraftReducer(state:StadiumDraftState,action:StadiumDraftAction):StadiumDraftState {
  if(action.type==='edit')return {...state,draft:action.draft,dirty:true,stale:state.stale&&!sameObservation(action.draft,state.observation)};
  if(action.type==='replace')return {draft:action.draft,observation:action.observation,dirty:action.dirty,stale:action.dirty&&!sameObservation(action.draft,action.observation)};
  if(action.type==='use_latest')return {...state,draft:{...state.draft,current:{...state.observation.current},treasury:state.observation.treasury},stale:false};
  if(sameObservation(state.observation,action.observation))return state;
  return state.dirty?{...state,observation:action.observation,stale:!sameObservation(state.draft,action.observation)}:
    {...state,observation:action.observation,draft:{...state.draft,current:{...action.observation.current},treasury:action.observation.treasury},stale:false};
}

function stadiumObservation(d:Props['d']):StadiumObservation {
  const current=blankValues();
  for(const [key] of categories){const raw=d.current_team.meta['stadium_'+key];if(raw!==null&&raw!==undefined&&raw!==''&&Number.isInteger(Number(raw))&&Number(raw)>=0)current[key]=Number(raw);}
  const raw=d.current_team.meta.bank_balance;
  return {current,treasury:raw!==null&&raw!==undefined&&raw!==''&&Number.isFinite(Number(raw))&&Number(raw)>=0?Number(raw):null};
}
function initialScenario(d:Props['d']):Scenario {
  return {id:uuid(),name:'',...stadiumObservation(d),target:blankValues(),unit_costs:blankValues(),reserve:null,note:''};
}

export function StadiumScenarios(props:Props) {return <StadiumPanel key={props.d.current_team.id} {...props}/>;}
function StadiumPanel({d}:Props) {
  const model=useInsights(d),{bundle,save,pending}=model;
  const [draftState,dispatch]=useReducer(stadiumDraftReducer,d,value=>({draft:initialScenario(value),observation:stadiumObservation(value),dirty:false,stale:false}));
  const [capacityTotal,setCapacityTotal]=useState(''),[capacityMessage,setCapacityMessage]=useState('');
  const distribution=stadiumCapacityTarget(capacityTotal);
  const draft=draftState.draft,observation=stadiumObservation(d),observationKey=JSON.stringify(observation);
  useEffect(()=>{dispatch({type:'observe',observation})},[observationKey]);
  const setDraft=(value:Scenario)=>dispatch({type:'edit',draft:value});
  const clearCapacity=()=>{setCapacityTotal('');setCapacityMessage('');};
  const resetDraft=()=>{dispatch({type:'replace',draft:initialScenario(d),observation,dirty:false});clearCapacity();};
  const [compare,setCompare]=useState<string[]>([]);
  const select=(id:string)=>{const saved=bundle?.document.stadium_scenarios.find(s=>s.id===id);if(saved){dispatch({type:'replace',draft:structuredClone(saved),observation,dirty:true});clearCapacity();}else resetDraft();};
  const setValue=(group:'current'|'target'|'unit_costs',key:Category,value:string)=>setDraft({...draft,[group]:{...draft[group],[key]:optionalNumber(value)}});
  const rows=bundle?.stadium.filter(s=>compare.length===0||compare.includes(s.id))||[];
  return <section className="card insights-card" aria-label={tr("Scénarios financiers du stade")}><div className="card-heading"><div><span className="eyebrow">{tr("STADE / FINANCEMENT")}</span><h2>{tr("Nommer, chiffrer, comparer.")}</h2></div><span className="insights-tag">{tr("Monnaie virtuelle")}</span></div><div className="insights-body"><Status model={model}/>{bundle&&<>
    <p className="muted">{tr("Les capacités et la trésorerie d’un nouveau scénario suivent la dernière observation tant que vous ne le modifiez pas. Les scénarios enregistrés conservent leurs valeurs. Renseignez les cibles, les coûts unitaires du jeu et votre réserve. Une case vide reste inconnue ; aucun tarif n’est proposé.")}</p>
    {draftState.stale&&<div className="notice" role="status"><p>{tr("Les capacités ou la trésorerie de ce scénario diffèrent de la dernière observation du club. Vos choix ont été conservés.")}</p><button className="button secondary" disabled={pending} onClick={()=>dispatch({type:'use_latest'})}><RefreshCw size={16}/>{tr("Reprendre la dernière observation")}</button><p className="tiny">{tr("Actualise uniquement les capacités actuelles et la trésorerie ; conserve vos cibles, tarifs, réserve et notes.")}</p></div>}
    <div className="insights-actions"><label>{tr("Scénario")}<select value={bundle.document.stadium_scenarios.some(s=>s.id===draft.id)?draft.id:''} onChange={e=>select(e.target.value)}><option value="">{tr("Nouveau scénario")}</option>{bundle.document.stadium_scenarios.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><button className="button secondary" onClick={resetDraft}><Plus size={16}/>{tr("Nouveau scénario")}</button></div>
    <div className="insights-distribution">
      <h3>{tr("Répartir une capacité totale")}</h3>
      <p className="muted">{tr("Reprenez les proportions du modèle de Franck : 22 / 39 / 30 / 8 / 1 %. Saisissez la capacité totale souhaitée, puis remplacez explicitement les cinq cibles du scénario ci-dessous. Les places entières conservent exactement votre total.")}</p>
      <div className="insights-actions"><label>{tr("Capacité totale souhaitée")}<input type="number" min="0" max={stadiumMaximumTotal} step="1" placeholder={tr("À renseigner")} value={capacityTotal} aria-invalid={capacityTotal!==''&&Boolean(distribution.error)} onChange={e=>{setCapacityTotal(e.target.value);setCapacityMessage('');}}/></label><button type="button" className="button secondary" disabled={pending||!distribution.target} onClick={()=>{if(distribution.target){setDraft({...draft,target:{...distribution.target}});setCapacityMessage('Les cinq capacités cibles ont été remplacées dans le brouillon. Enregistrez le scénario pour le conserver.');}}}>{tr("Remplacer les cinq capacités cibles")}</button></div>
      {capacityTotal!==''&&distribution.error&&<p className="notice error" role="alert">{distribution.error}</p>}
      {distribution.target&&<ul className="insights-distribution-preview" aria-label={tr("Aperçu de la répartition")}>{categories.map(([key,label],index)=><li key={key}><span>{tr(label)} · {stadiumRatios[index]} %</span><strong>{fmt(distribution.target![key])}{tr(" places")}</strong></li>)}</ul>}
      {capacityMessage&&<p className="insights-status" role="status">{capacityMessage}</p>}
      <p className="tiny">{tr("Ce bouton modifie uniquement les cibles du brouillon. Vérifiez les tarifs et frais du devis réel dans Classic, puis renseignez les coûts et la réserve ci-dessous. Les montants sont virtuels ; aucun travail de construction n’est lancé.")}</p>
    </div>
    <form className="insights-form" onSubmit={e=>{e.preventDefault();void save({stadium_scenarios:[...bundle.document.stadium_scenarios.filter(s=>s.id!==draft.id),draft]});}}><label>{tr("Nom du scénario")}<input required maxLength={100} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder={tr("Ex. Extension prudente, saison 64")}/></label><div className="table-scroll"><table className="insights-capacities"><thead><tr><th>{tr("Catégorie")}</th><th>{tr("Capacité actuelle")}</th><th>{tr("Capacité cible")}</th><th>{tr("Coût par place ajoutée")}</th></tr></thead><tbody>{categories.map(([key,label])=><tr key={key}><th>{tr(label)}</th>{(['current','target','unit_costs'] as const).map(group=><td key={group}><input aria-label={label+' · '+{current:'capacité actuelle',target:'capacité cible',unit_costs:'coût unitaire'}[group]} type="number" min="0" max={group==='unit_costs'?1e12:1e6} step={group==='unit_costs'?'0.01':'1'} placeholder={tr("Inconnu")} value={draft[group][key]??''} onChange={e=>setValue(group,key,e.target.value)}/></td>)}</tr>)}</tbody></table></div><div className="insights-grid"><label>{tr("Trésorerie disponible")}<input type="number" min="0" max="1000000000000" step="0.01" placeholder={tr("Inconnue")} value={draft.treasury??''} onChange={e=>setDraft({...draft,treasury:optionalNumber(e.target.value)})}/></label><label>{tr("Réserve à conserver")}<input type="number" min="0" max="1000000000000" step="0.01" placeholder={tr("À renseigner, même si 0")} value={draft.reserve??''} onChange={e=>setDraft({...draft,reserve:optionalNumber(e.target.value)})}/></label></div><label>{tr("Hypothèses / date de vérification des tarifs")}<textarea maxLength={1000} value={draft.note} onChange={e=>setDraft({...draft,note:e.target.value})}/></label><div className="insights-actions"><button className="button primary" disabled={pending}><Save size={16}/>{tr("Enregistrer et calculer")}</button>{bundle.document.stadium_scenarios.some(s=>s.id===draft.id)&&<button className="text-button" type="button" disabled={pending} onClick={()=>void save({stadium_scenarios:bundle.document.stadium_scenarios.filter(s=>s.id!==draft.id)}).then(ok=>{if(ok){setCompare(compare.filter(id=>id!==draft.id));resetDraft();}})}>{tr("Supprimer ce scénario")}</button>}</div></form>
    {bundle.stadium.length>0&&<><h3>{tr("Comparaison des scénarios enregistrés")}</h3><p className="tiny">{tr("Sélectionnez les scénarios à comparer ; sans sélection, tous sont affichés. Les modifications du formulaire ne figurent ici qu’après enregistrement.")}</p><div className="insights-choices">{bundle.stadium.map(s=><label key={s.id}><input type="checkbox" checked={compare.includes(s.id)} onChange={()=>setCompare(compare.includes(s.id)?compare.filter(id=>id!==s.id):[...compare,s.id])}/>{s.name}</label>)}</div><div className="table-scroll"><table><thead><tr><th>{tr("Scénario")}</th><th>{tr("Capacité cible")}</th><th>{tr("Coût des ajouts")}</th><th>{tr("Reste après travaux et réserve")}</th><th>{tr("Données à vérifier")}</th></tr></thead><tbody>{rows.map(s=><tr key={s.id}><td><button className="text-button" onClick={()=>select(s.id)}>{s.name}</button></td><td>{fmt(s.target_capacity)}</td><td>{s.construction_cost===null?tr("Incomplet"):fmt(s.construction_cost)}</td><td className={s.remaining_available!==null&&s.remaining_available<0?'text-amber':''}>{s.remaining_available===null?tr("Non calculable"):fmt(s.remaining_available)}</td><td>{s.missing_categories.length>0&&<span>{tr("Capacité ou coût manquant : ")}{s.missing_categories.map(key=>categories.find(([k])=>k===key)?.[1]).join(', ')}. </span>}{s.reduction_categories.length>0&&<span>{tr("Réduction demandée : coût de démolition et éventuel remboursement non évalués. ")}</span>}{s.remaining_available!==null&&s.remaining_available<0&&<span>{tr("La réserve ne serait pas couverte.")}</span>}{s.remaining_available===null&&s.missing_categories.length===0&&<span>{tr("Renseignez trésorerie et réserve.")}</span>}</td></tr>)}</tbody></table></div></>}
    <p className="notice">{tr("Coût = places ajoutées × tarif saisi, par catégorie. Reste disponible = trésorerie − travaux − réserve. Les réductions n’accordent aucun remboursement. Frais annexes, affluence et rentabilité ne sont pas évalués.")}</p>
  </>}</div></section>;
}
