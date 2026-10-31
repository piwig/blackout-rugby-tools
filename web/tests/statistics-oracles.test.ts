import assert from 'node:assert/strict';
import test from 'node:test';
import {counterChange, statisticsRows} from '../src/coaching-model.ts';

function permutations<T>(items:T[]):T[][] {
  return items.length === 0 ? [[]] : items.flatMap((item,index) =>
    permutations(items.filter((_,other) => other !== index)).map(rest => [item,...rest]));
}

test('every input order yields the same numerical counter sort with unknown values last', () => {
  const rows = [
    {player_id:'1',player_name:'Émile',counters:{tries:null}},
    {player_id:'2',player_name:'Emile Junior',counters:{tries:0}},
    {player_id:'3',player_name:'Paul',counters:{tries:2}},
    {player_id:'4',player_name:'Anne',counters:{tries:10}},
  ];
  for(const input of permutations(rows)) {
    const previous = structuredClone(input);
    assert.deepEqual(statisticsRows(input,'','tries',false).map(p=>p.player_id),['2','3','4','1']);
    assert.deepEqual(statisticsRows(input,'','tries',true).map(p=>p.player_id),['4','3','2','1']);
    assert.deepEqual(statisticsRows(input,'  eMiLe  ','tries',true).map(p=>p.player_id),['2','1']);
    assert.deepEqual(input,previous);
  }
});

test('cumulative deltas compare UTC instants, reject resets, and never cross seasons or scopes', () => {
  const before = {scope:'league',season:61,observed_at:'2026-10-31T11:00:00Z'};
  const after = {...before,observed_at:'2026-10-31T12:01:00+01:00'};
  assert.deepEqual(counterChange(before,after,0,3),{delta:3,reason:null});
  assert.deepEqual(counterChange(before,after,0,0),{delta:0,reason:null});
  assert.deepEqual(counterChange(before,after,3,0),{delta:null,reason:'counter_reset'});
  for(const observed_at of ['2026-10-31T12:00:00+01:00','2026-10-31T11:59:59+01:00','invalid']) {
    assert.deepEqual(counterChange(before,{...after,observed_at},0,3),{delta:null,reason:'invalid_order'});
  }
  for(const previous of [null,undefined,NaN,Infinity]) {
    assert.deepEqual(counterChange(before,after,previous,3),{delta:null,reason:'unknown'});
  }
  for(const current of [null,undefined,NaN,Infinity]) {
    assert.deepEqual(counterChange(before,after,0,current),{delta:null,reason:'unknown'});
  }
  assert.deepEqual(counterChange(before,{...after,season:62},0,3),{delta:null,reason:'different_period'});
  assert.deepEqual(counterChange(before,{...after,scope:'career',season:null},0,3),{delta:null,reason:'different_period'});
});
