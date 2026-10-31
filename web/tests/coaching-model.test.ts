import assert from 'node:assert/strict';
import test from 'node:test';
import {existsSync} from 'node:fs';

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
