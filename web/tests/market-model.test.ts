import test from 'node:test';
import assert from 'node:assert/strict';
import {marketNumber,observedMarketSkill,classicPlayerUrl,toLocalDateTime,toObservedAt,marketDraft,emptyCandidate,emptyInvestment} from '../src/market-model.ts';

test('empty money remains unknown while explicit zero is retained',()=>{
  assert.equal(marketNumber(''),null);
  assert.equal(marketNumber('  '),null);
  assert.equal(marketNumber('0'),0);
  assert.equal(marketNumber('12.50'),12.5);
  for(const value of ['Infinity','NaN','-1','1e309'])assert.throws(()=>marketNumber(value));
});
test('only positive decimal Classic IDs can create an official link',()=>{
  assert.equal(classicPlayerUrl('123'), 'https://www.blackoutrugby.com/game/club.squad.php#player=123');
  for(const value of [null,'','0','https://evil.test','123#x','1234567890123456'])assert.equal(classicPlayerUrl(value),null);
});
test('imported numeric skills are comparable while masked, blank and invalid values stay unknown',()=>{
  for(const [value,expected] of [[0,0],['0',0],[' 9,5 ',9.5],['12.25',12.25],[21,21]])assert.equal(observedMarketSkill(value),expected);
  for(const value of [null,undefined,'',true,false,'B','?',Infinity,-1,22])assert.equal(observedMarketSkill(value),null);
});
test('dates retain an instant through local input and blanks remain undated',()=>{
  const instant='2026-10-31T11:24:00.000Z';
  assert.equal(toObservedAt(toLocalDateTime(instant)),instant);
  assert.equal(toObservedAt(''),null);
  assert.equal(toLocalDateTime(null),'');
  assert.throws(()=>toObservedAt('invalid'));
});
test('new scenarios contain no assumed fees, salary, revenue or cost',()=>{
  const candidate=emptyCandidate('a'.repeat(32)),investment=emptyInvestment('b'.repeat(32));
  assert.equal(candidate.price,null);assert.equal(candidate.fees,null);assert.equal(candidate.weekly_salary,null);
  assert.equal(Object.values(candidate.skills).every(value=>value===null),true);
  assert.equal(investment.initial_cost,null);assert.equal(investment.weekly_cost,null);
  const doc={revision:8,updated_at:null,plan:{cash:null,weekly_income:null,weekly_expenses:null,reserve:null,committed_bids:null,complete:false,observed_at:null},candidates:[candidate],investments:[investment],analysis:{}};
  assert.deepEqual(Object.keys(marketDraft(doc)).sort(),['candidates','investments','plan']);
});
