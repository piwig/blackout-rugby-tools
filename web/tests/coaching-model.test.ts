import assert from 'node:assert/strict';
import test from 'node:test';
import {existsSync} from 'node:fs';
import type {ReportPlayer,TrainingReport} from '../src/coaching-model.ts';

test('statistics keep unknown values last and search names without accents', async()=>{
  assert.ok(existsSync(new URL('../src/coaching-model.ts',import.meta.url)),'The coaching model must exist');
  const {statisticsRows}=await import('../src/coaching-model.ts');
  const rows=[{player_id:'1',player_name:'Émile',counters:{tries:null}},{player_id:'2',player_name:'Emile Jr',counters:{tries:0}},{player_id:'3',player_name:'Paul',counters:{tries:9}}];
  assert.deepEqual(statisticsRows(rows,'emile','tries',false).map(p=>p.player_id),['2','1']);
  assert.deepEqual(statisticsRows(rows,'','tries',true).map(p=>p.player_id),['3','2','1']);
  assert.deepEqual(statisticsRows(rows,'3','tries',false).map(p=>p.player_id),['3']);
  assert.equal(rows[0].player_id,'1');
});

test('counter changes require the same period, a previous date and a known nondecreasing counter',async()=>{
  assert.ok(existsSync(new URL('../src/coaching-model.ts',import.meta.url)),'The coaching model must exist');
  const {counterChange}=await import('../src/coaching-model.ts');
  const before={scope:'league',season:61,observed_at:'2026-10-01T10:00:00Z'};
  const after={...before,observed_at:'2026-10-02T10:00:00Z'};
  assert.deepEqual(counterChange(before,after,3,5),{delta:2,reason:null});
  assert.equal(counterChange(before,{...after,season:62},3,5).reason,'different_period');
  assert.equal(counterChange(before,{...after,scope:'career'},3,5).delta,null);
  assert.equal(counterChange(after,before,3,5).reason,'invalid_order');
  assert.equal(counterChange(before,after,null,5).reason,'unknown');
  assert.equal(counterChange(before,after,8,5).reason,'counter_reset');
  assert.deepEqual(counterChange(before,after,0,0),{delta:0,reason:null});
});

function trainingReport(team:ReportPlayer[]|null,individual:ReportPlayer[]|null):TrainingReport{
  return {key:'synthetic-report',report_id:null,season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
    team:{skills:null,players:team},individual:{players:individual}};
}

test('phase totals use their own populations while the continuous total uses the distinct union',async()=>{
  const {trainingReportSummary}=await import('../src/coaching-model.ts');
  const result=trainingReportSummary(trainingReport(
    [{player_id:'a',csr_before:100,csr_after:110},{player_id:'b',csr_before:90,csr_after:98}],
    [{player_id:'a',csr_before:110,csr_after:112},{player_id:'c',csr_before:200,csr_after:201}],
  ));
  assert.deepEqual(result.team.csr,{delta:18,population:2,known:2,unknown:0,positive:2,negative:0,stable:0});
  assert.deepEqual(result.individual.csr,{delta:3,population:2,known:2,unknown:0,positive:2,negative:0,stable:0});
  assert.deepEqual(result.continuous.csr,{delta:12,population:3,known:1,unknown:2,positive:1,negative:0,stable:0});
  assert.equal(result.continuous.populationIncomplete,false);
  assert.deepEqual([...result.continuous.players],[['a',12],['b',null],['c',null]]);
});

test('an unknown phase makes the union incomplete while a known empty phase does not',async()=>{
  const {trainingReportSummary}=await import('../src/coaching-model.ts');
  const player={player_id:'a',csr_before:310,csr_after:315};
  const absent=trainingReportSummary(trainingReport(null,[player]));
  const empty=trainingReportSummary(trainingReport([],[player]));
  assert.equal(absent.team.csr.population,null);
  assert.equal(absent.team.csr.unknown,null);
  assert.equal(empty.team.csr.population,0);
  assert.equal(empty.team.csr.unknown,0);
  assert.equal(empty.team.csr.delta,null);
  assert.deepEqual(absent.continuous.csr,{delta:null,population:1,known:0,unknown:1,positive:0,negative:0,stable:0});
  assert.deepEqual(empty.continuous.csr,absent.continuous.csr);
  assert.equal(absent.continuous.populationIncomplete,true);
  assert.equal(empty.continuous.populationIncomplete,false);
});

