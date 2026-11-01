import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {createDraftRegistry}=require('../src/draft-registry.ts');

const document={token:'synthetic-token',expires_at:'2099-01-01T00:00:00Z',datasets:[{id:'0',sheet:'latouff_players',count:1,players:[{id:'42',name:'Synthetic source name'}],observed_at:null,game_date:{season:62,round:9,day:5}}],destinations:[{team_id:'9',name:'Synthetic club',cohorts:['seniors','academy'],current:{seniors:{count:23,observed_at:'2026-10-20T00:00:00Z'}}},{team_id:'u20:9',name:'Synthetic selection',cohorts:['selection'],current:{}}],excluded:[{name:'private_analysis',reason:'roster_only'}],limitations:[]};

function harness(locale='fr'){
  let cursor=0,effects=[];const hooks=[],requests=[],registry=createDraftRegistry(),fileInput={value:''};
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value;},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((v,k)=>!Object.is(v,old.deps[k]))){hooks[i]={deps,effect,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()});}}};
  const request=(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}));
  react.useContext=()=>registry;react.useLayoutEffect=react.useEffect;
  const artifact={exports:{}};
  let guard;
  const load=id=>{
    if(id==='./navigation-guard'){
      if(!guard){guard={exports:{}};vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/navigation-guard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:guard,exports:guard.exports,require:load,Symbol});}
      return guard.exports;
    }
    return id==='react'?react:id==='./App'?{request}:id==='./i18n'?{getLocale:()=>locale,tr:value=>value}:id==='./draft-registry'?{createDraftRegistry}:id.endsWith('.css')?{}:require(id);
  };
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/import-preview.tsx',import.meta.url),'utf8')+'\nexport {ImportPreviewPanel};',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:load,Date,JSON,FormData,File,window:{setTimeout:()=>1,clearTimeout(){}},setTimeout:()=>1,clearTimeout(){}});
  const props={d:{user:{username:'synthetic'},csrf:'session',classic_account:null},busy:false,act:request};
  return {requests,props,registry,fileInput,retainedFiles:()=>hooks.filter(h=>h.value instanceof File).map(h=>h.value),render(){cursor=0;effects=[];const tree=artifact.exports.ImportPreviewPanel(props);const input=elements(tree).find(n=>n.type==='input'&&n.props.type==='file');if(input?.props.ref)input.props.ref.current=fileInput;effects.forEach(fn=>fn());return tree;},unmount(){hooks.forEach(h=>h.cleanup?.())},html(tree){return renderToStaticMarkup(tree)}};
}
function elements(tree){return Array.isArray(tree)?tree.flatMap(elements):tree&&typeof tree==='object'?[tree,...elements(tree.props?.children)]:[]}
async function settle(){for(let i=0;i<10;i++)await Promise.resolve()}
async function analyzed(locale='fr'){
  const h=harness(locale);let tree=h.render();
  elements(tree).find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[new File(['[]'],'roster.json')]}});tree=h.render();
  const form=elements(tree).find(n=>n.type==='form');form.props.onSubmit({preventDefault(){}});form.props.onSubmit({preventDefault(){}});
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].url,'/import/preview');
  h.requests[0].resolve(structuredClone(document));await settle();return {h,tree:h.render()};
}

test('preview shows source players and exclusions with no destination inferred from legacy sheet names',async()=>{
  const {h,tree}=await analyzed();const html=h.html(tree);
  assert.match(html,/Synthetic source name/);assert.match(html,/private_analysis/);assert.match(html,/latouff_players/);
  assert.match(html,/Date du relevé/);assert.match(html,/Saison 62/);
  const select=elements(tree).find(n=>n.type==='select');assert.equal(select.props.value,'');
  const confirm=elements(tree).find(n=>n.type==='button'&&n.props['data-confirm']);assert.equal(confirm.props.disabled,true);
});

