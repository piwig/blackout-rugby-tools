import {navigationItems} from './navigation';

type AudienceOptions={script_url:string;website_id:string;hostname:string};
type AudiencePayload={website:string;hostname:string;url:string;title:string;referrer:string};
export type AudienceChoice={disabled:boolean;doNotTrack:boolean;storageAvailable:boolean};
declare global {interface Window {umami?:{track:(payload:AudiencePayload)=>unknown}}}

const storageKey='brt-audience-disabled';
const listeners=new Set<()=>void>();
let current:{url:string;admin:boolean}|null=null;
let lastUrl:string|null=null;
let optionsRequested=false;
let options:AudienceOptions|null=null;
let scriptState:'absent'|'loading'|'ready'|'failed'='absent';
let storageListening=false;
let sessionDisabled=false;
let storageWritable:boolean|undefined;

export function getAudienceChoice():AudienceChoice{
  let disabled=sessionDisabled,storageAvailable=true;
  try{
    const saved=window.localStorage.getItem(storageKey);
    // A readable store can still reject writes (for example quota exhaustion).
    // Probe once per page, preserving the existing choice, so a reload cannot
    // silently resume collection when a refusal could not be saved.
    if(storageWritable===undefined){window.localStorage.setItem(storageKey,saved??'0');storageWritable=true}
    storageAvailable=storageWritable;
    disabled=disabled||saved==='1'||!storageAvailable;
  }catch{storageWritable=false;disabled=true;storageAvailable=false}
  const browser=typeof window==='undefined'?undefined:window;
  const legacy=browser?.navigator as (Navigator&{msDoNotTrack?:string})|undefined;
  const doNotTrack=[legacy?.doNotTrack,legacy?.msDoNotTrack,(browser as (Window&{doNotTrack?:string})|undefined)?.doNotTrack].some(value=>value==='1'||value==='yes');
  return {disabled,doNotTrack,storageAvailable};
}

function notifyChoice(){for(const listener of listeners)listener()}
function listenToStorage(){
  if(storageListening)return;
  storageListening=true;
  window.addEventListener('storage',event=>{
    if(event.key!==storageKey&&event.key!==null)return;
    sessionDisabled=false;
    notifyChoice();
    measureCurrentView();
  });
}
export function subscribeAudienceChoice(listener:()=>void){
  listenToStorage();listeners.add(listener);
  return()=>{listeners.delete(listener)};
}
export function setAudienceDisabled(disabled:boolean){
  sessionDisabled=disabled;
  try{window.localStorage.setItem(storageKey,disabled?'1':'0')}catch{storageWritable=false;sessionDisabled=true}
  notifyChoice();
  measureCurrentView();
}

function syntheticPath(screen:string|null):string|null{
  if(screen==='login')return '/';
  if(screen==='register')return '/register';
  if(screen==='onboarding')return '/onboarding';
  return navigationItems.some(item=>item.id===screen)?'/app/'+screen:null;
}

function validateOptions(value:unknown):AudienceOptions|null{
  if(!value||typeof value!=='object')return null;
  const config=value as Record<string,unknown>;
  if(config.enabled!==true||typeof config.script_url!=='string'||typeof config.website_id!=='string'||typeof config.hostname!=='string')return null;
  if(!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(config.website_id)||!/^(?=.{1,253}$)[a-z\d](?:[a-z\d.-]*[a-z\d])?$/i.test(config.hostname))return null;
  try{
    const url=new URL(config.script_url);
    if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash)return null;
    return {script_url:url.href,website_id:config.website_id,hostname:config.hostname};
  }catch{return null}
}

function externalReferrer():string{
  try{
    const url=new URL(document.referrer);
    return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password&&url.hostname!==window.location.hostname?url.protocol+'//'+url.hostname:'';
  }catch{return ''}
}

function mayMeasure(){const choice=getAudienceChoice();return current!==null&&!current.admin&&!choice.disabled&&!choice.doNotTrack}

function measureCurrentView(){
  if(!mayMeasure())return;
  if(!optionsRequested){
    optionsRequested=true;
    // Do not use the authenticated application request helper or its headers.
    try{void fetch('/api/audience/options',{credentials:'omit'}).then(response=>response.ok?response.json():null).then(value=>{
      options=validateOptions(value);measureCurrentView();
    }).catch(()=>{})}catch{/* Offline or blocked measurement never affects the application. */}
    return;
  }
  if(!options||window.location.hostname!==options.hostname)return;
  if(scriptState==='absent'){
    scriptState='loading';
    try{
      const script=document.createElement('script');
      script.async=true;script.src=options.script_url;script.crossOrigin='anonymous';script.referrerPolicy='no-referrer';
      script.setAttribute('data-website-id',options.website_id);
      script.setAttribute('data-domains',options.hostname);
      script.setAttribute('data-auto-track','false');
      script.setAttribute('data-do-not-track','true');
      script.setAttribute('data-fetch-credentials','omit');
      script.onload=()=>{scriptState='ready';measureCurrentView()};
      script.onerror=()=>{scriptState='failed'};
      document.head.appendChild(script);
    }catch{scriptState='failed'}
    return;
  }
  if(scriptState!=='ready'||!window.umami||!current||current.url===lastUrl)return;
  lastUrl=current.url;
  try{
    // Umami 3 object mode replaces defaults. Never spread defaults or use its
    // string/callback overloads, which could include the real URL or title.
    void Promise.resolve(window.umami.track({website:options.website_id,hostname:options.hostname,url:current.url,title:'Blackout Rugby Tools',referrer:externalReferrer()})).catch(()=>{});
  }catch{/* A collector or blocker failure must remain invisible to the app. */}
}

export function setAudienceView(screen:string|null,admin:boolean){
  const url=syntheticPath(screen);
  current=url?{url,admin}:null;
  listenToStorage();
  measureCurrentView();
}
