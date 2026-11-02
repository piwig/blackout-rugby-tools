import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function load(file,cache=new Map()){
 if(cache.has(file))return cache.get(file).exports;
 const module={exports:{}};cache.set(file,module);
 const req=id=>{
  if(id.includes('i18n'))return {localeTag:()=> 'fr-FR',tr:(s,p={})=>s.replace(/\{(\w+)\}/g,(_,k)=>p[k]??`{${k}}`)};
  if(id==='./components')return {Skill:({value})=>React.createElement('span',null,value??'—')};
  if(id.endsWith('.css'))return {};
  if(!id.startsWith('.'))return require(id);
  const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(existsSync);return load(target,cache);
 };
 vm.runInNewContext(ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:req,Date,Intl,Math,Number});return module.exports;
}

test('complete junior table renders full stars, comments, unknowns and accessible controls',()=>{
 const {RosterTable}=load(path.resolve(import.meta.dirname,'../src/roster-table.tsx'));
 const player={id:'1',name:'Young Example',stars:600,age:17,csr:null,energy:0,weight:95,handling:'High',changes:{},metrics:{skill_total:20}};
 const props={players:[player],notes:{'1':{text:'<script>not markup</script> '.repeat(8),watch:false}},youth:true,complete:true,sort:'stars',descending:true,busy:false,compare:[],onSort(){},onOpen(){},onWatch(){},onCompare(){}};
 const html=renderToStaticMarkup(React.createElement(RosterTable,props));
 assert.match(html,/600/);assert.match(html,/&lt;script&gt;not markup&lt;\/script&gt;/);
 assert.doesNotMatch(html,/<script>/);assert.match(html,/Commentaires/);assert.match(html,/Modifier la note de Young Example/);
 assert.match(html,/aria-sort="descending"/);assert.match(html,/Hauteur|Taille/);assert.match(html,/Énergie/);
 assert.match(html,/>0<\/span>|>0<\/td>/);
});
