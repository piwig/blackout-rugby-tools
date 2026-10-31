import {useMemo,useRef,useState} from 'react';
import {ArrowRight,Check,ChevronLeft,ChevronRight,RefreshCw,Save,Search,Undo2} from 'lucide-react';
import {request,type Actions} from './App';
import {Modal,Pill} from './components';
import {tr} from './i18n';
import {useUnsavedChanges} from './navigation-guard';
import {useFormDraft} from './use-form-draft';
import {annotationChange,attackOptions,eventDraft,eventSource,eventText,eventTime,needsReview,reviewPage,useSuggestion,type Classification,type EventDraft,type ReviewEvent,type ReviewFilter} from './match-review-model';
import type {Match} from './types';
import './match-review.css';

type ReviewProps=Pick<Actions,'act'|'busy'>&{match:Match;scope:string;onUpdated:(match:Match)=>void};
function classificationLabel(event:ReviewEvent):string {
  const value=eventDraft(event);
  if(value.classification==='non_attack')return tr("Hors attaque");
  if(value.classification==='unclassified')return tr("Non classé");
  return tr(attackOptions.find(([key])=>key===value.att)?.[1]??'Attaque à préciser');
}
function sideName(value:unknown,match:Match):string {
  return value===0||value==='0'?match.home:value===1||value==='1'?match.away:tr("Côté inconnu");
}
const zoneLabels=['0 · 22 m domicile','1 · 22 m domicile','2 · Moitié domicile','3 · Moitié extérieur','4 · 22 m extérieur','5 · 22 m extérieur'];

