import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Save} from 'lucide-react';
import {type State,type Player,date,fmt} from './types';
import {type Actions,request} from './App';
import {Modal,Pill,Radar,SkillList} from './components';
import {useUnsavedChanges} from './navigation-guard';

export function PlayerDetail({player,d,act,close}:{player:Player;d:State;act:Actions['act'];close:()=>void}){
 const [baseline,setBaseline]=useState(()=>({text:d.notes[player.id]?.text||'',watch:!!d.notes[player.id]?.watch}));
 const [note,setNote]=useState(baseline.text),[watch,setWatch]=useState(baseline.watch);
 const [history,setHistory]=useState<any[]>([]),[historyError,setHistoryError]=useState('');
 const [pending,setPending]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false),[message,setMessage]=useState('');
 const sending=useRef(false),mounted=useRef(true);
 const dirty=note!==baseline.text||watch!==baseline.watch;
 useUnsavedChanges(dirty||pending);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 useEffect(()=>{
  let active=true;setHistory([]);setHistoryError('');
  request('/history/'+d.current_team.id+'/'+player.id)
   .then(value=>{if(active)setHistory(value)})
   .catch(e=>{if(active)setHistoryError(e.message)});
  return()=>{active=false};
 },[player.id,d.current_team.id]);
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
    <div className="player-facts"><Pill>{player.age||'—'} ans</Pill><Pill tone="neutral">{player.height||'—'} cm</Pill><Pill tone="neutral">{player.weight||'—'} kg</Pill>{player.wc_projection&&<Pill>Génération S{player.wc_projection}</Pill>}</div>
    <Radar player={player}/><p className="tiny">{player.metrics.known_skills}/10 compétences dévoilées. Les valeurs masquées ne sont pas estimées.</p>
    <div className="role-list">{player.metrics.roles.slice(0,3).map(r=><div key={r.name}><span>{r.name}</span><strong>{r.score}/21</strong></div>)}</div>
    <p className="tiny">Affinités indicatives, pondérations propres à cet outil.</p>
    <a className="text-button" href={'https://www.blackoutrugby.com/game/club.squad.php#player='+player.id} target="_blank" rel="noreferrer">Ouvrir Classic<ArrowUpRight size={14}/></a>
   </div>
   <div><SkillList player={player}/><div className="note-box" aria-busy={pending}>
    <h3>Votre note de recruteur</h3>
    <textarea aria-label="Note sur le joueur" rows={3} maxLength={3000} disabled={pending} value={note} onChange={e=>{setNote(e.target.value);setMessage('')}} placeholder="Potentiel, poste envisagé, prochain objectif…"/>
    <label className="check"><input type="checkbox" disabled={pending} checked={watch} onChange={e=>{setWatch(e.target.checked);setMessage('')}}/>Garder ce joueur à l’œil</label>
    {error&&<p className="text-error" role="alert">{error}</p>}
    {conflict&&<button type="button" className="button secondary" disabled={pending} onClick={()=>void reloadNote()}>Relire la note enregistrée</button>}
    <button type="button" className="button primary" disabled={pending||!dirty} onClick={()=>void save()}><Save size={15}/>{pending?'Enregistrement en cours…':dirty?'Enregistrer la note':'Note enregistrée'}</button>
    <p className="tiny" role="status">{pending?'Veuillez patienter avant de fermer cette fiche.':message|| (dirty?'Modifications non enregistrées.':'Cette note reste privée dans votre espace.')}</p>
   </div></div>
  </div>
  <div className="history-section"><h3>Historique des observations</h3>{historyError?<p className="text-error" role="alert">{historyError}</p>:<div className="history-list">{history.map((h,i)=><div key={i}><strong>{date(h.observed_at)}</strong><span>{h.source}</span><span>Attaque {fmt(h.player.attack)} · Défense {fmt(h.player.defense)} · Force {fmt(h.player.strength)}</span></div>)}</div>}</div>
 </Modal>
}

