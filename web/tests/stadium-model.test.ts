import test from 'node:test';
import assert from 'node:assert/strict';
import * as model from '../src/stadium-model.ts';

test('membership capacity rounds decimal halves upward before allocating seats',()=>{
  const capacity=(model as Record<string,Function>).stadiumMembershipTarget;
  assert.equal(typeof capacity,'function');
  // Integer arithmetic is an independent oracle for every slider step.
  for(let members=0;members<=1000;members++)for(let step=100;step<=240;step++){
    const expected=Math.floor((members*step+10)/20);
    assert.equal(capacity(members,step/20),expected,`${members} members x ${step/20}`);
  }
  assert.equal(capacity(25,5.1),128);
  assert.equal(capacity(1.5,9),14);
  assert.equal(capacity(1e-7,9),0);
  assert.equal(capacity(1_000_000,20),20_000_000);
});
