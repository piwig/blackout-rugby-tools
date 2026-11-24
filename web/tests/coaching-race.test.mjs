import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react');
const model=require('../src/coaching-model.ts');

// Exercise the production panel's effects and handlers without a browser or
// network. Local imports unrelated to request ordering are deliberately stubbed.
function panelHarness({classicAccess=true}={}){
  const hooks=[],requests=[];
  let cursor=0,pendingEffects=[],dirty=false;
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
  const request=(url,body,csrf)=>new Promise((resolve,reject)=>requests.push({url,body,csrf,resolve,reject}));
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
    if(id==='./types')return {formatStatistic:value=>value??'—',labels:{}};
    if(id==='./navigation-guard')return {useUnsavedChanges(value){dirty=value}};
    if(id==='./coaching-model')return model;
    if(id.endsWith('.css'))return {};
    return require(id);
  };
  vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,URLSearchParams,FormData});
  const props={mode:'training',busy:false,go(){},d:{
    user:{username:'synthetic-coach'},csrf:'synthetic-session',current_team:{id:'123',name:'Example Club'},
    classic_account:classicAccess?{team_ids:['123']}:null,settings:{developer_ready:classicAccess},game_date:null,
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
    classicCoaching:artifact.exports.ClassicCoaching,
    props,
    isDirty:()=>dirty,
    unmount:()=>hooks.filter(hook=>hook.kind==='effect').forEach(hook=>hook.cleanup?.()),
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

const form=(tree,label)=>elements(tree).find(node=>node.type==='form'&&node.props['aria-label']===label);
const fileInput=(tree)=>elements(tree).find(node=>node.type==='input'&&node.props.type==='file');
const chooseFile=(tree,file)=>fileInput(tree).props.onChange({currentTarget:{files:[file]}});
const upload=(tree)=>form(tree,'Importer un rapport reçu par mail').props.onSubmit({preventDefault(){}});
const button=(tree,label)=>elements(tree).find(node=>node.type==='button'&&text(node)===label);
const reportData={key:'report:1:2:mail:synthetic',report_id:null,season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
  team:{players:[]},individual:{players:[]},provenance:{source:'Classic email',source_format:'eml',club_name:'Example Club',club_id:null}};
const reportPreview={team_id:'123',kind:'report',preview_id:'synthetic-mail-token',expires_at:'2026-10-01T10:10:00Z',
  expected_revision:0,status:'available',already_imported:false,warnings:['L’identité déclarée dans le fichier ne certifie pas son expéditeur.'],
  identity:{club_name:'Example Club',club_id:null,player_count:0,roster_match_count:0,missing_player_ids:[]},data:reportData};
const emptyBundle={team_id:'123',revision:0,instructions:null,reports:[],statistics:[],
  report_total:0,statistics_total:0,history_limit:20,report_offset:0,statistics_offset:0};

test('local file preview and confirmation use the selected club and CSRF with no Classic access',async()=>{
  const panel=panelHarness({classicAccess:false});
  let tree=panel.render();
  const file=new File(['<table></table>'],'synthetic.eml',{type:'message/rfc822'});
  chooseFile(tree,file);
  tree=panel.render();
  assert.equal(panel.isDirty(),true);
  form(tree,'Lecture par l’API Classic').props.onSubmit({preventDefault(){}});
  assert.equal(panel.requests.length,1,'Submitting the disabled API form must not call Classic');
  upload(tree);
  const request=panel.requests[1];
  assert.equal(request.url,'/clubs/123/coaching/import-preview');
  assert.equal(request.csrf,'synthetic-session');
  assert.deepEqual([...request.body.keys()],['file']);
  assert.equal(request.body.get('file'),file);
  request.resolve(reportPreview);
  await settle();
  tree=panel.render();
  assert.match(text(tree),/Destination.*Example Club/);
  assert.match(text(tree),/identité déclarée/);

  button(tree,'Conserver ce relevé').props.onClick();
  const confirmation=panel.requests[2];
  assert.equal(confirmation.url,'/clubs/123/coaching/confirm');
  assert.equal(confirmation.csrf,'synthetic-session');
  assert.equal(confirmation.body.preview_id,'synthetic-mail-token');
  assert.equal(confirmation.body.expected_revision,0);
  tree=panel.render();
  assert.equal(fileInput(tree).props.disabled,true);
  assert.equal(button(tree,'Annuler cet aperçu').props.disabled,true);
  confirmation.resolve({ok:true,imported:true,unchanged:false,bundle:{...emptyBundle,revision:1,reports:[reportData],report_total:1}});
  await settle();
  panel.requests[0].reject(new Error('Outdated history error'));
  await settle();
  tree=panel.render();
  assert.equal(panel.isDirty(),false);
  assert.equal(panel.bundle().revision,1);
  assert.match(text(tree),/Relevé conservé/);
  assert.doesNotMatch(text(tree),/Outdated history error/);
});

test('a failed upload preserves the selected file, and cancelling clears the draft and input',async()=>{
  const panel=panelHarness({classicAccess:false});
  let tree=panel.render();
  chooseFile(tree,new File(['synthetic'],'synthetic.html'));
  upload(panel.render());
  panel.requests[1].reject(new Error('Synthetic upload error'));
  await settle();
  tree=panel.render();
  assert.match(text(tree),/Synthetic upload error/);
  assert.equal(panel.isDirty(),true);
  upload(tree);
  panel.requests[2].resolve(reportPreview);
  await settle();
  tree=panel.render();
  const input={value:'synthetic.html'};
  fileInput(tree).props.ref.current=input;
  button(tree,'Annuler cet aperçu').props.onClick();
  tree=panel.render();
  assert.equal(input.value,'');
  assert.equal(panel.isDirty(),false);
  assert.equal(button(tree,'Conserver ce relevé'),undefined);
  upload(tree);
  assert.equal(panel.requests.length,3);
});

test('replacing a file suppresses stale preview errors and results without unlocking a newer upload',async()=>{
  const panel=panelHarness();
  let tree=panel.render();
  chooseFile(tree,new File(['first'],'first.eml'));
  upload(panel.render());
  chooseFile(panel.render(),new File(['second'],'second.eml'));
  upload(panel.render());
  const [first,second]=panel.requests.slice(1);
  first.reject(new Error('Stale file error'));
  await settle();
  tree=panel.render();
  assert.doesNotMatch(text(tree),/Stale file error/);
  upload(tree);
  assert.equal(panel.requests.length,3);

  chooseFile(tree,new File(['third'],'third.eml'));
  upload(panel.render());
  second.resolve(reportPreview);
  await settle();
  tree=panel.render();
  assert.equal(button(tree,'Conserver ce relevé'),undefined);
  panel.requests[3].resolve({...reportPreview,preview_id:'current-mail-token'});
  await settle();
  tree=panel.render();
  button(tree,'Conserver ce relevé').props.onClick();
  assert.equal(panel.requests[4].body.preview_id,'current-mail-token');
});

test('club, session, manager and tab changes give the panel a fresh React mount identity',()=>{
  const panel=panelHarness();
  const view=panel.classicCoaching;
  const {d}=panel.props;
  const original=view(panel.props).key;
  assert.notEqual(view({...panel.props,d:{...d,current_team:{id:'124'}}}).key,original);
  assert.notEqual(view({...panel.props,d:{...d,csrf:'another-session'}}).key,original);
  assert.notEqual(view({...panel.props,d:{...d,user:{username:'another-manager'}}}).key,original);
  assert.notEqual(view({...panel.props,mode:'statistics'}).key,original);
});

test('resolving a mail preview after a club unmount cannot install it in that panel',async()=>{
  const panel=panelHarness({classicAccess:false});
  chooseFile(panel.render(),new File(['synthetic'],'synthetic.eml'));
  upload(panel.render());
  panel.unmount();
  panel.requests[1].resolve(reportPreview);
  await settle();
  assert.equal(button(panel.render(),'Conserver ce relevé'),undefined);
});

test('a Classic confirmation conflict leaves the API preview available to cancel',async()=>{
  const panel=panelHarness();
  const tree=panel.render();
  form(tree,'Lecture par l’API Classic').props.onSubmit({preventDefault(){}});
  panel.requests[1].resolve({team_id:'123',kind:'instructions',preview_id:'synthetic-instructions-token',
    expected_revision:0,expires_at:'2026-10-01T10:10:00Z',status:'available',already_imported:false,warnings:[],
    data:{key:'instructions:synthetic:1',observed_at:'2026-10-01T10:00:00Z',team_skills:null,youth_skills:null,individual:[]}});
  await settle();
  button(panel.render(),'Conserver ce relevé').props.onClick();
  panel.requests[2].reject(Object.assign(new Error('Synthetic confirmation conflict'),{status:409}));
  await settle();
  const failed=panel.render();
  assert.match(text(failed),/Synthetic confirmation conflict/);
  assert.ok(button(failed,'Annuler cet aperçu'));
});

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