export function MatchReview({match:m,act,busy,scope,onUpdated}:ReviewProps) {
  const [filter,setFilter]=useState<ReviewFilter>('unknown'),[query,setQuery]=useState(''),[page,setPage]=useState(0),[editing,setEditing]=useState<string|null>(null),[feedback,setFeedback]=useState('');
  const events=m.events??[],positions=useMemo(()=>new Map(events.map((event,index)=>[event.event_key,index])),[events]);
  const shown=useMemo(()=>reviewPage(events,filter,query,page),[events,filter,query,page]);
  const event=editing?events.find(item=>item.event_key===editing):undefined;
  const total=m.summary.total_events??events.length,classified=m.summary.classified??0,coverage=total?Math.round(classified/total*100):0;
  const nextUnknown=()=>{
    const unknown=events.find(needsReview);if(unknown?.event_key){setEditing(unknown.event_key);setFeedback('')}
    else setFeedback(tr("Tous les événements disponibles ont été relus ou disposent d’un classement exploitable."));
  };
  const saved=(updated:Match,next:boolean)=>{
    const previous=positions.get(editing)??-1,updatedEvents=updated.events??[];
    onUpdated(updated);setFeedback(tr("Correction enregistrée. Les statistiques ont été recalculées."));
    const after=next?[...updatedEvents.slice(previous+1),...updatedEvents.slice(0,previous+1)].find(needsReview):undefined;
    setEditing(after?.event_key??null);
  };
  return <section className="match-review" aria-labelledby="match-review-title">
    <div className="card-heading"><div><span className="eyebrow">{tr("ATELIER DES ÉVÉNEMENTS")}</span><h2 id="match-review-title">{tr("Donnez un sens aux actions non classées.")}</h2><p>{tr("Cliquez sur « Non classé » pour choisir une attaque, préciser son contexte ou signaler un événement hors attaque.")}</p></div><button className="button secondary" disabled={busy||!m.review||!events.some(needsReview)} onClick={nextUnknown}>{tr("Prochain événement à relire")}<ArrowRight size={16}/></button></div>
    <div className="match-review-metrics">
      <div><strong>{classified} <small>/ {total}</small></strong><span>{tr("Attaques exploitables")}</span><small>{tr('{percent} % des événements',{percent:coverage})}</small></div>
      <div><strong>{m.summary.unclassified??events.filter(needsReview).length}</strong><span>{tr("À relire")}</span><small>{tr('Dont {count} attaques sans contexte complet',{count:m.summary.attack_missing_context??0})}</small></div>
      <div><strong>{m.review?.annotation_count??m.summary.manual??0}</strong><span>{tr("Corrections manuelles")}</span><small>{tr('Hors attaque : {count}',{count:m.summary.non_attack??0})}</small></div>
      <div><strong>{m.review?.suggestion_count??m.summary.suggested??0}</strong><span>{tr("Suggestions à valider")}</span><small>{tr("Jamais ajoutées seules aux statistiques")}</small></div>
    </div>
    <p className="tiny">{tr('Parmi les attaques exploitables : {source} données sources, {manual} corrections manuelles et {inferred} estimations textuelles.',{source:m.summary.provenance?.source??0,manual:m.summary.manual??0,inferred:m.summary.inferred??0})}</p>
    {Boolean(m.review?.orphaned_count)&&<p className="notice">{tr('{count} corrections concernent des événements absents de cette source. Elles sont conservées à part et exclues de l’analyse.',{count:m.review!.orphaned_count})}</p>}
    {Boolean(m.review?.learning_conflicts)&&<p className="notice">{tr('{count} modèles de commentaires ont des exemples contradictoires. Ils ne produisent aucune suggestion.',{count:m.review!.learning_conflicts})}</p>}
    <div className="toolbar match-review-toolbar"><label className="search"><Search size={17}/><input value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}} placeholder={tr("Rechercher dans les commentaires…")} aria-label={tr("Rechercher dans les événements sources")}/></label><label className="match-review-filter">{tr("Afficher")}<select value={filter} onChange={e=>{setFilter(e.target.value as ReviewFilter);setPage(0)}}><option value="unknown">{tr("Non classés et incomplets")}</option><option value="all">{tr("Tous les événements")}</option><option value="corrected">{tr("Corrigés manuellement")}</option><option value="suggestions">{tr("Avec une suggestion")}</option><option value="non_attack">{tr("Hors attaque")}</option></select></label></div>
    <div className="match-review-results" role="status">{tr('{count} événements · Page {page} sur {pages}',{count:shown.total,page:shown.page+1,pages:shown.pageCount})}</div>
    <ol className="match-review-events" start={shown.page*50+1}>{shown.events.map((item,index)=>{
      const position=positions.get(item.event_key)??shown.page*50+index,source=eventSource(item),manual=Boolean(item.annotation),unknown=needsReview(item);
      return <li key={item.event_key??position} className="match-review-event"><div className="match-event-time"><strong>{String(eventTime(item,position))}</strong><small>{tr('Événement {number}',{number:position+1})}</small></div><div className="match-event-comment"><p>{eventText(item)||tr("Événement structuré")}</p><div className="match-event-context"><span>{sideName(source.possession,m)}</span><span>{tr('Zone source : {zone}',{zone:source.field??'—'})}</span>{manual&&<Pill tone="green">{tr("Corrigé")}</Pill>}{item.att_origin==='commentary-rule'&&!manual&&<Pill tone="neutral">{tr("Estimé")}</Pill>}{item.suggestion&&<Pill tone="amber">{tr("Suggestion disponible")}</Pill>}</div></div><div className="match-event-classification"><button className={'button '+(unknown?'secondary':'match-classified')} disabled={busy||!m.review||!item.event_key} aria-label={tr('Classer l’événement {number} : {classification}',{number:position+1,classification:classificationLabel(item)})} onClick={()=>{setEditing(item.event_key);setFeedback('')}}>{classificationLabel(item)}<ChevronRight size={15}/></button>{unknown&&eventDraft(item).classification==='attack'&&<small>{tr("Contexte incomplet")}</small>}</div></li>;
    })}</ol>
    {!shown.total&&<p className="match-review-empty">{filter==='unknown'?tr("Aucun événement à relire dans cette sélection. Consultez tous les événements pour vérifier les actions déjà classées."):tr("Aucun événement ne correspond à ces filtres.")}</p>}
    {shown.pageCount>1&&<nav className="match-review-pagination" aria-label={tr("Pagination des événements")}><button className="button secondary" disabled={shown.page===0} onClick={()=>setPage(shown.page-1)}><ChevronLeft size={16}/>{tr("Précédent")}</button><span>{tr('{from}–{to} sur {count}',{from:shown.page*50+1,to:Math.min((shown.page+1)*50,shown.total),count:shown.total})}</span><button className="button secondary" disabled={shown.page===shown.pageCount-1} onClick={()=>setPage(shown.page+1)}>{tr("Suivant")}<ChevronRight size={16}/></button></nav>}
    {feedback&&<p className="notice success" role="status"><Check size={16}/>{feedback}</p>}
    {event&&m.review&&<EventEditor key={m.type+':'+m.id+':'+event.event_key} match={m} event={event} position={positions.get(event.event_key)??0} scope={scope} act={act} busy={busy} onClose={()=>setEditing(null)} onSaved={saved} onReload={updated=>{onUpdated(updated);setEditing(null);setFeedback(tr("Version enregistrée rechargée. Rouvrez l’événement pour reprendre votre classement."))}}/>}
  </section>;
}

