import assert from 'node:assert/strict';
import test from 'node:test';
import * as model from '../src/academy-planner-model.ts';

const api = model as Record<string, (...args:any[])=>any>;
const blank=()=>Array.from({length:4},()=>Array<string>(16).fill(''));
const gameDate={season:63,round:15,day:4};

test('projection excludes past and current weeks, then crosses the season boundary',()=>{
  assert.equal(typeof api.projectAcademy,'function');
  const past=blank(),current=blank(),next=blank();
  past[0].fill('attack');current[0][13]='attack';current[0][14]='attack';current[0][15]='attack';
  next[0][0]='attack';next[1][0]='attack';next[0][1]='defense';
  const result=api.projectAcademy({player:{attack:10,defense:6},plans:{62:past,63:current,64:next},gameDate,startSeason:62,startWeek:1,horizon:3,gain:0.2});
  assert.equal(result.error,'');
  assert.deepEqual(result.seasons.map((s:any)=>s.sessions),[0,1,3]);
  assert.deepEqual(result.seasons.map((s:any)=>s.projected.attack),[10,10.2,10.6]);
  assert.equal(result.seasons[2].projected.defense,6.2);
  assert.equal(result.totalSessions,4);
});

test('a future starting week and unplanned seasons contribute only their real saved slots',()=>{
  assert.equal(typeof api.projectAcademy,'function');
  const plan=blank();plan[0][2]='handling';plan[0][3]='handling';plan[1][15]='handling';
  const result=api.projectAcademy({player:{handling:9},plans:{64:plan},gameDate,startSeason:64,startWeek:4,horizon:2,gain:0.15});
  assert.deepEqual(result.seasons.map((s:any)=>s.sessions),[2,0]);
  assert.equal(result.seasons[0].openSlots,50);
  assert.equal(result.seasons[1].saved,false);
  assert.equal(result.seasons[1].projected.handling,9.3);
});

test('academy sessions stop at 13.99 and never lower an observed 14 or estimate IGT',()=>{
  assert.equal(typeof api.projectAcademy,'function');
  const plan=blank();plan[0].fill('attack');plan[1].fill('defense');
  const result=api.projectAcademy({player:{attack:13.9,defense:14},plans:{64:plan},gameDate,startSeason:64,startWeek:1,horizon:1,gain:0.2});
  assert.equal(result.seasons[0].projected.attack,13.99);
  assert.equal(result.seasons[0].projected.defense,14);
  assert.ok(Math.abs(result.seasons[0].gains.attack-0.09)<1e-12);
  assert.equal(result.seasons[0].gains.defense,0);
});

test('unrevealed, blank and invalid skills remain unknown despite planned sessions',()=>{
  assert.equal(typeof api.projectAcademy,'function');
  const plan=blank();plan[0].fill('attack');
  const result=api.projectAcademy({player:{attack:null,defense:'',handling:'?',speed:NaN,agility:false,stamina:0,strength:'8,5'},plans:{64:plan},gameDate,startSeason:64,startWeek:1,horizon:1,gain:0.2});
  for(const skill of ['attack','defense','handling','speed','agility','kicking'])assert.equal(result.seasons[0].projected[skill],null,skill);
  assert.equal(result.seasons[0].projected.stamina,0);
  assert.equal(result.seasons[0].projected.strength,8.5);
});

test('unknown game dates and invalid projection assumptions do not fabricate future gains',()=>{
  assert.equal(typeof api.projectAcademy,'function');
  const valid={player:{attack:10},plans:{},gameDate,startSeason:64,startWeek:1,horizon:1,gain:0.2};
  for(const change of [{gameDate:null},{gameDate:{season:63,round:17,day:1}},{gain:NaN},{gain:-0.2},{startWeek:0},{startSeason:1.2},{horizon:5},{startSeason:999,horizon:2}]){
    const result=api.projectAcademy({...valid,...change});
    assert.ok(result.error);assert.deepEqual(result.seasons,[]);
  }
});

test('target estimates distinguish achieved, unknown and unreachable without IGT',()=>{
  assert.equal(typeof api.academyTarget,'function');
  assert.deepEqual(api.academyTarget(13,13.99,0.2),{status:'remaining',sessions:5});
  assert.deepEqual(api.academyTarget(13.99,14,0.2),{status:'above-cap',sessions:null});
  assert.deepEqual(api.academyTarget(14,14,0.2),{status:'reached',sessions:0});
  assert.deepEqual(api.academyTarget(null,10,0.2),{status:'unknown',sessions:null});
  assert.deepEqual(api.academyTarget(10,'',0.2),{status:'unset',sessions:null});
  assert.deepEqual(api.academyTarget(10,11,0),{status:'no-gain',sessions:null});
});

