import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const sourceDir=path.resolve(import.meta.dirname,'../src'),cache=new Map();
const i18n=require('../src/i18n/runtime.ts');
i18n.installCatalogs({fr:JSON.parse(readFileSync(path.join(sourceDir,'i18n/locales/fr.json'),'utf8'))});
function production(file) {
  if(cache.has(file))return cache.get(file).exports;
  const artifact={exports:{}};cache.set(file,artifact);
  const compiled=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const load=id=>{
    if(id==='./i18n')return i18n;
    if(id.endsWith('.css'))return {};
    if(id==='./App')return {request:()=>{throw new Error('Rendering must not make network requests')}};
    if(!id.startsWith('.'))return require(id);
    const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(candidate=>existsSync(candidate));
    return production(target);
  };
  vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,structuredClone,Map,Set,URLSearchParams});
  return artifact.exports;
}
const {MatchReview}=production(path.join(sourceDir,'match-review.tsx'));
const {NavigationGuardProvider}=production(path.join(sourceDir,'navigation-guard.tsx'));
const {HistoryDistribution}=production(path.join(sourceDir,'match-history.tsx'));

test('20,000 source events render a bounded, keyboard-editable first page with unchanged source text',()=>{
  const events=Array.from({length:20000},(_,i)=>({event_key:String(i),source_event:{minute:i===0?0:i,text:i===0?'Original <commentaire>':'Événement '+i,possession:0,field:0},annotation:null,suggestion:null}));
  const match={id:'123',type:0,home:'Domicile',away:'Extérieur',events,summary:{classified:0,total_events:20000,unclassified:20000},review:{revision:0,source_digest:'a'.repeat(64),annotation_count:0,orphaned_count:0,suggestion_count:0,learning_conflicts:0}};
  const html=renderToStaticMarkup(React.createElement(NavigationGuardProvider,null,React.createElement(MatchReview,{match,scope:'test',act:()=>{},busy:false,onUpdated:()=>{}})));
  assert.equal((html.match(/class="match-review-event"/g)||[]).length,50);
  assert.match(html,/Original &lt;commentaire&gt;/);
  assert.match(html,/aria-label="Classer l’événement 1 : Non classé"/);
  assert.match(html,/Page 1 sur 400/);
  assert.match(html,/<strong>0<\/strong><small>Événement 1/);
  assert.doesNotMatch(html,/NaN|Infinity/);
});

test('an empty historical distribution displays unknown percentages without a fake observed percentage',()=>{
  const html=renderToStaticMarkup(React.createElement(HistoryDistribution,{title:'Test',values:[{name:'22',count:0,percent:null}]}));
  assert.match(html,/<strong>0<small>—<\/small>/);
  assert.doesNotMatch(html,/>0 %<|NaN|Infinity/);
  assert.match(html,/aria-hidden="true"/);
});

test('match review distinguishes an unknown coverage from a small real percentage',()=>{
  for(const [classified,total,text] of [[1,20000,'0,005 %'],[0,0,'— %']]){
    const match={id:'123',type:0,home:'Home',away:'Away',events:[],summary:{classified,total_events:total},review:{revision:0}};
    const html=renderToStaticMarkup(React.createElement(NavigationGuardProvider,null,React.createElement(MatchReview,{match,scope:'test',act:()=>{},busy:false,onUpdated:()=>{}})));
    assert.ok(html.includes(text),text);
  }
});
