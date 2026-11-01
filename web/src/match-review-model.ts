export type ReviewEvent=Record<string,any>;
export type Classification='attack'|'non_attack'|'unclassified';
export type ReviewFilter='unknown'|'all'|'corrected'|'suggestions'|'non_attack';
export type EventDraft={classification:Classification;att:string;possession:string;field:string;learn:boolean};
export const attackOptions=[['percu','Percussion'],['png','Pick and go'],['large','Large'],['crea','Créatif'],['kick','Jeu au pied']] as const;
const aliases:Record<string,string>={percu:'percu',percussion:'percu',drive:'percu',driving:'percu',png:'png','pick and go':'png','pick&go':'png',pickngo:'png',large:'large',wide:'large',expansive:'large',crea:'crea','créatif':'crea',creative:'crea',kick:'kick',kicking:'kick','jeu au pied':'kick'};
export function attackCode(value:unknown):string{return aliases[String(value??'').trim().toLowerCase()]||''}
function contextValue(value:unknown,max:number):string {
  if(typeof value!=='string'&&typeof value!=='number')return '';
  // Match attack_summary's canonical digits and Python integer whitespace,
  // including NEL but excluding BOM; numeric coercion would invent context.
  const text=String(value).replace(/^\p{White_Space}+|\p{White_Space}+$/gu,'');
  return /^[0-5]$/.test(text)&&Number(text)<=max?text:'';
}
export function eventSource(event:ReviewEvent):ReviewEvent{return event.source_event??event}
export function eventText(event:ReviewEvent):string {
  const source=eventSource(event);return String(source.text??source.commentary??source.comment??'');
}
export function eventTime(event:ReviewEvent,_index?:number):string|number {
  const source=eventSource(event),value=source.minute??source.time;
  return value===undefined||value===null||value===''?'—':value;
}
export function eventDraft(event:ReviewEvent):EventDraft {
  const correction=event.annotation,att=attackCode(correction?.att??event.att);
  const classification:Classification=correction?.classification??event.classification??(att?'attack':'unclassified');
  return {classification,att:classification==='attack'?att:'',possession:contextValue(correction&&Object.hasOwn(correction,'possession')?correction.possession:event.possession,1),field:contextValue(correction&&Object.hasOwn(correction,'field')?correction.field:event.field,5),learn:correction?.learn===true};
}
export function needsReview(event:ReviewEvent):boolean {
  const d=eventDraft(event);return d.classification==='unclassified'||d.classification==='attack'&&(!d.att||d.possession===''||d.field==='');
}
export function useSuggestion(draft:EventDraft,suggestion:ReviewEvent):EventDraft {
  return {...draft,classification:suggestion.classification,att:suggestion.classification==='attack'?attackCode(suggestion.att):'',learn:false};
}
export function annotationChange(eventKey:string,draft:EventDraft) {
  if(!eventKey||!['attack','non_attack','unclassified'].includes(draft.classification)||draft.classification==='attack'&&!attackOptions.some(([key])=>key===draft.att))throw new Error('Choisissez un type d’attaque.');
  const possession=contextValue(draft.possession,1),field=contextValue(draft.field,5);
  if(draft.possession!==''&&possession===''||draft.field!==''&&field==='')throw new Error('Vérifiez le côté et la zone.');
  return {event_key:eventKey,classification:draft.classification,att:draft.classification==='attack'?draft.att:null,possession:possession===''?null:Number(possession),field:field===''?null:Number(field),learn:draft.classification!=='unclassified'&&draft.learn};
}
function normalized(text:string):string{return text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\s+/g,' ').trim()}
export function reviewPage(events:ReviewEvent[],filter:ReviewFilter,query:string,page:number) {
  const search=normalized(query),filtered=events.filter(event=>{
    const matches=filter==='all'||filter==='unknown'&&needsReview(event)||filter==='corrected'&&Boolean(event.annotation)||filter==='suggestions'&&Boolean(event.suggestion)||filter==='non_attack'&&eventDraft(event).classification==='non_attack';
    return matches&&(!search||normalized(eventText(event)).includes(search));
  });
  const pageCount=Math.max(1,Math.ceil(filtered.length/50)),safePage=Math.max(0,Math.min(pageCount-1,Math.trunc(page)||0));
  return {events:filtered.slice(safePage*50,safePage*50+50),total:filtered.length,page:safePage,pageCount};
}
