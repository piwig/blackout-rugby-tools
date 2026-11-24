import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require=createRequire(import.meta.url);
const sourceUrl=new URL('../src/audience.ts',import.meta.url);
const config={enabled:true,script_url:'https://stats.example/script.js',website_id:'fbe43dbb-6413-40a9-a833-97cb73779123',hostname:'brt.example'};
async function settle(){for(let i=0;i<15;i++)await Promise.resolve()}

// Only browser I/O is replaced. The production singleton validates options,
// constructs payloads, owns preferences and arbitrates all asynchronous work.
function audienceHarness({dnt=false,stored=null,storageDenied=false,writesDenied=false,referrer='https://external.example/a?secret=1#private'}={}){
  assert.ok(existsSync(sourceUrl),'The optional audience module must exist');
  const sent=[],scripts=[],requests=[],writes=[],events=new Map();
  let saved=stored,denied=storageDenied;
  const storage={getItem(){if(denied)throw Error('Storage denied');return saved},setItem(key,value){if(denied||writesDenied)throw Error('Storage denied');saved=value;writes.push([key,value])}};
  const window={location:{origin:'https://brt.example',hostname:'brt.example',href:'https://brt.example/?token=secret#club'},navigator:{doNotTrack:dnt?'1':null},localStorage:storage,
    addEventListener(name,listener){events.set(name,listener)},removeEventListener(name){events.delete(name)}};
  const document={referrer,title:'PRIVATE MANAGER / CLUB',createElement(){return {attributes:{},setAttribute(key,value){this.attributes[key]=value}}},head:{appendChild(script){scripts.push(script)}}};
  const artifact={exports:{}};
  const compiled=ts.transpileModule(readFileSync(sourceUrl,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const context={module:artifact,exports:artifact.exports,require:id=>id==='./navigation'?require('../src/navigation.ts'):require(id),window,document,navigator:window.navigator,localStorage:storage,URL,
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))};
  vm.runInNewContext(compiled,context);
  return {api:artifact.exports,sent,scripts,requests,writes,window,document,
    async options(value=config){requests.at(-1).resolve({ok:true,json:async()=>value});await settle()},
    async loaded(){window.umami={track:payload=>{sent.push(JSON.parse(JSON.stringify(payload)));return Promise.resolve()}};scripts.at(-1).onload();await settle()},
    denyStorage(){denied=true},externalChoice(value){saved=value;events.get('storage')?.({key:'brt-audience-disabled'})},
  };
}

test('only a closed synthetic payload reaches Umami, with no private page defaults',async()=>{
  const h=audienceHarness();
  h.api.setAudienceView('home',false);
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/audience/options');
  assert.equal(h.requests[0].options.credentials,'omit');
  await h.options();
  assert.equal(h.scripts[0].attributes['data-auto-track'],'false');
  assert.equal(h.scripts[0].attributes['data-fetch-credentials'],'omit');
  assert.equal(h.scripts[0].attributes['data-domains'],'brt.example');
  assert.equal(h.scripts[0].referrerPolicy,'no-referrer');
  await h.loaded();
  assert.deepEqual(h.sent,[{website:config.website_id,hostname:'brt.example',url:'/app/home',title:'Blackout Rugby Tools',referrer:'https://external.example'}]);
});

test('a copied or preview hostname cannot load the tracker or send BRT views',async()=>{
  const preview=audienceHarness();preview.api.setAudienceView('home',false);await preview.options({...config,hostname:'production.example'});
  assert.equal(preview.scripts.length,0);assert.equal(preview.sent.length,0);
  const changed=audienceHarness();changed.api.setAudienceView('home',false);await changed.options();changed.window.location.hostname='preview.example';await changed.loaded();
  assert.equal(changed.sent.length,0);
});

test('internal, malformed and non-HTTP referrers never expose page details',async()=>{
  for(const referrer of ['https://brt.example/private?account=1','http://brt.example/private','https://brt.example:8443/private','not a URL','file:///private','javascript:secret','https://name:password@external.example/private']){
    const h=audienceHarness({referrer});h.api.setAudienceView('login',false);await h.options();await h.loaded();
    assert.equal(h.sent[0].referrer,'');assert.equal(h.sent[0].url,'/');
  }
});

test('external referrers retain their hostname without an unnecessary port',async()=>{
  const h=audienceHarness({referrer:'https://external.example:8443/private?secret=1'});
  h.api.setAudienceView('login',false);await h.options();await h.loaded();
  assert.equal(h.sent[0].referrer,'https://external.example');
});

test('unknown and inherited object names never become measured screens',async()=>{
  for(const screen of [null,'initial','error','private-account-name','__proto__','constructor','home?account=1']){
    const h=audienceHarness();h.api.setAudienceView(screen,false);await settle();
    assert.equal(h.requests.length,0);assert.equal(h.sent.length,0);
  }
});

test('consecutive views deduplicate across StrictMode cleanup while A/B/A counts three',async()=>{
  const h=audienceHarness();
  h.api.setAudienceView('home',false);h.api.setAudienceView(null,false);h.api.setAudienceView('home',false);
  await h.options();await h.loaded();
  h.api.setAudienceView('home',false);h.api.setAudienceView('home',false);
  h.api.setAudienceView('squad',false);h.api.setAudienceView('home',false);await settle();
  assert.deepEqual(h.sent.map(view=>view.url),['/app/home','/app/squad','/app/home']);
  assert.equal(h.requests.length,1);assert.equal(h.scripts.length,1);
});