function EventEditor({match,event,position,scope,act,busy,onClose,onSaved,onReload}:Omit<ReviewProps,'onUpdated'>&{event:ReviewEvent;position:number;onClose:()=>void;onSaved:(match:Match,next:boolean)=>void;onReload:(match:Match)=>void}) {
  const baseline=useMemo(()=>eventDraft(event),[event]),draft=useFormDraft(baseline,scope+':'+match.type+':'+match.id+':'+event.event_key),value=draft.value;
  const [version]=useState(()=>match.review!);
  const pending=useRef(false),source=eventSource(event),disabled=busy||draft.saving;
  useUnsavedChanges(draft.dirty||draft.saving);
  const close=()=>{if(disabled)return;if(draft.dirty&&!window.confirm(tr("Abandonner les modifications non enregistrées de cet événement ?")))return;onClose()};
  const edit=(changes:Partial<EventDraft>)=>draft.edit({...value,...changes});
  const save=async(next=false,reset=false)=>{
    if(disabled||pending.current||draft.conflict)return;
    if(reset&&!window.confirm(tr("Retirer cette correction et retrouver le classement de la source ?")))return;
    pending.current=true;let updated:Match|undefined;
    const ok=await draft.save(async current=>{
      const change=reset?{event_key:event.event_key,reset:true}:annotationChange(event.event_key,current);
      updated=await act('/matches/'+match.type+'/'+encodeURIComponent(match.id)+'/annotations',{expected_revision:version.revision,expected_source_digest:version.source_digest,changes:[change]},tr("Classement enregistré"));
    });
    pending.current=false;if(ok&&updated)onSaved(updated,next);
  };
  const reload=async()=>{
    if(disabled||pending.current||!window.confirm(tr("Recharger la version enregistrée abandonnera votre brouillon. Relevez vos choix avant de continuer.")))return;
    pending.current=true;let updated:Match|undefined;
    const ok=await draft.reload(async()=>{
      updated=await request('/matches/'+match.type+'/'+encodeURIComponent(match.id));
      const fresh=updated?.events?.find(item=>item.event_key===event.event_key);
      return fresh?eventDraft(fresh):baseline;
    });
    pending.current=false;if(ok&&updated)onReload(updated);
  };
  const suggestion=event.suggestion;
  return <Modal title={tr('Classer l’événement {number}',{number:position+1})} onClose={close} wide>
    <form className="match-event-editor" onSubmit={e=>{e.preventDefault();void save()}}>
      <section className="match-event-source" aria-label={tr("Commentaire source inchangé")}><div><Pill tone="neutral">{tr('Temps source : {time}',{time:String(eventTime(event,position))})}</Pill><span>{sideName(source.possession,match)} · {tr('Zone source : {zone}',{zone:source.field??'—'})}</span></div><blockquote>{eventText(event)||tr("Événement structuré")}</blockquote><small>{tr("Le commentaire source reste inchangé. Seul votre classement est enregistré.")}</small></section>
      {suggestion&&<section className="match-event-suggestion"><div><strong>{tr("Suggestion issue de vos exemples")}</strong><p>{suggestion.classification==='non_attack'?tr("Hors attaque"):tr(attackOptions.find(([key])=>key===suggestion.att)?.[1]??'Attaque à préciser')} · {tr('{count} exemples',{count:suggestion.example_count??0})}</p><small>{tr("Vérifiez le commentaire, le côté et la zone avant d’enregistrer.")}</small>{suggestion.template&&<details><summary>{tr("Pourquoi cette suggestion ?")}</summary><p className="tiny">{tr("Ce modèle de commentaire correspond à des exemples que vous avez validés :")}</p><code>{suggestion.template}</code></details>}</div><button type="button" className="button secondary" disabled={disabled} onClick={()=>draft.edit(useSuggestion(value,suggestion))}>{tr("Reprendre cette suggestion")}</button></section>}
      <fieldset disabled={disabled} className="match-editor-fields"><legend className="sr-only">{tr("Votre classement")}</legend>
        <label>{tr("Nature de l’événement")}<select value={value.classification} onChange={e=>edit({classification:e.target.value as Classification,att:e.target.value==='attack'?value.att:'',learn:e.target.value==='unclassified'?false:value.learn})}><option value="unclassified">{tr("Non classé")}</option><option value="attack">{tr("Attaque")}</option><option value="non_attack">{tr("Hors attaque")}</option></select></label>
        {value.classification==='attack'&&<label>{tr("Type d’attaque")}<select required value={value.att} onChange={e=>edit({att:e.target.value})}><option value="">{tr("Choisir un type d’attaque…")}</option>{attackOptions.map(([key,label])=><option key={key} value={key}>{tr(label)}</option>)}</select></label>}
        <div className="form-grid"><label>{tr("Équipe en possession")}<select value={value.possession} onChange={e=>edit({possession:e.target.value})}><option value="">{tr("Inconnue")}</option><option value="0">{tr('Domicile : {team}',{team:match.home})}</option><option value="1">{tr('Extérieur : {team}',{team:match.away})}</option></select></label><label>{tr("Zone du terrain (repère domicile)")}<select value={value.field} onChange={e=>edit({field:e.target.value})}><option value="">{tr("Inconnue")}</option>{zoneLabels.map((label,index)=><option value={index} key={index}>{tr(label)}</option>)}</select></label></div>
        <p className="tiny">{tr("Les codes 0 à 5 suivent le terrain depuis le côté domicile. L’analyse inverse ensuite les zones pour l’équipe à l’extérieur. Laissez inconnu ce que le commentaire ne permet pas d’établir.")}</p>
        {value.classification==='attack'&&(value.possession===''||value.field==='')&&<p className="notice">{tr("Cette attaque restera hors des répartitions par zone tant que son côté ou sa zone est inconnu.")}</p>}
        {value.classification!=='unclassified'&&<label className="match-learn-choice"><input type="checkbox" checked={value.learn} onChange={e=>edit({learn:e.target.checked})}/><span><strong>{tr("Utiliser cet exemple pour mes prochaines suggestions")}</strong><small>{tr("Apprentissage privé à partir de commentaires similaires. Le côté et la zone ne sont pas appris ; chaque suggestion attend votre validation.")}</small></span></label>}
      </fieldset>
      {draft.error&&<p className="notice error" role="alert">{tr(draft.error)}</p>}
      {draft.conflict&&<div className="notice"><span>{tr("Votre brouillon est conservé. Une autre version du match existe ; relisez-la avant toute nouvelle sauvegarde.")}</span><button type="button" className="button secondary" disabled={disabled} onClick={()=>void reload()}><RefreshCw size={16}/>{tr("Relire la version enregistrée")}</button></div>}
      <div className="match-review-actions"><button type="submit" className="button primary" disabled={disabled||draft.conflict||!draft.dirty||value.classification==='attack'&&!value.att}><Save size={16}/>{draft.saving?tr("Enregistrement…"):tr("Enregistrer")}</button><button type="button" className="button secondary" disabled={disabled||draft.conflict||!draft.dirty||value.classification==='attack'&&!value.att} onClick={()=>void save(true)}>{tr("Enregistrer et suivant")}<ArrowRight size={16}/></button><button type="button" className="text-button" disabled={disabled} onClick={close}>{tr("Annuler")}</button>{event.annotation&&<button type="button" className="text-button" disabled={disabled||draft.conflict} onClick={()=>void save(false,true)}><Undo2 size={15}/>{tr("Retirer ma correction")}</button>}</div>
    </form>
  </Modal>;
}
