import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');

function load(react=React,request=()=>{throw Error('No request during rendering')},confirmLeave=()=>true){
  const source=readFileSync(new URL('../src/player-pool.tsx',import.meta.url),'utf8')+'\nexport {PoolSelected};';
  const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const artifact={exports:{}};
  vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:id=>{
    if(id==='react')return react;
    if(id==='./App')return {request};
    if(id==='./i18n')return {tr:(value,params={})=>value.replace(/\{(\w+)\}/g,(_,key)=>String(params[key]??key))};
    if(id==='./types')return {fmt:value=>value??'—',date:value=>value??'—',skills:['stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking'],labels:{attack:'Attaque'}};
    if(id==='./navigation-guard'||id.endsWith('.css'))return {useUnsavedChanges(){},useNavigationGuard:()=>({confirmLeave})};
    return require(id);
  },URLSearchParams});
  return artifact.exports;
}
const observation={snapshot_id:12,team_id:'u20:42',team_name:'Selection synthetic',kind:'u20',cohort:'squad',archive:true,source:'Annuler',observed_at:'2026-01-01',first_observed_at:'2025-12-01',first_source:'old.csv',imported_at:'2026-04-01',game_date:null,availability:'unknown',quality:'partial',player:{id:'7',name:'Annuler',age:20,nationality:'FR',attack:12,metrics:{known_skills:1,roles:[],estimated_csr:null},changes:{}}};

test('comparison keeps archive provenance and unknown skills visible without guessing eligibility',()=>{
  const {PoolObservations}=load();
  const html=renderToStaticMarkup(React.createElement(PoolObservations,{observations:[observation],conflicts:{age:[19,20]},d:{current_team:{id:'42'},squad_source:{id:12},squad:[observation.player],academy:[]},openPlayer(){throw Error('must not open foreign context')}}));
  assert.match(html,/Selection synthetic/);assert.match(html,/Archive en pause/);assert.match(html,/2025-12-01/);assert.match(html,/2026-01-01/);assert.match(html,/2026-04-01/);
  assert.match(html,/Annuler/);assert.match(html,/—/);assert.doesNotMatch(html,/Ouvrir la fiche de l’équipe sélectionnée/);
  assert.match(html,/ne confirment aucune éligibilité/);
});

test('existing player details require matching team, cohort and exact current snapshot',()=>{
  const {playerForCurrentContext}=load();
  const d={current_team:{id:'42'},squad_source:{id:12},academy_source:{id:13},squad:[observation.player],academy:[{...observation.player,name:'Academy'}]};
  assert.equal(playerForCurrentContext(observation,d),undefined);
  assert.equal(playerForCurrentContext({...observation,team_id:'42',snapshot_id:11},d),undefined);
  assert.equal(playerForCurrentContext({...observation,team_id:'42'},d),d.squad[0]);
  assert.equal(playerForCurrentContext({...observation,team_id:'42',cohort:'academy',snapshot_id:12},d),undefined);
  assert.equal(playerForCurrentContext({...observation,team_id:'42',cohort:'academy',snapshot_id:13},d),d.academy[0]);
});

function harness(component,props,confirmLeave=()=>true){
  let cursor=0,effects=[];const hooks=[],requests=[];
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,v=>{hooks[i].value=typeof v==='function'?v(hooks[i].value):v}]},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps?.some((v,k)=>!Object.is(v,old.deps[k]))){hooks[i]={deps,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()})}}};
  const api=load(react,(url,body,csrf)=>new Promise((resolve,reject)=>requests.push({url,body,csrf,resolve,reject})),confirmLeave);
  return {props,requests,render(){cursor=0;effects=[];const tree=api[component](props);effects.forEach(effect=>effect());return tree},unmount(){hooks.forEach(h=>h?.cleanup?.())}};
}
function nodes(value){if(Array.isArray(value))return value.flatMap(nodes);if(!value||typeof value!=='object')return [];return [value,...nodes(value.props?.children)]}
function text(value){if(Array.isArray(value))return value.map(text).join('');if(value===null||value===undefined||typeof value==='boolean')return '';return typeof value==='object'?text(value.props?.children):String(value)}
async function settle(){for(let i=0;i<12;i++)await Promise.resolve()}

