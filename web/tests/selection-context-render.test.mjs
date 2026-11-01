import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const sourceDir=path.resolve(import.meta.dirname,'../src');
const teams=[{id:'1',name:'Account Club',country:'BE',kind:'club'},{id:'2',name:'Followed Club',country:'FR',kind:'club'},{id:'u20:1',name:'Active Youth',country:'BE',kind:'u20'},{id:'nt:1',name:'Paused National',country:'BE',kind:'nt'}];
function state(kind='u20',active=false){
  const team=teams.find(team=>team.kind===kind)||teams[0];
  return {user:{username:'synthetic',admin:false},csrf:'synthetic-session',teams,current_team:{...team,meta:{}},classic_account:{id:'synthetic-account',username:'synthetic',imported_at:'2026-11-01T12:00:00Z',team_ids:['1'],selection_ids:active?[team.id]:[]},squad:[],academy:[],notes:{},plans:{},lineup:{},training:[],snapshots:[],matches:[],squad_source:null,academy_source:null,game_date:{season:62,round:1,day:1},settings:{developer_ready:false,manager_ready:false}};
}
function harness(overrides={},directFile=''){
  const cache=new Map(),calls=[];
  function production(file){
    if(cache.has(file))return cache.get(file).exports;
    const artifact={exports:{}};cache.set(file,artifact);let stateIndex=0;
    const react=path.basename(file)===directFile?{...React,useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useMemo:fn=>fn(),useRef:initial=>({current:initial})}:{...React,useState(initial){const index=stateIndex++;return React.useState(()=>Object.hasOwn(overrides[path.basename(file)]||{},index)?overrides[path.basename(file)][index]:typeof initial==='function'?initial():initial)}};
    const load=id=>{
      if(id==='react')return react;
      if(id==='./i18n')return {tr:(value,params={})=>value.replace(/\{(\w+)\}/g,(_,key)=>String(params[key]??'{'+key+'}')),localeTag:()=> 'fr-FR',getLocale:()=> 'fr',useLocale:()=>({locale:'fr',setLocale(){}}),normalizeLocale:value=>value,LanguageSelect:()=>null};
      if(id==='./App')return {request:()=>{throw Error('Rendering must not issue network requests')}};
      if(id.endsWith('.css'))return {};
      if(!id.startsWith('.'))return require(id);
      const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(existsSync);
      return production(target);
    };
    const compiled=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
    vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,structuredClone,crypto,URLSearchParams,AbortController,localStorage:{getItem:()=>null,setItem(){}},window:{matchMedia:()=>({matches:false})},setTimeout,clearTimeout,Map,Set});
    return artifact.exports;
  }
  const props=d=>({d,busy:false,act:async(...args)=>calls.push(args),go:page=>calls.push(page),openPlayer(){},selectTeam:(...args)=>calls.push(args)});
  const component=(file,name)=>production(path.join(sourceDir,file))[name];
  const render=(file,name,d,extra={})=>renderToStaticMarkup(React.createElement(component('navigation-guard.tsx','NavigationGuardProvider'),null,React.createElement(component(file,name),{...props(d),...extra})));
  return {component,render,props,calls};
}
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[];}
const text=node=>nodes(node).flatMap(node=>typeof node.props?.children==='string'?[node.props.children]:Array.isArray(node.props?.children)?node.props.children.filter(value=>typeof value==='string'):[]).join('');

for(const kind of ['u20','nt']){
  test(`${kind} suspended dashboard retains local analysis and offers reconnection instead of sync`,()=>{
    const h=harness(),d=state(kind),tree=h.component('selection-dashboard.tsx','SelectionDashboard')(h.props(d));
    const buttons=nodes(tree).filter(node=>node.type==='button');
    assert.equal(buttons.some(node=>text(node).includes('Actualiser la sélection')),false);
    const reconnect=buttons.find(node=>text(node).includes('Rattacher la sélection'));
    assert.ok(reconnect,'a suspended selection must expose a recovery action');reconnect.props.onClick();assert.deepEqual(h.calls,['settings']);
    for(const page of ['squad','progression','matches'])assert.ok(buttons.some(node=>{h.calls.length=0;node.props.onClick?.();return h.calls[0]===page}));
    assert.match(h.render('selection-dashboard.tsx','SelectionDashboard',d),/Sélection suspendue/);
  });
  test(`${kind} active dashboard syncs only its namespaced selection`,async()=>{
    const h=harness(),d=state(kind,true),tree=h.component('selection-dashboard.tsx','SelectionDashboard')(h.props(d));
    const sync=nodes(tree).find(node=>node.type==='button'&&text(node).includes('Actualiser la sélection'));
    assert.ok(sync);sync.props.onClick();await Promise.resolve();assert.equal(h.calls[0][0],'/classic/selections/sync');assert.equal(h.calls[0][1].team_id,d.current_team.id);
    assert.match(h.render('selection-dashboard.tsx','SelectionDashboard',d),/LE POINT DU JOUR/);
  });
  test(`${kind} suspended player table keeps export and local analysis without offering sync`,()=>{
    const html=harness().render('pages.tsx','Players',state(kind),{youth:false});
    assert.doesNotMatch(html,/>Synchroniser</);assert.match(html,/Rattacher la sélection/);assert.match(html,/Exporter CSV/);assert.match(html,/Composer mon XV/);
  });
  test(`${kind} active player synchronization uses its existing targeted sync route`,async()=>{
    const h=harness({},'pages.tsx'),d=state(kind,true),tree=h.component('pages.tsx','Players')({...h.props(d),youth:false});
    const sync=nodes(tree).find(node=>node.type==='button'&&text(node).includes('Synchroniser'));
    assert.ok(sync);sync.props.onClick();await Promise.resolve();assert.equal(h.calls[0][0],'/sync');assert.equal(h.calls[0][1].team_id,d.current_team.id);assert.equal(h.calls[0][1].kind,'squad');
  });
  test(`${kind} calendar keeps manual dates and does not offer unsupported Classic import`,()=>{
    const html=harness().render('workbench.tsx','SeasonPlanner',state(kind));
    assert.doesNotMatch(html,/Lire les prochaines rencontres Classic/);assert.match(html,/Ajouter une date/);assert.match(html,/calendrier manuel/i);
    assert.equal(html.includes('lisez les prochaines rencontres Classic'),false,'the selection empty state must not promise unsupported Classic imports');
  });
}
test('club calendar and player synchronization remain available',()=>{
  const h=harness(),d=state('club'),calendar=h.render('workbench.tsx','SeasonPlanner',d);assert.match(calendar,/Lire les prochaines rencontres Classic/);assert.match(calendar,/lisez les prochaines rencontres Classic/);assert.match(h.render('pages.tsx','Players',d,{youth:false}),/>Synchroniser</);
});

