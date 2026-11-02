import test from 'node:test';
import assert from 'node:assert/strict';
import {isRecentComparison,recentFixtureLink} from '../src/match-recent-model.ts';

const scope={team_id:'9',match_type:0,fixture_id:'900',participants:['9','8'] as [string,string]};
function report(){return {team_id:'9',match_type:0,fixture_id:'900',retrieved_at:'2026-01-15T12:00:00Z',history_limit:20,match_limit:4,sides:[
 {team_id:'9',name:'Home',history_count:1,excluded_count:0,eligible_count:1,matches:[{id:'100',type:0,home_id:'9',guest_id:'8',home_name:'Home',guest_name:'Away',start_at:'2026-01-10T12:00:00Z',finish_at:'2026-01-10T14:00:00Z',competition:'Friendly',weather_code:'3',home_score:0,guest_score:0,score_source:'reporter',report_state:'available',ratings:{scrum:11},pack_weight:850,xv_weight:1450,starting_csr:null}]},
 {team_id:'8',name:'Away',history_count:0,excluded_count:0,eligible_count:0,matches:[]}]}}

test('recent comparison accepts zero scores and incomplete histories',()=>assert.equal(isRecentComparison(report(),scope),true));
test('wrong owner, fixture, population, side or match participant is refused',()=>{
 for(const change of [r=>r.team_id='8',r=>r.fixture_id='901',r=>r.match_type=3,r=>r.sides[1].team_id='7',r=>r.sides[0].matches[0].type=3,r=>r.sides[0].matches[0].home_id='7']){
  const r=report();change(r);assert.equal(isRecentComparison(r,scope),false);
 }
});
test('nonfinite ratings, five matches and repeated fixtures are refused',()=>{
 let r=report();r.sides[0].matches[0].ratings.scrum=NaN;assert.equal(isRecentComparison(r,scope),false);
 r=report();r.sides[0].matches=Array(5).fill(r.sides[0].matches[0]);assert.equal(isRecentComparison(r,scope),false);
 r=report();r.sides[0].matches.push(r.sides[0].matches[0]);assert.equal(isRecentComparison(r,scope),false);
});
test('official report links carry the right population without credentials',()=>{
 for(const [kind,flag] of [[0,''],[1,'&u20=1'],[2,'&nat=1'],[3,'&youth=1']])assert.equal(recentFixtureLink('100',Number(kind)),`https://www.blackoutrugby.com/game/tools.live.scoring.php#fixture=100${flag}`);
 assert.equal(recentFixtureLink('100&mk=secret',0),null);
});

test('an unavailable report cannot carry reporter figures',()=>{
 const r=report();r.sides[0].matches[0].report_state='unavailable';
 assert.equal(isRecentComparison(r,scope),false);
});

test('a missing report can keep a separately confirmed score without fabricated notes',()=>{
 const r=report(),m=r.sides[0].matches[0];Object.assign(m,{report_state:'unavailable',score_source:'match_score',ratings:{},pack_weight:null,xv_weight:null,starting_csr:null});
 assert.equal(isRecentComparison(r,scope),true);
});
