import {comparePlayerValues,matchesPlayerSearch} from './player-table.ts';

export type CoachingKind='instructions'|'report'|'statistics';
export type CoachingPeriod={scope:string;season:number|null;observed_at:string};
export type CounterPlayer={player_id:string;player_name?:string|null;counters:Record<string,number|null>;tackle_success_rate?:number|null};
export type SourceInfo={source?:string;source_resource?:string;source_game_date?:{season:number;round:number;day:number}|null;
  source_format?:'html'|'eml';club_name?:string|null;club_id?:string|null};
export type Instructions={key:string;observed_at:string;team_skills:(string|null)[]|null;youth_skills:(string|null)[]|null;individual:{player_id:string;player_name?:string|null;skill:string;sessions:number|null}[]|null;provenance?:SourceInfo};
export type SkillChange={skill:string;before:number|null;after:number|null;before_label?:string|null;after_label?:string|null};
type ReportEnergy={kind:'label';before:string|null;after:string|null}
  |{kind:'numeric';scale:'unreported';before:number|null;after:number|null};
type ReportSkill={skill:string;sessions:number|null;pops?:SkillChange[]|null;trainer?:{name:string|null;level:number|null;type:string|null}|null};
export type ReportPlayer={player_id:string;player_name?:string|null;csr_before?:number|null;csr_after?:number|null;
  energy?:ReportEnergy|null;energy_before?:number|null;energy_after?:number|null;
  pops?:SkillChange[]|null;drops?:SkillChange[]|null;skills?:ReportSkill[]|null};
export type TrainingReport={key:string;report_id:string|null;season:number;round:number;observed_at:string;
  team?:{skills?:string[]|null;players?:ReportPlayer[]|null}|null;individual?:{players?:ReportPlayer[]|null}|null;
  provenance?:SourceInfo|null;schema_version?:number;source_disagreement?:boolean};
export type PlayerStatistics=CoachingPeriod&{key:string;requested_count:number;missing_player_ids:string[];players:CounterPlayer[];provenance?:SourceInfo};
export type CoachingBundle={team_id:string;revision:number;instructions:Instructions|null;reports:TrainingReport[];statistics:PlayerStatistics[];history_limit:number;report_total:number;statistics_total:number;report_offset:number;statistics_offset:number};
export type CoachingPreview={team_id:string;kind:CoachingKind;preview_id:string;expires_at:string;expected_revision:number;status:'available'|'empty';already_imported:boolean;
  warnings:string[];identity?:{club_name:string;club_id:string|null;player_count:number;roster_match_count:number|null;missing_player_ids:string[]|null};
  data:Instructions|TrainingReport|PlayerStatistics};

export type CsrCoverage={delta:number|null;population:number|null;known:number;unknown:number|null;positive:number;negative:number;stable:number};
export type CountCoverage={total:number|null;entries:number;known:number;unknown:number};
type PhaseSummary={
  csr:CsrCoverage;
  sessions:(CountCoverage&{missingSkillLists:number})|null;
  rises:CountCoverage|null;
  drops:CountCoverage|null;
};
type Discontinuity=Pick<ReportPlayer,'player_id'|'player_name'>&{team_after:number;individual_before:number};
export type TrainingReportSummary={
  team:PhaseSummary;
  individual:PhaseSummary;
  continuous:{csr:CsrCoverage;populationIncomplete:boolean;players:Map<string,number|null>;discontinuities:Discontinuity[]};
};

const knownNumber=(value:number|null|undefined):value is number=>typeof value==='number'&&Number.isFinite(value);

export function csrDelta(before:number|null|undefined,after:number|null|undefined):number|null{
  return knownNumber(before)&&knownNumber(after)?after-before:null;
}

function csrCoverage(deltas:(number|null)[]|null):CsrCoverage{
  const population=deltas?.length??null;
  const known=deltas?.filter(knownNumber)??[];
  return {
    delta:known.length?known.reduce((sum,value)=>sum+value,0):null,
    population,known:known.length,unknown:population===null?null:population-known.length,
    positive:known.filter(value=>value>0).length,
    negative:known.filter(value=>value<0).length,
    stable:known.filter(value=>value===0).length,
  };
}

