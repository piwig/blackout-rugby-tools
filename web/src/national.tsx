import {useState} from 'react';
import {Flag,Plus,RefreshCw} from 'lucide-react';
import type {Actions} from './App';
import './national.css';

export function NationalSelections({d,act,busy}:Pick<Actions,'d'|'act'|'busy'>){
  const [kind,setKind]=useState<'u20'|'nt'>('u20');
  const [country,setCountry]=useState('');
  const [result,setResult]=useState('');
  const account=d.classic_account;
  if(!account)return null;
  const selections=d.teams.filter(team=>team.kind==='u20'||team.kind==='nt');
  async function attach(event:React.FormEvent){
    event.preventDefault();setResult('');
    try{
      const response=await act('/classic/selections',{kind,country},'Sélection rattachée à votre espace');
      setResult(`${response.team.name} : ${response.team.squad} joueur(s) observé(s). Retrouvez la sélection dans le choix d’équipe en haut de page.`);
    }catch{/* The shared action displays the server's safe error message. */}
  }
  return <div className="national-panel">
    <div className="national-heading"><Flag size={20}/><div><h3>Vos sélections nationales</h3><p>Vous êtes sélectionneur U20 ou senior ? Rattachez la sélection au même compte Classic.</p></div></div>
    {selections.length>0&&<ul className="national-list">{selections.map(team=>{
      const active=!!account.selection_ids?.includes(team.id);
      return <li key={team.id}><div><strong>{team.name}</strong><small>{team.country} · {active?'Synchronisation active':'Synchronisation suspendue · historique conservé'}</small></div><div className="national-actions">{active?<>
        <button type="button" className="text-button" disabled={busy} onClick={()=>{setResult('');void act('/classic/selections/sync',{team_id:team.id},'Effectif de la sélection actualisé').catch(()=>{})}} aria-label={'Actualiser '+team.name}><RefreshCw size={15}/>Actualiser</button>
        <button type="button" className="text-button" disabled={busy} onClick={()=>{setResult('');void act('/classic/selections/pause',{team_id:team.id,expected_revision:account.selection_revision??0},'Synchronisation suspendue ; historique conservé').catch(()=>{})}}>Suspendre la synchronisation</button>
      </>:<button type="button" className="text-button" disabled={busy} onClick={()=>{setResult('');void act('/classic/selections',{kind:team.kind,country:team.country},'Droits vérifiés ; sélection rattachée').catch(()=>{})}}>Rattacher à nouveau</button>}</div></li>;
    })}</ul>}
    <form className="national-form" onSubmit={attach}><fieldset disabled={busy}>
      <label>Sélection<select value={kind} onChange={event=>setKind(event.target.value as 'u20'|'nt')}><option value="u20">Moins de 20 ans</option><option value="nt">Nationale senior</option></select></label>
      <label>Code du pays<input required pattern="[A-Z]{2}" maxLength={2} value={country} onChange={event=>setCountry(event.target.value.toUpperCase())} placeholder="BE" autoComplete="off" aria-describedby="national-country-help"/></label>
      <button className="button secondary" disabled={busy||country.length!==2}><Plus size={16}/>{busy?'Lecture en cours…':'Rattacher la sélection'}</button>
    </fieldset><p id="national-country-help" className="tiny">Code Classic à deux lettres, par exemple BE pour la Belgique. Le compte connecté doit être le sélectionneur actuel.</p></form>
    <p className="tiny">L’effectif, les compétences, les notes et le XV préparé restent dans votre espace privé. La sélection n’a pas d’académie de club ; aucun ordre n’est envoyé dans Classic. Si votre mandat se termine, suspendez sa synchronisation pour conserver l’historique et continuer à actualiser vos clubs.</p>
    {result&&<p className="notice success" role="status">{result}</p>}
  </div>;
}
