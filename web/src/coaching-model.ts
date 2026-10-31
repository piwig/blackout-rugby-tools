import {comparePlayerValues,matchesPlayerSearch} from './player-table.ts';

export type CoachingKind='instructions'|'report'|'statistics';
export type CoachingPeriod={scope:string;season:number|null;observed_at:string};
export type CounterPlayer={player_id:string;player_name?:string|null;counters:Record<string,number|null>;tackle_success_rate?:number|null};
export type SourceInfo={source_resource?:string;source_game_date?:{season:number;round:number;day:number}|null};
export type Instructions={key:string;observed_at:string;team_skills:(string|null)[]|null;youth_skills:(string|null)[]|null;individual:{player_id:string;player_name?:string|null;skill:string;sessions:number|null}[]|null;provenance?:SourceInfo};
export type SkillChange={skill:string;before:number|null;after:number|null};
export type ReportPlayer={player_id:string;player_name?:string|null;csr_before:number|null;csr_after:number|null;energy_before:number|null;energy_after:number|null;pops?:SkillChange[];drops?:SkillChange[];skills?:{skill:string;sessions:number|null;pops?:SkillChange[]}[]};
export type TrainingReport={key:string;report_id:string;season:number;round:number;observed_at:string;team:{skills:string[]|null;players:ReportPlayer[]}|null;individual:{players:ReportPlayer[]}|null;provenance?:SourceInfo};
export type PlayerStatistics=CoachingPeriod&{key:string;requested_count:number;missing_player_ids:string[];players:CounterPlayer[];provenance?:SourceInfo};
export type CoachingBundle={team_id:string;revision:number;instructions:Instructions|null;reports:TrainingReport[];statistics:PlayerStatistics[];history_limit:number;report_total:number;statistics_total:number;report_offset:number;statistics_offset:number};
export type CoachingPreview={team_id:string;kind:CoachingKind;preview_id:string;expires_at:string;expected_revision:number;status:'available'|'empty';already_imported:boolean;warnings:string[];data:Instructions|TrainingReport|PlayerStatistics};

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