test('private note saves CAS revision and preserves draft after conflict while comparing server note',async()=>{
  const saved=[],p=harness('PoolNoteEditor',{playerId:'7',document:{revision:3,watch:false,text:'Initial',updated_at:null},csrf:'session',busy:false,onSaved:doc=>saved.push(doc)});
  let tree=p.render();
  nodes(tree).find(n=>n.type==='textarea').props.onChange({target:{value:'My private draft'}});
  tree=p.render();nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
  assert.equal(p.requests[0].url,'/player-pool/7');assert.equal(p.requests[0].body.expected_revision,3);assert.equal(p.requests[0].body.text,'My private draft');assert.equal(p.requests[0].csrf,'session');
  p.requests[0].reject(Object.assign(Error('Conflict'),{status:409}));await settle();
  tree=p.render();assert.equal(nodes(tree).find(n=>n.type==='textarea').props.value,'My private draft');
  nodes(tree).find(n=>n.type==='button'&&text(n)==='Comparer la note enregistrée').props.onClick();
  p.requests[1].resolve({document:{revision:4,watch:true,text:'Other tab',updated_at:'2026-01-01'}});await settle();
  tree=p.render();assert.match(text(tree),/Other tab/);assert.equal(nodes(tree).find(n=>n.type==='textarea').props.value,'My private draft');
  nodes(tree).find(n=>n.type==='button'&&text(n)==='Conserver mon brouillon sur cette révision').props.onClick();
  tree=p.render();nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
  assert.equal(p.requests[2].body.expected_revision,4);assert.equal(p.requests[2].body.text,'My private draft');
  p.requests[2].resolve({revision:5,watch:false,text:'My private draft',updated_at:'2026-01-02'});await settle();
  assert.equal(saved[0].revision,5);
});

test('filter changes ignore an older list response and start pagination at zero',async()=>{
  const p=harness('PoolPanel',{d:{user:{username:'coach'},csrf:'session',current_team:{id:'42'}},busy:false,openPlayer(){},go(){},act(){}});
  let tree=p.render();const old=p.requests[0];
  nodes(tree).find(n=>n.type==='input'&&n.props.type==='search').props.onChange({target:{value:'Ada'}});
  tree=p.render();assert.match(p.requests[1].url,/q=Ada/);assert.match(p.requests[1].url,/offset=0/);
  p.requests[1].resolve({players:[{player_id:'7',names:['Ada'],ages:[20],nationalities:['FR'],positions:[],observation_count:1,archive_count:0,conflicts:{},document:{watch:false,text:'',revision:0}}],total:1,offset:0,limit:25,position_options:[],limits:{contexts:256,observations:16000,page_size:100}});await settle();
  old.resolve({players:[],total:0,offset:0,limit:25,position_options:[],limits:{}});await settle();
  tree=p.render();assert.match(text(tree),/Ada/);assert.doesNotMatch(text(tree),/Aucun joueur observé/);
});

test('declining the dirty editor guard keeps the currently selected dossier',async()=>{
  let allow=true;
  const p=harness('PoolPanel',{d:{user:{username:'coach'},csrf:'session',current_team:{id:'42'}},busy:false,openPlayer(){},go(){},act(){}},()=>allow);
  p.render();p.requests[0].resolve({players:['7','8'].map(player_id=>({player_id,names:['Player '+player_id],ages:[],nationalities:[],positions:[],observation_count:1,archive_count:0,conflicts:{},document:{watch:false,text:'',revision:0}})),total:2,offset:0,limit:25,position_options:[],limits:{}});await settle();
  let tree=p.render();nodes(tree).filter(n=>n.type==='button'&&text(n)==='Comparer et suivre')[0].props.onClick();
  tree=p.render();assert.equal(nodes(tree).filter(n=>n.type==='button'&&text(n)==='Comparer et suivre')[0].props['aria-expanded'],true);
  allow=false;nodes(tree).filter(n=>n.type==='button'&&text(n)==='Comparer et suivre')[1].props.onClick();
  tree=p.render();assert.equal(nodes(tree).filter(n=>n.type==='button'&&text(n)==='Comparer et suivre')[0].props['aria-expanded'],true);assert.equal(nodes(tree).filter(n=>n.type==='button'&&text(n)==='Comparer et suivre')[1].props['aria-expanded'],false);
});

