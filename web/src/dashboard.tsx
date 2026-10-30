import {ArrowRight,ArrowUpRight,CalendarRange,CheckCircle2,Clock3,Database,Palette,Sprout,Star,Target,TrendingUp,Users} from 'lucide-react';
import type {ReactNode} from 'react';
import type {Actions} from './App';
import {date} from './types';
import {Empty,Metric,Pill} from './components';
import {DailyHub} from './workbench';
import {MatchdayHero,RugbyGallery} from './rugby';
import {ProgressionSummary} from './progression';
import {defaultProfile,type ProfilePreferences} from './profile';

export function Dashboard(props:Actions&{selectTeam:(id:string,page:string)=>void;profile:ProfilePreferences}) {
  const {d,go,openPlayer,profile}=props;
  const youth=d.academy,ready=youth.filter(p=>p.wc_projection),tracked=youth.filter(p=>d.notes[p.id]?.watch);
  const priorities=[...youth].sort((a,b)=>(b.wc_projection||0)-(a.wc_projection||0)||(b.stars||0)-(a.stars||0)).slice(0,4);
  const connected=!!d.classic_account,hasPlayers=!!(d.academy_source||d.squad_source);
  const sections:Record<string,ReactNode>={
    priorities:<DailyHub {...props}/>,
    metrics:<section className="dashboard-numbers" aria-label="Les chiffres de votre club"><div className="metrics">
      <Metric label="Seniors" value={d.squad_source?d.squad.length:'—'} hint="Préparer l’effectif et le XV" icon={<Users size={20}/>} onClick={()=>go('squad')}/>
      <Metric label="Jeunes en formation" value={d.academy_source?youth.length:'—'} hint="Observer l’académie" icon={<Sprout size={20}/>} onClick={()=>go('academy')}/>
      <Metric label="Potentiels U20" value={d.academy_source?ready.length:'—'} hint="Projection d’âge indicative" icon={<Target size={20}/>} accent onClick={()=>go('academy')}/>
      <Metric label="Jeunes suivis" value={tracked.length} hint="Vos favoris de l’académie" icon={<Star size={20}/>} onClick={()=>go('academy')}/>
    </div></section>,
    progress:<ProgressionSummary {...props}/>,
    talents:<section className="card"><div className="card-heading"><div><span className="eyebrow">LA RELÈVE</span><h2>Vos jeunes à observer</h2></div><button className="text-button" onClick={()=>go('academy')}>Toute l’académie<ArrowUpRight size={16}/></button></div>
      {priorities.length?<div className="talent-list">{priorities.map(p=><button className="talent-row" onClick={()=>openPlayer(p)} key={p.id}>
        <span className="player-avatar">{p.name.split(' ').map(n=>n[0]).slice(0,2).join('')}</span><span className="talent-name"><strong>{p.name}</strong><small>{p.age??'—'} ans · {p.metrics.known_skills}/10 compétences connues</small></span>
        {p.wc_projection?<Pill>Projection S{p.wc_projection}</Pill>:<Pill tone="neutral">À observer</Pill>}<ArrowUpRight size={16}/></button>)}</div>:<Empty title="L’académie attend ses premières données" action={<button className="button primary" onClick={()=>go('settings')}>Importer mon académie</button>}>Connectez Classic ou importez votre fichier pour retrouver vos jeunes ici.</Empty>}
      <div className="card-foot">{d.academy_source?<>Dernière observation : {date(d.academy_source.observed_at)} · {d.academy_source.source}</>:'Les compétences masquées restent inconnues.'}</div>
    </section>,
    actions:<section className="card dashboard-actions"><div className="card-heading"><div><span className="eyebrow">VOTRE PROCHAINE DÉCISION</span><h2>Du constat à la préparation</h2></div></div><div className="dashboard-action-grid">
      {[{label:'Préparer mon XV',detail:'Comparer des compositions, puis conserver votre choix.',page:'optimization',Icon:Users},{label:'Organiser ma semaine',detail:'Matchs, séances et rappels dans un calendrier.',page:'season',Icon:CalendarRange},{label:'Suivre les progrès',detail:'Comparer les observations réelles dans le temps.',page:'progression',Icon:TrendingUp}].map(({Icon,...a})=><button key={a.page} onClick={()=>go(a.page)}><Icon size={23}/><strong>{a.label}</strong><span>{a.detail}</span><ArrowRight size={18}/></button>)}
    </div><p className="dashboard-local-note">Ces préparations restent dans l’outil. Les envois vers le jeu se contrôlent séparément dans Mode vacances.</p></section>,
    gallery:<RugbyGallery go={go}/>,
  };
  return <>
    <MatchdayHero club={d.current_team.name} banner={profile.banner} onExplore={()=>go('optimization')}/>
    <section className="dashboard-orientation" aria-label="Les repères de votre espace">
      <button onClick={()=>go('settings')}><span className={'orientation-icon '+(connected?'ready':'')}>{connected?<CheckCircle2 size={20}/>:<Database size={20}/>}</span><span><strong>{connected?'Compte Classic relié':hasPlayers?'Données importées':'Commencer par vos données'}</strong><small>{connected?`${d.teams.length} club${d.teams.length>1?'s':''} dans votre espace`:'Connecter Classic ou importer un fichier'}</small></span><ArrowUpRight size={16}/></button>
      <div><span className="orientation-icon"><Clock3 size={20}/></span><span><strong>Dernières observations</strong><small>Seniors : {d.squad_source?date(d.squad_source.observed_at):'à importer'}<br/>Académie : {d.academy_source?date(d.academy_source.observed_at):'à importer'}</small></span></div>
      <button onClick={()=>go('profile')}><span className="orientation-icon"><Palette size={20}/></span><span><strong>Un atelier à votre image</strong><small>Profil, couleurs et ordre des rubriques</small></span><ArrowUpRight size={16}/></button>
    </section>
    {!hasPlayers&&<section className="dashboard-start card"><div><span className="eyebrow">PREMIERS PAS</span><h2>Votre club prend vie avec ses données.</h2><p>Importez vos joueurs, découvrez leurs profils, puis préparez votre première composition. Le guide vous accompagne à chaque étape.</p></div><button className="button primary" onClick={()=>go('settings')}>Importer mes joueurs<ArrowRight size={16}/></button><button className="button secondary" onClick={()=>go('guide')}>Voir le tutoriel</button></section>}
    <div className="dashboard-widgets">{(profile.dashboard_sections??defaultProfile.dashboard_sections).map(id=><div className={'dashboard-widget widget-'+id} key={id}>{sections[id]}</div>)}</div>
    {!profile.dashboard_sections.length&&<Empty title="Votre accueil est en mode essentiel" action={<button className="button primary" onClick={()=>go('profile')}>Choisir mes rubriques</button>}>Réactivez les priorités, les chiffres ou les courbes depuis Profil & affichage.</Empty>}
    <div className="dashboard-bottom"><span>Besoin d’un repère ? Le mode d’emploi suit l’écran que vous consultez.</span><button className="text-button" onClick={()=>go('guide')}>Parcourir le tutoriel<ArrowRight size={16}/></button></div>
  </>;
}
