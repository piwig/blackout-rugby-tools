import test from 'node:test';
import assert from 'node:assert/strict';
import {preparationWindow,sheetReadiness} from '../src/match-sheet-model.ts';

const report=(changes={})=>({team_id:'9',retrieved_at:'2026-11-02T15:00:00Z',fixture:{start_at:'2026-11-02T18:35:00Z'},
 home:{team_id:'9',deadline_at:'2026-11-02T15:30:00Z',tactics_deadline_at:'2026-11-02T16:30:00Z',players:[]},
 guest:{team_id:'8',deadline_at:'2026-11-02T10:00:00Z',tactics_deadline_at:'2026-11-02T11:00:00Z',players:[]},...changes});
test('windows use the own side and report reading instant, including equality locks',()=>{
 assert.equal(preparationWindow(report()).stage,'lineup');
 assert.equal(preparationWindow(report({retrieved_at:'2026-11-02T15:30:00Z'})).stage,'tactics');
 assert.equal(preparationWindow(report({retrieved_at:'2026-11-02T16:30:00Z'})).stage,'closed');
 const away=report({team_id:'u20:8'});assert.equal(preparationWindow(away).stage,'closed');
});
test('absent, naive or contradictory deadlines cannot assert an open window',()=>{
 for(const side of [{deadline_at:null,tactics_deadline_at:null},{deadline_at:'2026-11-02T15:30:00',tactics_deadline_at:null},
  {deadline_at:'2026-11-02T16:30:00Z',tactics_deadline_at:'2026-11-02T15:30:00Z'},
  {deadline_at:'2026-11-02T20:30:00Z',tactics_deadline_at:null}]){
  const r=report();Object.assign(r.home,side);assert.equal(preparationWindow(r).stage,'unknown');
 }
 const r=report();r.home.tactics_deadline_at=null;
 assert.equal(preparationWindow({...r,retrieved_at:'2026-11-02T16:00:00Z'}).stage,'lineup_closed');
 assert.equal(preparationWindow({...r,team_id:'nt:7'}).stage,'unknown');
});
test('readiness counts identities, keeps missing profiles, and detects duplicate players',()=>{
 const r=report();r.home.players=Array.from({length:23},(_,i)=>({slot:i+1,player_id:String(i+1),captain:i===0,kicker:i===9})) as any;
 assert.deepEqual(sheetReadiness(r),{starters:15,bench:8,captain:true,kicker:true,duplicates:0});
 r.home.players[22].player_id='1';assert.equal(sheetReadiness(r).duplicates,1);
 r.home.players[0].captain=false;assert.equal(sheetReadiness(r).captain,false);
 assert.equal(sheetReadiness({...r,team_id:'nt:7'}).starters,0);
});
