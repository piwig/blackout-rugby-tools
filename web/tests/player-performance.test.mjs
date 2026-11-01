import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function harness(){
  const hooks=[],requests=[],dirtyStates=[];let cursor=0,effects=[];
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value;},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((value,k)=>!Object.is(value,old.deps[k]))){hooks[i]={deps,effect,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()});}}};
  const module={exports:{}};
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/player-performance.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:(url,body,csrf)=>new Promise((resolve,reject)=>requests.push({url,body,csrf,resolve,reject}))};
    if(id==='./i18n')return {tr:(s,p)=>s.replace(/\{([^}]+)\}/g,(_,k)=>p?.[k]??k)};
    if(id==='./types')return {fmt:v=>v??'—',date:v=>v??'—'};
    if(id==='./navigation-guard')return {useUnsavedChanges(value){dirtyStates.push(value)}};
    if(id.endsWith('.css'))return {};
    return require(id);
  },Date,JSON,URLSearchParams,Blob,URL,window:{confirm:()=>true},document:{getElementById:()=>null}});
  const props={busy:false,d:{user:{username:'synthetic'},csrf:'session-1',current_team:{id:'72450'},teams:[{id:'72450',name:'Synthetic XV'}],squad:[],academy:[],squad_source:null,academy_source:null}};
  return {requests,props,dirty:()=>dirtyStates.at(-1),render(){cursor=0;effects=[];const tree=module.exports.PlayerPerformance(props);effects.forEach(f=>f());return tree},unmount(){hooks.forEach(h=>h.cleanup?.())}};
}
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[]}
function named(tree,name){return nodes(tree).find(n=>n.props?.name===name)}
function button(tree,phrase){return nodes(tree).find(n=>n.type==='button'&&JSON.stringify(n.props.children).includes(phrase))}
async function settle(){for(let i=0;i<15;i++)await Promise.resolve()}
const empty={revision:0,total:0,total_stored:0,groups:[],observations:[],options:{team_id:[],context:[],position:[],rating_scale:[],competition:[],opponent:[],venue:[]}};
const sample={team_id:'72450',context:'club',player_id:'42',player_name:'Synthetic player',position:'Centre',rating_scale:'observer-10',scale_min:0,scale_max:10,matches:3,rated:2,missing_ratings:1,mean:7,min:6,max:8,known_minutes:80,minutes_observations:2,missing_minutes:1,small_sample:true,first_match:'2026-10-01',last_match:'2026-10-03'};

test('empty state offers documented file preview and missing values render without zero ratings',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();let html=renderToStaticMarkup(tree);
 assert.match(html,/Aucune observation de match/);assert.match(html,/Télécharger le modèle CSV/);assert.match(html,/type="file"/);assert.match(html,/Les statistiques Classic de carrière/);
 h.props.d.current_team.id='999';tree=h.render();h.requests[1].resolve({...empty,total:1,total_stored:1,groups:[{...sample,mean:null,min:null,max:null,known_minutes:null}]});await settle();html=renderToStaticMarkup(h.render());
 assert.match(html,/Petit échantillon/);assert.match(html,/Notes manquantes : 1/);assert.match(html,/Minutes manquantes : 1/);assert.match(html,/observer-10/);assert.match(html,/—/);
});

test('preview carries exact revision, content and mode, edits invalidate approval, and confirmation is single submission',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();named(tree,'observations-content').props.onChange({target:{value:'[{"example":true}]'}});tree=h.render();
 button(tree,'Préparer l’aperçu').props.onClick();button(tree,'Préparer l’aperçu').props.onClick();assert.equal(h.requests.length,2);assert.equal(h.requests[1].body.content,'[{"example":true}]');assert.equal(h.requests[1].body.expected_revision,0);assert.equal(h.requests[1].csrf,'session-1');
 const preview={preview_id:'a'.repeat(32),revision:0,added:1,replaced:0,duplicates:0,observations:[]};h.requests[1].resolve(preview);await settle();tree=h.render();assert.ok(button(tree,'Confirmer l’import'));
 named(tree,'observations-content').props.onChange({target:{value:'[]'}});tree=h.render();assert.equal(button(tree,'Confirmer l’import'),undefined);
 button(tree,'Préparer l’aperçu').props.onClick();h.requests[2].resolve(preview);await settle();tree=h.render();button(tree,'Confirmer l’import').props.onClick();button(tree,'Confirmer l’import').props.onClick();assert.equal(h.requests.length,4);assert.deepEqual(JSON.parse(JSON.stringify(h.requests[3].body)),{preview_id:'a'.repeat(32),expected_revision:0});
});

test('late previews after account changes are discarded and cannot be confirmed',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();named(tree,'observations-content').props.onChange({target:{value:'[]'}});tree=h.render();button(tree,'Préparer l’aperçu').props.onClick();h.props.d.csrf='session-2';h.props.d.user.username='other';h.render();h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,added:1,replaced:0,duplicates:0,observations:[]});await settle();tree=h.render();assert.equal(button(tree,'Confirmer l’import'),undefined);
});

