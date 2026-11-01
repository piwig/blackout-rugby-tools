import {tr} from './i18n';
import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Save} from 'lucide-react';
import {type State,type Player,date,fmt} from './types';
import {type Actions,request} from './App';
import {Modal,Pill,Radar,SkillList} from './components';
import {useUnsavedChanges} from './navigation-guard';

export type PlayerHistoryCohort='club'|'youth'|'u20'|'nt';
type PlayerObservation={snapshot_id:number;team_id:string;cohort:PlayerHistoryCohort;youth:boolean;observed_at:string;source:string;player:Player};
const cohortLabel=(cohort:PlayerHistoryCohort)=>tr(cohort==='youth'?'Juniors':cohort==='u20'?'Sélection U20':cohort==='nt'?'Sélection nationale':'Seniors');

export function PlayerDetail({player,cohort,d,act,close}:{player:Player;cohort:PlayerHistoryCohort;d:State;act:Actions['act'];close:()=>void}){
 const [baseline,setBaseline]=useState(()=>({text:d.notes[player.id]?.text||'',watch:!!d.notes[player.id]?.watch}));
 const [note,setNote]=useState(baseline.text),[watch,setWatch]=useState(baseline.watch);
 const historyScope=JSON.stringify([d.user.username,d.csrf,d.current_team.id,player.id,cohort]);
 const [historyState,setHistoryState]=useState<{scope:string;rows:PlayerObservation[];loading:boolean;error:string}>({scope:'',rows:[],loading:true,error:''});
 const currentHistoryScope=useRef(historyScope);currentHistoryScope.current=historyScope;
 const history=historyState.scope===historyScope?historyState.rows:[],historyError=historyState.scope===historyScope?historyState.error:'',historyLoading=historyState.scope!==historyScope||historyState.loading;
 const [pending,setPending]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false),[message,setMessage]=useState('');
 const sending=useRef(false),mounted=useRef(true);
 const dirty=note!==baseline.text||watch!==baseline.watch;
 useUnsavedChanges(dirty||pending);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 useEffect(()=>{
  let active=true;setHistoryState({scope:historyScope,rows:[],loading:true,error:''});
  request('/history/'+encodeURIComponent(d.current_team.id)+'/'+encodeURIComponent(player.id)+'?cohort='+cohort)
   .then(value=>{if(active&&currentHistoryScope.current===historyScope)setHistoryState({scope:historyScope,rows:value,loading:false,error:''})})
   .catch(e=>{if(active&&currentHistoryScope.current===historyScope)setHistoryState({scope:historyScope,rows:[],loading:false,error:e.message})});
  return()=>{active=false};
 },[historyScope]);
 const dismiss=()=>{
  if(sending.current)return;
  if(dirty&&!window.confirm('Abandonner les modifications non enregistrées de cette note ?'))return;
  close();
 };
 const save=async()=>{
  if(sending.current||!dirty)return;
  sending.current=true;setPending(true);setError('');setMessage('');
  const saved={text:note,watch};
  try{
   await act('/notes',{team_id:d.current_team.id,player_id:player.id,...saved,expected_note:baseline},'');
   if(mounted.current){setBaseline(saved);setConflict(false);setMessage('Note du joueur enregistrée.')}
  }catch(e){
   if(mounted.current){setError((e as Error).message);setConflict((e as {status?:number}).status===409)}
  }finally{
   sending.current=false;if(mounted.current)setPending(false);
  }
 };
 const reloadNote=async()=>{
  if(sending.current||!window.confirm('Remplacer votre brouillon par la note actuellement enregistrée ?'))return;
  sending.current=true;setPending(true);setError('');setMessage('');
  try{
   const current:State=await request('/state?team_id='+encodeURIComponent(d.current_team.id));
   if(current.user.username!==d.user.username||current.csrf!==d.csrf||current.current_team?.id!==d.current_team.id)throw new Error('La session ou le club a changé. Fermez cette fiche puis reconnectez-vous.');
   const next={text:current.notes[player.id]?.text||'',watch:!!current.notes[player.id]?.watch};
   if(mounted.current){setBaseline(next);setNote(next.text);setWatch(next.watch);setConflict(false);setMessage('Note enregistrée rechargée. Vous pouvez reprendre votre saisie.')}
  }catch(e){if(mounted.current)setError((e as Error).message)}
  finally{sending.current=false;if(mounted.current)setPending(false)}
 };
 return <Modal title={player.name} onClose={dismiss} wide>
  <div className="player-detail">
   <div>
    <div className="player-facts"><Pill>{player.age||'—'}{tr(" ans")}</Pill><Pill tone="neutral">{player.height||'—'}{tr(" cm")}</Pill><Pill tone="neutral">{player.weight||'—'}{tr(" kg")}</Pill>{player.wc_projection&&<Pill>{tr("Génération S")}{player.wc_projection}</Pill>}</div>
    <Radar player={player}/><p className="tiny">{player.metrics.known_skills}{tr("/10 compétences dévoilées. Les valeurs masquées ne sont pas estimées.")}</p>
    <div className="role-list">{player.metrics.roles.slice(0,3).map(r=><div key={r.name}><span>{r.name}</span><strong>{r.score}/21</strong></div>)}</div>
    <p className="tiny">{tr("Affinités indicatives, pondérations propres à cet outil.")}</p>
    <a className="text-button" href={'https://www.blackoutrugby.com/game/'+(cohort==='youth'?'club.squad.youth.php':'club.squad.php')+'#player='+player.id} target="_blank" rel="noreferrer">{tr("Ouvrir Classic")}<ArrowUpRight size={14}/></a>
   </div>
   <div><SkillList player={player}/><div className="note-box" aria-busy={pending}>
    <h3>{tr("Votre note de recruteur")}</h3>
    <textarea aria-label={tr("Note sur le joueur")} rows={3} maxLength={3000} disabled={pending} value={note} onChange={e=>{setNote(e.target.value);setMessage('')}} placeholder={tr("Potentiel, poste envisagé, prochain objectif…")}/>
    <label className="check"><input type="checkbox" disabled={pending} checked={watch} onChange={e=>{setWatch(e.target.checked);setMessage('')}}/>{tr("Garder ce joueur à l’œil")}</label>
    {error&&<p className="text-error" role="alert">{tr(error)}</p>}
    {conflict&&<button type="button" className="button secondary" disabled={pending} onClick={()=>void reloadNote()}>{tr("Relire la note enregistrée")}</button>}
    <button type="button" className="button primary" disabled={pending||!dirty} onClick={()=>void save()}><Save size={15}/>{pending?tr("Enregistrement en cours…"):dirty?tr("Enregistrer la note"):tr("Note enregistrée")}</button>
    <p className="tiny" role="status">{pending?tr("Veuillez patienter avant de fermer cette fiche."):message|| (dirty?tr("Modifications non enregistrées."):tr("Cette note reste privée dans votre espace."))}</p>
   </div></div>
  </div>
  <div className="history-section"><h3>{tr("Historique des observations")} · {cohortLabel(cohort)}</h3><p className="tiny">{tr('Jusqu’à 100 observations du joueur, dans cette population, par import le plus récent.')}</p>{historyLoading?<p role="status">{tr('Chargement…')}</p>:historyError?<p className="text-error" role="alert">{historyError}</p>:history.length?<div className="history-list">{history.map(h=><div key={h.snapshot_id}><strong><time dateTime={h.observed_at}>{date(h.observed_at)}</time></strong><span>{cohortLabel(h.cohort)}</span><span>{h.source} · {h.observed_at}</span><span>{tr("Attaque ")}{fmt(h.player.attack)}{tr(" · Défense ")}{fmt(h.player.defense)}{tr(" · Force ")}{fmt(h.player.strength)}</span></div>)}</div>:<p role="status">{tr('Aucune observation')}</p>}</div>
 </Modal>
}

