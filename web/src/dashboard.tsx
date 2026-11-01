import {tr} from './i18n';
import {ArrowRight,ArrowUpRight,CalendarRange,CheckCircle2,Clock3,Database,Palette,Sprout,Star,Target,TrendingUp,Users} from 'lucide-react';
import type {ReactNode} from 'react';
import type {Actions} from './App';
import {date} from './types';
import {Empty,Metric,Pill} from './components';
import {DailyHub} from './workbench';
import {StarterCard} from './starter';
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
    metrics:<section className="dashboard-numbers" aria-label={tr("Les chiffres de votre club")}><div className="metrics">
      <Metric label={tr("Seniors")} value={d.squad_source?d.squad.length:'—'} hint={tr("Préparer l’effectif et le XV")} icon={<Users size={20}/>} onClick={()=>go('squad')}/>
      <Metric label={tr("Jeunes en formation")} value={d.academy_source?youth.length:'—'} hint={tr("Suivre la relève du club")} icon={<Sprout size={20}/>} onClick={()=>go('academy')}/>
      <Metric label={tr("Potentiels U20")} value={d.academy_source?ready.length:'—'} hint={tr("Projection d’âge indicative")} icon={<Target size={20}/>} accent onClick={()=>go('academy')}/>
      <Metric label={tr("Jeunes suivis")} value={tracked.length} hint={tr("Vos favoris de l’académie")} icon={<Star size={20}/>} onClick={()=>go('academy')}/>
    </div></section>,
    progress:<ProgressionSummary {...props}/>,
    talents:<section className="card"><div className="card-heading"><div><span className="eyebrow">{tr("LA RELÈVE")}</span><h2>{tr("La relève à suivre de près")}</h2></div><button className="text-button" onClick={()=>go('academy')}>{tr("Toute l’académie")}<ArrowUpRight size={16}/></button></div>
      {priorities.length?<div className="talent-list">{priorities.map(p=><button className="talent-row" onClick={()=>openPlayer(p,true)} key={p.id}>
        <span className="player-avatar">{p.name.split(' ').map(n=>n[0]).slice(0,2).join('')}</span><span className="talent-name"><strong>{p.name}</strong><small>{p.age??'—'}{tr(" ans · ")}{p.metrics.known_skills}{tr("/10 compétences connues")}</small></span>
        {p.wc_projection?<Pill>{tr("Projection S")}{p.wc_projection}</Pill>:<Pill tone="neutral">{tr("À observer")}</Pill>}<ArrowUpRight size={16}/></button>)}</div>:<Empty title={tr("Faisons connaissance avec vos jeunes")} action={<button className="button primary" onClick={()=>go('settings')}>{tr("Importer mon académie")}</button>}>{tr("Connectez Classic ou importez votre fichier : vous pourrez alors examiner les premiers profils de votre académie.")}</Empty>}
      <div className="card-foot">{d.academy_source?<>{tr("Dernière observation : ")}{date(d.academy_source.observed_at)} · {d.academy_source.source}</>:tr("Les compétences masquées restent inconnues.")}</div>
    </section>,
    actions:<section className="card dashboard-actions"><div className="card-heading"><div><span className="eyebrow">{tr("VOTRE PROCHAINE DÉCISION")}</span><h2>{tr("À vous de préparer la suite")}</h2></div></div><div className="dashboard-action-grid">
      {[{label:'Préparer mon XV',detail:'Mettez les profils en regard et choisissez votre composition.',page:'optimization',Icon:Users},{label:'Organiser ma semaine',detail:'Matchs, séances et rappels dans un calendrier.',page:'season',Icon:CalendarRange},{label:'Suivre les progrès',detail:'Voyez ce qui a changé d’une observation à l’autre.',page:'progression',Icon:TrendingUp}].map(({Icon,...a})=><button key={a.page} onClick={()=>go(a.page)}><Icon size={23}/><strong>{tr(a.label)}</strong><span>{tr(a.detail)}</span><ArrowRight size={18}/></button>)}
    </div><p className="dashboard-local-note">{tr("Ces préparations restent dans l’outil. Les envois vers le jeu se contrôlent séparément dans Mode vacances.")}</p></section>,
    gallery:<RugbyGallery go={go}/>,
  };
  return <>
    <MatchdayHero club={d.current_team.name} banner={profile.banner} onExplore={()=>go('optimization')}/>
    <section className="dashboard-orientation" aria-label={tr("Les repères de votre espace")}>
      <button onClick={()=>go('settings')}><span className={'orientation-icon '+(connected?'ready':'')}>{connected?<CheckCircle2 size={20}/>:<Database size={20}/>}</span><span><strong>{connected?tr("Compte Classic relié"):hasPlayers?tr("Données importées"):tr("Commencer par vos données")}</strong><small>{connected?tr('Clubs dans votre espace : {count}',{count:d.teams.length}):tr("Connecter Classic ou importer un fichier")}</small></span><ArrowUpRight size={16}/></button>
      <div><span className="orientation-icon"><Clock3 size={20}/></span><span><strong>{tr("Dernières observations")}</strong><small>{tr("Seniors : ")}{d.squad_source?date(d.squad_source.observed_at):tr("à importer")}<br/>{tr("Académie : ")}{d.academy_source?date(d.academy_source.observed_at):tr("à importer")}</small></span></div>
      <button onClick={()=>go('profile')}><span className="orientation-icon"><Palette size={20}/></span><span><strong>{tr("Un atelier à votre image")}</strong><small>{tr("Profil, couleurs et ordre des rubriques")}</small></span><ArrowUpRight size={16}/></button>
    </section>
    {!hasPlayers&&<section className="dashboard-start card"><div><span className="eyebrow">{tr("PREMIERS PAS")}</span><h2>{tr("Commençons par votre effectif.")}</h2><p>{tr("Importez vos joueurs pour lire les premières tendances et préparer votre XV. Le guide vous accompagne, du premier fichier aux choix de composition.")}</p></div><button className="button primary" onClick={()=>go('settings')}>{tr("Importer mes joueurs")}<ArrowRight size={16}/></button><button className="button secondary" onClick={()=>go('guide')}>{tr("Voir le tutoriel")}</button></section>}
    <StarterCard d={d} go={go} busy={props.busy}/>
    <div className="dashboard-widgets">{(profile.dashboard_sections??defaultProfile.dashboard_sections).map(id=><div className={'dashboard-widget widget-'+id} key={id}>{sections[id]}</div>)}</div>
    {!profile.dashboard_sections.length&&<Empty title={tr("Votre accueil est en mode essentiel")} action={<button className="button primary" onClick={()=>go('profile')}>{tr("Choisir mes rubriques")}</button>}>{tr("Réactivez les priorités, les chiffres ou les courbes depuis Profil & affichage.")}</Empty>}
    <div className="dashboard-bottom"><span>{tr("Un point à éclaircir ? Le mode d’emploi vous accompagne sur chaque écran.")}</span><button className="text-button" onClick={()=>go('guide')}>{tr("Parcourir le tutoriel")}<ArrowRight size={16}/></button></div>
  </>;
}
