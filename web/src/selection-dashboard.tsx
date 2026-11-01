import {tr} from './i18n';
import {ArrowRight,RefreshCw,Users,Flag,TrendingUp} from 'lucide-react';
import type {Actions} from './App';
import {date} from './types';
import {CoachAdvice} from './coach-advice';
import {DailyHub} from './workbench';
import {isActiveSelection} from './team-context';

export function SelectionDashboard(props:Actions&{selectTeam?:(id:string,page:string)=>void}) {
  const {d,act,busy,go}=props,active=isActiveSelection(d,d.current_team);
  return <>
    <section className="card prose"><span className="eyebrow"><Flag size={18}/>{tr(" SÉLECTION ")}{d.current_team.kind === 'u20' ? tr("U20") : tr("NATIONALE")}</span><h2>{tr("Le point avant le rendez-vous international.")}</h2><p>{d.squad.length}{tr(" joueurs observés · dernière observation : ")}{d.squad_source ? date(d.squad_source.observed_at) : tr("à actualiser")}.</p><p>{tr("Qui associer, quels profils retenir, quelles évolutions suivre ? Comparez vos joueurs pour préparer le XV de la sélection dans cet espace privé. Les entraînements, l’académie et les finances restent gérés par leurs clubs.")}</p><p role="status">{active?tr("Sélection active"):tr("Sélection suspendue : vos observations et analyses locales restent disponibles. Rattachez cette sélection dans Connexion & données pour reprendre les actualisations.")}</p><div className="sync-buttons">{active?<button className="button primary" disabled={busy} onClick={()=>void act('/classic/selections/sync',{team_id:d.current_team.id},'Sélection actualisée').catch(()=>{})}><RefreshCw size={16}/>{tr("Actualiser la sélection")}</button>:<button className="button primary" disabled={busy} onClick={()=>go('settings')}>{tr("Rattacher la sélection")}</button>}<button className="button secondary" onClick={()=>go('squad')}><Users size={16}/>{tr("Préparer le XV")}</button><button className="button secondary" onClick={()=>go('progression')}><TrendingUp size={16}/>{tr("Voir la progression")}</button><button className="button secondary" onClick={()=>go('matches')}>{tr("Analyser les matchs")}<ArrowRight size={16}/></button></div></section>
    <section className="card prose"><h2>{tr("Un œil sur tout votre vivier")}</h2><p>{tr("Comparez les observations de vos clubs et sélections, puis confrontez les profils aux performances renseignées.")}</p><div className="sync-buttons"><button className="button secondary" onClick={()=>go('pool')}>{tr("Ouvrir le vivier")}<ArrowRight size={16}/></button><button className="button secondary" onClick={()=>go('performance')}>{tr("Comparer les performances")}<ArrowRight size={16}/></button></div></section>
    <DailyHub {...props}/>
    <CoachAdvice d={d}/>
  </>;
}
