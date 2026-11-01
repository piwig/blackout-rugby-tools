import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react');
const nodes=tree=>Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[];

function harness(team){
  const states=[],components=new Map();let cursor=0;
  const component=name=>{if(!components.has(name))components.set(name,()=>null);return components.get(name)};
  const common=new Proxy({},{get:(_,key)=>component(key)});
  const d={user:{username:'synthetic'},csrf:'session',current_team:{id:team,meta:{},name:'Synthetic team'},teams:[{id:team,name:'Synthetic team'}],squad:[],academy:[],notes:{},game_date:null};
  const react={...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=i===2?d:i===4?false:i===5?'squad':typeof initial==='function'?initial():initial;return [states[i],next=>states[i]=typeof next==='function'?next(states[i]):next]},useEffect(){},useCallback:fn=>fn,useRef:value=>({current:value})};
  const artifact={exports:{}};
  const load=id=>{
    if(id==='react')return react;
    if(id==='./i18n')return {...common,tr:value=>value,getLocale:()=> 'fr',useLocale:()=>({locale:'fr',setLocale(){}}),normalizeLocale:value=>value};
    if(id==='./team-context')return {teamKind:team=>team.id.startsWith('u20:')?'u20':team.id.startsWith('nt:')?'nt':'club',isSelectionTeam:team=>team.id.includes(':'),groupedTeams:()=>[{label:'Teams',teams:d.teams}]};
    if(id==='./navigation-guard')return {useNavigationGuard:()=>({confirmLeave:()=>true})};
    if(id==='./navigation')return {navigationItems:[{id:'squad',label:'Squad'}],isClubOnly:()=>false};
    if(id==='./profile')return {...common,defaultProfile:{motion:'full',density:'normal',text_size:'normal',display_name:''}};
    if(id==='./workbench')return new Proxy({clubTheme:()=>({})},{get:(target,key)=>target[key]??component(key)});
    if(id.startsWith('.'))return common;
    return require(id);
  };
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:load,localStorage:{getItem:()=>team},window:{matchMedia:()=>({matches:false})},URLSearchParams,setTimeout,clearTimeout});
  return {d,render(){cursor=0;return artifact.exports.default()},find(tree,name){return nodes(tree).find(node=>node.type===component(name))}};
}

test('App preserves explicit population when the same player ID is opened from both club rosters',()=>{
  const h=harness('72450'),player={id:'42',name:'Same ID'};
  h.find(h.render(),'Players').props.openPlayer(player,true);
  const junior=h.find(h.render(),'PlayerDetail');assert.equal(junior.props.cohort,'youth');assert.equal(junior.props.player,player);
  h.find(h.render(),'Players').props.openPlayer(player,false);
  const senior=h.find(h.render(),'PlayerDetail');assert.equal(senior.props.cohort,'club');assert.notEqual(junior.key,senior.key);
});

for(const [team,cohort] of [['u20:72450','u20'],['nt:72450','nt']])test(`App keeps ${cohort} separate from club youth`,()=>{
  const h=harness(team),player={id:'42',name:'Synthetic selection player',age:18};
  h.find(h.render(),'Players').props.openPlayer(player,false);
  const detail=h.find(h.render(),'PlayerDetail');assert.equal(detail.props.cohort,cohort);assert.equal(detail.props.d.current_team.id,team);
});
