import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const sourceDir=path.resolve(import.meta.dirname,'../src'),cache=new Map(),i18n=require('../src/i18n/runtime.ts');
i18n.installCatalogs({fr:{},en:{'Annuler':'Cancel'}});i18n.setLocale('en');
function production(file){
  if(cache.has(file))return cache.get(file).exports;
  const artifact={exports:{}};cache.set(file,artifact);
  const compiled=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const load=id=>{
    if(id==='./i18n'||id==='./i18n/runtime.ts')return i18n;
    if(id.endsWith('.css'))return {};
    if(id==='./App')return {request:()=>{throw new Error('Rendering must not issue requests')}};
    if(!id.startsWith('.'))return require(id);
    const base=path.resolve(path.dirname(file),id),target=[base,base+'.ts',base+'.tsx'].find(existsSync);
    return production(target);
  };
  vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,structuredClone,Map,Set,URLSearchParams});
  return artifact.exports;
}
const {TrainingReportView,InstructionsView,PlayerStatisticsView}=production(path.join(sourceDir,'coaching.tsx'));
const {RoleWeightsEditor}=production(path.join(sourceDir,'role-weights.tsx'));
const {NavigationGuardProvider}=production(path.join(sourceDir,'navigation-guard.tsx'));
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));

test('a report with unknown team skills renders its known player observations',()=>{
  const html=render(TrainingReportView,{data:{key:'report:1',report_id:'1',season:62,round:1,observed_at:'2026-10-01T10:00:00Z',team:{skills:null,players:[{player_id:'1',player_name:'Annuler',csr_before:null,csr_after:12000,energy_before:null,energy_after:null,pops:[],drops:[]}]},individual:null}});
  assert.match(html,/Annuler/);assert.match(html,/12,000/);assert.doesNotMatch(html,/NaN|Infinity|Cancel/);
});

test('a saved mail report shows its provenance, warning, trainer level and original labels',()=>{
  const html=render(TrainingReportView,{data:{key:'mail:1',report_id:null,season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
    provenance:{source:'Classic email',source_format:'eml',club_name:'Example & Club',club_id:null},
    source_disagreement:true,team:null,individual:{players:[
      {player_id:'1',csr_before:110,csr_after:115,energy:{kind:'label',before:'Fresh',after:'Annuler'},
        skills:[{skill:'pace',sessions:2,trainer:{name:'Coach Démo',level:7,type:null},
          pops:[{skill:'pace',before:null,after:null,before_label:'Some',after_label:'More'}]}]},
    ]}}});
  assert.match(html,/Mail Classic.*EML/);
  assert.match(html,/Example &amp; Club/);
  assert.match(html,/Des rapports enregistrés pour cette période diffèrent sur des valeurs communes/);
  assert.match(html,/Coach Démo.*niveau 7/i);
  assert.match(html,/Fresh → Annuler/);
  assert.match(html,/Some → More/);
  assert.doesNotMatch(html,/RAPPORT OFFICIEL|API Classic|Cancel|%/);
});

test('a mail preview identifies its file source before it is saved',()=>{
  const data={key:'mail:preview',report_id:null,season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
    provenance:{source:'Classic email',source_format:'html',club_name:'Example Club',club_id:null},
    team:{players:[]},individual:{players:[]}};
  const html=render(TrainingReportView,{data,preview:true});
  assert.match(html,/Mail Classic · HTML · Analysé le/);
  assert.doesNotMatch(html,/Importé le/);
});

test('an individual result identifies the skill that changed when a different skill was trained',()=>{
  const data={key:'api:pop',report_id:'1',season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
    individual:{players:[{player_id:'1',skills:[
      {skill:'speed',sessions:2,pops:[{skill:'kicking',before:3,after:4}]},
    ]}]}};
  const html=render(TrainingReportView,{data});
  assert.match(html,/<strong>Vitesse<\/strong> · 2 séances/);
  assert.match(html,/Jeu au pied · 3 → 4/);
});

test('report detail and coverage distinguish unknown lists, empty lists and a known absence of rises',()=>{
  const html=render(TrainingReportView,{data:{key:'api:1',report_id:'1',season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
    team:{players:[]},individual:{players:[
      {player_id:'1',csr_before:110,csr_after:105,energy_before:105,energy_after:95,
        skills:[{skill:'pace',sessions:0,pops:[]},{skill:'defense',sessions:null,pops:null}]},
      {player_id:'2',skills:null},
      {player_id:'3',skills:[]},
    ]}}});
  assert.match(html,/API Classic/);
  assert.match(html,/Aucun joueur dans cette partie du rapport/);
  assert.match(html,/105 → 95/);
  assert.match(html,/Aucun passage de niveau signalé/);
  assert.match(html,/Passages de niveau non renseignés/);
  assert.match(html,/Liste de compétences non renseignée/);
  assert.match(html,/Aucune compétence entraînée indiquée/);
  assert.match(html,/1\/2 entrées de compétence renseignées/);
  assert.match(html,/0\/3 joueurs avec un écart CSR calculable/);
  assert.doesNotMatch(html,/105 %|95 %/);
});

test('continuous coverage shows known breaks alongside signed phase deltas',()=>{
  const html=render(TrainingReportView,{data:{key:'api:1',report_id:'1',season:1,round:2,observed_at:'2026-10-01T10:00:00Z',
    team:{players:[{player_id:'1',player_name:'Example Player',csr_before:100,csr_after:110}]},
    individual:{players:[{player_id:'1',csr_before:112,csr_after:107}]}}});
  assert.match(html,/\+10/);
  assert.match(html,/-5/);
  assert.match(html,/Ruptures de continuité du CSR/);
  assert.match(html,/Example Player.*110.*112/);
  assert.doesNotMatch(html,/\+7|\+5/);
});

test('unknown instruction slots are distinct from explicitly free slots',()=>{
  const html=render(InstructionsView,{data:{key:'instructions:1',observed_at:'2026-10-01T10:00:00Z',team_skills:['unreported',null,'strength','speed'],youth_skills:null,individual:[]}});
  assert.match(html,/Non renseigné/);assert.equal((html.match(/Créneau libre/g)||[]).length,1);
  assert.doesNotMatch(html,/unreported/);
});

test('statistics render one bounded page and retain known zero versus unknown',()=>{
  const players=Array.from({length:200},(_,i)=>({player_id:String(i+1),player_name:'Player '+(i+1),counters:{tries:0,metres_gained:null,carries:0,try_assists:null},tackle_success_rate:null}));
  const html=render(PlayerStatisticsView,{data:{key:'stats:1',scope:'career',season:null,observed_at:'2026-10-01T10:00:00Z',requested_count:200,missing_player_ids:[],players}});
  assert.equal((html.match(/<small class="sub-cell">#/g)||[]).length,25);
  assert.match(html,/<td>0<\/td>/);assert.match(html,/<td>—<\/td>/);assert.doesNotMatch(html,/NaN|Infinity/);
});

test('a manager profile name matching a translation key remains unchanged',()=>{
  const html=renderToStaticMarkup(React.createElement(NavigationGuardProvider,null,React.createElement(RoleWeightsEditor,{team:'123',csrf:'synthetic-session',players:[],value:{weight_profile_name:'Annuler'},onChange:()=>{},locked:false})));
  assert.match(html,/>Vos critères de sélection[^<]*Annuler<\/summary>/);
  assert.doesNotMatch(html,/Cancel/);
});
