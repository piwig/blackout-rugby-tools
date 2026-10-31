import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react');

// Exercise the production panel's effects and handlers without a browser or
// network. Local imports unrelated to request ordering are deliberately stubbed.
function panelHarness(){
  const hooks=[],requests=[];
  let cursor=0,pendingEffects=[];
  const react={...React,
    useState(initial){
      const index=cursor++;
      if(!hooks[index])hooks[index]={kind:'state',value:typeof initial==='function'?initial():initial};
      return [hooks[index].value,value=>{hooks[index].value=typeof value==='function'?value(hooks[index].value):value}];
    },
    useRef(initial){
      const index=cursor++;
      if(!hooks[index])hooks[index]={kind:'ref',value:{current:initial}};
      return hooks[index].value;
    },
    useEffect(effect,dependencies){
      const index=cursor++,previous=hooks[index];
      if(!previous||!dependencies||dependencies.some((value,i)=>!Object.is(value,previous.dependencies?.[i]))){
        hooks[index]={kind:'effect',dependencies,cleanup:previous?.cleanup};
        pendingEffects.push(()=>{hooks[index].cleanup?.();hooks[index].cleanup=effect()});
      }
    },
  };
  const request=(url,body)=>new Promise(resolve=>requests.push({url,body,resolve}));
  const source=readFileSync(new URL('../src/coaching.tsx',import.meta.url),'utf8');
  // Export the private component only in this in-memory test compilation.
  const compiled=ts.transpileModule(source+'\nexport {CoachingPanel};',{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX},
  }).outputText;
  const artifact={exports:{}};
  const load=id=>{
    if(id==='react')return react;
    if(id==='./App')return {request};
    if(id==='./i18n')return {tr:value=>value,localeTag:()=> 'fr-FR'};
    if(id==='./types')return {fmt:value=>value??'—',labels:{}};
    if(id==='./navigation-guard')return {useUnsavedChanges(){}};
    if(id==='./coaching-model'||id.endsWith('.css'))return {};
    return require(id);
  };
  vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,URLSearchParams});
  const props={mode:'training',busy:false,go(){},d:{
    user:{username:'synthetic-coach'},csrf:'synthetic-session',current_team:{id:'123'},
    classic_account:{team_ids:['123']},settings:{developer_ready:true},game_date:null,
  }};
  return {
    requests,
    render(){
      cursor=0;pendingEffects=[];
      const tree=artifact.exports.CoachingPanel(props);
      pendingEffects.forEach(effect=>effect());
      return tree;
    },
    bundle:()=>hooks.find(hook=>hook.kind==='state'&&hook.value?.team_id==='123'&&'revision' in hook.value)?.value,
    instructionsView:artifact.exports.InstructionsView,
  };
}

function elements(value){
  if(Array.isArray(value))return value.flatMap(elements);
  if(!value||typeof value!=='object')return [];
  return [value,...elements(value.props?.children)];
}
function text(value){
  if(Array.isArray(value))return value.map(text).join('');
  if(value===null||value===undefined||typeof value==='boolean')return '';
  return typeof value==='object'?text(value.props?.children):String(value);
}
async function settle(){for(let i=0;i<10;i++)await Promise.resolve()}

test('a delayed initial GET cannot replace a newly confirmed coaching observation',async()=>{
  const panel=panelHarness();
  let tree=panel.render();
  assert.equal(panel.requests.length,1);
  const initialRead=panel.requests[0];
  assert.match(initialRead.url,/\/coaching\?/);
  assert.equal(initialRead.body,undefined);

  elements(tree).find(node=>node.type==='form').props.onSubmit({preventDefault(){}});
  const previewRead=panel.requests[1];
  assert.match(previewRead.url,/\/coaching\/preview$/);
  const instruction={key:'instructions:synthetic:1',observed_at:'2026-10-31T12:00:00Z',
    team_skills:['stamina',null,'unreported','unreported'],youth_skills:null,individual:[]};
  previewRead.resolve({team_id:'123',kind:'instructions',preview_id:'synthetic-preview-token',
    expected_revision:0,expires_at:'2026-10-31T12:10:00Z',status:'available',
    already_imported:false,warnings:[],data:instruction});
  await settle();

  tree=panel.render();
  elements(tree).find(node=>node.type==='button'&&text(node)==='Conserver ce relevé').props.onClick();
  const confirmation=panel.requests[2];
  assert.match(confirmation.url,/\/coaching\/confirm$/);
  const oldBundle={team_id:'123',revision:0,instructions:null,reports:[],statistics:[],
    report_total:0,statistics_total:0,history_limit:20,report_offset:0,statistics_offset:0};
  confirmation.resolve({ok:true,imported:true,unchanged:false,
    bundle:{...oldBundle,revision:1,instructions:instruction}});
  await settle();
  panel.render();
  assert.equal(panel.bundle().revision,1,'The successful confirmation must be visible first');

  initialRead.resolve(oldBundle);
  await settle();
  tree=panel.render();
  assert.equal(panel.bundle().revision,1,'A delayed GET must not roll back the confirmed bundle');
  assert.equal(panel.bundle().instructions.key,instruction.key);
  const savedView=elements(tree).find(node=>node.type===panel.instructionsView);
  assert.equal(savedView?.props.data.key,instruction.key,'The saved observation must remain rendered');
  assert.equal(panel.requests.length,3,'No implicit Classic retry should be needed');
});
