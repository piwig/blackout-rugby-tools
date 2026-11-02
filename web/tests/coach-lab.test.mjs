import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function harness(){
  const hooks=[],requests=[],dirtyStates=[],browser={confirm:()=>true};let cursor=0,effects=[];
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value;},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((value,k)=>!Object.is(value,old.deps[k]))){hooks[i]={deps,effect,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()});}}};
  const module={exports:{}};
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/coach-lab.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:(url,body,csrf)=>new Promise((resolve,reject)=>requests.push({url,body,csrf,resolve,reject}))};
    if(id==='./i18n')return {tr:(s,p)=>s.replace(/\{([^}]+)\}/g,(_,k)=>p?.[k]??k)};
    if(id==='./types')return {fmt:v=>v??'—',date:v=>v??'—'};
    if(id==='./navigation-guard')return {useUnsavedChanges(value){dirtyStates.push(value)}};
    if(id.endsWith('.css'))return {};
    return require(id);
  },Date,JSON,URLSearchParams,Blob,URL,window:browser,document:{getElementById:()=>null}});
  const props={busy:false,d:{user:{username:'synthetic'},csrf:'session-1',current_team:{id:'72450'},teams:[{id:'72450',name:'Synthetic XV'}],squad:[],academy:[],squad_source:null,academy_source:null}};
  return {requests,props,browser,dirty:()=>dirtyStates.at(-1),render(){cursor=0;effects=[];const tree=module.exports.CoachLab(props);effects.forEach(f=>f());return tree},unmount(){hooks.forEach(h=>h.cleanup?.())}};
}
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[]}
function named(tree,name){return nodes(tree).find(n=>n.props?.name===name)}
function button(tree,phrase){return nodes(tree).find(n=>n.type==='button'&&JSON.stringify(n.props.children).includes(phrase))}
async function settle(){for(let i=0;i<15;i++)await Promise.resolve()}

const attrs=['stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking','height','weight','form','aggression','discipline','leadership','experience'];

