import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const runtime=require('../src/i18n/runtime.ts'),models=require('../src/market-model.ts');
runtime.installCatalogs(Object.fromEntries(['fr','en','es','it'].map(locale=>[locale,JSON.parse(readFileSync(new URL('../src/i18n/locales/'+locale+'.json',import.meta.url),'utf8'))])));
const candidate={...models.emptyCandidate('a'.repeat(32)),name:'Annuler',classic_id:'123',role:'Centre',price:500,fees:20,weekly_salary:50,skills:{stamina:10,handling:10,attack:12,defense:11,technique:8,strength:8,jumping:null,speed:12,agility:10,kicking:null}};
const scenario={id:candidate.id,status:'unknown',missing_fields:['complete'],warnings:['budget_incomplete'],initial_cost:520,four_week_cost:720,immediate_headroom:-20,projected_cash:580,projected_headroom:480,purchase_ceiling:null,comparison:{role:'Centre',score:10.5,known_skills:8,missing_skills:[],squad_known:1,squad_total:2,squad_best:11,squad_average:11,delta_best:-0.5,rank:2}};
const draft={plan:{cash:700,weekly_income:200,weekly_expenses:100,reserve:100,committed_bids:100,complete:false,observed_at:'2026-10-31T09:00:00+01:00'},candidates:[candidate],investments:[{...models.emptyInvestment('b'.repeat(32)),name:'Projet fictif',initial_cost:0,weekly_cost:null}]};
const analysis={horizon_weeks:4,confirmed:false,missing_fields:['complete'],warnings:['budget_incomplete'],base:{weekly_net:100,projected_cash:1000,immediate_headroom:500,projected_headroom:900,purchase_ceiling:null},squad:{snapshot_id:1,observed_at:'2026-10-31T08:00:00Z',total:2,criteria_method:'weighted-average-v1'},candidates:[scenario],investments:[{...scenario,id:draft.investments[0].id,initial_cost:0,four_week_cost:null}]};
const document={revision:1,updated_at:'2026-10-31T10:00:00Z',...draft,analysis};

function fixture(locale='fr',analysisSnapshot=1){
  runtime.setLocale(locale);let cursor=0;
  const values=[document,draft,{...analysis,squad:{...analysis.squad,snapshot_id:analysisSnapshot}},analysisSnapshot,false,'',false,''];
  const react={...React,useState:initial=>[cursor<values.length?values[cursor++]:typeof initial==='function'?initial():initial,()=>{}],useRef:initial=>({current:initial}),useEffect(){}};
  const artifact={exports:{}};
  const load=id=>{
    if(id==='react')return react;
    if(id==='./App')return {request:()=>{throw Error('SSR must not request data')}};
    if(id==='./i18n')return runtime;
    if(id==='./types')return {fmt:value=>value??'—',date:value=>value||'—',labels:{stamina:'Endurance',handling:'Dextérité',attack:'Attaque',defense:'Défense',technique:'Technique',strength:'Force',jumping:'Saut',speed:'Vitesse',agility:'Agilité',kicking:'Jeu au pied'}};
    if(id==='./navigation-guard')return {useUnsavedChanges(){}};
    if(id==='./market-model')return models;
    if(id==='./role-weights-model')return require('../src/role-weights-model.ts');
    if(id.endsWith('.css'))return {};
    return require(id);
  };
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/market.tsx',import.meta.url),'utf8')+'\nexport {MarketPanel,Scenario};',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:artifact,exports:artifact.exports,require:load,Date,JSON,crypto});
  const props={busy:false,onRefresh:async()=>{},d:{user:{username:'synthetic'},csrf:'synthetic',current_team:{id:'1'},squad_source:{id:1,observed_at:'2026-10-31T08:00:00Z'},squad:[{id:'42',name:'Senior fictif',stamina:12},{id:'43',name:'Autre senior',stamina:null}]}};
  return {html:renderToStaticMarkup(React.createElement(artifact.exports.MarketPanel,props)),scenario:artifact.exports.Scenario};
}
test('unknown affordability stays neutral, negative cash stays visible and zero differs from blank',()=>{
  const {html}=fixture();
  assert.match(html,/status-unknown/);assert.doesNotMatch(html,/status-affordable/);
  assert.match(html,/is-negative[^]*?<strong>-20<\/strong>/);
  assert.match(html,/Prix maximum du joueur<\/span><strong>—<\/strong>/);
  assert.match(html,/Coût initial<input[^>]*value="0"/);
  assert.match(html,/Coût supplémentaire \/ semaine<input[^>]*value=""/);
  assert.match(html,/name="cash"[^>]*value="700"/);
  assert.match(html,/Effectif comparable : 1\/2 joueurs/);
});
test('candidate names remain source data and all four locales render the planning boundary',()=>{
  for(const [locale,heading,phrase] of [['fr','Les joueurs à étudier','Aucun joueur n’est acheté ou vendu'],['en','Players to consider','No player is bought or sold'],['es','Jugadores a estudiar',''],['it','Giocatori da valutare','']]){
    const {html}=fixture(locale);
    assert.match(html,/<h3>Annuler<\/h3>/);
    assert.match(html,/https:\/\/www.blackoutrugby.com\/game\/club.squad.php#player=123/);
    assert.ok(!html.includes('invalid_market_number'));
    if(phrase)assert.ok(html.includes(phrase));
    if(locale==='fr'||locale==='en')assert.ok(html.includes(heading));
  }
});
test('forms expose associated labels, required names, limits and table headers',()=>{
  const {html}=fixture();
  assert.match(html,/<label>Nom du candidat<input required="" maxLength="100"/);
  assert.match(html,/<label>Identifiant Classic \(facultatif\)<input[^>]*pattern="\[1-9\]\[0-9\]\{0,14\}"/);
  assert.match(html,/<label>Date du relevé<input type="datetime-local"/);
  assert.match(html,/<th scope="col">Compétence<\/th>/);
  assert.match(html,/aria-label="Retirer le candidat Annuler"/);
  assert.match(html,/aria-label="Endurance du candidat Annuler"/);
});
test('different squad snapshots hide old references and role indices while retaining budget results',()=>{
  const {html}=fixture('fr',2);
  assert.doesNotMatch(html,/Meilleur indice de l’effectif|Senior de référence \(facultatif\)|Senior fictif|Effectif observé le/);
  assert.match(html,/Actualiser l’effectif et recalculer/);
  assert.match(html,/Décaissement initial<\/span><strong>520<\/strong>/);
  assert.match(html,/aria-label="Endurance du candidat Annuler"/);
});

if(process.env.BRT_MARKET_RENDER_OUTPUT){
  const output=path.resolve(process.env.BRT_MARKET_RENDER_OUTPUT);mkdirSync(path.dirname(output),{recursive:true});
  const css=['styles.css','rugby-design.css','market.css'].map(file=>readFileSync(new URL('../src/'+file,import.meta.url),'utf8')).join('\n');
  writeFileSync(output,'<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mercato — données fictives</title><style>'+css+'body{padding:24px;max-width:1200px;margin:auto}</style><body>'+fixture().html+'</body></html>');
}
