import {tr} from './i18n';
import {ArrowRight,RefreshCw,Users,Flag,TrendingUp} from 'lucide-react';
import type {Actions} from './App';
import {date} from './types';
import {CoachAdvice} from './coach-advice';

export function SelectionDashboard({d,act,busy,go}:Actions) {
  return <>
    <section className="card prose"><span className="eyebrow"><Flag size={18}/>{tr(" SÉLECTION ")}{d.current_team.kind === 'u20' ? tr("U20") : tr("NATIONALE")}</span><h2>{tr("Le point avant le rendez-vous international.")}</h2><p>{d.squad.length}{tr(" joueurs observés · dernière observation : ")}{d.squad_source ? date(d.squad_source.observed_at) : tr("à actualiser")}.</p><p>{tr("Qui associer, quels profils retenir, quelles évolutions suivre ? Comparez vos joueurs pour préparer le XV de la sélection dans cet espace privé. Les entraînements, l’académie et les finances restent gérés par leurs clubs.")}</p><div className="sync-buttons"><button className="button primary" disabled={busy} onClick={()=>void act('/classic/selections/sync',{team_id:d.current_team.id},'Sélection actualisée').catch(()=>{})}><RefreshCw size={16}/>{tr("Actualiser la sélection")}</button><button className="button secondary" onClick={()=>go('squad')}><Users size={16}/>{tr("Préparer le XV")}</button><button className="button secondary" onClick={()=>go('progression')}><TrendingUp size={16}/>{tr("Voir la progression")}</button><button className="button secondary" onClick={()=>go('matches')}>{tr("Analyser les matchs")}<ArrowRight size={16}/></button></div></section>
    <CoachAdvice d={d}/>
  </>;
}
