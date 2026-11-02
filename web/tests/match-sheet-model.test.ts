import test from 'node:test';
import assert from 'node:assert/strict';
import {populationFor,referenceId,isSheetReport,isSheetCalendar} from '../src/match-sheet-model.ts';

test('club juniors and national U20 have distinct match populations',()=>{
  assert.equal(populationFor('9',false),0);assert.equal(populationFor('9',true),3);
  assert.equal(populationFor('u20:9',false),1);assert.equal(populationFor('nt:9',true),2);
});
test('fixture reference validation keeps fixture and population separate',()=>{
  assert.equal(referenceId('90'),'90');
  assert.equal(referenceId('https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture=90&youth=1'),'90');
  assert.equal(referenceId('https://www.blackoutrugby.com/game/tools.live.scoring.php?id=90&fixture=91'),null);
});
test('calendar from another team or population is rejected',()=>{
  const c={team_id:'9',match_type:3,retrieved_at:'2026-01-01T12:00:00Z',fixtures:[],excluded_count:0};
  assert.equal(isSheetCalendar(c,'9',3),true);
  assert.equal(isSheetCalendar(c,'9',0),false);assert.equal(isSheetCalendar(c,'8',3),false);
});
test('report identity and jersey order are validated before rendering',()=>{
  const side={team_id:'9',name:'Test',lineup_state:'available',energy_scale:'auto',deadline_at:null,tactics_deadline_at:null,
    players:Array.from({length:23},(_,i)=>({slot:i+1,player_id:null,status:'not_provided',captain:false,kicker:false,name:null,
      csr:null,weight:null,height:null,form:null,experience:null,aggression:null,discipline:null,energy_raw:null,energy_percent:null,energy_scale:'unknown',adjusted_csr:null})),groups:[]};
  const r={team_id:'9',match_type:3,retrieved_at:'2026-01-01T12:00:00Z',fixture:{id:'90',home_id:'9',guest_id:'8',type:3,start_at:null,finish_at:null},home:side,guest:{...side,team_id:'8'},timing:{indicative:{lineup_at:null,publication_at:null,tactics_at:null}}};
  assert.equal(isSheetReport(r,'9',3,'90'),true);
  for(const [team,kind,id] of [['8',3,'90'],['9',0,'90'],['9',3,'91']] as const) assert.equal(isSheetReport(r,team,kind,id),false);
  assert.equal(isSheetReport({...r,home:{...side,players:side.players.slice(1)}},'9',3,'90'),false);
  const swapped=structuredClone(r);swapped.home.players[2].slot=4;
  assert.equal(isSheetReport(swapped,'9',3,'90'),false);
});