test('clearing a date filter removes it from the request instead of sending an invalid empty date',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();
 const start=nodes(tree).find(n=>n.type==='input'&&n.props.type==='date');start.props.onChange({target:{value:'2026-10-01'}});tree=h.render();assert.match(h.requests[1].url,/start=2026-10-01/);
 nodes(tree).find(n=>n.type==='input'&&n.props.type==='date').props.onChange({target:{value:''}});h.render();assert.doesNotMatch(h.requests[2].url,/start=/);
});

test('correction exports only editable observation fields and deletion uses the displayed revision',async()=>{
 const h=harness();h.render();const observation={id:'b'.repeat(64),team_id:'72450',context:'club',match_id:'17',match_date:'2026-10-01',competition:'League',opponent:'Synthetic XV',venue:'home',player_id:'42',player_name:'Synthetic player',position:'Centre',rating:6,rating_scale:'observer-10',scale_min:0,scale_max:10,minutes:null,source:'Notebook',imported_at:'2026-10-03',updated_at:'2026-10-03'};
 h.requests[0].resolve({...empty,revision:4,total:1,total_stored:1,groups:[sample],observations:[observation]});await settle();let tree=h.render();
 button(tree,'Corriger cette observation').props.onClick();tree=h.render();const parsed=JSON.parse(named(tree,'observations-content').props.value)[0];assert.equal(parsed.rating,6);assert.equal(parsed.source,'Notebook');assert.equal(parsed.id,undefined);assert.equal(parsed.imported_at,undefined);
 button(tree,'Préparer l’aperçu').props.onClick();assert.equal(h.requests[1].body.mode,'replace');assert.equal(h.requests[1].body.expected_revision,4);h.requests[1].resolve({preview_id:'a'.repeat(32),revision:4,added:0,replaced:1,duplicates:0,observations:[observation]});await settle();tree=h.render();
 button(tree,'Supprimer l’observation').props.onClick();assert.equal(h.requests[2].url,'/player-performance/delete');assert.equal(h.requests[2].body.expected_revision,4);assert.deepEqual([...h.requests[2].body.ids],['b'.repeat(64)]);
});

test('skill estimates belong only to the selected team and the matching senior or youth source',async()=>{
 const h=harness();h.props.d.squad=[{id:'42',metrics:{roles:[{name:'Centre',score:12.5}]}}];h.props.d.squad_source={observed_at:'2026-10-31'};h.props.d.academy=[];
 h.render();h.requests[0].resolve({...empty,total:3,total_stored:3,groups:[sample,{...sample,context:'youth'},{...sample,team_id:'999'}]});await settle();const html=renderToStaticMarkup(h.render());
 assert.equal((html.match(/Indice de compétences/g)||[]).length,1);assert.match(html,/12.5/);assert.match(html,/Effectif observé le 2026-10-31/);assert.equal((html.match(/Aucun indice actuel comparable connu/g)||[]).length,2);
});


test('switching accounts hides previous editor content and previews in the first render',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();named(tree,'observations-content').props.onChange({target:{value:'private account A'}});tree=h.render();button(tree,'Préparer l’aperçu').props.onClick();h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,added:1,replaced:0,duplicates:0,observations:[]});await settle();h.render();
 h.props.d.csrf='session-2';h.props.d.user.username='other';tree=h.render();assert.equal(named(tree,'observations-content').props.value,'');assert.equal(button(tree,'Confirmer l’import'),undefined);
});

test('Classic read prepares one match with explicit context and presents source warnings before confirmation',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();
 named(tree,'classic-fixture').props.onChange({target:{value:'17'}});named(tree,'classic-context').props.onChange({target:{value:'youth'}});tree=h.render();button(tree,'Lire ce match Classic').props.onClick();button(tree,'Lire ce match Classic').props.onClick();
 assert.equal(h.requests.length,2);assert.equal(h.requests[1].url,'/player-performance/classic-preview');assert.deepEqual(JSON.parse(JSON.stringify(h.requests[1].body)),{team_id:'72450',context:'youth',fixture_id:'17',expected_revision:0,mode:'append'});
 h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,added:1,replaced:0,duplicates:0,observations:[],warnings:['Minutes Classic indisponibles pour ce relevé ; aucune durée n’est déduite.']});await settle();tree=h.render();const html=renderToStaticMarkup(tree);assert.match(html,/Minutes Classic indisponibles/);assert.ok(button(tree,'Confirmer l’import'));
});


test('a ready Classic preview stays protected until confirmation completes',async()=>{
 const h=harness();h.render();h.requests[0].resolve(empty);await settle();let tree=h.render();
 named(tree,'classic-fixture').props.onChange({target:{value:'17'}});tree=h.render();button(tree,'Lire ce match Classic').props.onClick();tree=h.render();assert.equal(h.dirty(),true);
 h.requests[1].resolve({preview_id:'a'.repeat(32),revision:0,added:1,replaced:0,duplicates:0,observations:[],warnings:[]});await settle();tree=h.render();assert.ok(button(tree,'Confirmer l’import'));assert.equal(named(tree,'observations-content').props.value,'');assert.equal(h.dirty(),true);
 button(tree,'Confirmer l’import').props.onClick();h.requests[2].resolve({revision:1});await settle();tree=h.render();assert.equal(button(tree,'Confirmer l’import'),undefined);assert.equal(h.dirty(),false);
});
