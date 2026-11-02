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
    if(id==='./App')return {request:overrides.request||(()=>{throw Error('Unexpected network call during rendering')})};
    if(id==='./i18n')return {localeTag:()=> 'fr-FR',tr:(s,p={})=>s.replace(/\{(\w+)\}/g,(_,k)=>p[k]??`{${k}}`)};
    if(id.endsWith('.css'))return {};
    if(!id.startsWith('.'))return require(id);
    const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(existsSync);return load(target,cache,overrides);
  };
  const source=readFileSync(file,'utf8')+(file.endsWith('match-sheet.tsx')?'\nexport {ScopedMatchSheet};':'');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:req,URL,URLSearchParams,Date,Math,Error});
  return module.exports;
}
test('every jersey has a stable pair, with role badges and unknown values',()=>{
  const {SheetReportView}=load(path.join(root,'match-sheet.tsx'));
  const side={team_id:'9',name:'Home',lineup_state:'available',deadline_at:null,tactics_deadline_at:null,energy_scale:'auto',groups:[],
    players:Array.from({length:23},(_,i)=>({slot:i+1,player_id:String(100+i),status:i===2?'missing_player':'available',name:i===2?null:`Player ${i+1}`,captain:i===0,kicker:i===9,csr:10000,weight:null,height:190,form:7,energy_raw:10,energy_percent:null,energy_scale:'unknown',experience:7,aggression:3,discipline:4,adjusted_csr:null}))};
  const r={retrieved_at:'2026-01-01T12:00:00Z',fixture:{id:'90',start_at:null},home:side,guest:{...side,team_id:'8',name:'Away',lineup_state:'not_provided'},timing:{indicative:{lineup_at:null,publication_at:null,tactics_at:null}}};
  const html=renderToStaticMarkup(React.createElement(SheetReportView,{report:r}));
  assert.equal((html.match(/data-jersey="\d+"/g)||[]).length,23);
  assert.match(html,/Capitaine/);assert.match(html,/Buteur/);assert.match(html,/Fiche non fournie/);
  assert.match(html,/Échelle inconnue/);assert.match(html,/Feuille non fournie par Classic/);
  assert.match(html,/Repères indicatifs/);assert.match(html,/Indice personnel/);
  assert.match(html,/Notre contrôle avant match/);
  assert.match(html,/Horaires à confirmer dans Classic/);
  assert.match(html,/<article[^>]*aria-label="Home · #1 · Player 1"/);
  assert.match(html,/aria-label="Poids total · Home"/);
  assert.match(html,/aria-label="Poids total · Away"/);
  const unavailable=renderToStaticMarkup(React.createElement(SheetReportView,{report:{...r,guest:{...r.guest,lineup_state:'unavailable'}}}));
  assert.match(unavailable,/Lecture impossible pour cette feuille/);
});

const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props?.children)]:[];
function interaction(){
  const hooks=[],requests=[];let cursor=0,cleanup;
  const react={...React,useId:()=> 'test-id',useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:initial};return [hooks[i].value,v=>{hooks[i].value=typeof v==='function'?v(hooks[i].value):v}]},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value},useEffect(fn){if(!cleanup)cleanup=fn()}};
  const {ScopedMatchSheet}=load(path.join(root,'match-sheet.tsx'),new Map(),{react,request:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
  const props={d:{user:{username:'synthetic'},csrf:'test-session',current_team:{id:'9'}},kind:3};
  const render=()=>{cursor=0;return ScopedMatchSheet(props)};
  return {hooks,requests,render,unmount:()=>cleanup?.()};
}
test('a late calendar response cannot update an unmounted team context',async()=>{
  const h=interaction(),tree=h.render();
  nodes(tree).find(n=>n.type==='button'&&n.props.className==='button secondary').props.onClick();
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].body.match_type,3);
  h.unmount();h.requests[0].resolve({team_id:'9',match_type:3,retrieved_at:'2026-01-01T12:00:00Z',fixtures:[]});
  for(let i=0;i<5;i++)await Promise.resolve();
  assert.equal(h.hooks[2].value,null);
});
test('a failed refresh keeps the previous dated report',async()=>{
  const h=interaction();let tree=h.render();
  nodes(tree).find(n=>n.type==='input').props.onChange({target:{value:'90'}});
  const previous={retrieved_at:'2026-01-01T12:00:00Z'};h.hooks[4].value=previous;
  tree=h.render();nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].body.reference,'90');
  h.requests[0].reject(Error('Temporary Classic failure'));
  for(let i=0;i<5;i++)await Promise.resolve();
  assert.equal(h.hooks[4].value,previous);assert.equal(h.hooks[6].value,'Temporary Classic failure');
});

test('a verified fallback calendar is explicitly labelled incomplete',()=>{
  const h=interaction();h.render();h.hooks[2].value={partial:true,fixtures:[]};
  const notice=nodes(h.render()).find(n=>n.type==='p'&&n.props.className==='notice warning');
  assert.match(notice.props.children,/calendrier junior complet/);
  assert.match(notice.props.children,/vérifiées/);
});
