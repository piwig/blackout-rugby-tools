import test from 'node:test';
import assert from 'node:assert/strict';
import {roleNames, skillKeys, validRoleWeights, roleCoverage, changeRoleWeight} from '../src/role-weights-model.ts';

const weights = () => Object.fromEntries(roleNames.map(role => [role,Object.fromEntries(skillKeys.map(skill => [skill,skill==='speed'?1:0]))]));

test('strict complete coefficients reject fabricated values and unknown keys', () => {
  const w = weights();
  assert.equal(validRoleWeights(w),true);
  assert.equal(validRoleWeights({...w,other:w.Pilier}),false);
  for(const value of [NaN,Infinity,-1,11,1.5,true,'2']) {
    assert.equal(validRoleWeights({...w,Pilier:{...w.Pilier,speed:value}}),false);
  }
  assert.equal(validRoleWeights({...w,Pilier:Object.fromEntries(skillKeys.map(skill=>[skill,0]))}),false);
});

test('coverage needs exactly positive-weight known skills; editing preserves previous snapshot', () => {
  const w = weights();
  assert.deepEqual(roleCoverage([{speed:10,handling:null},{speed:null},{speed:'NaN'},{speed:true}],w.Pilier),{known:1,total:4});
  const edited = changeRoleWeight(w,'Pilier','handling',2);
  assert.equal(w.Pilier.handling,0);
  assert.equal(edited.Pilier.handling,2);
  assert.deepEqual(roleCoverage([{speed:10,handling:null}],edited.Pilier),{known:0,total:1});
});