test('continuous CSR requires all four values and retains known midpoint breaks',async()=>{
  const {trainingReportSummary}=await import('../src/coaching-model.ts');
  const result=trainingReportSummary(trainingReport(
    [{player_id:'a',csr_before:100,csr_after:null},{player_id:'b',player_name:'Démo',csr_before:50,csr_after:60},
      {player_id:'c',csr_before:null,csr_after:90}],
    [{player_id:'a',csr_before:107,csr_after:111},{player_id:'b',csr_before:63,csr_after:68},
      {player_id:'c',csr_before:91,csr_after:null}],
  ));
  assert.equal(result.team.csr.delta,10);
  assert.equal(result.individual.csr.delta,9);
  assert.equal(result.continuous.csr.delta,null);
  assert.equal(result.continuous.csr.unknown,3);
  assert.deepEqual(result.continuous.discontinuities,[
    {player_id:'b',player_name:'Démo',team_after:60,individual_before:63},
    {player_id:'c',player_name:undefined,team_after:90,individual_before:91},
  ]);
});

test('session and level-change coverage retains zero, missing lists, and signed CSR',async()=>{
  const {trainingReportSummary}=await import('../src/coaching-model.ts');
  const result=trainingReportSummary(trainingReport(
    [{player_id:'a',csr_before:100,csr_after:100,pops:[],drops:[]},
      {player_id:'b',csr_before:207,csr_after:200,pops:null,drops:null}],
    [{player_id:'a',csr_before:100,csr_after:100,skills:[{skill:'speed',sessions:0,pops:[]},{skill:'tackling',sessions:null,pops:null}]},
      {player_id:'b',csr_before:200,csr_after:202,skills:[{skill:'speed',sessions:2,pops:[{skill:'speed',before:null,after:null,before_label:'Low',after_label:'Medium'}]}],
        pops:[{skill:'speed',before:null,after:null,before_label:'Low',after_label:'Medium'},{skill:'kicking',before:3,after:4}],drops:[]},
      {player_id:'c',skills:null,pops:[]},{player_id:'d',skills:[]}],
  ));
  assert.equal(result.team.sessions,null);
  assert.deepEqual(result.individual.sessions,{total:2,entries:3,known:2,unknown:1,missingSkillLists:1});
  assert.deepEqual(result.team.rises,{total:0,entries:2,known:1,unknown:1});
  assert.deepEqual(result.team.drops,{total:0,entries:2,known:1,unknown:1});
  assert.deepEqual(result.individual.rises,{total:2,entries:3,known:2,unknown:1});
  assert.deepEqual(result.individual.drops,{total:0,entries:4,known:1,unknown:3});
  assert.deepEqual(result.team.csr,{delta:-7,population:2,known:2,unknown:0,positive:0,negative:1,stable:1});
  assert.deepEqual(result.continuous.csr,{delta:-5,population:4,known:2,unknown:2,positive:0,negative:1,stable:1});
  assert.equal(result.continuous.players.get('a'),0);
});

test('individual rises distinguish transitions in the same skill and deduplicate identical observations',async()=>{
  const {trainingReportSummary}=await import('../src/coaching-model.ts');
  const result=trainingReportSummary(trainingReport([],[
    {player_id:'a',skills:[
      {skill:'speed',sessions:1,pops:[{skill:'kicking',before:3,after:4}]},
      {skill:'kicking',sessions:1,pops:[{skill:'kicking',before:4,after:5}]},
    ],pops:[{skill:'kicking',before:3,after:4,before_label:null,after_label:null}]},
    {player_id:'b',skills:[
      {skill:'speed',sessions:1,pops:[{skill:'kicking',before:null,after:null,before_label:'Low',after_label:'Medium'}]},
      {skill:'kicking',sessions:1,pops:[{skill:'kicking',before:null,after:null,before_label:'Medium',after_label:'High'}]},
    ],pops:[{skill:'kicking',before:null,after:null,before_label:'Low',after_label:'Medium'}]},
  ]));
  assert.deepEqual(result.individual.rises,{total:4,entries:4,known:4,unknown:0});
});
