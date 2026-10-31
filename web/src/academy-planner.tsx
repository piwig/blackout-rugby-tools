import {localeTag,tr} from './i18n';
import {useEffect,useState} from 'react';
import {ArrowRight,CalendarRange,RefreshCw,Star,Target} from 'lucide-react';
import {request} from './App';
import {date,labels,skills,type State} from './types';
import {academyNumber,academyTarget,prioritizeAcademy,projectAcademy,type AcademyGoal} from './academy-planner-model';
import './academy-planner.css';

type Props={d:State;draftSeason:number;draftGrid:string[][];dirty:boolean;locked:boolean;onSeason:(season:number)=>void};
const decimal=(value:number|null)=>value===null?tr('Non dévoilé'):new Intl.NumberFormat(localeTag(),{maximumFractionDigits:2}).format(value);
const nextWeek=(d:State,season:number)=>season===d.game_date?.season?(d.game_date.round>=16?1:d.game_date.round+1):1;

export function AcademyPlanner(props:Props) {
  return <AcademyPlannerClub key={JSON.stringify([props.d.user.username,props.d.csrf,props.d.current_team.id])} {...props}/>;
}

function AcademyPlannerClub(props:Props) {
  const {d}=props;
  const [goals,setGoals]=useState<AcademyGoal[]|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    let active=true;setGoals(null);setError('');
    void request('/insights/'+encodeURIComponent(d.current_team.id),undefined,d.csrf).then(result=>{
      if(active&&result.team_id===d.current_team.id)setGoals(result.document.goals);
    }).catch((e:Error)=>{if(active)setError(e.message)});
    return()=>{active=false};
  },[d.current_team.id,d.csrf,d.academy_source?.id,attempt]);
  return <AcademyProjectionPanel {...props} goals={goals} goalsError={tr(error)} onReloadGoals={()=>setAttempt(value=>value+1)}/>;
}