test('registration and onboarding use fixed public paths',async()=>{
  const h=audienceHarness();h.api.setAudienceView('register',false);await h.options();await h.loaded();
  h.api.setAudienceView('onboarding',false);await settle();
  assert.deepEqual(h.sent.map(view=>view.url),['/register','/onboarding']);
});

test('administrators, DNT and a saved local opt-out prevent even tracker loading',async()=>{
  for(const settings of [{admin:true},{dnt:true},{stored:'1'},{storageDenied:true}]){
    const h=audienceHarness(settings);h.api.setAudienceView('home',settings.admin??false);await settle();
    assert.equal(h.requests.length,0);assert.equal(h.scripts.length,0);assert.equal(h.sent.length,0);
  }
});

test('local opt-out persists without an account key and cannot override DNT',async()=>{
  const h=audienceHarness();h.api.setAudienceDisabled(true);h.api.setAudienceView('home',false);await settle();
  assert.deepEqual(h.writes.at(-1),['brt-audience-disabled','1']);
  assert.ok(h.writes.every(([key])=>key==='brt-audience-disabled'));assert.equal(h.requests.length,0);
  h.api.setAudienceDisabled(false);await h.options();await h.loaded();assert.equal(h.sent.length,1);
  const dnt=audienceHarness({dnt:true});dnt.api.setAudienceDisabled(false);dnt.api.setAudienceView('home',false);await settle();
  assert.equal(dnt.requests.length,0);assert.equal(dnt.api.getAudienceChoice().doNotTrack,true);
});

test('readable but unwritable storage stays closed across a page reload',async()=>{
  const h=audienceHarness({writesDenied:true});
  h.api.setAudienceDisabled(true);h.api.setAudienceView('home',false);await settle();
  assert.equal(h.api.getAudienceChoice().storageAvailable,false);
  assert.equal(h.requests.length,0);
  const reloaded=audienceHarness({writesDenied:true});
  reloaded.api.setAudienceView('home',false);await settle();
  assert.equal(reloaded.api.getAudienceChoice().disabled,true);
  assert.equal(reloaded.requests.length,0);
});

test('late options revalidate opt-out, administrator and current screen before loading',async()=>{
  for(const transition of [h=>h.api.setAudienceDisabled(true),h=>h.api.setAudienceView('home',true),h=>h.api.setAudienceView(null,false)]){
    const h=audienceHarness();h.api.setAudienceView('login',false);transition(h);await h.options();
    assert.equal(h.scripts.length,0);assert.equal(h.sent.length,0);
  }
  const h=audienceHarness();h.api.setAudienceView('login',false);h.api.setAudienceView('squad',false);await h.options();await h.loaded();
  assert.deepEqual(h.sent.map(view=>view.url),['/app/squad']);
});

test('late script completion revalidates opt-out, admin, DNT and unknown screens',async()=>{
  for(const transition of [h=>h.api.setAudienceDisabled(true),h=>h.api.setAudienceView('home',true),h=>{h.window.navigator.doNotTrack='1'},h=>h.api.setAudienceView('PRIVATE',false),h=>h.externalChoice('1')]){
    const h=audienceHarness();h.api.setAudienceView('login',false);await h.options();transition(h);await h.loaded();
    assert.equal(h.sent.length,0);
  }
  const h=audienceHarness();h.api.setAudienceView('login',false);await h.options();h.api.setAudienceView('contact',false);await h.loaded();
  assert.deepEqual(h.sent.map(view=>view.url),['/app/contact']);
});

test('unavailable or malformed options and failed scripts stay optional',async()=>{
  for(const value of [{enabled:false},{enabled:true},{...config,script_url:'http://stats.example/script.js'},{...config,script_url:'https://name:secret@stats.example/script.js'},{...config,script_url:'https://stats.example/script.js?secret=1'},{...config,website_id:'private-user'},{...config,hostname:'brt.example/private'}]){
    const h=audienceHarness();h.api.setAudienceView('home',false);await h.options(value);
    assert.equal(h.scripts.length,0);assert.equal(h.sent.length,0);
  }
  const unavailable=audienceHarness();unavailable.api.setAudienceView('home',false);unavailable.requests[0].reject(Error('offline'));await settle();
  assert.doesNotThrow(()=>unavailable.api.setAudienceView('squad',false));assert.equal(unavailable.requests.length,1);
  const broken=audienceHarness();broken.api.setAudienceView('home',false);await broken.options();broken.scripts[0].onerror();await settle();
  assert.doesNotThrow(()=>broken.api.setAudienceView('squad',false));assert.equal(broken.scripts.length,1);assert.equal(broken.sent.length,0);
});

test('storage loss and rejected collector requests leave navigation and choice functional',async()=>{
  const h=audienceHarness();h.api.setAudienceView('home',false);await h.options();await h.loaded();
  h.window.umami.track=()=>Promise.reject(Error('blocked collector'));
  assert.doesNotThrow(()=>h.api.setAudienceView('squad',false));await settle();
  h.denyStorage();assert.doesNotThrow(()=>h.api.setAudienceDisabled(true));
  assert.equal(h.api.getAudienceChoice().disabled,true);assert.equal(h.api.getAudienceChoice().storageAvailable,false);
  assert.doesNotThrow(()=>h.api.setAudienceView('matches',false));await settle();assert.equal(h.sent.length,1);
});