test('unmounting note editor ignores a delayed write and prevents duplicate submissions',async()=>{
  const saved=[],p=harness('PoolNoteEditor',{playerId:'7',document:{revision:0,watch:false,text:'',updated_at:null},csrf:'session',busy:false,onSaved:doc=>saved.push(doc)});
  let tree=p.render();nodes(tree).find(n=>n.type==='textarea').props.onChange({target:{value:'Draft'}});tree=p.render();
  const submit=nodes(tree).find(n=>n.type==='form').props.onSubmit;
  submit({preventDefault(){}});submit({preventDefault(){}});assert.equal(p.requests.length,1);
  p.unmount();p.requests[0].resolve({revision:1,watch:false,text:'Draft',updated_at:'2026-01-01'});await settle();assert.equal(saved.length,0);
});

test('rereading the pool refreshes selected observation sources',async()=>{
  const p=harness('PoolSelected',{playerId:'7',d:{csrf:'session'},busy:false,openPlayer(){},onSaved(){},reload:0});
  p.render();p.requests[0].resolve({player_id:'7',names:['Ada'],document:{revision:0,watch:false,text:'',updated_at:null},observations:[observation],conflicts:{}});await settle();p.render();
  p.props.reload=1;p.render();assert.equal(p.requests.length,2);
  p.requests[1].resolve({player_id:'7',names:['Ada'],document:{revision:1,watch:true,text:'Remote note',updated_at:null},observations:[{...observation,source:'new.csv'}],conflicts:{}});await settle();
  const tree=p.render();assert.equal(nodes(tree).find(n=>n.type?.name==='PoolObservations').props.observations[0].source,'new.csv');
});

test('reread updates a clean note and preserves a dirty note against the refreshed revision',()=>{
  const document={revision:0,watch:false,text:'Initial',updated_at:null};
  const p=harness('PoolNoteEditor',{playerId:'7',document,csrf:'session',busy:false,onSaved(){}});
  p.render();p.props.document={revision:1,watch:true,text:'Fresh server note',updated_at:null};p.render();let tree=p.render();assert.equal(nodes(tree).find(n=>n.type==='textarea').props.value,'Fresh server note');
  nodes(tree).find(n=>n.type==='textarea').props.onChange({target:{value:'Local draft'}});p.render();
  p.props.document={revision:2,watch:false,text:'New remote note',updated_at:null};p.render();tree=p.render();assert.equal(nodes(tree).find(n=>n.type==='textarea').props.value,'Local draft');
  nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});assert.equal(p.requests[0].body.expected_revision,1);
});

test('a shrinking pool clamps the current page and reloads its first remaining page',async()=>{
  const p=harness('PoolPanel',{d:{user:{username:'coach'},csrf:'session',current_team:{id:'42'}},busy:false,openPlayer(){},go(){},act(){}});
  p.render();p.requests[0].resolve({players:[],total:26,offset:0,limit:25,position_options:[],limits:{}});await settle();let tree=p.render();nodes(tree).find(n=>n.type==='button'&&text(n)==='Suivant').props.onClick();p.render();
  p.requests[1].resolve({players:[],total:1,offset:25,limit:25,position_options:[],limits:{}});await settle();p.render();assert.equal(p.requests.length,3);assert.match(p.requests[2].url,/offset=0/);
});

test('adopting a compared server note never rolls back to an older parent document',async()=>{
  const p=harness('PoolNoteEditor',{playerId:'7',document:{revision:3,watch:false,text:'Old',updated_at:null},csrf:'session',busy:false,onSaved(){}});
  let tree=p.render();nodes(tree).find(n=>n.type==='textarea').props.onChange({target:{value:'Local'}});tree=p.render();nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});p.requests[0].reject(Object.assign(Error('Conflict'),{status:409}));await settle();
  tree=p.render();nodes(tree).find(n=>n.type==='button'&&text(n)==='Comparer la note enregistrée').props.onClick();p.requests[1].resolve({document:{revision:4,watch:true,text:'Compared server',updated_at:null}});await settle();tree=p.render();nodes(tree).find(n=>n.type==='button'&&text(n)==='Utiliser la version enregistrée').props.onClick();p.render();tree=p.render();assert.equal(nodes(tree).find(n=>n.type==='textarea').props.value,'Compared server');
});
