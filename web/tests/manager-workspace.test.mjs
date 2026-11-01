import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react');
function harness(){
  let selected,allowed=true,checks=0,focused='';
  const artifact={exports:{}};
  const load=id=>id==='react'?{...React,useId:()=> 'workspace',useState:initial=>[selected??=initial,next=>{selected=next}]}:id==='./i18n'?{tr:value=>value}:id==='./navigation-guard'?{useNavigationGuard:()=>({confirmLeave:()=>{checks++;return allowed}})}:id.endsWith('.css')?{}:require(id);
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/manager-workspace.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:load,document:{getElementById:id=>({focus(){focused=id}})}});
  const props={label:'Gestion du stade',tabs:[{id:'income',label:'Recettes',description:'Prévoir',content:React.createElement('div',{'data-editor':'income'})},{id:'construction',label:'Travaux',description:'Construire',content:React.createElement('div',{'data-editor':'construction'})}],busy:false};
  return {render:()=>artifact.exports.ManagerWorkspace(props),props,allow:value=>{allowed=value},checks:()=>checks,focused:()=>focused};
}
const nodes=tree=>Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[];
const tabs=tree=>nodes(tree).filter(n=>n.props?.role==='tab');
test('tab change preserves a rejected dirty draft and only mounts the selected editor',()=>{
  const h=harness();h.allow(false);tabs(h.render())[1].props.onClick();
  assert.equal(h.checks(),1);assert.equal(nodes(h.render()).find(n=>n.props?.['data-editor']).props['data-editor'],'income');
  h.allow(true);tabs(h.render())[1].props.onClick();
  const tree=h.render();assert.equal(nodes(tree).filter(n=>n.props?.['data-editor']).length,1);
  assert.equal(nodes(tree).find(n=>n.props?.['data-editor']).props['data-editor'],'construction');
  assert.equal(nodes(tree).find(n=>n.props?.role==='tabpanel').props['aria-labelledby'],'workspace-construction');
});
test('keyboard selection honors busy state and moves focus only after an accepted change',()=>{
  const h=harness(),event={key:'End',preventDefault(){}};
  h.props.busy=true;tabs(h.render())[0].props.onKeyDown(event);assert.equal(h.checks(),0);assert.equal(h.focused(),'');
  h.props.busy=false;h.allow(false);tabs(h.render())[0].props.onKeyDown(event);assert.equal(h.focused(),'');
  h.allow(true);tabs(h.render())[0].props.onKeyDown(event);assert.equal(h.focused(),'workspace-construction');
  assert.equal(tabs(h.render())[1].props.tabIndex,0);
});
