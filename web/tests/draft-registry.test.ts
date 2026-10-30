import test from 'node:test';
import assert from 'node:assert/strict';
import {createDraftRegistry} from '../src/draft-registry.ts';

test('clean editors never ask to abandon changes',()=>{
 const drafts=createDraftRegistry();let prompts=0;
 assert.equal(drafts.canLeave(()=>{prompts++;return false}),true);
 assert.equal(prompts,0);
});
test('saving one of two editors does not remove the other draft',()=>{
 const drafts=createDraftRegistry(),plan=Symbol('plan'),note=Symbol('note');
 drafts.set(plan,true);drafts.set(note,true);drafts.set(plan,false);
 assert.equal(drafts.hasChanges(),true);
 assert.equal(drafts.canLeave(()=>false),false);
 drafts.remove(note);assert.equal(drafts.hasChanges(),false);
});
test('a cancelled departure preserves the guard; approval waits for unmount',()=>{
 const drafts=createDraftRegistry(),owner=Symbol('editor');let prompts=0;
 drafts.set(owner,true);
 assert.equal(drafts.canLeave(()=>{prompts++;return false}),false);
 assert.equal(drafts.hasChanges(),true);
 assert.equal(drafts.canLeave(()=>{prompts++;return true}),true);
 assert.equal(drafts.hasChanges(),true);
 assert.equal(prompts,2);
 drafts.remove(owner);assert.equal(drafts.canLeave(()=>false),true);
});
test('changing an editor to clean and repeated cleanup are harmless',()=>{
 const drafts=createDraftRegistry(),owner=Symbol();
 drafts.set(owner,true);drafts.set(owner,false);drafts.remove(owner);drafts.remove(owner);
 assert.equal(drafts.hasChanges(),false);
});