const emptySeries={points:[],players:[],snapshot_count:0,total_snapshots:0,snapshot_limit:500,invalid_dates:0,invalid_payloads:0,invalid_players:0,history_truncated:false,omitted_player_observations:0};
for(const kind of ['club','u20','nt'])test(`${kind} progression population controls respect team capabilities`,()=>{
  const d=state(kind),bundle={team_id:d.current_team.id,seniors:emptySeries,academy:emptySeries};
  const h=harness({'progression.tsx':{2:{scope:`synthetic:synthetic-session:${d.current_team.id}`,bundle,error:''}}});
  const html=h.render('progression.tsx','Progression',d);
  if(kind==='club')assert.match(html,/<option value="academy">Académie<\/option>/);
  else {assert.doesNotMatch(html,/<option value="academy">/);assert.doesNotMatch(html,/Rapports d’entraînement/);}
});

test('App groups every team once by account ownership and selection state',()=>{
  const d=state('u20',true);d.teams=[...teams,teams[0]];
  // App now has a cohort preference before its data/loading/team state hooks.
  const h=harness({'App.tsx':{2:d,4:false,6:d.current_team.id}}),html=h.render('App.tsx','default',d);
  const selector=html.match(/<select aria-label="Choisir une équipe"[^]*?<\/select>/)?.[0];
  assert.ok(selector);for(const label of ['Clubs du compte Classic','Clubs suivis','Sélections actives','Sélections suspendues'])assert.ok(selector.includes(`<optgroup label="${label}">`),label);
  for(const id of ['1','2','u20:1','nt:1'])assert.equal((selector.match(new RegExp(`value="${id}"`,'g'))||[]).length,1,id);
});

test('the followed clubs section counts and lists clubs without national selections',()=>{
  const html=harness().render('pages.tsx','Settings',state('club'));
  const section=html.match(/<section class="card"><div class="card-heading"><div><span class="eyebrow">03 \/ VOTRE RÉSEAU[^]*?<\/section>/)?.[0];
  assert.ok(section);assert.match(section,/2 clubs/);assert.match(section,/Account Club/);assert.match(section,/Followed Club/);assert.doesNotMatch(section,/Active Youth|Paused National/);
});

function report({id,name,country}){return {team:{id,name,country},objective:'balanced',season:62,generated_at:'2026-11-01T12:00:00Z',sources:{squad:null,academy:null},warnings:[],summary:{seniors:0,academy:0,eligible:0,selected:0,low_energy:0,unknown_energy:0},lineup:{slots:{},players:[],unfilled:[],excluded:[],comparison:{saved_score:null,proposed_score:null,delta:null}},recommendations:[],training:{priorities:[],grid:[],added:0,preserved:0,remaining_weeks:0,start_week:1},season_plan:[],matches:[],methodology:[]};}
test('optimization overview identifies clubs, U20 and national teams without labelling selections as followed clubs',()=>{
  const d=state('u20',true),reports=teams.map(report),query=new URLSearchParams({team_id:d.current_team.id,objective:'balanced',energy_floor:'60',energy_scale:'auto',season:'62',scope:'all'}).toString();
  const h=harness({'optimization.tsx':{4:'all',9:{reports,state:d,key:query+':0'}}}),html=h.render('optimization.tsx','Optimization',d);
  assert.match(html,/Votre vue multi-équipes/);assert.match(html,/4 équipes/);
  const cards=[...html.matchAll(/<button[^>]*class="opt-club [^]*?<\/button>/g)].map(match=>match[0]);
  assert.equal(cards.length,4);
  assert.match(cards[0],/Club du compte Classic/);assert.match(cards[1],/Club suivi/);assert.match(cards[2],/Sélection U20/);assert.match(cards[3],/Sélection nationale/);
  assert.doesNotMatch(cards[2]+cards[3],/Club suivi/);
});
