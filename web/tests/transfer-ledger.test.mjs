import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const statistic={count:0,cancelled_count:0,buy_count:0,sell_count:0,purchases:'0.00',sales:'0.00',fees:'0.00',balance:'0.00',average_buy_gross:null,average_sell_gross:null,largest_purchase_gross:null,largest_sale_gross:null,largest_sale_net:null};
const empty={revision:0,updated_at:null,entries:[],statistics:statistic,by_season:[],by_player:[],seasons:[],total:0,total_stored:0,offset:0,limit:50};
function harness(){
  const hooks=[],requests=[];let cursor=0,effects=[],dirty=false;
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={kind:'state',value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={kind:'ref',value:{current:initial}};return hooks[i].value;},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((v,k)=>!Object.is(v,old.deps[k]))){hooks[i]={kind:'effect',deps,effect,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()});}}};
  const artifact={exports:{}};
  const load=id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))};
    if(id==='./i18n')return {tr:(value,vars={})=>value.replace(/\{(\w+)\}/g,(_,key)=>String(vars[key]??key)),localeTag:()=> 'fr-FR'};
    if(id==='./navigation-guard')return {useUnsavedChanges(value){dirty=value}};
    if(id.endsWith('.css'))return {};
    return require(id);
  };
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/transfer-ledger.tsx',import.meta.url),'utf8')+'\nexport {TransferLedgerPanel};',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:load,crypto,window:{confirm:()=>true},Date,JSON,Intl,URL,URLSearchParams,Blob});
  const props={busy:false,d:{user:{username:'synthetic'},csrf:'session',current_team:{id:'123'}}};
  return {requests,props,dirty:()=>dirty,render(){cursor=0;effects=[];const tree=artifact.exports.TransferLedgerPanel(props);effects.forEach(e=>e());return tree},unmount(){hooks.filter(h=>h.kind==='effect').forEach(h=>h.cleanup?.())},replayEffects(){hooks.filter(h=>h.kind==='effect').forEach(h=>{h.cleanup?.();h.cleanup=h.effect()})},component:artifact.exports.TransferLedger};
}
const elements=tree=>Array.isArray(tree)?tree.flatMap(elements):tree&&typeof tree==='object'?[tree,...elements(tree.props?.children)]:[];
const button=(tree,label)=>elements(tree).find(n=>n.type==='button'&&JSON.stringify(n.props.children).includes(label));
const field=(tree,name)=>elements(tree).find(n=>n.props?.name===name);
const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
async function opened(data=empty){const p=harness();p.render();p.requests[0].resolve(structuredClone(data));await tick();return p}

test('manual writes keep decimal text and the edit revision while duplicate submits are blocked',async()=>{
  const p=await opened();button(p.render(),'Ajouter une opération').props.onClick();let tree=p.render();
  assert.equal(p.dirty(),true);
  field(tree,'player_name').props.onChange({target:{value:'Synthetic player'}});
  tree=p.render();field(tree,'amount').props.onChange({target:{value:'0.10'}});
  tree=p.render();const form=elements(tree).find(n=>n.type==='form'&&n.props['data-ledger-editor']);
  form.props.onSubmit({preventDefault(){}});form.props.onSubmit({preventDefault(){}});
  assert.equal(p.requests.length,2);
  assert.equal(p.requests[1].body.entry.amount,'0.10');
  assert.equal(p.requests[1].body.expected_revision,0);
  p.requests[1].reject(Object.assign(Error('Le registre a changé.'),{status:409}));await tick();
  assert.equal(field(p.render(),'player_name').props.value,'Synthetic player');
  assert.equal(p.dirty(),true);
});

test('late responses after leaving a club cannot populate the abandoned view',async()=>{
  const p=harness();p.render();p.unmount();p.requests[0].resolve({...structuredClone(empty),revision:9});await tick();
  assert.ok(!JSON.stringify(p.render()).includes('Ajouter une opération'));
});

test('StrictMode replay ignores the first request and loads a fresh document',async()=>{
  const p=harness();p.render();p.replayEffects();assert.equal(p.requests.length,2);
  p.requests[1].resolve(structuredClone(empty));await tick();
  p.requests[0].resolve({...structuredClone(empty),revision:99});await tick();
  button(p.render(),'Ajouter une opération').props.onClick();let tree=p.render();
  elements(tree).find(n=>n.type==='form'&&n.props['data-ledger-editor']).props.onSubmit({preventDefault(){}});
  assert.equal(p.requests[2].body.expected_revision,0);
});

test('editing import content invalidates its confirmation token',async()=>{
  const p=await opened();let tree=p.render();field(tree,'import_content').props.onChange({target:{value:'[]'}});
  tree=p.render();elements(tree).find(n=>n.type==='form'&&n.props['data-ledger-import']).props.onSubmit({preventDefault(){}});
  p.requests[1].resolve({preview_id:'synthetic',revision:0,entries:[],added:1,duplicates:0,corrected:0,statistics:{...statistic,balance:'93.70'}});await tick();
  tree=p.render();assert.ok(button(tree,'Confirmer cet import'));
  const html=renderToStaticMarkup(tree);assert.match(html,/Bilan du club après cet import/);assert.match(html,/93,70/);
  field(tree,'import_content').props.onChange({target:{value:'[{}]'}});
  assert.equal(button(p.render(),'Confirmer cet import'),undefined);
});

