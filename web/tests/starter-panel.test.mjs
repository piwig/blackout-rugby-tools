import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url);
const {translate}=require('../src/i18n/core.ts');
const french=JSON.parse(readFileSync(new URL('../src/i18n/locales/fr.json',import.meta.url),'utf8'));
const artifact={exports:{}};
const source=ts.transpileModule(readFileSync(new URL('../src/starter.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const load=id=>id==='./i18n'?{tr:(source,params)=>translate(french,source,params)}:id==='./App'||id==='./navigation-guard'||id.endsWith('.css')?{}:id==='./starter-state'?require('../src/starter-state.ts'):require(id);
vm.runInNewContext(source,{module:artifact,exports:artifact.exports,require:load});
const {renderToStaticMarkup}=require('react-dom/server');
const React=require('react');
const state={document:{team_id:'123',revision:0,updated_at:null,completed:[],collapsed:false},value:{completed:[],collapsed:false},pending:null,error:'',conflict:false,saved:false};
const render=overrides=>renderToStaticMarkup(React.createElement(artifact.exports.StarterPanel,{clubName:'Club test',state:{...state,...overrides},busy:false,onToggle(){},onComplete(){},onSave(){},onReload(){},go(){}}));

test('the expanded starter offers seven unchecked, labelled declarations without implied game completion',()=>{
  const html=render();
  assert.equal((html.match(/type="checkbox"/g)||[]).length,7);
  assert.equal((html.match(/aria-labelledby="starter-/g)||[]).length,8);
  assert.doesNotMatch(html,/ checked=""/);
  assert.match(html,/aria-expanded="true"/);
  assert.match(html,/ne confirment aucune action dans Classic/);
});

test('a collapsed starter keeps the title, expand button, status and save action reachable',()=>{
  const html=render({value:{completed:['mentor'],collapsed:true}});
  assert.match(html,/<h2[^>]*>Bien démarrer<\/h2>/);
  assert.match(html,/aria-expanded="false"/);
  assert.match(html,/aria-controls="starter-content"/);
  assert.match(html,/Enregistrer mon suivi/);
  assert.match(html,/role="status"/);
  assert.doesNotMatch(html,/type="checkbox"/);
});

test('saving disables every declaration and the disclosure control',()=>{
  const html=render({pending:'save'});
  assert.equal((html.match(/<input[^>]*disabled=""/g)||[]).length,7);
  assert.match(html,/<button[^>]*aria-expanded="true"[^>]*disabled=""/);
});

test('conflict recovery and the error stay visible even when the card is collapsed',()=>{
  const html=render({value:{completed:['mentor'],collapsed:true},conflict:true,error:'Brouillon conservé'});
  assert.match(html,/role="alert"/);
  assert.match(html,/Brouillon conservé/);
  assert.match(html,/Relire la version enregistrée/);
  const saveButton=html.match(/<button\b[^]*?<\/button>/g)?.find(button=>button.includes('Enregistrer mon suivi'));
  assert.match(saveButton??'',/disabled=""/);
});
