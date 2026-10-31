import {skillKeys} from './role-weights-model.ts';
import type {MarketCandidate,MarketDraft,MarketInvestment} from './market-types.ts';

export function marketNumber(value:string):number|null{
  if(value.trim()==='')return null;
  const number=Number(value);
  if(!Number.isFinite(number)||number<0)throw new Error('invalid_market_number');
  return number;
}
export function observedMarketSkill(value:unknown):number|null{
  if(value===null||value===undefined||typeof value==='boolean'||String(value).trim()==='')return null;
  const number=Number(String(value).replace(',','.'));
  return Number.isFinite(number)&&number>=0&&number<=21?number:null;
}
export function classicPlayerUrl(id:string|null):string|null{
  return id&&/^[1-9]\d{0,14}$/.test(id)?'https://www.blackoutrugby.com/game/club.squad.php#player='+id:null;
}
export function toLocalDateTime(value:string|null):string{
  if(!value)return '';
  const instant=new Date(value);
  if(!Number.isFinite(instant.getTime()))return '';
  return new Date(instant.getTime()-instant.getTimezoneOffset()*60000).toISOString().slice(0,16);
}
export function toObservedAt(value:string):string|null{
  return value?new Date(value).toISOString():null;
}
export function marketDraft(value:MarketDraft):MarketDraft{
  return {plan:value.plan,candidates:value.candidates,investments:value.investments};
}
export function emptyCandidate(id:string):MarketCandidate{
  return {id,name:'',classic_id:null,role:'Pilier',age:null,price:null,weekly_salary:null,fees:null,skills:Object.fromEntries(skillKeys.map(skill=>[skill,null])) as MarketCandidate['skills'],notes:'',status:'watch'};
}
export function emptyInvestment(id:string):MarketInvestment{
  return {id,name:'',initial_cost:null,weekly_cost:null,notes:''};
}
