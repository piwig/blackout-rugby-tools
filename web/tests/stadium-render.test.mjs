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
