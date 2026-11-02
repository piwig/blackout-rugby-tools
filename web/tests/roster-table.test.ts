import test from 'node:test';
import assert from 'node:assert/strict';
import {rosterValue,rosterDelta,rosterColumns,compareRosterPlayers} from '../src/roster-table-model.ts';
import {comparePlayerValues} from '../src/player-table.ts';

test('full roster keeps 600/1000 stars and numeric zero, with unknowns last',()=>{
  const players=[{id:'1',stars:127},{id:'2',stars:600},{id:'3',stars:1000},{id:'4',stars:null},{id:'5',stars:0}];
  players.sort((a,b)=>comparePlayerValues(rosterValue(a,'stars'),rosterValue(b,'stars'),true));
  assert.deepEqual(players.map(p=>p.id),['3','2','1','5','4']);
  assert.equal(rosterValue({stars:true},'stars'),null);
  assert.equal(rosterValue({energy:'0'},'energy'),0);
  assert.equal(rosterValue({form:'Unknown'},'form'),null);
});

test('delta distinguishes revelation from a measured numeric gain',()=>{
  assert.deepEqual(rosterDelta({changes:{handling:{before:'High',after:12}}},'handling'),{kind:'revealed',before:'High',after:12});
  assert.deepEqual(rosterDelta({changes:{csr:{before:1000,after:980}}},'csr'),{kind:'numeric',before:1000,after:980,delta:-20});
  assert.equal(rosterDelta({changes:{form:{before:7,after:7}}},'form'),null);
});

test('complete columns expose observed attributes for both populations',()=>{
  for(const youth of [false,true]){
    const columns=rosterColumns(youth,true);
    for(const key of ['csr','weight','height','form','energy','aggression','discipline','leadership','experience','salary','stars','hand','foot','stamina','handling','kicking'])assert.ok(columns.includes(key),key);
  }
  assert.ok(rosterColumns(true,false).includes('stars'));
  assert.ok(rosterColumns(false,false).includes('csr'));
});

test('text and indicative generation headers actually sort while unknowns stay last',()=>{
 assert.ok(compareRosterPlayers({nationality:'FR'},{nationality:'IE'},'nationality',false)<0);
 assert.ok(compareRosterPlayers({wc_projection:64},{wc_projection:66},'generation',false)<0);
 assert.ok(compareRosterPlayers({}, {nationality:'FR'},'nationality',true)>0);
});
