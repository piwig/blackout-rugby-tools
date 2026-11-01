import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const tr=(s,p)=>s?.replace(/\{([^}]+)\}/g,(_,k)=>p?.[k]??k);
const junior={id:'77',type:3,home:'Synthetic home',away:'Synthetic away',summary:{classified:1,inferred:0,unclassified:0},events:[],event_count:1};
const senior={...junior,type:0};
function harness(file,entry){
  const hooks=[],requests=[],actions=[];let cursor=0,effects=[];
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value;},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((v,k)=>!Object.is(v,old.deps[k]))){hooks[i]={deps,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()});}},useMemo(fn){cursor++;return fn()}};
  const module={exports:{}},children=({children})=>children;
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/'+file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:(url,body,csrf)=>new Promise((resolve,reject)=>requests.push({url,body,csrf,resolve,reject}))};
    if(id==='./i18n')return {tr,localeTag:()=> 'fr-FR'};
    if(id==='./components')return {Empty:children,Pill:children,Modal:children};
    if(id==='./types')return {fmt:v=>v??'—',formatStatistic:v=>v??'—',date:v=>v??'—',skills:[],labels:{}};
    if(id==='./navigation-guard')return {useUnsavedChanges:()=>{}};
    if(id.startsWith('.'))return new Proxy({},{get:()=>()=>null});
    return require(id);
  },URLSearchParams,FormData,TextEncoder,Date,JSON,Map,Set,requestAnimationFrame:()=>{},window:{},document:{}});
  const props={busy:false,d:{user:{username:'synthetic'},csrf:'synthetic-session',current_team:{id:'72450',kind:'club',name:'Synthetic XV',meta:{}},matches:[senior,junior],plans:{},settings:{developer_ready:true}},act:(url,body,message)=>new Promise((resolve,reject)=>actions.push({url,body,message,resolve,reject})),go:()=>{},onSelect:()=>{},selected:null};
  return {props,requests,actions,render(){cursor=0;effects=[];let tree=module.exports[entry](props);if(entry==='OpponentInsights')tree=tree.type(tree.props);effects.forEach(f=>f());return tree}};
}
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[]}
function text(tree){return Array.isArray(tree)?tree.map(text).join(''):tree&&typeof tree==='object'?text(tree.props?.children):String(tree??'')}
function button(tree,label){return nodes(tree).find(n=>n.type==='button'&&text(n)===label)}
function select(tree,label){return nodes(nodes(tree).find(n=>n.type==='label'&&text(n).startsWith(label))).find(n=>n.type==='select')}
function change(node,value){node.props.onChange({target:{value}})}
async function settle(){for(let i=0;i<15;i++)await Promise.resolve()}

