import test from 'node:test';
import assert from 'node:assert/strict';
import {createDraft, changeDraft, isDraftDirty, sameFormScope, type DraftState} from '../src/form-draft.ts';

test('saving uses the original baseline and refuses edits until a delayed response completes', async () => {
  let state = createDraft({one:'1'});
  state = changeDraft(state,{type:'edit',value:{one:'2'}});
  state = changeDraft(state,{type:'begin'});
  assert.deepEqual(state.baseline,{one:'1'});
  state = changeDraft(state,{type:'edit',value:{one:'3'}});
  await Promise.resolve();
  state = changeDraft(state,{type:'saved'});
  assert.deepEqual(state.value,{one:'2'});
  assert.deepEqual(state.baseline,{one:'2'});
  assert.equal(isDraftDirty(state),false);
});

test('conflict keeps the draft and original baseline until an explicit replacement', () => {
  let state = createDraft({one:'1'});
  state = changeDraft(state,{type:'edit',value:{one:'2'}});
  state = changeDraft(state,{type:'begin'});
  state = changeDraft(state,{type:'failed',error:'Conflict',conflict:true});
  state = changeDraft(state,{type:'refresh',value:{one:'3'}});
  assert.deepEqual(state.value,{one:'2'});
  assert.deepEqual(state.baseline,{one:'1'});
  assert.equal(state.conflict,true);
  assert.equal(isDraftDirty(state),true);
  state = changeDraft(state,{type:'replace',value:{one:'3'}});
  assert.deepEqual(state.value,{one:'3'});
  assert.equal(isDraftDirty(state),false);
  assert.equal(state.conflict,false);
});

test('unchanged form is clean regardless of object key order and can receive new observations', () => {
  let state:DraftState<Record<string,string>> = createDraft({one:'1',two:'2'});
  state = changeDraft(state,{type:'edit',value:{two:'2',one:'1'}});
  assert.equal(isDraftDirty(state),false);
  state = changeDraft(state,{type:'refresh',value:{one:'3'}});
  assert.deepEqual(state.value,{one:'3'});
});

test('external observations cannot replace a draft or pending save', () => {
  let state = createDraft([['']]);
  state = changeDraft(state,{type:'edit',value:[['attack']]});
  state = changeDraft(state,{type:'begin'});
  state = changeDraft(state,{type:'refresh',value:[['speed']]});
  assert.deepEqual(state.value,[['attack']]);
  assert.deepEqual(state.baseline,[['']]);
});

test('a reload response cannot move a draft into another manager, session or club', () => {
  const scope={user:{username:'manager-a'},csrf:'session-a',current_team:{id:'1'}};
  assert.equal(sameFormScope(scope,{...scope}),true);
  assert.equal(sameFormScope(scope,{...scope,user:{username:'manager-b'}}),false);
  assert.equal(sameFormScope(scope,{...scope,csrf:'session-b'}),false);
  assert.equal(sameFormScope(scope,{...scope,current_team:{id:'2'}}),false);
});

test('the loaded baseline remains independent of changes to its source object', () => {
  const original=[['attack']];
  const state=createDraft(original);
  original[0][0]='speed';
  assert.deepEqual(state.baseline,[['attack']]);
  assert.deepEqual(state.value,[['attack']]);
});
