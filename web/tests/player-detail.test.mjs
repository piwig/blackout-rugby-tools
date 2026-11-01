import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');

function harness(cohort='youth',team='72450'){
  const hooks=[],requests=[];let cursor=0,effects=[];
  const react={...React,useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next}];},useRef(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:{current:initial}};return hooks[i].value;},useEffect(effect,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((value,k)=>!Object.is(value,old.deps[k]))){hooks[i]={deps,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect()})}}};
  const artifact={exports:{}};
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/player-detail.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))};
    if(id==='./i18n')return {tr:value=>value};
    if(id==='./types')return {date:value=>value,fmt:value=>value??'—'};
    if(id==='./components')return {Modal:({children})=>React.createElement('section',null,children),Pill:({children})=>React.createElement('span',null,children),Radar:()=>null,SkillList:()=>null};
    if(id==='./navigation-guard')return {useUnsavedChanges(){}};
    return require(id);
  },URLSearchParams,window:{confirm:()=>true}});
  const props={cohort,player:{id:'42',name:'Synthetic player',age:18,metrics:{known_skills:0,roles:[]}},d:{user:{username:'synthetic'},csrf:'session-a',current_team:{id:team},notes:{}},act:async()=>{},close(){}};
  return {props,requests,render(){cursor=0;effects=[];const tree=artifact.exports.PlayerDetail(props);effects.forEach(effect=>effect());return renderToStaticMarkup(tree)},unmount(){hooks.forEach(h=>h.cleanup?.())}};
}
const observation=(cohort='youth',source='Junior source')=>({snapshot_id:1,team_id:'72450',cohort,youth:cohort==='youth',observed_at:'2026-01-01T10:00:00+02:00',source,player:{id:'42',attack:0,defense:null,strength:'Unknown'}});
async function settle(){for(let i=0;i<10;i++)await Promise.resolve()}

for(const [cohort,team,label] of [['club','72450','Seniors'],['youth','72450','Juniors'],['u20','u20:72450','Sélection U20'],['nt','nt:72450','Sélection nationale']])test(`history explicitly requests and labels the ${cohort} source cohort`,()=>{
  const h=harness(cohort,team),html=h.render();
  const url=new URL(h.requests[0].url,'https://local.invalid');
  assert.equal(decodeURIComponent(url.pathname),'/history/'+team+'/42');
  assert.equal(url.searchParams.get('cohort'),cohort);
  assert.match(html,/Chargement…/);assert.ok(html.includes(label));
});

for(const [cohort,team,path] of [
  ['youth','72450','club.squad.youth.php'],
  ['club','72450','club.squad.php'],
  ['u20','u20:72450','club.squad.php'],
  ['nt','nt:72450','club.squad.php']
])test(`Classic player link uses the ${cohort} source cohort`,()=>{
  const html=harness(cohort,team).render();
  assert.ok(html.includes('href="https://www.blackoutrugby.com/game/'+path+'#player=42"'));
});

test('history renders exact provenance and preserves zero versus unknown values',async()=>{
  const h=harness();h.render();h.requests[0].resolve([observation()]);await settle();
  const html=h.render();
  assert.match(html,/Junior source/);assert.match(html,/2026-01-01T10:00:00\+02:00/);
  assert.match(html,/Attaque 0/);assert.match(html,/Défense —/);assert.match(html,/Force Unknown/);
  assert.doesNotMatch(html,/Chargement…/);
});

test('an empty cohort has an explicit empty state after loading',async()=>{
  const h=harness();assert.doesNotMatch(h.render(),/Aucune observation/);
  h.requests[0].resolve([]);await settle();
  assert.match(h.render(),/Aucune observation/);
});

test('switching population hides prior rows immediately and ignores a late reply',async()=>{
  const h=harness();h.render();const old=h.requests[0];
  h.props.cohort='club';assert.doesNotMatch(h.render(),/Junior source/);
  assert.equal(h.requests.length,2);
  h.requests[1].resolve([observation('club','Senior source')]);await settle();
  old.resolve([observation()]);await settle();
  const html=h.render();assert.match(html,/Senior source/);assert.doesNotMatch(html,/Junior source/);
  h.props.player={...h.props.player,id:'43'};
  assert.doesNotMatch(h.render(),/Senior source/);assert.equal(h.requests.length,3);
  h.props.d={...h.props.d,csrf:'session-b'};
  assert.doesNotMatch(h.render(),/Senior source/);assert.equal(h.requests.length,4);
});

test('a late failure from an abandoned player cannot replace the current history',async()=>{
  const h=harness();h.render();const old=h.requests[0];
  h.props.player={...h.props.player,id:'43'};h.render();
  h.requests[1].resolve([]);await settle();old.reject(Error('Abandoned history error'));await settle();
  assert.match(h.render(),/Aucune observation/);assert.doesNotMatch(h.render(),/Abandoned history error/);
});