for(const modern of [false,true])test(`saved ${modern?'current':'legacy'} bench keeps its actual methodology`,async()=>{
 const h=harness();h.render();h.requests[0].resolve({...doc,sheet:{...sheet,method:modern?'coach-lab-v2':'coach-lab-v1',bench:{...sheet.bench,method:modern?'exact-indicative-coverage-v1':undefined}}});await settle();
 const html=renderToStaticMarkup(h.render());
 if(modern){assert.match(html,/80 %/);assert.doesNotMatch(html,/Ancienne feuille : recalculez/)}
 else{assert.match(html,/Ancienne feuille : recalculez/);assert.doesNotMatch(html,/affinité complète atteignant 80 %/)}
});
const config={weights:Object.fromEntries([...Array.from({length:15},(_,i)=>String(i+1)),'captain','kicker'].map(k=>[k,Object.fromEntries(attrs.map(a=>[a,a==='strength'?1:0]))])),references:Object.fromEntries(attrs.map(a=>[a,{min:0,max:21,direction:'higher'}])),energy_scale:'percent',energy_floor:60,energy_penalty:0,mode:'skills',rating_scale:'',position_scope:'exact',position_basis:'observed',minimum_notes:1,skill_share:50,locks:{},excluded_ids:[],objective:'balanced',conditions:{weather:'unknown',wind:'unknown'},opponent:null};
const doc={revision:0,config,sheet:null,scales:[],performance_revision:0};
const sheet={slots:{'1':'42'},players:[{slot:1,id:'42',name:'Synthetic',score:null,skills:{score:null,missing:['strength'],components:[]},performance:{count:0,small_sample:true,bounds:[null,null],evidence:[]}}],unfilled:Array.from({length:14},(_,i)=>i+2),responsibles:{captain:{selected:null,backups:[],ranking:[]},kicker:{selected:null,backups:[],ranking:[]}},tactics:{attacks:{driving:25,pickandgo:25,expansive:25,creative:25},kick_frequency:20,kick_types:{touch:50,territory:30,contestable:20},defense:'drift',intensity:65,discipline:'balanced',variants:[],base_plan:true,unknown_attributes:['strength'],known_means:{},conditions:{weather:'unknown',wind:'unknown'}},bench:{coverage:{Pilier:[]},gaps:['Pilier']},warnings:[],window:{start:'2026-07-01',end:'2026-11-01'},source:null};
test('controls send numeric weights and revisions; edits invalidate a previously prepared sheet',async()=>{
 const h=harness();h.render();h.requests[0].resolve(doc);await settle();let tree=h.render();
 named(tree,'coach-weight-strength').props.onChange({target:{value:'4'}});tree=h.render();assert.equal(h.dirty(),true);
 button(tree,'Calculer le XV').props.onClick();button(tree,'Calculer le XV').props.onClick();assert.equal(h.requests.length,2);assert.equal(h.requests[1].body.config.weights['1'].strength,4);assert.equal(h.requests[1].body.expected_revision,0);
 h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,sheet});await settle();tree=h.render();assert.ok(button(tree,'Enregistrer la feuille'));
 named(tree,'coach-weight-strength').props.onChange({target:{value:'5'}});tree=h.render();assert.equal(button(tree,'Enregistrer la feuille'),undefined);
});
test('a late preview cannot cross team or session scope and private drafts hide immediately',async()=>{
 const h=harness();h.render();h.requests[0].resolve(doc);await settle();let tree=h.render();button(tree,'Calculer le XV').props.onClick();h.props.d.csrf='session-2';h.props.d.user.username='other';tree=h.render();assert.equal(named(tree,'coach-weight-strength'),undefined);
 h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,sheet});await settle();tree=h.render();assert.equal(button(tree,'Enregistrer la feuille'),undefined);
});
test('cohort changes use separate requests and manual sheet corrections are explicit',async()=>{
 const h=harness();h.props.d.academy=[{id:'42',name:'Synthetic'}];h.render();h.requests[0].resolve({...doc,sheet});await settle();let tree=h.render();named(tree,'coach-cohort').props.onChange({target:{value:'youth'}});h.render();assert.match(h.requests[1].url,/cohort=youth/);
 h.requests[1].resolve({...doc,sheet});await settle();tree=h.render();named(tree,'coach-slot-1').props.onChange({target:{value:'42'}});tree=h.render();button(tree,'Préparer la feuille corrigée').props.onClick();assert.equal(h.requests[2].body.cohort,'youth');assert.equal(h.requests[2].body.manual_slots['1'],'42');
});
test('unknown scores render as unknown and saved sheet can be reviewed without mutation',async()=>{
 const h=harness();h.render();h.requests[0].resolve({...doc,sheet});await settle();const html=renderToStaticMarkup(h.render());assert.match(html,/Synthetic/);assert.match(html,/Incomplet/);assert.match(html,/2026-07-01/);assert.equal(button(h.render(),'Enregistrer la feuille'),undefined);
});

test('saved manual tactics survive reopening and are retained in the next preview',async()=>{
 const h=harness();h.render();h.requests[0].resolve({...doc,sheet:{...sheet,tactics:{...sheet.tactics,manual:true,intensity:33}}});await settle();let tree=h.render();button(tree,'Préparer la feuille corrigée').props.onClick();assert.equal(h.requests[1].body.tactics?.intensity,33);
});

test('declining a cohort change preserves the dirty draft and does not fetch another cohort',async()=>{
 const h=harness();h.render();h.requests[0].resolve(doc);await settle();let tree=h.render();named(tree,'coach-weight-strength').props.onChange({target:{value:'7'}});tree=h.render();h.browser.confirm=()=>false;named(tree,'coach-cohort').props.onChange({target:{value:'youth'}});tree=h.render();assert.equal(h.requests.length,1);assert.equal(named(tree,'coach-cohort').props.value,'club');assert.equal(named(tree,'coach-weight-strength').props.value,7);assert.equal(h.dirty(),true);
});
test('local application uses the State-refreshing action and clears dirty state after confirmation',async()=>{
 const h=harness();let action;h.props.act=(path,body)=>{action={path,body};return Promise.resolve({...doc,revision:1,sheet})};h.render();h.requests[0].resolve(doc);await settle();let tree=h.render();button(tree,'Calculer le XV').props.onClick();h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,sheet});await settle();tree=h.render();button(tree,'Enregistrer et appliquer au XV local').props.onClick();await settle();tree=h.render();assert.equal(action.path,'/coach-lab/confirm');assert.equal(action.body.apply_local,true);assert.equal(action.body.preview_id,'a'.repeat(32));assert.equal(h.dirty(),false);assert.equal(button(tree,'Enregistrer la feuille'),undefined);
});

