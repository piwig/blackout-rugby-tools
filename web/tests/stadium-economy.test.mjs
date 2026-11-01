import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react');

// Execute the production component; only React's scheduling and network boundary are controlled.
function harness(){
 const hooks=[],requests=[],confirmations=[];let cursor=0,effects=[],dirty=false,confirmResult=true;
 const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={kind:'state',value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}]},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={kind:'ref',value:{current:initial}};return hooks[i].value},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((value,k)=>!Object.is(value,old.deps[k]))){hooks[i]={kind:'effect',deps,effect,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()})}}};
 const artifact={exports:{}};
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/stadium-economy.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:id=>{
  if(id==='react')return react;
  if(id==='./App')return {request:(url,body,csrf)=>new Promise((resolve,reject)=>requests.push({url,body,csrf,resolve,reject}))};
  if(id==='./i18n')return {tr:s=>s};
  if(id==='./navigation-guard')return {useUnsavedChanges:value=>{dirty=value}};
  if(id.endsWith('.css'))return {};
  return require(id);
 },crypto,structuredClone,JSON,Date,URL,Blob,setTimeout,window:{confirm:message=>{confirmations.push(message);return confirmResult}}});
 const props={busy:false,d:{user:{username:'synthetic'},csrf:'session-1',current_team:{id:'101'}}};
 return {props,requests,confirmations,dirty:()=>dirty,setConfirm:value=>{confirmResult=value},render(){cursor=0;effects=[];const tree=artifact.exports.StadiumEconomy(props);effects.forEach(effect=>effect());return tree},unmount(){hooks.filter(h=>h.kind==='effect').forEach(h=>h.cleanup?.())},replay(){hooks.filter(h=>h.kind==='effect').forEach(h=>{h.cleanup?.();h.cleanup=h.effect()})}};
}
const nodes=tree=>Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[];
const button=(tree,label)=>nodes(tree).find(node=>node.type==='button'&&JSON.stringify(node.props.children).includes(label));
const field=(tree,side,kind)=>nodes(tree).find(node=>node.props?.['aria-label']===`Debout · ${side} · ${kind}`);
const settle=async()=>{for(let i=0;i<15;i++)await Promise.resolve()};
function seed(capacity=100){return {seats:Object.fromEntries(['standing','uncovered','covered','members','corporate'].map(key=>[key,{capacity:key==='standing'?capacity:null,price:null,occupancy:null,variable_cost:null}])),ancillary_revenue_per_spectator:null,ancillary_cost_per_spectator:null,ancillary_revenue_fixed:null,ancillary_cost_fixed:null,match_fixed_cost:null,weekly_upkeep:null,investment:null,source:'API Classic',observed_on:'2026-11-01'}}
function document(capacity=100,team='101'){return {team_id:team,revision:0,scenarios:[],initial_current:seed(capacity)}}
async function opened(){const h=harness();h.render();h.requests[0].resolve(document());await settle();return h}

test('save then new retains verified capacity even when an older POST response omits the seed',async()=>{
 const h=await opened();button(h.render(),'Nouveau scénario').props.onClick();let tree=h.render();assert.equal(field(tree,'Situation actuelle','Capacité').props.value,100);
 button(tree,'Enregistrer les scénarios').props.onClick();button(tree,'Enregistrer les scénarios').props.onClick();assert.equal(h.requests.length,2);
 h.requests[1].resolve({team_id:'101',revision:1,scenarios:h.requests[1].body.scenarios});await settle();
 button(h.render(),'Nouveau scénario').props.onClick();tree=h.render();assert.equal(field(tree,'Situation actuelle','Capacité').props.value,100);assert.equal(field(tree,'Situation actuelle','Prix par entrée').props.value,'');
});

test('project starts collapsed and explicit copy confirmation preserves current inputs and unknowns',async()=>{
 const h=await opened();button(h.render(),'Nouveau scénario').props.onClick();let tree=h.render();
 const project=nodes(tree).find(n=>n.type==='details'&&n.props['data-stadium-project']);assert.ok(project);assert.ok(!project.props.open);
 const order=nodes(tree);assert.ok(order.indexOf(button(tree,'Copier les hypothèses'))<order.indexOf(project));
 field(tree,'Situation actuelle','Prix par entrée').props.onChange({target:{value:'12.34'}});tree=h.render();
 field(tree,'Projet de stade','Capacité').props.onChange({target:{value:'77'}});tree=h.render();
 h.setConfirm(false);button(tree,'Copier les hypothèses').props.onClick();tree=h.render();assert.equal(field(tree,'Projet de stade','Capacité').props.value,77);
 h.setConfirm(true);button(tree,'Copier les hypothèses').props.onClick();tree=h.render();assert.equal(h.confirmations.length,2);assert.equal(field(tree,'Projet de stade','Capacité').props.value,100);assert.equal(field(tree,'Projet de stade','Prix par entrée').props.value,'12.34');assert.equal(field(tree,'Projet de stade','Remplissage (%)').props.value,'');
 field(tree,'Projet de stade','Prix par entrée').props.onChange({target:{value:'99'}});tree=h.render();assert.equal(field(tree,'Situation actuelle','Prix par entrée').props.value,'12.34');assert.equal(h.dirty(),true);
 button(tree,'Calculer la comparaison').props.onClick();const input=h.requests[1].body.scenario;assert.equal(input.project.weekly_upkeep,null);assert.equal(input.project.ancillary_revenue_fixed,null);
});

test('old save and load cannot restore drafts or capacity across team and session changes',async()=>{
 const h=await opened();button(h.render(),'Nouveau scénario').props.onClick();button(h.render(),'Enregistrer les scénarios').props.onClick();
 h.props.d.current_team.id='202';h.props.d.user.username='other';h.props.d.csrf='session-2';let tree=h.render();assert.equal(field(tree,'Situation actuelle','Capacité'),undefined);assert.equal(h.requests[2].csrf,'session-2');
 h.requests[1].resolve({revision:99,team_id:'101',scenarios:h.requests[1].body.scenarios,initial_current:seed(999)});await settle();tree=h.render();assert.equal(field(tree,'Situation actuelle','Capacité'),undefined);
 h.requests[2].resolve(document(200,'202'));await settle();button(h.render(),'Nouveau scénario').props.onClick();tree=h.render();assert.equal(field(tree,'Situation actuelle','Capacité').props.value,200);
 const abandoned=harness();abandoned.render();abandoned.props.d.current_team.id='202';abandoned.render();abandoned.requests[1].resolve(document(200,'202'));await settle();abandoned.requests[0].resolve(document(999));await settle();button(abandoned.render(),'Nouveau scénario').props.onClick();assert.equal(field(abandoned.render(),'Situation actuelle','Capacité').props.value,200);
});

test('StrictMode replay and leaving the view invalidate outstanding requests',async()=>{
 const h=harness();h.render();h.replay();assert.equal(h.requests.length,2);h.requests[1].resolve(document(200));await settle();h.requests[0].resolve(document(999));await settle();button(h.render(),'Nouveau scénario').props.onClick();assert.equal(field(h.render(),'Situation actuelle','Capacité').props.value,200);
 const abandoned=harness();abandoned.render();abandoned.unmount();abandoned.requests[0].resolve(document());await settle();assert.equal(field(abandoned.render(),'Situation actuelle','Capacité'),undefined);
});