export function AcademyProjectionPanel({d,draftSeason,draftGrid,dirty,locked,onSeason,goals,goalsError,onReloadGoals}:Props&{goals:AcademyGoal[]|null;goalsError:string;onReloadGoals:()=>void}) {
  const players=prioritizeAcademy(d.academy);
  const [playerId,setPlayerId]=useState(players[0]?.id||''),[generation,setGeneration]=useState('all');
  const [startSeason,setStartSeason]=useState(String(draftSeason===d.game_date?.season&&d.game_date.round>=16?draftSeason+1:draftSeason)),[startWeek,setStartWeek]=useState(String(nextWeek(d,draftSeason))),[horizon,setHorizon]=useState('3'),[gain,setGain]=useState('0.2');
  const [targets,setTargets]=useState<Record<string,Record<string,string>>>({});
  const filtered=players.filter(player=>generation==='all'||String(player.wc_projection??'unknown')===generation);
  const player=filtered.find(candidate=>candidate.id===playerId)||filtered[0];
  const goal=goals?.find(candidate=>candidate.player_id===player?.id);
  const plans={...d.plans,[draftSeason]:draftGrid};
  const gainNumber=gain.trim()===''?NaN:Number(gain),start=Number(startSeason);
  const projection=projectAcademy({player:player||{},plans,gameDate:d.game_date,startSeason:start,startWeek:Number(startWeek),horizon:Number(horizon),gain:gainNumber});
  const final=projection.seasons.at(-1);
  const draftIncluded=projection.seasons.some(item=>item.season===draftSeason)&&dirty;
  const targetValue=(skill:string)=>player?(targets[player.id]?.[skill]??(goal?.skill===skill&&goal.target!==null?String(goal.target):'')):'';
  const generationOptions=[...new Set(players.map(candidate=>candidate.wc_projection).filter(value=>value!=null))].sort((a,b)=>a!-b!);
  const targetStatus=(skill:string)=>{
    const status=academyTarget(final?.projected[skill as typeof skills[number]],targetValue(skill),gainNumber);
    switch(status.status){
      case 'unset':return 'Aucune cible';
      case 'unknown':return 'Valeur inconnue';
      case 'above-cap':return 'Hors plafond des séances';
      case 'no-gain':return 'Gain nul : cible non atteinte';
      case 'remaining':return `${status.sessions} séance(s) supplémentaire(s)`;
      case 'reached':return 'Cible atteinte dans la simulation';
    }
  };
  return <section className="card academy-planner" aria-labelledby="academy-planner-title">
    <div className="card-heading"><div><span className="eyebrow">{tr("ACADÉMIE / PLUSIEURS SAISONS")}</span><h2 id="academy-planner-title"><Target size={21}/>{tr("Préparer la suite pour vos jeunes.")}</h2></div><span className="academy-planner-badge">{tr("Simulation locale")}</span></div>
    <div className="academy-planner-body">
      <p>{tr("Choisissez un jeune, regardez où il en est, puis confrontez vos cibles aux séances prévues. La simulation cumule vos hypothèses sur 1 à 4 saisons.")}</p>
      <div className="academy-planner-controls">
        <label>{tr("Saison de départ")}<input type="number" min="1" max="999" step="1" value={startSeason} onChange={e=>setStartSeason(e.target.value)}/></label>
        <label>{tr("Première semaine")}<input type="number" min="1" max="16" step="1" value={startWeek} onChange={e=>setStartWeek(e.target.value)}/></label>
        <label>{tr("Horizon")}<select value={horizon} onChange={e=>setHorizon(e.target.value)}>{[1,2,3,4].map(value=><option key={value} value={value}>{value}{value>1?tr(" saisons"):tr(" saison")}</option>)}</select></label>
        <label>{tr("Gain par séance")}<input type="number" min="0" max="1" step="0.01" value={gain} onChange={e=>setGain(e.target.value)}/></label>
      </div>
      <p className="tiny">{tr("Hypothèse de Franck du 31 octobre 2026 : +0,20 par séance, plafond à 13,99. L’IGT peut permettre d’atteindre 14 mais n’est pas prédit ici. Un 14 déjà observé est conservé. Le gain est modifiable pour comparer vos hypothèses.")}</p>
      <p className="academy-planner-date"><CalendarRange size={17}/>{d.game_date?`Date de jeu importée : saison ${d.game_date.season}, semaine ${d.game_date.round}, jour ${d.game_date.day}.`:tr("Date de jeu indisponible.")}{tr(" Les semaines passées et la semaine courante sont exclues : les créneaux n’ont pas d’horaire. Actualisez les données si cette date est ancienne.")}</p>
      {projection.error?<p className="notice error" role="alert">{tr(projection.error)}</p>:<>
        <div className="academy-season-cards" aria-label={tr("Saisons de la projection")}>{projection.seasons.map(season=><article key={season.season}>
          <div><strong>{tr("Saison ")}{season.season}</strong><span>{season.season===draftSeason&&dirty?tr("Brouillon affiché"):d.plans[String(season.season)]?tr("Plan enregistré"):tr("Aucun plan enregistré")}</span></div>
          <p><b>{season.sessions}</b>{season.sessions>1?tr(" séances"):tr(" séance")}{season.sessions>1?tr(" futures"):tr(" future")}</p>
          <small>{season.firstWeek?`Semaines ${season.firstWeek}–16 · ${season.openSlots} case(s) libre(s)`:tr("Aucune semaine future retenue")}</small>
          <button type="button" className="text-button" disabled={locked} onClick={()=>onSeason(season.season)} aria-label={tr("Modifier le planning de la saison ")+season.season}>{season.season===draftSeason?tr("Saison affichée"):tr("Modifier cette saison")}<ArrowRight size={14}/></button>
        </article>)}</div>
        <p className="tiny">{projection.totalSessions}{tr(" séances comptées sur l’horizon. ")}{draftIncluded?tr("Le brouillon affiché est inclus ; enregistrez la saison pour le conserver."):tr("Les autres saisons utilisent leurs plans enregistrés.")}{tr(" Une saison sans plan n’ajoute aucun gain.")}</p>
      </>}
      <div className="academy-planner-player-controls">
        <label>{tr("Génération indicative")}<select value={generation} onChange={e=>setGeneration(e.target.value)}><option value="all">{tr("Toutes les générations")}</option>{generationOptions.map(value=><option key={value} value={value}>{tr("Saison ")}{value}</option>)}<option value="unknown">{tr("Sans repère de génération")}</option></select></label>
        <label>{tr("Jeune à projeter")}<select value={player?.id||''} onChange={e=>setPlayerId(e.target.value)} disabled={!filtered.length}>{!filtered.length&&<option value="">{tr("Aucun jeune pour ce filtre")}</option>}{filtered.map(candidate=><option key={candidate.id} value={candidate.id}>{candidate.name} · {decimal(academyNumber(candidate.stars))} ★{candidate.wc_projection?tr(" · génération S")+candidate.wc_projection:''}</option>)}</select></label>
      </div>
      <p className="tiny">{tr("Ordre de priorité : étoiles, puis génération indicative existante. Ce repère personnel ne certifie pas l’éligibilité U20. L’âge ne sert pas à classer les joueurs.")}</p>
      {goals===null&&!goalsError&&<p className="tiny" role="status">{tr("Lecture des objectifs enregistrés…")}</p>}
      {goalsError&&<p className="notice" role="status">{tr("Objectifs enregistrés indisponibles : ")}{goalsError}{tr(" Les cibles locales restent utilisables. ")}<button type="button" className="text-button" onClick={onReloadGoals}><RefreshCw size={14}/>{tr("Relire les objectifs")}</button></p>}
      {player?<>
        <div className="academy-player-summary"><div><Star size={18}/><strong>{player.name}</strong><span>{decimal(academyNumber(player.stars))}{tr(" étoiles")}</span></div><span>{tr("Observation du ")}{date(d.academy_source?.observed_at)}</span></div>
        {goal&&<p className="academy-saved-goal"><strong>{tr("Objectif enregistré :")}</strong> {goal.text}{goal.skill&&goal.target!==null?` · ${tr(labels[goal.skill])} ${decimal(goal.target)}`:''}{goal.due_season?` · échéance S${goal.due_season}`:''}{tr(". Les cibles du tableau sont comparées en fin d’horizon.")}</p>}
        {!projection.error&&<div className="table-scroll academy-projection-scroll" role="region" tabIndex={0} aria-label={tr("Compétences projetées par saison")}><table className="academy-projection-table">
          <caption>{tr("Niveaux hypothétiques en fin de saison, si le jeune reste à l’académie durant tout l’horizon. Sortie de l’académie, promotion et IGT non simulés.")}</caption>
          <thead><tr><th scope="col">{tr("Compétence")}</th><th scope="col">{tr("Observée")}</th><th scope="col">{tr("Cible locale")}</th>{projection.seasons.map(season=><th scope="col" key={season.season}>{tr("Fin S")}{season.season}<small>{season.sessions}{tr(" séances au total")}</small></th>)}<th scope="col">{tr("Reste après l’horizon")}</th></tr></thead>
          <tbody>{skills.map(skill=><tr key={skill}><th scope="row">{tr(labels[skill])}</th><td>{decimal(academyNumber(player[skill]))}</td><td><input aria-label={tr("Cible ")+labels[skill]+tr(" pour ")+player.name} type="number" min="0" max="21" step="0.01" value={targetValue(skill)} placeholder={tr("Aucune")} onChange={e=>setTargets({...targets,[player.id]:{...targets[player.id],[skill]:e.target.value}})}/></td>{projection.seasons.map(season=><td key={season.season}><strong>{decimal(season.projected[skill])}</strong><small>{season.counts[skill]}{tr(" séance(s)")}{season.gains[skill]!==null&&season.gains[skill]!>0?' · +'+decimal(season.gains[skill]):''}</small></td>)}<td className="academy-target-status">{tr(targetStatus(skill))}</td></tr>)}</tbody>
        </table></div>}
        <p className="tiny">{tr("Les cibles locales reprennent l’objectif enregistré quand il existe. Vos essais restent sur cet écran et ne remplacent pas les objectifs conservés dans Académie. Une compétence non dévoilée reste inconnue, même avec des séances planifiées.")}</p>
      </>:<p className="notice">{players.length?tr("Aucun jeune ne correspond à cette génération."):tr("Importez vos jeunes pour examiner leur trajectoire dans cette simulation. Vous pouvez déjà préparer les saisons ci-dessus.")}</p>}
    </div>
  </section>;
}
