import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react');
function harness(){
  const hooks=[],requests=[];let cursor=0,effects=[],refreshCount=0;
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={kind:'state',value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={kind:'ref',value:{current:initial}};return hooks[i].value;},useEffect(effect,dependencies){const i=cursor++,old=hooks[i];if(!old||dependencies.some((value,k)=>!Object.is(value,old.dependencies[k]))){hooks[i]={kind:'effect',dependencies,effect,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()});}}};
  const artifact={exports:{}};
  const load=id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))};
    if(id==='./i18n')return {tr:value=>value,localeTag:()=> 'fr-FR'};
    if(id==='./types')return {fmt:value=>value??'—',date:value=>value??'—',labels:{}};
    if(id==='./navigation-guard')return {useUnsavedChanges(){}};
    if(id.endsWith('.css'))return {};
    if(id==='./market-model'||id==='./role-weights-model')return require('../src/'+id.slice(2)+'.ts');
    return require(id);
  };
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/market.tsx',import.meta.url),'utf8')+'\nexport {MarketPanel};',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:load,structuredClone,crypto,window:{confirm:()=>true},Date,JSON});
  const props={busy:false,onRefresh:async()=>{refreshCount++;props.d.squad_source={id:2,observed_at:'2026-10-31T10:00:00Z'}},d:{user:{username:'synthetic'},csrf:'session',current_team:{id:'123'},squad:[],squad_source:null}};
  return {requests,props,refreshCount:()=>refreshCount,render(){cursor=0;effects=[];const tree=artifact.exports.MarketPanel(props);effects.forEach(effect=>effect());return tree;},replayEffects(){hooks.filter(h=>h.kind==='effect').forEach(h=>{h.cleanup?.();h.cleanup=h.effect()})},unmount(){hooks.filter(h=>h.kind==='effect').forEach(h=>h.cleanup?.());},values:()=>hooks.filter(h=>h.kind==='state').map(h=>h.value)};
}
const empty={revision:0,updated_at:null,plan:{cash:null,weekly_income:null,weekly_expenses:null,reserve:null,committed_bids:null,complete:false,observed_at:null},candidates:[],investments:[],analysis:{confirmed:false,base:{},missing_fields:[],warnings:[],squad:{snapshot_id:null,observed_at:null,total:0},candidates:[],investments:[]}};
function elements(tree){return Array.isArray(tree)?tree.flatMap(elements):tree&&typeof tree==='object'?[tree,...elements(tree.props?.children)]:[];}
async function settle(){for(let i=0;i<12;i++)await Promise.resolve()}

test('save conflict retains the draft and synchronous duplicate submissions are blocked',async()=>{
  const panel=harness();panel.render();panel.requests[0].resolve(structuredClone(empty));await settle();let tree=panel.render();
  elements(tree).find(node=>node.props?.name==='cash').props.onChange({target:{value:'500'}});tree=panel.render();
  const form=elements(tree).find(node=>node.type==='form');form.props.onSubmit({preventDefault(){}});form.props.onSubmit({preventDefault(){}});
  assert.equal(panel.requests.length,2);assert.equal(panel.requests[1].body.plan.cash,500);assert.equal(panel.requests[1].body.expected_revision,0);
  panel.requests[1].reject(Object.assign(Error('conflict'),{status:409}));await settle();tree=panel.render();
  assert.equal(elements(tree).find(node=>node.props?.name==='cash').props.value,500);
  assert.ok(JSON.stringify(tree).includes('brouillon est conservé'));
});
test('responses from an unmounted club cannot populate the abandoned editor',async()=>{
  const panel=harness();panel.render();panel.unmount();panel.requests[0].resolve(structuredClone(empty));await settle();
  assert.equal(panel.values().some(value=>value?.revision===0),false);
});
test('StrictMode effect replay restarts loading and ignores the first read',async()=>{
  const panel=harness();panel.render();panel.replayEffects();
  assert.equal(panel.requests.length,2);
  panel.requests[1].resolve({...structuredClone(empty),revision:2});await settle();
  panel.requests[0].resolve({...structuredClone(empty),revision:1});await settle();
  assert.equal(panel.values().some(value=>value?.revision===2),true);
  assert.equal(panel.values().some(value=>value?.revision===1),false);
});
test('successful saves advance the optimistic revision used by subsequent saves',async()=>{
  const panel=harness();panel.render();panel.requests[0].resolve(structuredClone(empty));await settle();let tree=panel.render();
  elements(tree).find(node=>node.props?.name==='cash').props.onChange({target:{value:'500'}});tree=panel.render();elements(tree).find(node=>node.type==='form').props.onSubmit({preventDefault(){}});
  panel.requests[1].resolve({...structuredClone(empty),revision:1,plan:{...empty.plan,cash:500}});await settle();tree=panel.render();
  elements(tree).find(node=>node.props?.name==='cash').props.onChange({target:{value:'700'}});tree=panel.render();elements(tree).find(node=>node.type==='form').props.onSubmit({preventDefault(){}});
  assert.equal(panel.requests[2].body.expected_revision,1);assert.equal(panel.requests[2].body.plan.cash,700);
});
test('a newer analysis source requires a real squad refresh and preserves the unsaved budget',async()=>{
  const panel=harness();panel.props.d.squad_source={id:1,observed_at:'2026-10-30T10:00:00Z'};
  panel.render();panel.requests[0].resolve({...structuredClone(empty),analysis:{...empty.analysis,squad:{snapshot_id:1,observed_at:'2026-10-30T10:00:00Z',total:0}}});await settle();let tree=panel.render();
  elements(tree).find(node=>node.props?.name==='cash').props.onChange({target:{value:'500'}});tree=panel.render();
  elements(tree).find(node=>node.type==='button'&&JSON.stringify(node.props.children).includes('Comparer les scénarios')).props.onClick();
  const newer={...empty.analysis,squad:{snapshot_id:2,observed_at:'2026-10-31T10:00:00Z',total:0}};
  panel.requests[1].resolve({analysis:newer});await settle();tree=panel.render();
  const refresh=elements(tree).find(node=>node.type==='button'&&JSON.stringify(node.props.children).includes('Actualiser l’effectif et recalculer'));
  assert.ok(refresh,'must offer an App state refresh instead of merely re-analyzing against stale props');
  refresh.props.onClick();refresh.props.onClick();await settle();
  assert.equal(panel.refreshCount(),1);assert.equal(panel.requests.length,3);
  assert.equal(panel.requests[2].body.plan.cash,500);
  panel.requests[2].resolve({analysis:newer});await settle();tree=panel.render();
  assert.equal(elements(tree).find(node=>node.props?.name==='cash').props.value,500);
  assert.equal(JSON.stringify(tree).includes('Brouillon non enregistré'),true);
  assert.equal(JSON.stringify(tree).includes('Actualiser l’effectif et recalculer'),false);
});
