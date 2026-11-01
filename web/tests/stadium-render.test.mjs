import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const sourceDir=path.resolve(import.meta.dirname,'../src'),cache=new Map(),i18n=require('../src/i18n/runtime.ts');
i18n.installCatalogs({fr:{},en:{}});i18n.setLocale('en');
function production(file){
  if(cache.has(file))return cache.get(file).exports;
  const artifact={exports:{}};cache.set(file,artifact);
  const compiled=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const load=id=>{
    if(id==='./i18n'||id==='./i18n/runtime.ts')return i18n;
    if(id.endsWith('.css'))return {};
    if(id==='./App')return {request:()=>{throw new Error('Rendering must not issue requests')}};
    if(id==='./insights')return {StadiumScenarios:()=>null};
    if(!id.startsWith('.'))return require(id);
    const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(existsSync);
    return production(target);
  };
  vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,structuredClone,Map,Set,URLSearchParams});
  return artifact.exports;
}
const {Stadium}=production(path.join(sourceDir,'pages.tsx'));

test('the visible membership simulator conserves the total and agrees with the server allocation',()=>{
  for(const [members,total] of [[1,9],[7,63],[73,657],[1001,9009]]){
    const html=renderToStaticMarkup(React.createElement(Stadium,{d:{current_team:{id:'1',meta:{members}}},act:()=>{},busy:false}));
    const displayed=new Intl.NumberFormat('en-GB').format(total);
    assert.ok(html.includes('<strong>'+displayed+'</strong>'),`target for ${members} members must be ${total}`);
    if(members===1){
      const body=html.match(/<tbody>(.*?)<\/tbody>/s)[1];
      const targets=[...body.matchAll(/<\/td><td>(\d+)<\/td><td class=/g)].map(match=>Number(match[1]));
      assert.deepEqual(targets,[2,3,3,1,0]);
    }
  }
});

test('missing or invalid observations stay blank and cannot produce a capacity recommendation',()=>{
  for(const unknown of [undefined,null,'',' ',false,'invalid',-1,Infinity]){
    const html=renderToStaticMarkup(React.createElement(Stadium,{d:{current_team:{id:'1',meta:{members:unknown,stadium_standing:unknown}}},act:()=>{},busy:false}));
    const target=html.match(/class="stadium-target">(.*?)<\/div>/s)[1];
    assert.match(target,/<strong>—<\/strong>/,String(unknown));
    assert.doesNotMatch(target,/0 places à ajouter/);
    assert.match(html,/aria-label="Capacité : Debout"[^>]*value=""/,String(unknown));
  }
});

test('nondecimal source text cannot become a known member or seat count',()=>{
  for(const invalid of ['0x10','0b10','0o10','1__0','1_','1e_2','\ufeff16\ufeff']){
    const html=renderToStaticMarkup(React.createElement(Stadium,{d:{current_team:{id:'1',meta:{members:invalid,stadium_standing:invalid}}},act:()=>{},busy:false}));
    const target=html.match(/class="stadium-target">(.*?)<\/div>/s)[1];
    assert.match(target,/<strong>—<\/strong>/,invalid);
    assert.match(html,/aria-label="Capacité : Debout"[^>]*value=""/,invalid);
  }
});

test('decimal and scientific source counts retain the server numeric meaning',()=>{
  // Hand-calculated capacities at the default multiplier of nine.
  for(const [source,target] of [['1e2',900],['.5e2',450],['1,5e2',1350],['1_0',90],['\u008510\u0085',90],['+0',0],['0.0',0]]){
    const html=renderToStaticMarkup(React.createElement(Stadium,{d:{current_team:{id:'1',meta:{members:source}}},act:()=>{},busy:false}));
    const output=html.match(/class="stadium-target">(.*?)<\/div>/s)[1];
    assert.ok(output.includes('<strong>'+new Intl.NumberFormat('en-GB').format(target)+'</strong>'),source);
  }
});

test('known total capacity cannot replace missing per-section observations',()=>{
  const html=renderToStaticMarkup(React.createElement(Stadium,{d:{current_team:{id:'1',meta:{members:100,stadium_capacity:900}}},act:()=>{},busy:false}));
  const target=html.match(/class="stadium-target">(.*?)<\/div>/s)[1];
  assert.match(target,/<strong>900<\/strong>/);
  assert.doesNotMatch(target,/900 places à ajouter/);
  assert.match(html,/<tfoot><tr><th>Total<\/th><td>100 %<\/td><td>—<\/td><td>900<\/td><td>—<\/td><td>—<\/td>/);
});

test('explicit zero observations remain usable for a capacity simulation',()=>{
  const seats={stadium_standing:0,stadium_uncovered:0,stadium_covered:0,stadium_members:0,stadium_corporate:0};
  for(const [members,target] of [[0,0],[100,900]]){
    const html=renderToStaticMarkup(React.createElement(Stadium,{d:{current_team:{id:'1',meta:{members,...seats}}},act:()=>{},busy:false}));
    assert.match(html,new RegExp(`${target} places à ajouter`));
    assert.match(html,/aria-label="Capacité : Debout"[^>]*value="0"/);
  }
});

test('manual simulation can fill missing observations and clearing one seat makes additions unknown',()=>{
  const states=[];let cursor=0;
  const props={d:{current_team:{id:'1',meta:{}}},act:()=>{},busy:false};
  function render(){
    cursor=0;const savedState=React.useState,savedEffect=React.useEffect;
    React.useState=initial=>{const i=cursor++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return [states[i],next=>{states[i]=typeof next==='function'?next(states[i]):next}];};
    React.useEffect=()=>{};
    try{return Stadium(props)}finally{React.useState=savedState;React.useEffect=savedEffect}
  }
  const elements=tree=>Array.isArray(tree)?tree.flatMap(elements):tree&&typeof tree==='object'?[tree,...elements(tree.props?.children)]:[];
  let tree=render();
  elements(tree).find(node=>node.type==='input'&&node.props.max==='1000000').props.onChange({target:{value:'100'}});
  // Each real handler captures its current render, as a browser event does.
  for(let index=0;index<5;index++)elements(render()).filter(node=>node.type==='input'&&node.props.className==='seat-input')[index].props.onChange({target:{value:'0'}});
  assert.match(renderToStaticMarkup(render()),/900 places à ajouter/);
  elements(render()).find(node=>node.props?.['aria-label']==='Capacité : Debout').props.onChange({target:{value:''}});
  const html=renderToStaticMarkup(render());
  assert.doesNotMatch(html,/900 places à ajouter/);
  assert.match(html,/aria-label="Capacité : Debout"[^>]*value=""/);
});