test('junior file import previews its context and opens the exact type plus fixture after confirmation',async()=>{
  const h=harness('pages.tsx','Matches');let tree=h.render();button(tree,'Import avancé JSON / CSV').props.onClick();tree=h.render();
  const kind=select(tree,'Type du match');assert.ok(nodes(kind).some(n=>n.type==='option'&&n.props.value==='3'&&text(n)==='Juniors'));
  change(kind,'3');change(nodes(tree).find(n=>n.type==='textarea'),JSON.stringify({...junior,youth:true}));tree=h.render();button(tree,'Vérifier avant import').props.onClick();
  assert.equal(h.requests[0].url,'/matches/import?type=3&preview=true');assert.equal(h.requests[0].body.youth,true);assert.equal(h.actions.length,0);
  h.requests[0].resolve({match:junior});await settle();tree=h.render();assert.match(renderToStaticMarkup(tree),/Juniors · #77/);
  button(tree,'Confirmer l’import').props.onClick();assert.equal(h.actions[0].url,'/matches/import?type=3');assert.equal(h.actions[0].body.type,3);
  h.actions[0].resolve({id:'77',type:3});await settle();assert.equal(h.requests[1].url,'/matches/3/77');
});

test('junior history exposes a distinct filter and selects the junior fixture when its id equals a senior fixture',async()=>{
  const h=harness('match-history.tsx','MatchHistory'),selected=[];h.props.onSelect=m=>selected.push(m);let tree=h.render();
  const kind=select(tree,'Type du match');assert.ok(nodes(kind).some(n=>n.type==='option'&&n.props.value==='3'&&text(n)==='Juniors'));change(kind,'3');h.render();
  assert.match(h.requests[1].url,/type=3/);h.requests[1].resolve({options:{seasons:[],teams:[],types:[3]},mixed_types:false,total_stored:2,total_filtered:1,matches:[junior],totals:{matches:1,scored_matches:0,events:1,classified:1,unclassified:0,non_attack:0,manual:0,inferred:0,coverage_pct:100,points_total:0,points_per_match:null},attacks:[],zones:[],by_season:[],team_record:null});await settle();tree=h.render();
  assert.match(renderToStaticMarkup(tree),/Juniors/);const card=nodes(tree).find(n=>n.type==='button'&&n.props.className?.includes('match-card'));card.props.onClick();assert.equal(selected[0].type,3);assert.equal(selected[0].id,'77');
});

test('opponent links and filters retain junior context without replacing the senior link of the same fixture',async()=>{
  const h=harness('insights.tsx','OpponentInsights');h.render();const seniorLink={match_id:'77',match_type:0,club_side:'home',opponent:'Senior opponent',season:null};
  const document={version:1,revision:4,updated_at:null,goals:[],sessions:[],match_links:[seniorLink],stadium_scenarios:[]};
  h.requests.filter(r=>r.url==='/insights/72450').forEach(r=>r.resolve({document}));await settle();let tree=h.render();
  const match=select(tree,'Rencontre de la bibliothèque');const option=nodes(match).find(n=>n.type==='option'&&n.props.value==='3:77');assert.match(text(option),/^Juniors #77/);
  change(match,'3:77');change(select(tree,'Côté de '),'away');change(nodes(nodes(tree).find(n=>n.type==='label'&&text(n).startsWith('Nom du dossier'))).find(n=>n.type==='input'),'Junior opponent');tree=h.render();
  nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});const save=h.requests.find(r=>r.body);assert.deepEqual(JSON.parse(JSON.stringify(save.body.document.match_links)),[seniorLink,{match_id:'77',match_type:3,club_side:'away',opponent:'Junior opponent',season:null}]);assert.equal(save.body.expected_revision,4);
  const filter=select(tree,'Type');assert.ok(nodes(filter).some(n=>n.type==='option'&&n.props.value==='3'));change(filter,'3');h.render();assert.match(h.requests.at(-1).url,/match_type=3/);
});

test('direct junior reads request an explicit junior cohort and preserve it from recent fixture to preview',async()=>{
  const h=harness('match-direct.tsx','MatchDirect');let tree=h.render();
  const population=select(tree,'Population des rencontres récentes');assert.ok(population);change(population,'3');tree=h.render();
  button(tree,'Afficher les rencontres récentes').props.onClick();assert.deepEqual(JSON.parse(JSON.stringify(h.requests[0].body)),{team_id:'72450',type:3});
  h.requests[0].resolve({fixtures:[junior]});await settle();tree=h.render();
  nodes(tree).find(n=>n.type==='button'&&n.props.className==='match-recent-item').props.onClick();assert.equal(h.requests[1].body.type,3);assert.equal(h.requests[1].body.reference,'77');
  h.requests[1].resolve({match:junior,source_token:'synthetic-token',expected_revision:0,expected_source_digest:null});await settle();tree=h.render();assert.match(renderToStaticMarkup(tree),/Juniors · #77/);
  assert.equal(select(tree,'Type du match').props.value,3);
});

test('direct manual links offer juniors while recent selection teams retain their own automatic namespace',()=>{
  for(const [kind,id,type] of [['club','72450',0],['u20','u20:9',1],['nt','nt:9',2]]){
    const h=harness('match-direct.tsx','MatchDirect');h.props.d.current_team={...h.props.d.current_team,kind,id};const tree=h.render();
    assert.ok(nodes(select(tree,'Type du match')).some(n=>n.type==='option'&&n.props.value===3&&text(n)==='Juniors'));
    if(kind!=='club')assert.equal(select(tree,'Population des rencontres récentes'),undefined);
    button(tree,'Afficher les rencontres récentes').props.onClick();assert.deepEqual(JSON.parse(JSON.stringify(h.requests[0].body)),{team_id:id,type});
  }
});
