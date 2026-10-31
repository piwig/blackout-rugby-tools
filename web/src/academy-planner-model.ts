import {skills} from './types.ts';

export const ACADEMY_CAP=13.99;
type Skill=typeof skills[number];
type SkillValues=Record<Skill,number|null>;
type SkillCounts=Record<Skill,number>;
export type AcademyGoal={player_id:string;text:string;skill:string|null;target:number|null;due_season:number|null};
export type AcademyProjectionInput={player:Record<string,unknown>;plans:Record<string,string[][]>;gameDate:{season:number;round:number;day:number}|null;startSeason:number;startWeek:number;horizon:number;gain:number};
export type AcademySeasonProjection={season:number;saved:boolean;firstWeek:number|null;sessions:number;openSlots:number;counts:SkillCounts;projected:SkillValues;gains:SkillValues};

export function academyNumber(value:unknown):number|null {
  if(typeof value!=='number'&&typeof value!=='string'||typeof value==='string'&&!value.trim())return null;
  const number=Number(typeof value==='string'?value.replace(',','.'):value);
  return Number.isFinite(number)&&number>=0?number:null;
}
const rounded=(value:number)=>Math.round((value+Number.EPSILON)*100)/100;
const counts=()=>Object.fromEntries(skills.map(skill=>[skill,0])) as SkillCounts;
const integer=(value:number,min:number,max:number)=>Number.isInteger(value)&&value>=min&&value<=max;

/** Current-week slots have no timestamps: only later weeks can safely be counted as future. */
export function projectAcademy({player,plans,gameDate,startSeason,startWeek,horizon,gain}:AcademyProjectionInput) {
  const result:{error:string;seasons:AcademySeasonProjection[];totalSessions:number;counts:SkillCounts}={error:'',seasons:[],totalSessions:0,counts:counts()};
  if(!gameDate||!integer(gameDate.season,1,999)||!integer(gameDate.round,1,16)||!integer(gameDate.day,1,7))return {...result,error:'La date du jeu est inconnue ou invalide. Actualisez les données Classic avant de compter les séances futures.'};
  if(!integer(startSeason,1,999)||!integer(startWeek,1,16)||!integer(horizon,1,4)||startSeason+horizon-1>999||!Number.isFinite(gain)||gain<0||gain>1)return {...result,error:'Choisissez une saison de 1 à 999, une semaine de 1 à 16, un horizon de 1 à 4 saisons et un gain entre 0 et 1.'};
  let projected=Object.fromEntries(skills.map(skill=>[skill,academyNumber(player[skill])])) as SkillValues;
  for(let offset=0;offset<horizon;offset++){
    const season=startSeason+offset,grid=plans[String(season)],seasonCounts=counts();
    const firstWeek=Math.max(offset===0?startWeek:1,season<gameDate.season?17:season===gameDate.season?gameDate.round+1:1);
    for(let week=firstWeek;week<=16;week++)for(let slot=0;slot<4;slot++){
      const skill=grid?.[slot]?.[week-1];
      if(skills.includes(skill as Skill))seasonCounts[skill as Skill]++;
    }
    const gains={} as SkillValues,next={} as SkillValues;
    for(const skill of skills){
      const current=projected[skill];
      next[skill]=current===null?null:current>=ACADEMY_CAP?current:rounded(Math.min(ACADEMY_CAP,current+seasonCounts[skill]*gain));
      gains[skill]=current===null?null:rounded(next[skill]!-current);
      result.counts[skill]+=seasonCounts[skill];
    }
    const sessions=Object.values(seasonCounts).reduce((sum,value)=>sum+value,0);
    result.seasons.push({season,saved:!!grid,firstWeek:firstWeek<=16?firstWeek:null,sessions,openSlots:Math.max(0,17-firstWeek)*4-sessions,counts:seasonCounts,projected:next,gains});
    result.totalSessions+=sessions;projected=next;
  }
  return result;
}

export function academyTarget(current:unknown,target:unknown,gain:number):{status:'unset'|'unknown'|'reached'|'above-cap'|'no-gain'|'remaining';sessions:number|null} {
  const value=academyNumber(current),goal=academyNumber(target);
  if(goal===null)return {status:'unset',sessions:null};
  if(value===null)return {status:'unknown',sessions:null};
  if(value>=goal)return {status:'reached',sessions:0};
  if(goal>ACADEMY_CAP)return {status:'above-cap',sessions:null};
  if(!Number.isFinite(gain)||gain<=0)return {status:'no-gain',sessions:null};
  return {status:'remaining',sessions:Math.ceil(rounded(goal-value)/gain-1e-9)};
}

/** Copy prepares a new draft only; the editor still saves against its original server baseline. */
export function copyAcademyPlan(source:string[][]|undefined,draft:string[][],saved:string[][]):{grid:string[][]|null;error:string} {
  if(draft.some(row=>row.some(Boolean))||saved.some(row=>row.some(Boolean)))return {grid:null,error:'La saison de destination doit être vide, dans le brouillon et dans la version enregistrée.'};
  if(!source||source.length!==4||source.some(row=>row.length!==16||row.some(skill=>skill!==''&&!skills.includes(skill as Skill)))||!source.some(row=>row.some(Boolean)))return {grid:null,error:'Choisissez une saison enregistrée contenant au moins une séance.'};
  return {grid:source.map(row=>[...row]),error:''};
}

export function prioritizeAcademy<T extends {name:string;stars?:unknown;wc_projection?:unknown}>(players:T[]):T[] {
  return [...players].sort((a,b)=>(academyNumber(b.stars)??-1)-(academyNumber(a.stars)??-1)||(academyNumber(a.wc_projection)??Infinity)-(academyNumber(b.wc_projection)??Infinity)||a.name.localeCompare(b.name,'fr'));
}
