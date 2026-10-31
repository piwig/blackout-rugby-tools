import test from 'node:test';
import assert from 'node:assert/strict';
import {createStarterController,isStarterDirty,type StarterDocument,type StarterRequest} from '../src/starter-state.ts';

const scope={username:'manager-a',csrf:'session-a',teamId:'123'};
const empty:StarterDocument={team_id:'123',revision:0,updated_at:null,completed:[],collapsed:false};
function deferred<T>() {let resolve!:(value:T)=>void;let reject!:(error:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}}

test('only explicit declarations are posted with the loaded revision, CSRF and club path',async()=>{
  const calls:unknown[][]=[];
  const request:StarterRequest=async(...args)=>{
    calls.push(args);
    if(args[1]===undefined)return empty;
    return {...empty,revision:calls.length-1,updated_at:'2026-10-31T12:00:00Z',completed:['mentor'],collapsed:calls.length>2};
  };
  const controller=createStarterController(scope,request);
  assert.equal(await controller.load(),true);
  assert.deepEqual(calls[0],['/workbench/starter/123',undefined,'session-a']);
  assert.deepEqual(controller.getSnapshot().value,{completed:[],collapsed:false});
  controller.setCompleted('mentor',true);
  assert.equal(await controller.save(),true);
  assert.deepEqual(calls[1],['/workbench/starter/123',{expected_revision:0,completed:['mentor'],collapsed:false},'session-a']);
  controller.setCollapsed(true);
  assert.equal(await controller.save(),true);
  assert.deepEqual(calls[2],['/workbench/starter/123',{expected_revision:1,completed:['mentor'],collapsed:true},'session-a']);
  assert.equal(controller.getSnapshot().document?.revision,2);
  assert.equal(controller.getSnapshot().saved,true);
});

test('a pending save synchronously refuses duplicate submits, reloads and edits',async()=>{
  const pending=deferred<StarterDocument>();let posts=0;
  const controller=createStarterController(scope,async(_path,body)=>body===undefined?empty:(posts++,pending.promise));
  await controller.load();controller.setCompleted('treasury',true);
  const saving=controller.save();
  assert.equal(controller.getSnapshot().pending,'save');
  controller.setCompleted('staff',true);controller.setCollapsed(true);
  assert.equal(await controller.save(),false);
  assert.equal(await controller.load(true),false);
  assert.equal(posts,1);
  assert.deepEqual(controller.getSnapshot().value,{completed:['treasury'],collapsed:false});
  pending.resolve({...empty,revision:1,completed:['treasury']});
  assert.equal(await saving,true);
});

test('409 preserves the draft and blocks saves until an explicitly confirmed reload',async()=>{
  let reads=0,posts=0;
  const controller=createStarterController(scope,async(_path,body)=>{
    if(body===undefined)return ++reads===1?empty:{...empty,revision:4,completed:['staff']};
    posts++;throw Object.assign(new Error('Concurrent update'),{status:409});
  });
  await controller.load();controller.setCompleted('mentor',true);controller.setCollapsed(true);
  assert.equal(await controller.save(),false);
  assert.equal(controller.getSnapshot().conflict,true);
  assert.equal(controller.getSnapshot().document?.revision,0);
  assert.deepEqual(controller.getSnapshot().value,{completed:['mentor'],collapsed:true});
  assert.equal(await controller.save(),false);
  assert.equal(await controller.load(),false);
  assert.equal(posts,1);assert.equal(reads,1);
  assert.equal(await controller.load(true),true);
  assert.deepEqual(controller.getSnapshot().value,{completed:['staff'],collapsed:false});
  assert.equal(controller.getSnapshot().conflict,false);
});

test('a failed explicit reload leaves the unsaved declarations available',async()=>{
  let reads=0;
  const controller=createStarterController(scope,async()=>{if(++reads===1)return empty;throw new Error('Hors ligne')});
  await controller.load();controller.setCompleted('stadium',true);
  assert.equal(await controller.load(),false);
  assert.equal(reads,1);
  assert.equal(await controller.load(true),false);
  assert.deepEqual(controller.getSnapshot().value,{completed:['stadium'],collapsed:false});
  assert.equal(controller.getSnapshot().error,'Hors ligne');
});

test('a stopped read cannot replace a newer read or clear its pending indicator',async()=>{
  const first=deferred<StarterDocument>(),second=deferred<StarterDocument>();let reads=0;
  const controller=createStarterController(scope,async()=>++reads===1?first.promise:second.promise);
  const oldRead=controller.load();controller.stop();const newRead=controller.load();
  first.resolve({...empty,completed:['mentor']});
  assert.equal(await oldRead,false);
  assert.equal(controller.getSnapshot().pending,'load');
  assert.equal(controller.getSnapshot().document,null);
  second.resolve({...empty,revision:2,completed:['lineup']});
  assert.equal(await newRead,true);
  assert.deepEqual(controller.getSnapshot().value?.completed,['lineup']);
});

test('late saves from a previous manager, session or club never change the new controller',async()=>{
  for(const nextScope of [{...scope,username:'manager-b'},{...scope,csrf:'session-b'},{...scope,teamId:'456'}]){
    const pending=deferred<StarterDocument>();
    const old=createStarterController(scope,async(_path,body)=>body===undefined?empty:pending.promise);
    await old.load();old.setCompleted('mentor',true);const saving=old.save();old.stop();
    const next=createStarterController(nextScope,async()=>({...empty,team_id:nextScope.teamId}));
    await next.load();
    pending.resolve({...empty,revision:1,completed:['mentor']});
    assert.equal(await saving,false);
    assert.deepEqual(next.getSnapshot().value,{completed:[],collapsed:false});
    assert.equal(next.getSnapshot().saved,false);
  }
});

test('a response for another club is rejected without displaying its declarations',async()=>{
  const controller=createStarterController(scope,async()=>({...empty,team_id:'456',completed:['mentor']}));
  assert.equal(await controller.load(),false);
  assert.equal(controller.getSnapshot().value,null);
  assert.ok(controller.getSnapshot().error);
});

test('a changed cookie session rejects a stale tab read without exposing the new manager document',async()=>{
  let currentSession='session-a';
  const controller=createStarterController(scope,async(_path,_body,csrf)=>{
    if(csrf!==currentSession)throw Object.assign(new Error('Session modifiée. Reconnectez-vous.'),{status:403});
    return currentSession==='session-a'?empty:{...empty,completed:['staff']};
  });
  assert.equal(await controller.load(),true);
  controller.setCompleted('mentor',true);
  currentSession='session-b';
  assert.equal(await controller.load(true),false);
  assert.deepEqual(controller.getSnapshot().value?.completed,['mentor']);
  assert.deepEqual(controller.getSnapshot().document?.completed,[]);
  assert.match(controller.getSnapshot().error,/Session modifiée/);
});

test('undoing the declarations and disclosure change clears the navigation guard without posting',async()=>{
  let posts=0;
  const controller=createStarterController(scope,async(_path,body)=>{if(body!==undefined)posts++;return empty});
  await controller.load();
  assert.equal(isStarterDirty(controller.getSnapshot()),false);
  controller.setCompleted('economy',true);controller.setCollapsed(true);
  assert.equal(isStarterDirty(controller.getSnapshot()),true);
  controller.setCompleted('economy',false);
  assert.equal(isStarterDirty(controller.getSnapshot()),true);
  controller.setCollapsed(false);
  assert.equal(isStarterDirty(controller.getSnapshot()),false);
  assert.equal(await controller.save(),false);
  assert.equal(posts,0);
});
