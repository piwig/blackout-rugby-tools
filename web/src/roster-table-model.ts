import {skills} from './types.ts';
import {comparePlayerValues} from './player-table.ts';

const number=(v:unknown):number|null=>(typeof v==='number'||typeof v==='string'&&v.trim()!=='')&&Number.isFinite(Number(v))?Number(v):null;
const texts=new Set(['name','nationality','hand','foot','nat','u20']);
export function rosterValue(player:Record<string,any>,key:string):unknown{
  if(texts.has(key))return typeof player[key]==='string'?player[key]:null;
  return number(key==='total'?player.metrics?.skill_total:key==='generation'?player.wc_projection:player[key]);
}
export function compareRosterPlayers(a:Record<string,any>,b:Record<string,any>,key:string,descending:boolean):number{
 const first=rosterValue(a,key),second=rosterValue(b,key);
 if(first===null||first==='')return second===null||second===''?0:1;
 if(second===null||second==='')return -1;
 return comparePlayerValues(first,second,descending,texts.has(key));
}
export function rosterColumns(youth:boolean,complete:boolean):string[]{
  return complete?['nationality','age','stars','csr','salary','height','weight','hand','foot','form','energy','aggression','discipline','leadership','experience',...skills,'total','nat','u20']:
    ['age',youth?'stars':'csr',...skills,youth?'generation':'energy'];
}
export function rosterDelta(player:Record<string,any>,key:string){
  const change=player.changes?.[key];if(!change)return null;
  const before=number(change.before),after=number(change.after);
  if(before!==null&&after!==null)return before===after?null:{kind:'numeric' as const,before,after,delta:Math.round((after-before)*100)/100};
  return before===null&&after!==null?{kind:'revealed' as const,before:String(change.before??'Unknown'),after}:null;
}