const automaticSheet={...sheet,responsibles:{captain:{selected:'42',manual:false,backups:[],ranking:[]},kicker:{selected:'42',manual:false,backups:[],ranking:[]}}};
test('automatic responsible suggestions stay automatic after coefficient edits and corrected previews',async()=>{
 const h=harness();h.props.d.squad=[{id:'42',name:'Synthetic'}];h.render();h.requests[0].resolve(doc);await settle();let tree=h.render();button(tree,'Calculer le XV').props.onClick();h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,sheet:automaticSheet});await settle();tree=h.render();
 assert.equal(named(tree,'coach-captain').props.value,'');assert.equal(named(tree,'coach-kicker').props.value,'');assert.match(renderToStaticMarkup(named(tree,'coach-captain')),/Synthetic/);
 named(tree,'coach-weight-role').props.onChange({target:{value:'captain'}});tree=h.render();named(tree,'coach-weight-strength').props.onChange({target:{value:'8'}});tree=h.render();button(tree,'Préparer la feuille corrigée').props.onClick();assert.equal(h.requests[2].body.captain,null);assert.equal(h.requests[2].body.kicker,null);
});
test('reopening saved automatic choices does not create manual overrides',async()=>{
 const h=harness();h.render();h.requests[0].resolve({...doc,sheet:automaticSheet});await settle();let tree=h.render();button(tree,'Préparer la feuille corrigée').props.onClick();assert.equal(h.requests[1].body.captain,null);assert.equal(h.requests[1].body.kicker,null);
});
test('explicit manual responsible choices survive previews and saved-sheet reopening',async()=>{
 const manualSheet={...sheet,responsibles:{captain:{selected:'42',manual:true,backups:[],ranking:[]},kicker:{selected:'42',manual:true,backups:[],ranking:[]}}};
 const h=harness();h.props.d.squad=[{id:'42',name:'Synthetic'}];h.render();h.requests[0].resolve({...doc,sheet:automaticSheet});await settle();let tree=h.render();named(tree,'coach-captain').props.onChange({target:{value:'42'}});named(tree,'coach-kicker').props.onChange({target:{value:'42'}});tree=h.render();button(tree,'Préparer la feuille corrigée').props.onClick();assert.equal(h.requests[1].body.captain,'42');assert.equal(h.requests[1].body.kicker,'42');h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,sheet:manualSheet});await settle();tree=h.render();assert.equal(named(tree,'coach-captain').props.value,'42');assert.equal(named(tree,'coach-kicker').props.value,'42');
 const reopened=harness();reopened.render();reopened.requests[0].resolve({...doc,sheet:manualSheet});await settle();tree=reopened.render();button(tree,'Préparer la feuille corrigée').props.onClick();assert.equal(reopened.requests[1].body.captain,'42');assert.equal(reopened.requests[1].body.kicker,'42');
});
test('bench rows without a single positional index are not labelled as incomplete',async()=>{
 const h=harness();h.render();h.requests[0].resolve({...doc,sheet:{...sheet,slots:{'1':'42','16':'43'},players:[...sheet.players,{slot:16,id:'43',name:'Complete bench',score:null}]}});await settle();const tree=h.render();const bench=nodes(tree).find(n=>n.type==='tr'&&nodes(n).some(child=>child.props?.name==='coach-slot-16'));const starter=nodes(tree).find(n=>n.type==='tr'&&nodes(n).some(child=>child.props?.name==='coach-slot-1'));assert.doesNotMatch(renderToStaticMarkup(bench),/Incomplet/);assert.match(renderToStaticMarkup(bench),/Selon le poste couvert/);assert.match(renderToStaticMarkup(starter),/Incomplet/);
});
