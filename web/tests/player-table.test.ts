import test from 'node:test';
import assert from 'node:assert/strict';
import {comparePlayerValues, matchesPlayerSearch} from '../src/player-table.ts';

test('numeric skills sort numerically with every unknown value last in both directions', () => {
  const values = ['Unknown', 9, 'High', '12', null, '', 0, undefined, 'Low', 'Medium'];
  assert.deepEqual(values.toSorted((a,b)=>comparePlayerValues(a,b,false)).slice(0,3), [0,9,'12']);
  assert.deepEqual(values.toSorted((a,b)=>comparePlayerValues(a,b,true)).slice(0,3), ['12',9,0]);
  assert.equal(comparePlayerValues('Unknown',12,true), 1);
  assert.equal(comparePlayerValues('High',null,false), 0);
});

test('name ordering ignores accents and case without treating names as unknown skills', () => {
  const names = ['Zoé', 'éMILE', 'Alice'];
  assert.deepEqual(names.toSorted((a,b)=>comparePlayerValues(a,b,false,true)), ['Alice','éMILE','Zoé']);
  assert.deepEqual(names.toSorted((a,b)=>comparePlayerValues(a,b,true,true)), ['Zoé','éMILE','Alice']);
});

test('player search matches accents, repeated spaces and identifiers', () => {
  const player = {name:'  Émile   de la Côte ',id:'123456'};
  assert.equal(matchesPlayerSearch(player,' EMILE  de la cote '), true);
  assert.equal(matchesPlayerSearch(player,'2345'), true);
  assert.equal(matchesPlayerSearch(player,'   '), true);
  assert.equal(matchesPlayerSearch(player,'Émilie'), false);
});
