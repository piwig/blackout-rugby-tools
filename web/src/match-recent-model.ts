export type RecentScope={team_id:string;match_type:number;fixture_id:string;participants:[string,string]};
export type RecentMatch={id:string;type:number;home_id:string;guest_id:string;home_name:string|null;guest_name:string|null;start_at:string|null;finish_at:string;competition:string;weather_code:string|null;
 home_score:number|null;guest_score:number|null;score_source:'reporter'|'match_score'|null;report_state:'available'|'unavailable'|'inconsistent'|'not_played';ratings:Record<string,number|null>;pack_weight:number|null;xv_weight:number|null;starting_csr:number|null};
export type RecentSide={team_id:string;name:string|null;history_count:number;eligible_count:number;excluded_count:number;matches:RecentMatch[]};
export type RecentComparison={team_id:string;match_type:number;fixture_id:string;retrieved_at:string;history_limit:number;match_limit:number;sides:RecentSide[]};
const id=(v:any)=>typeof v==='string'&&/^[1-9]\d{0,14}$/.test(v);
const record=(v:any)=>!!v&&typeof v==='object'&&!Array.isArray(v);
const date=(v:any)=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/i.test(v)&&Number.isFinite(Date.parse(v));
const number=(v:any,max=1e9)=>v===null||typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=max;
const count=(v:any)=>Number.isInteger(v)&&v>=0&&v<=20;
const ratingKeys=new Set(['scrum','lineout','kicking','ruck','maul','handling','attack','defense','stamina','pickandgo','driving','expansive','creative']);
export function isRecentComparison(value:any,scope:RecentScope):value is RecentComparison{
 if(!record(value)||value.team_id!==scope.team_id||value.match_type!==scope.match_type||value.fixture_id!==scope.fixture_id||!date(value.retrieved_at)||!Array.isArray(value.sides)||value.sides.length!==2)return false;
 return value.sides.every((side:any,index:number)=>record(side)&&side.team_id===scope.participants[index]&&count(side.history_count)&&count(side.eligible_count)&&count(side.excluded_count)&&Array.isArray(side.matches)&&side.matches.length<=4&&new Set(side.matches.map((m:any)=>m?.id)).size===side.matches.length&&side.matches.every((m:any)=>
   record(m)&&id(m.id)&&m.type===scope.match_type&&id(m.home_id)&&id(m.guest_id)&&m.home_id!==m.guest_id&&[m.home_id,m.guest_id].includes(side.team_id)&&date(m.finish_at)&&Date.parse(m.finish_at)<=Date.parse(value.retrieved_at)&&(m.start_at===null||date(m.start_at)&&Date.parse(m.start_at)<=Date.parse(m.finish_at))&&typeof m.competition==='string'&&['available','unavailable','inconsistent','not_played'].includes(m.report_state)&&
   number(m.home_score,100000)&&number(m.guest_score,100000)&&[m.home_score,m.guest_score].every(v=>v===null||Number.isInteger(v))&&
   (m.score_source===null?m.home_score===null&&m.guest_score===null:m.score_source==='match_score'?m.home_score!==null&&m.guest_score!==null:m.score_source==='reporter'&&(m.home_score!==null||m.guest_score!==null))&&
   number(m.pack_weight,30000)&&number(m.xv_weight,30000)&&number(m.starting_csr)&&record(m.ratings)&&Object.entries(m.ratings).every(([k,v])=>ratingKeys.has(k)&&number(v,1000))&&(m.weather_code===null||typeof m.weather_code==='string'&&/^\d{1,2}$/.test(m.weather_code))&&
   (m.report_state==='available'||[m.pack_weight,m.xv_weight,m.starting_csr,...Object.values(m.ratings)].every(v=>v===null)&&
    (m.home_score===null&&m.guest_score===null||m.score_source==='match_score'&&m.home_score!==null&&m.guest_score!==null))));
}
export function recentFixtureLink(fixture:string,kind:number):string|null{
 if(!id(fixture)||!Number.isInteger(kind)||kind<0||kind>3)return null;
 return 'https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture='+fixture+({0:'',1:'&u20=1',2:'&nat=1',3:'&youth=1'}[kind as 0|1|2|3]);
}