test('a projection with no effective sessions preserves the observation and has no gain',()=>{
  const base={player:{strength:10.125},plans:{},gameDate,startSeason:64,startWeek:1,horizon:4,gain:0.2};
  for(const input of [base,{...base,plans:{64:blank()},gain:0}]){
    const result=api.projectAcademy(input);
    assert.deepEqual(result.seasons.map((s:any)=>s.projected.strength),[10.125,10.125,10.125,10.125]);
    assert.deepEqual(result.seasons.map((s:any)=>s.gains.strength),[0,0,0,0]);
  }
});

test('small hypothetical gains accumulate independently of season boundaries',()=>{
  const one=blank();one[0][0]='strength';
  const four=blank();four[0].splice(0,4,'strength','strength','strength','strength');
  const base={player:{strength:10},gameDate,startSeason:64,startWeek:1,horizon:4,gain:0.004};
  const split=api.projectAcademy({...base,plans:{64:one,65:one,66:one,67:one}});
  const combined=api.projectAcademy({...base,plans:{64:four}});
  // Four sessions at 0.004 add 0.016, regardless of their season placement.
  assert.equal(split.totalSessions,4);
  assert.equal(combined.totalSessions,4);
  assert.ok(Math.abs(split.seasons[3].projected.strength-10.016)<1e-12);
  assert.equal(split.seasons[3].projected.strength,combined.seasons[3].projected.strength);
});

test('remaining sessions use the full positive target gap',()=>{
  assert.deepEqual(api.academyTarget(10.001,10.002,0.2),{status:'remaining',sessions:1});
  // A two-hundredth rounding of 0.204 would incorrectly claim one session.
  assert.deepEqual(api.academyTarget(10,10.204,0.2),{status:'remaining',sessions:2});
  assert.deepEqual(api.academyTarget(10,10.2,0.2),{status:'remaining',sessions:1});
  assert.deepEqual(api.academyTarget(1.001,1.002,0.001),{status:'remaining',sessions:1});
  assert.deepEqual(api.academyTarget(10,10.20000000001,0.2),{status:'remaining',sessions:2});
});

for(const gain of [Number.MIN_VALUE,1e-20,1/(Number.MAX_SAFE_INTEGER+1)]){
  test(`target estimates reject an unsafe session count with gain ${gain}`,()=>{
    assert.deepEqual(api.academyTarget(0,1,gain),{status:'out-of-range',sessions:null});
    assert.deepEqual(api.academyTarget(1,1,gain),{status:'reached',sessions:0});
  });
}

test('zero gain and a one-session subnormal gain retain their distinct meanings',()=>{
  assert.deepEqual(api.academyTarget(0,Number.MIN_VALUE,Number.MIN_VALUE),{status:'remaining',sessions:1});
  assert.deepEqual(api.academyTarget(0,1,0),{status:'no-gain',sessions:null});
});

test('copying a saved plan cannot replace filled destination cells or alias the source',()=>{
  assert.equal(typeof api.copyAcademyPlan,'function');
  const source=blank();source[0][0]='attack';
  const copied=api.copyAcademyPlan(source,blank(),blank());
  assert.equal(copied.error,'');assert.equal(copied.grid[0][0],'attack');
  copied.grid[0][0]='defense';assert.equal(source[0][0],'attack');
  for(const [draft,saved] of [[source,blank()],[blank(),source]])assert.equal(api.copyAcademyPlan(source,draft,saved).grid,null);
  assert.equal(api.copyAcademyPlan(blank(),blank(),blank()).grid,null);
});

test('player priority uses stars and the existing generation marker, never age',()=>{
  assert.equal(typeof api.prioritizeAcademy,'function');
  const players=[{id:'young',name:'Young',age:15,stars:3,wc_projection:68},{id:'older',name:'Older',age:18,stars:5,wc_projection:null},{id:'u20',name:'Generation',age:19,stars:5,wc_projection:64},{id:'unknown',name:'Unknown',age:14,stars:null,wc_projection:64}];
  assert.deepEqual(api.prioritizeAcademy(players).map((p:any)=>p.id),['u20','older','young','unknown']);
  assert.equal(players[0].id,'young');
});
