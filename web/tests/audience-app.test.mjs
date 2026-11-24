import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react');
const navigation=require('../src/navigation.ts');
const profile={motion:'normal',display_name:'',density:'normal',text_size:'normal'};
const state={user:{username:'PRIVATE MANAGER',admin:false},csrf:'PRIVATE TOKEN',teams:[],current_team:{id:'PRIVATE CLUB ID',name:'PRIVATE CLUB',meta:{}},profile:{profile}};
function compile(file,load,extra=''){
  const artifact={exports:{}};
  const source=ts.transpileModule(readFileSync(new URL('../src/'+file,import.meta.url),'utf8')+extra,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(source,{module:artifact,exports:artifact.exports,require:load,localStorage:{getItem:()=>null},window:{matchMedia:()=>({matches:false})}});return artifact.exports;
}
function appHarness(overrides={}){
  let cursor=0,values=overrides;
  const views=[],layouts=[];
  const react={...React,useState(initial){const index=cursor++;return [Object.hasOwn(values,index)?values[index]:typeof initial==='function'?initial():initial,()=>{}]},useCallback:value=>value,useRef:value=>({current:value}),useEffect(){},useLayoutEffect:effect=>layouts.push(effect)};
  // The real hook binds the App's selected screen to the measurement boundary.
  // The module's payload and async work are exercised in audience.test.mjs.
  const ui=compile('audience-ui.tsx',id=>id==='react'?react:id==='./audience'?{setAudienceView:(...args)=>views.push(args)}:id==='./i18n'?{tr:value=>value}:id.endsWith('.css')?{}:require(id));
  const empty=()=>null;
  const load=id=>{
    if(id==='react')return react;
    if(id==='./audience-ui')return ui;
    if(id==='./navigation')return navigation;
    if(id==='./i18n')return {tr:value=>value,useLocale:()=>({locale:'fr',setLocale(){}})};
    if(id==='./navigation-guard')return {useNavigationGuard:()=>({confirmLeave:()=>true})};
    if(id==='./team-context')return {isSelectionTeam:team=>['nt','u20'].includes(team.kind),groupedTeams:()=>[],teamKind:()=> 'club'};
    if(id==='./profile')return {defaultProfile:profile,ProfileAvatar:empty,ProfileSettings:empty};
    if(id==='./workbench')return {clubTheme:()=>({}),ClubBadge:empty};
    if(id.startsWith('./'))return new Proxy({},{get:()=>empty});
    return require(id);
  };
  const app=compile('App.tsx',load,'\nexport {Login};');
  return {views,ui,render(){cursor=0;layouts.length=0;const tree=app.default();layouts.forEach(effect=>effect());return tree},login(mode='login'){cursor=0;layouts.length=0;values={6:mode};const tree=app.Login({onLogin:async()=>{}});layouts.forEach(effect=>effect());return tree}};
}
function nodes(value){return Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props?.children)]:[]}

test('boot and initial error screens do not select a measurable view',()=>{
  for(const overrides of [{},{4:false,9:'Synthetic unavailable server'}]){
    const h=appHarness(overrides);h.render();assert.deepEqual(h.views,[[null,false]]);
  }
});

test('settled login, onboarding and navigation bind only their screen and admin flag',()=>{
  for(const [overrides,want] of [[{3:true,4:false},['login',false]],[{2:{...state,setup_required:true},4:false},['onboarding',false]],[{2:state,4:false,5:'squad'},['squad',false]],[{2:{...state,user:{...state.user,admin:true}},4:false},['home',true]]]){
    const h=appHarness(overrides);h.render();assert.deepEqual(h.views,[want]);
  }
});

test('registration mode selects its public screen and exposes the same local choice',()=>{
  for(const mode of ['login','register']){
    const h=appHarness(),tree=h.login(mode);
    assert.deepEqual(h.views,[[mode,false]]);
    assert.ok(nodes(tree).some(node=>node.type===h.ui.AudiencePreferences));
  }
});

test('the local audience choice remains available during onboarding and in the app footer',()=>{
  for(const d of [state,{...state,setup_required:true}]){
    const h=appHarness({2:d,4:false}),tree=h.render();
    assert.ok(nodes(tree).some(node=>node.type===h.ui.AudiencePreferences));
  }
});

test('a selection notice replacing a club-only screen is not a section consultation',()=>{
  const selection={...state,current_team:{...state.current_team,kind:'nt'}};
  const h=appHarness({2:selection,4:false,5:'academy'});h.render();
  assert.deepEqual(h.views,[[null,false]]);
});
