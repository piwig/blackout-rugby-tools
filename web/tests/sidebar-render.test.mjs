import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const artifact={exports:{}};
const source=ts.transpileModule(readFileSync(new URL('../src/sidebar.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const load=id=>id==='./i18n'?{tr:value=>value}:id==='./navigation'?require('../src/navigation.ts'):id==='./profile'?{ProfileAvatar:()=>React.createElement('span',{'data-avatar':true})}:require(id);
vm.runInNewContext(source,{module:artifact,exports:artifact.exports,require:load});
const render=overrides=>renderToStaticMarkup(React.createElement(artifact.exports.Sidebar,{page:'home',selection:false,username:'test-manager',displayName:'Manager',profile:{},busy:false,mobile:false,open:false,onClose(){},go(){},onLogout(){},...overrides}));

test('sidebar renders a distinct dashboard, four labelled disclosures and one current route',()=>{
  const html=render();
  assert.equal((html.match(/aria-expanded=/g)||[]).length,4);
  assert.equal((html.match(/aria-current="page"/g)||[]).length,1);
  assert.match(html,/id="navigation-group-account-label"[^>]*aria-expanded="false"[^>]*aria-controls="navigation-group-account"/);
  assert.match(html,/id="navigation-group-account"[^>]*hidden=""/);
  assert.match(html,/2\.9\.1/);
  assert.match(html,/Se déconnecter/);
});

test('opening a personal deep destination exposes its group and current route',()=>{
  const html=render({page:'contact'});
  assert.match(html,/id="navigation-group-account-label"[^>]*aria-expanded="true"/);
  assert.doesNotMatch(html,/id="navigation-group-account"[^>]*hidden=/);
  assert.match(html,/<button[^>]*aria-current="page"[^]*?<span>Contact &amp; idées<\/span>/);
});

test('a national selection hides club tools and the empty club disclosure',()=>{
  const html=render({selection:true,page:'progression'});
  assert.equal((html.match(/aria-expanded=/g)||[]).length,3);
  assert.doesNotMatch(html,/navigation-group-club|>Académie<|>Entraînement<|>Mode vacances<|>Stade &amp; finances</);
  assert.match(html,/Faire progresser/);
  assert.match(html,/Progression/);
});

test('closed mobile drawers are inert and open drawers expose a named modal',()=>{
  assert.match(render({mobile:true}),/<aside[^>]*inert=""/);
  const open=render({mobile:true,open:true,busy:true});
  assert.match(open,/<aside[^>]*role="dialog"[^>]*aria-modal="true"[^>]*aria-label="Menu de navigation"/);
  assert.doesNotMatch(open,/<aside[^>]*inert=/);
  assert.match(open,/<button[^>]*aria-label="Se déconnecter"[^>]*disabled=""/);
});
