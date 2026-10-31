import {ArrowRight,RefreshCw,Users,Flag,TrendingUp} from 'lucide-react';
import type {Actions} from './App';
import {date} from './types';
import {CoachAdvice} from './coach-advice';

export function SelectionDashboard({d,act,busy,go}:Actions) {
  return <>
    <section className="card prose"><span className="eyebrow"><Flag size={18}/> SÉLECTION {d.current_team.kind === 'u20' ? 'U20' : 'NATIONALE'}</span><h2>Préparez votre collectif international.</h2><p>{d.squad.length} joueurs observés · dernière observation : {d.squad_source ? date(d.squad_source.observed_at) : 'à actualiser'}.</p><p>Comparez les profils, préparez votre XV et suivez les observations dans cet espace privé. Les entraînements, l’académie et les finances restent gérés par les clubs des joueurs.</p><div className="sync-buttons"><button className="button primary" disabled={busy} onClick={()=>void act('/classic/selections/sync',{team_id:d.current_team.id},'Sélection actualisée').catch(()=>{})}><RefreshCw size={16}/>Actualiser la sélection</button><button className="button secondary" onClick={()=>go('squad')}><Users size={16}/>Préparer le XV</button><button className="button secondary" onClick={()=>go('progression')}><TrendingUp size={16}/>Voir la progression</button><button className="button secondary" onClick={()=>go('matches')}>Analyser les matchs<ArrowRight size={16}/></button></div></section>
    <CoachAdvice d={d}/>
  </>;
}