test('audit snapshots remain visible and cancelled entries are labelled without altering supplied totals',async()=>{
  const row={id:'cancelled',player_id:'42',player_name:'Synthetic player',kind:'sell',occurred_at:'2026-01-01T12:00:00Z',season:'S50',amount:'100.00',fees:'2.00',counterparty:'Synthetic club',source:'Notebook',notes:'',status:'cancelled',cancellation_reason:'Duplicate receipt'};
  row.versions=[{version:1,operation:'create',at:'2026-01-02T12:00:00Z',reason:'',entry:{...row,status:'active',cancellation_reason:''}},{version:2,operation:'cancel',at:'2026-01-03T12:00:00Z',reason:'Duplicate receipt',entry:{...row}}];
  const p=await opened({...empty,entries:[row],total:1,total_stored:1,statistics:{...statistic,cancelled_count:1}});
  const html=renderToStaticMarkup(p.render());
  assert.match(html,/Annulée/);assert.match(html,/Duplicate receipt/);assert.match(html,/Rétablir/);
  assert.match(html,/Balance nette<\/span><strong>0/);
  assert.match(html,/2 versions/);assert.match(html,/Notebook/);
});

test('large ledger totals preserve their exact cents in the rendered metrics',async()=>{
  // 999 permitted purchases of 10^12 plus one purchase of 0.01.
  const p=await opened({...empty,statistics:{...statistic,count:1000,buy_count:1000,
    purchases:'999000000000000.01',balance:'-999000000000000.01'}});
  const html=renderToStaticMarkup(p.render()).replace(/[\u202f\u00a0]/g,' ');
  assert.match(html,/Achats bruts<\/span><strong>999 000 000 000 000,01/);
  assert.match(html,/Balance nette<\/span><strong>-999 000 000 000 000,01/);
  const small=await opened({...empty,statistics:{...statistic,balance:'-0.01'}});
  assert.match(renderToStaticMarkup(small.render()),/Balance nette<\/span><strong>-0,01/);
});

test('public component remounts on team and session changes',()=>{
  const p=harness();let tree=p.component(p.props);const first=tree.key;
  p.props.d.current_team.id='456';assert.notEqual(p.component(p.props).key,first);
  const second=p.component(p.props).key;p.props.d.csrf='new-session';assert.notEqual(p.component(p.props).key,second);
});

test('actual frontend URLs open FastAPI and preserve start-only and end-only periods',async()=>{
  const p=harness();p.render();const urls=[p.requests[0].url];
  p.requests[0].resolve(structuredClone(empty));await tick();
  let tree=p.render();elements(tree).filter(n=>n.props?.type==='date')[0].props.onChange({target:{value:'2026-01-01'}});
  tree=p.render();elements(tree).find(n=>n.type==='form'&&!n.props['data-ledger-import']).props.onSubmit({preventDefault(){}});
  urls.push(p.requests[1].url);p.requests[1].resolve(structuredClone(empty));await tick();
  tree=p.render();elements(tree).filter(n=>n.props?.type==='date')[0].props.onChange({target:{value:''}});
  tree=p.render();elements(tree).filter(n=>n.props?.type==='date')[1].props.onChange({target:{value:'2026-01-31'}});
  tree=p.render();elements(tree).find(n=>n.type==='form'&&!n.props['data-ledger-import']).props.onSubmit({preventDefault(){}});
  urls.push(p.requests[2].url);
  const script=`import json,sys,tempfile
from fastapi.testclient import TestClient
from server.main import create_app
with tempfile.TemporaryDirectory() as directory:
 app=create_app(directory,'Synthetic-password-2026!',secure=False)
 with TestClient(app) as client:
  login=client.post('/api/login',json={'username':'piwig','password':'Synthetic-password-2026!'})
  headers={'X-CSRF-Token':login.json()['csrf']}
  client.post('/api/teams',headers=headers,json={'team_id':'123','name':'Synthetic club','country':'FR'})
  print(json.dumps([client.get('/api'+url).status_code for url in json.load(sys.stdin)]))
`;
  const python=process.env.BRT_TEST_PYTHON||(process.platform==='win32'?'python':'python3');
  const result=spawnSync(python,['-c',script],{cwd:fileURLToPath(new URL('../../',import.meta.url)),input:JSON.stringify(urls),encoding:'utf8',timeout:30000});
  assert.equal(result.status,0,result.stderr+'\nSet BRT_TEST_PYTHON to the project Python interpreter if needed.');
  assert.deepEqual(JSON.parse(result.stdout),[200,200,200]);
  assert.equal(new URL('http://synthetic'+urls[1]).searchParams.get('start'),'2026-01-01');
  assert.equal(new URL('http://synthetic'+urls[2]).searchParams.get('end'),'2026-01-31');
});
