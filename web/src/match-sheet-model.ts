export type EnergyScale='auto'|'percent'|'level';
export type SheetFixture={id:string;home_id:string;guest_id:string;type:number;start_at:string|null;finish_at:string|null;competition?:string};
export type SheetMetric={value:number|null;known:number;expected:number};
export type SheetGroup={key:string;size:number;metrics:Record<string,SheetMetric>};
export type SheetPlayer={slot:number;player_id:string|null;status:'available'|'not_provided'|'missing_player';name:string|null;captain:boolean;kicker:boolean;
  csr:number|null;weight:number|null;height:number|null;form:number|null;experience:number|null;aggression:number|null;discipline:number|null;
  energy_raw:number|null;energy_percent:number|null;energy_scale:'percent'|'level'|'unknown';adjusted_csr:number|null};
export type SheetSide={team_id:string;name:string|null;lineup_state:'available'|'not_provided'|'unavailable';energy_scale:EnergyScale;deadline_at:string|null;tactics_deadline_at:string|null;players:SheetPlayer[];groups:SheetGroup[]};
export type SheetReport={team_id:string;match_type:number;retrieved_at:string;fixture:SheetFixture;home:SheetSide;guest:SheetSide;timing:{indicative:{lineup_at:string|null;publication_at:string|null;tactics_at:string|null}}};
export type SheetCalendar={team_id:string;match_type:number;retrieved_at:string;fixtures:SheetFixture[];excluded_count:number;partial?:boolean;candidate_count?:number|null};
export function populationFor(team:string,junior:boolean){return team.startsWith('u20:')?1:team.startsWith('nt:')?2:junior?3:0}
export function referenceId(value:string):string|null{
  const clean=value.trim();if(/^[1-9]\d{0,14}$/.test(clean))return clean;
  try{
    const url=new URL(clean.replaceAll('&amp;','&')),q=new URLSearchParams(url.search),f=new URLSearchParams(url.hash.slice(1));
    const ids=['id','fixtureid','fixture'].flatMap(k=>[...q.getAll(k),...f.getAll(k)]);
    return ids.length&&ids.every(id=>/^[1-9]\d{0,14}$/.test(id)&&id===ids[0])?ids[0]:null;
  }catch{return null}
}
const record=(v:any):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const date=(v:any)=>typeof v==='string'&&/([zZ]|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
const optionalDate=(v:any)=>v===null||date(v);
const fixture=(v:any,kind:number)=>record(v)&&/^[1-9]\d{0,14}$/.test(v.id)&&typeof v.home_id==='string'&&typeof v.guest_id==='string'&&v.home_id!==v.guest_id&&v.type===kind&&optionalDate(v.start_at)&&optionalDate(v.finish_at);
export function isSheetCalendar(v:any,team:string,kind:number):v is SheetCalendar{
  return record(v)&&v.team_id===team&&v.match_type===kind&&(v.partial===undefined||typeof v.partial==='boolean')&&date(v.retrieved_at)&&Array.isArray(v.fixtures)&&v.fixtures.length<=200&&v.fixtures.every((f:any)=>fixture(f,kind)&&[f.home_id,f.guest_id].includes(team.split(':').at(-1)));
}
function side(v:any,id:string){
  return record(v)&&v.team_id===id&&['available','not_provided','unavailable'].includes(v.lineup_state)&&optionalDate(v.deadline_at)&&optionalDate(v.tactics_deadline_at)&&Array.isArray(v.players)&&v.players.length===23&&v.players.every((p:any,i:number)=>record(p)&&p.slot===i+1&&['available','not_provided','missing_player'].includes(p.status)&&typeof p.captain==='boolean'&&typeof p.kicker==='boolean'&&['csr','weight','height','form','experience','aggression','discipline','energy_raw','energy_percent','adjusted_csr'].every(k=>p[k]===null||typeof p[k]==='number'&&Number.isFinite(p[k])))&&Array.isArray(v.groups)&&v.groups.length<=10&&v.groups.every((g:any)=>record(g)&&typeof g.key==='string'&&record(g.metrics)&&Object.values(g.metrics).every((m:any)=>record(m)&&Number.isInteger(m.expected)&&m.expected>=1&&m.expected<=23&&Number.isInteger(m.known)&&m.known>=0&&m.known<=m.expected&&(m.value===null||typeof m.value==='number'&&Number.isFinite(m.value))));
}
export function isSheetReport(v:any,team:string,kind:number,id:string|null):v is SheetReport{
  return record(v)&&v.team_id===team&&v.match_type===kind&&date(v.retrieved_at)&&fixture(v.fixture,kind)&&v.fixture.id===id&&[v.fixture.home_id,v.fixture.guest_id].includes(team.split(':').at(-1))&&side(v.home,v.fixture.home_id)&&side(v.guest,v.fixture.guest_id)&&record(v.timing?.indicative)&&['lineup_at','publication_at','tactics_at'].every(k=>optionalDate(v.timing.indicative[k]));
}

function ownSide(report:any){
  const id=typeof report.team_id==='string'?report.team_id.split(':').at(-1):null;
  return [report.home,report.guest].find(s=>id&&s?.team_id===id);
}
export function preparationWindow(report:any):{stage:'unknown'|'lineup'|'tactics'|'lineup_closed'|'closed'}{
  const own=ownSide(report),read=report.retrieved_at;
  if(!own||!date(read))return {stage:'unknown'};
  const l=own.deadline_at,t=own.tactics_deadline_at,start=report.fixture?.start_at;
  if(!optionalDate(l)||!optionalDate(t)||l&&t&&Date.parse(l)>Date.parse(t)||date(start)&&[l,t].some(v=>v&&Date.parse(v)>Date.parse(start)))return {stage:'unknown'};
  const instant=Date.parse(read);
  if(l&&instant<Date.parse(l))return {stage:'lineup'};
  if(l)return {stage:!t?'lineup_closed':instant<Date.parse(t)?'tactics':'closed'};
  return {stage:'unknown'};
}
export function sheetReadiness(report:any){
  const players=(ownSide(report)?.players??[]).filter((p:any)=>typeof p.player_id==='string'&&p.player_id);
  const starters=players.filter((p:any)=>p.slot>=1&&p.slot<=15),bench=players.filter((p:any)=>p.slot>=16&&p.slot<=23);
  return {starters:starters.length,bench:bench.length,captain:starters.filter((p:any)=>p.captain).length===1,
    kicker:starters.filter((p:any)=>p.kicker).length===1,duplicates:players.length-new Set(players.map((p:any)=>p.player_id)).size};
}
