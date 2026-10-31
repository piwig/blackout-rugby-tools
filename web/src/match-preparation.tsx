import {localeTag,tr} from './i18n';
import {useEffect,useId,useRef,useState} from 'react';
import {CalendarRange,ChartNoAxesCombined,RefreshCw,Search,ShieldCheck} from 'lucide-react';
import {request} from './App';
import {fmt,type State} from './types';
import './match-preparation.css';

type Fixture={id:string;home_id:string;guest_id:string;opponent_id:string;side:'home'|'guest';start_at:string|null;finish_at:string|null;competition:string};
type Calendar={team_id:string;retrieved_at:string;fixtures:Fixture[];excluded_count:number};
type Metric={key:string;label:string;unit:string;average:number|null;sample_count:number};
type Report={team_id:string;retrieved_at:string;fixture:Fixture;opponent_id:string;matches:(Fixture&{metrics:Record<string,number|null>})[];summary:Metric[];missing_stats:{id:string;finish_at:string;reason:string}[];history_count:number;eligible_count:number;excluded_count:number;history_limit:number;match_limit:number;methodology:string[]};
type Props={d:State;busy?:boolean};
const moment=(value:string|null)=>value?new Date(value).toLocaleString(localeTag(),{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):tr('Date inconnue');
const unitValue=(value:number|null|undefined,unit:string)=>value==null?'—':`${fmt(value)}${unit==='%'?' %':''}`;

export function MatchPreparation(props:Props) {
  return <ScopedMatchPreparation key={JSON.stringify([props.d.user.username,props.d.csrf,props.d.current_team.id])} {...props}/>;
}

function ScopedMatchPreparation({d,busy=false}:Props) {
  const titleId=useId(),live=useRef(true),operation=useRef(false);
  const [calendar,setCalendar]=useState<Calendar|null>(null),[selectedId,setSelectedId]=useState(''),[report,setReport]=useState<Report|null>(null);
  const [pending,setPending]=useState<'calendar'|'scout'|null>(null),[error,setError]=useState('');
  const selection=d.current_team.id.includes(':'),locked=busy||pending!==null;
  useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
  const run=async(action:'calendar'|'scout')=>{
    if(operation.current||busy||selection||action==='scout'&&!selectedId)return;
    operation.current=true;setPending(action);setError('');
    if(action==='scout')setReport(null);
    const fixtureId=selectedId;
    try{
      if(action==='calendar'){
        const result=await request('/match-preparation/fixtures',{team_id:d.current_team.id},d.csrf) as Calendar;
        if(result.team_id!==d.current_team.id||!Array.isArray(result.fixtures))throw new Error('Le calendrier reçu ne correspond pas au club affiché. Actualisez votre espace.');
        if(live.current){setCalendar(result);setSelectedId(result.fixtures[0]?.id||'');setReport(null)}
      }else{
        const result=await request('/match-preparation/scout',{team_id:d.current_team.id,fixture_id:fixtureId},d.csrf) as Report;
        if(result.team_id!==d.current_team.id||result.fixture?.id!==fixtureId||!Array.isArray(result.matches)||!Array.isArray(result.summary)||!Array.isArray(result.missing_stats))throw new Error('L’analyse reçue ne correspond pas à cette rencontre. Actualisez le calendrier.');
        if(live.current){setReport(result);setCalendar(previous=>previous?{...previous,fixtures:previous.fixtures.map(item=>item.id===fixtureId?result.fixture:item)}:previous)}
      }
    }catch(cause){if(live.current)setError(cause instanceof Error?cause.message:'La lecture Classic a échoué. Réessayez.')}
    finally{operation.current=false;if(live.current)setPending(null)}
  };
  const selected=calendar?.fixtures.find(item=>item.id===selectedId);
  return <section className="card match-preparation" aria-labelledby={titleId} aria-busy={pending!==null}>
    <div className="card-heading"><div><span className="eyebrow">{tr("PRÉPARER LA PROCHAINE RENCONTRE")}</span><h2 id={titleId}><CalendarRange size={22}/>{tr("Qui se présente en face ?")}</h2></div><span className="match-prep-tag"><ShieldCheck size={14}/>{tr("Lecture Classic")}</span></div>
    <div className="match-prep-body">
      <p>{tr("Le prochain rendez-vous de ")}{d.current_team.name}{tr(" se prépare ici. Actualisez le calendrier, choisissez une rencontre, puis passez son adversaire en revue : jusqu’à cinq matchs récents, terminés, avec des statistiques disponibles et non signalés comme matchs de bots par Classic.")}</p>
      {selection?<p className="notice">{tr("Cette préparation est actuellement réservée aux clubs. La lecture des statistiques de match U20 et nationales doit encore être vérifiée ; aucun calendrier de club n’est utilisé pour votre sélection.")}</p>:<>
        <div className="match-prep-actions"><button type="button" className="button secondary" disabled={locked} onClick={()=>void run('calendar')}><RefreshCw size={16}/>{pending==='calendar'?tr("Lecture du calendrier…"):tr("Actualiser le calendrier")}</button>{calendar&&<span>{tr("Lu le ")}{moment(calendar.retrieved_at)}</span>}</div>
        {error&&<p className="notice error" role="alert">{tr(error)}</p>}
        {pending&&<p className="match-prep-loading" role="status">{pending==='calendar'?tr("On fait le point sur les prochains rendez-vous dans Classic…"):tr("On remonte les dernières rencontres pour réunir les statistiques disponibles. La recherche peut prendre un moment : les lectures Classic sont espacées et limitées à 20 matchs.")}</p>}
        {calendar&&<>
          {calendar.excluded_count>0&&<p className="tiny">{calendar.excluded_count}{tr(" entrée(s) non retenue(s) : date inconnue, rencontre passée ou appartenance au club non confirmée.")}</p>}
          {calendar.fixtures.length?<div className="match-prep-selection"><label>{tr("Rencontre à préparer")}<select disabled={locked} value={selectedId} onChange={e=>{setSelectedId(e.target.value);setReport(null);setError('')}}>{calendar.fixtures.map((fixture,index)=><option key={fixture.id} value={fixture.id}>{index===0?tr("Prochain match · "):''}{moment(fixture.start_at)} · #{fixture.opponent_id} · {fixture.side==='home'?tr("Domicile"):tr("Extérieur")} · {fixture.competition}</option>)}</select></label><button type="button" className="button primary" disabled={locked||!selectedId} onClick={()=>void run('scout')}><Search size={16}/>{pending==='scout'?tr("Étude en cours…"):tr("Étudier cet adversaire")}</button></div>:<p className="notice">{tr("Aucun prochain rendez-vous avec une date exploitable n’a été trouvé pour ce club. Vous pourrez relancer la lecture lorsque le calendrier sera renseigné dans Classic.")}</p>}
          {selected&&<p className="match-prep-fixture">{tr("Rencontre ")}<strong>#{selected.id}</strong>{tr(" · adversaire ")}<strong>#{selected.opponent_id}</strong> · {selected.side==='home'?tr("à domicile"):tr("à l’extérieur")} · {moment(selected.start_at)}{tr(". Les horaires sont affichés dans le fuseau de votre navigateur.")}</p>}
        </>}
        {!calendar&&!pending&&!error&&<p className="tiny">{tr("La lecture démarre uniquement avec le bouton ci-dessus. Aucun planning ni aucune composition ne sont envoyés dans le jeu.")}</p>}
        {report&&<div className="match-prep-report">
          <header><div><span className="eyebrow">{tr("ADVERSAIRE #")}{report.opponent_id}</span><h3><ChartNoAxesCombined size={20}/>{report.matches.length}{report.matches.length>1?tr(" rencontres"):tr(" rencontre")}{report.matches.length>1?tr(" documentées"):tr(" documentée")}</h3></div><span>{tr("Statistiques lues le ")}{moment(report.retrieved_at)}</span></header>
          <p className="muted">{report.history_count}{tr(" rencontre(s) retournée(s) sur les ")}{report.history_limit}{tr(" demandées ; ")}{report.eligible_count}{tr(" terminée(s), datée(s) et non signalée(s) comme matchs de bots. ")}{report.excluded_count}{tr(" exclue(s). Les ")}{report.match_limit}{tr(" plus récentes avec statistiques utilisables au maximum sont retenues.")}</p>
          {report.matches.length?<>
            <div className="match-prep-metrics" aria-label={tr("Moyennes observées de l’adversaire")}>{report.summary.map(metric=><div key={metric.key}><span>{metric.label}</span><strong>{unitValue(metric.average,metric.unit)}</strong><small>{metric.average===null?tr("Donnée indisponible"):`Moyenne · ${metric.sample_count}/${report.matches.length} matchs`}</small></div>)}</div>
            <div className="table-scroll match-prep-table-scroll" role="region" tabIndex={0} aria-label={tr("Derniers matchs documentés de l’adversaire")}><table><caption>{tr("Valeurs du côté de l’adversaire étudié, classées par fin réelle du match.")}</caption><thead><tr><th scope="col">{tr("Match terminé")}</th><th scope="col">{tr("Adversaire rencontré")}</th><th scope="col">{tr("Score de l’équipe étudiée")}</th><th scope="col">{tr("Essais")}</th><th scope="col">{tr("Possession")}</th><th scope="col">{tr("Territoire")}</th><th scope="col">{tr("Plaquages manqués")}</th><th scope="col">{tr("Pénalités concédées")}</th></tr></thead><tbody>{report.matches.map(match=><tr key={match.id}><th scope="row">#{match.id}<small>{moment(match.finish_at)} · {match.competition}</small></th><td>#{match.opponent_id}<small>{match.side==='home'?tr("Équipe étudiée à domicile"):tr("Équipe étudiée à l’extérieur")}</small></td><td><strong>{fmt(match.metrics.points_for)} – {fmt(match.metrics.points_against)}</strong></td><td>{fmt(match.metrics.tries)}</td><td>{unitValue(match.metrics.possession_pct,'%')}</td><td>{unitValue(match.metrics.territory_pct,'%')}</td><td>{fmt(match.metrics.missed_tackles)}</td><td>{fmt(match.metrics.penalties_conceded)}</td></tr>)}</tbody></table></div>
          </>:<p className="notice">{tr("Ces rencontres ne donnent pas encore de statistiques exploitables. Il faudra d’autres observations pour lire les tendances de cet adversaire ; aucune moyenne ni tactique ne peut être déduite ici.")}</p>}
          {report.missing_stats.length>0&&<details className="match-prep-missing"><summary>{report.missing_stats.length}{tr(" match(s) terminé(s) sans statistiques utilisables")}</summary><ul>{report.missing_stats.map(match=><li key={match.id}>#{match.id} · {moment(match.finish_at)} · {match.reason}</li>)}</ul></details>}
          <details className="match-prep-method"><summary>{tr("Les données derrière cette lecture")}</summary><ul>{report.methodology.map(line=><li key={line}>{line}</li>)}</ul><p>{tr("Source : calendrier et statistiques d’équipes de l’API officielle Classic. Les équipes sont identifiées par leur numéro ; aucune lecture de joueurs ou de tactiques privées n’est nécessaire.")}</p></details>
        </div>}
      </>}
    </div>
  </section>;
}