function countCoverage(values:(number|null|undefined)[]):CountCoverage{
  const known=values.filter(knownNumber);
  return {total:known.length?known.reduce((sum,value)=>sum+value,0):null,
    entries:values.length,known:known.length,unknown:values.length-known.length};
}

function phaseSummary(players:ReportPlayer[]|null,individual:boolean):PhaseSummary{
  const csr=csrCoverage(players?.map(player=>csrDelta(player.csr_before,player.csr_after))??null);
  if(!players)return {csr,sessions:null,rises:null,drops:null};
  const drops=countCoverage(players.map(player=>player.drops?.length));
  if(!individual)return {csr,sessions:null,rises:countCoverage(players.map(player=>player.pops?.length)),drops};

  const skills=players.flatMap(player=>player.skills??[]);
  const sessions={...countCoverage(skills.map(skill=>skill.sessions)),
    missingSkillLists:players.filter(player=>player.skills==null).length};
  const rises=countCoverage(skills.map(skill=>skill.pops?.length));
  // A rise may appear both on the player and under a trained skill.
  // Match the skill and both source values to preserve distinct transitions.
  const riseCounts=players.map(player=>{
    const observed=player.skills?.flatMap(skill=>skill.pops??[])??[];
    if(player.pops==null&&!player.skills?.some(skill=>skill.pops!=null))return null;
    const transitions=[...observed,...(player.pops??[])].map(change=>JSON.stringify([
      change.skill,change.before,change.after,change.before_label??null,change.after_label??null,
    ]));
    return new Set(transitions).size;
  });
  return {csr,sessions,rises:{...rises,total:countCoverage(riseCounts).total},drops};
}

export function trainingReportSummary(report:TrainingReport):TrainingReportSummary{
  const teamPlayers=report.team?.players??null;
  const individualPlayers=report.individual?.players??null;
  const team=new Map(teamPlayers?.map(player=>[player.player_id,player]));
  const individual=new Map(individualPlayers?.map(player=>[player.player_id,player]));
  const players=new Map<string,number|null>();
  const discontinuities:Discontinuity[]=[];
  for(const player_id of new Set([...team.keys(),...individual.keys()])){
    const first=team.get(player_id),second=individual.get(player_id);
    const team_after=first?.csr_after,individual_before=second?.csr_before;
    let delta=null;
    if(knownNumber(team_after)&&knownNumber(individual_before)){
      if(team_after===individual_before)delta=csrDelta(first?.csr_before,second?.csr_after);
      else discontinuities.push({player_id,player_name:second?.player_name??first?.player_name,team_after,individual_before});
    }
    players.set(player_id,delta);
  }
  return {
    team:phaseSummary(teamPlayers,false),
    individual:phaseSummary(individualPlayers,true),
    continuous:{csr:csrCoverage([...players.values()]),populationIncomplete:teamPlayers===null||individualPlayers===null,players,discontinuities},
  };
}

export function statisticsRows<T extends CounterPlayer>(players:T[],query:string,metric:string,descending:boolean):T[]{
  return players.filter(player=>matchesPlayerSearch({id:player.player_id,name:player.player_name||''},query))
    .sort((a,b)=>comparePlayerValues(a.counters[metric],b.counters[metric],descending)||a.player_id.localeCompare(b.player_id));
}

export function counterChange(before:CoachingPeriod,after:CoachingPeriod,previous:number|null|undefined,current:number|null|undefined):{delta:number|null;reason:string|null}{
  if(before.scope!==after.scope||before.season!==after.season)return {delta:null,reason:'different_period'};
  if(!Number.isFinite(Date.parse(before.observed_at))||!Number.isFinite(Date.parse(after.observed_at))||Date.parse(before.observed_at)>=Date.parse(after.observed_at))return {delta:null,reason:'invalid_order'};
  if(typeof previous!=='number'||typeof current!=='number'||!Number.isFinite(previous)||!Number.isFinite(current))return {delta:null,reason:'unknown'};
  if(current<previous)return {delta:null,reason:'counter_reset'};
  return {delta:current-previous,reason:null};
}
