import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(import.meta.dirname,'../src');
function load(file,cache=new Map(),overrides={}){
 if(cache.has(file))return cache.get(file).exports;
 const module={exports:{}};cache.set(file,module);
 const req=id=>{
  if(id==='react'&&overrides.react)return overrides.react;
  if(id==='./App')return {request:overrides.request};
  if(id.includes('i18n'))return {localeTag:()=> 'fr-FR',tr:(s,p={})=>s.replace(/\{(\w+)\}/g,(_,k)=>p[k]??`{${k}}`)};
  if(id.endsWith('.css'))return {};
  if(!id.startsWith('.'))return require(id);
  const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(existsSync);return load(target,cache,overrides);
 };
 vm.runInNewContext(ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:req,Date,Intl,Math,Number,Set});return module.exports;
}
const props={teamId:'9',kind:0,fixtureId:'900',participants:['9','8'],csrf:'synthetic',busy:false};
function interaction(){
 const hooks=[],requests=[];let cursor=0,cleanup;
 const react={...React,useId:()=> 'recent-test',useState(initial){const i=cursor++;hooks[i]??={value:initial};return [hooks[i].value,v=>hooks[i].value=typeof v==='function'?v(hooks[i].value):v]},useRef(initial){const i=cursor++;hooks[i]??={value:{current:initial}};return hooks[i].value},useEffect(fn){if(!cleanup)cleanup=fn()}};
 const {RecentMatchComparison}=load(path.join(root,'match-recent.tsx'),new Map(),{react,request:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
 return {hooks,requests,render:()=>{cursor=0;return RecentMatchComparison(props)},unmount:()=>cleanup?.()};
}
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props?.children)]:[];
test('recent comparison is deliberate, scoped and ignores a late unmounted response',async()=>{
 const h=interaction();nodes(h.render()).find(n=>n.type==='button').props.onClick();
 assert.deepEqual({...h.requests[0].body},{team_id:'9',match_type:0,reference:'900'});
 h.unmount();h.requests[0].resolve({team_id:'8'});for(let i=0;i<5;i++)await Promise.resolve();
 assert.equal(h.hooks[2].value,null);
});
test('failed refresh preserves the last report with an explicit error',async()=>{
 const h=interaction();h.render();const previous={retrieved_at:'2026-01-01T12:00:00Z',sides:[]};h.hooks[2].value=previous;
 nodes(h.render()).find(n=>n.type==='button').props.onClick();h.requests[0].reject(Error('Temporary failure'));
 for(let i=0;i<5;i++)await Promise.resolve();assert.equal(h.hooks[2].value,previous);
});
test('recent card shows a true zero score, raw weather code, rating and source without forecasts',()=>{
 const {RecentMatchCard}=load(path.join(root,'match-recent.tsx'));
 const match={id:'100',type:0,home_id:'9',guest_id:'8',home_name:'Home',guest_name:'Away',start_at:'2026-01-10T12:00:00Z',finish_at:'2026-01-10T14:00:00Z',competition:'Friendly',weather_code:'3',home_score:0,guest_score:0,report_state:'available',ratings:{scrum:11},pack_weight:850,xv_weight:1450,starting_csr:null};
 const html=renderToStaticMarkup(React.createElement(RecentMatchCard,{match,kind:0}));
 assert.match(html,/0 – 0/);assert.match(html,/Code météo Classic/);assert.match(html,/850/);assert.match(html,/Reporter Classic/);assert.match(html,/11/);
 const missing=renderToStaticMarkup(React.createElement(RecentMatchCard,{match:{...match,report_state:'unavailable',home_score:null,guest_score:null,ratings:{}},kind:0}));
 assert.match(missing,/Rapport indisponible/);assert.doesNotMatch(missing,/0 – 0/);
});
