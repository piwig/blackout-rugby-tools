import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function compile(file,load,globals={}){
  const path=new URL('../src/'+file,import.meta.url);
  assert.ok(existsSync(path),'The audience interface must exist');
  const artifact={exports:{}};
  const source=ts.transpileModule(readFileSync(path,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(source,{module:artifact,exports:artifact.exports,require:load,...globals});return artifact.exports;
}
function harness({locale='fr',disabled=false,dnt=false,denied=false,noNavigator=false}={}){
  let saved=disabled?'1':null;
  const writes=[],effects=[],requests=[],scripts=[];
  const window={navigator:{doNotTrack:dnt?'1':null},localStorage:{getItem(){if(denied)throw Error('denied');return saved},setItem(key,value){if(denied)throw Error('denied');saved=value;writes.push([key,value])}},addEventListener(){},location:{origin:'https://brt.example',hostname:'brt.example'}};
  if(noNavigator)delete window.navigator;
  const document={referrer:'',createElement:()=>({setAttribute(){}}),head:{appendChild:script=>scripts.push(script)}};
  const audience=compile('audience.ts',id=>id==='./navigation'?require('../src/navigation.ts'):require(id),{window,document,URL,fetch:()=>new Promise(resolve=>requests.push({resolve}))});
  const catalog=JSON.parse(readFileSync(new URL('../src/i18n/locales/'+locale+'.json',import.meta.url),'utf8'));
  const tr=source=>catalog[source]??source;
  const react={...React,useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useEffect:()=>{},useLayoutEffect:effect=>effects.push(effect)};
  const ui=compile('audience-ui.tsx',id=>id==='react'?react:id==='./audience'?audience:id==='./i18n'?{tr}:id.endsWith('.css')?{}:require(id));
  return {ui,audience,writes,effects,requests,scripts,tree:()=>ui.AudiencePreferences(),render:()=>renderToStaticMarkup(ui.AudiencePreferences())};
}
function nodes(value){return Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props?.children)]:[]}

test('audience information exposes an accessible local choice and technical processing in all languages',()=>{
  for(const [locale,label,technical] of [['fr','Autoriser la mesure d’audience','requêtes'],['en','Allow audience measurement','requests'],['es','Permitir la medición de audiencia','solicitudes'],['it','Consenti la misurazione del pubblico','richieste']]){
    const html=harness({locale}).render();
    assert.match(html,/<details[^>]*class="audience-preferences"/);
    assert.match(html,/<summary>/);assert.ok(html.includes(label));assert.ok(html.includes(technical));
    assert.match(html,/IP/);assert.match(html,/User-Agent/);assert.match(html,/<label[^>]*><input[^>]*type="checkbox"[^>]*checked=""/);
  }
});

test('the visible checkbox immediately persists a local refusal and can enable it again',()=>{
  const h=harness();
  const checkbox=nodes(h.tree()).find(node=>node.type==='input'&&node.props.type==='checkbox');
  checkbox.props.onChange({currentTarget:{checked:false}});
  assert.equal(h.audience.getAudienceChoice().disabled,true);
  assert.deepEqual(h.writes.at(-1),['brt-audience-disabled','1']);
  checkbox.props.onChange({currentTarget:{checked:true}});
  assert.equal(h.audience.getAudienceChoice().disabled,false);
});

test('DNT and denied storage explain why the audience choice is unavailable',()=>{
  for(const settings of [{dnt:true},{denied:true}]){
    const h=harness(settings),html=h.render();
    assert.match(html,/<input[^>]*disabled=""/);assert.doesNotMatch(html,/<input[^>]*checked=""/);
    assert.match(html,settings.dnt?/Do Not Track/:/stockage local/);
  }
});

test('the view hook starts after commit and cleanup prevents a late tracker load',async()=>{
  const h=harness();
  h.ui.useAudienceView('home',false);
  assert.equal(h.effects.length,1);
  assert.equal(h.requests.length,0);
  const cleanup=h.effects[0]();
  assert.equal(h.requests.length,1);
  cleanup();
  h.requests[0].resolve({ok:true,json:async()=>({enabled:true,script_url:'https://stats.example/script.js',website_id:'fbe43dbb-6413-40a9-a833-97cb73779123',hostname:'brt.example'})});
  for(let i=0;i<15;i++)await Promise.resolve();
  assert.equal(h.scripts.length,0);
});

test('audience information remains renderable without a browser navigator',()=>{
  assert.match(harness({noNavigator:true}).render(),/<summary>/);
});