test('confirmation sends chosen destination and explicit date, and blocks duplicate submits',async()=>{
  const {h}=await analyzed();let tree=h.render();
  elements(tree).find(n=>n.type==='select').props.onChange({target:{value:'u20:9|selection'}});tree=h.render();
  elements(tree).find(n=>n.type==='input'&&n.props.type==='datetime-local').props.onChange({target:{value:'2026-10-20T12:00'}});tree=h.render();
  const button=elements(tree).find(n=>n.props?.['data-confirm']);assert.equal(button.props.disabled,false);button.props.onClick();button.props.onClick();
  assert.equal(h.requests.length,2);assert.equal(h.requests[1].url,'/import/confirm');
  assert.equal(h.requests[1].body.mappings[0].team_id,'u20:9');assert.equal(h.requests[1].body.mappings[0].cohort,'selection');
  assert.match(h.requests[1].body.mappings[0].observed_at,/2026-10-20T/);
  h.requests[1].resolve({imported:[{count:1}],skipped:[]});await settle();assert.match(h.html(h.render()),/Import confirmé/);
});

test('late response after unmount cannot show a private preview',async()=>{
  const h=harness();let tree=h.render();elements(tree).find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[new File(['[]'],'r.json')]}});tree=h.render();elements(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
  h.unmount();h.requests[0].resolve(structuredClone(document));await settle();assert.doesNotMatch(h.html(h.render()),/Synthetic source name/);
});

test('all four languages render explicit routing and keep source names intact',async()=>{
  for(const [locale,title] of [['fr','Aperçu des effectifs'],['en','Roster preview'],['es','Vista previa de plantillas'],['it','Anteprima delle rose']]){
    const {h,tree}=await analyzed(locale);const html=h.html(tree);assert.ok(html.includes(title));assert.ok(html.includes('Synthetic source name'));
  }
});

test('selected, pending and prepared import work blocks navigation until successful confirmation releases every draft reference',async()=>{
  const h=harness();let tree=h.render();assert.equal(h.registry.hasChanges(),false);
  const file=new File(['[]'],'roster.json');h.fileInput.value='C:\\fakepath\\roster.json';
  elements(tree).find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[file]}});tree=h.render();
  assert.equal(h.registry.canLeave(()=>false),false);assert.deepEqual(h.retainedFiles(),[file]);
  elements(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});tree=h.render();assert.equal(h.registry.hasChanges(),true);
  h.requests[0].resolve(structuredClone(document));await settle();tree=h.render();
  elements(tree).find(n=>n.type==='select').props.onChange({target:{value:'9|seniors'}});tree=h.render();
  elements(tree).find(n=>n.type==='input'&&n.props.type==='datetime-local').props.onChange({target:{value:'2026-10-20T12:00'}});tree=h.render();
  assert.equal(h.registry.canLeave(()=>false),false);elements(tree).find(n=>n.props?.['data-confirm']).props.onClick();tree=h.render();assert.equal(h.registry.hasChanges(),true);
  h.requests[1].resolve({imported:[{count:1}],skipped:[]});await settle();tree=h.render();
  assert.equal(h.registry.hasChanges(),false);assert.equal(h.registry.canLeave(()=>false),true);assert.deepEqual(h.retainedFiles(),[]);assert.equal(h.fileInput.value,'');
  assert.equal(elements(tree).find(n=>n.type==='button'&&n.props.children==='Analyser le fichier').props.disabled,true);
});

test('explicit abandon before analysis and after prepared mappings clears navigation protection and file input',async()=>{
  for(const prepared of [false,true]){
    const h=harness();let tree=h.render();h.fileInput.value='C:\\fakepath\\roster.json';
    elements(tree).find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[new File(['[]'],'roster.json')]}});tree=h.render();
    if(prepared){elements(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});h.requests[0].resolve(structuredClone(document));await settle();tree=h.render();elements(tree).find(n=>n.type==='select').props.onChange({target:{value:'9|academy'}});tree=h.render();elements(tree).find(n=>n.type==='input'&&n.props.type==='datetime-local').props.onChange({target:{value:'2026-10-20T12:00'}});tree=h.render();}
    assert.equal(h.registry.hasChanges(),true);
    const abandon=elements(tree).find(n=>n.type==='button'&&n.props.children==='Effacer l’aperçu');assert.ok(abandon);abandon.props.onClick();tree=h.render();
    assert.equal(h.registry.hasChanges(),false);assert.deepEqual(h.retainedFiles(),[]);assert.equal(h.fileInput.value,'');assert.doesNotMatch(h.html(tree),/Synthetic source name/);
    assert.equal(elements(tree).find(n=>n.type==='button'&&n.props.children==='Analyser le fichier').props.disabled,true);
  }
});
