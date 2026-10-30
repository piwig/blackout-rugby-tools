import {useEffect, useId, useRef, useState} from 'react';
import {RefreshCw, ShieldCheck} from 'lucide-react';
import './antibot.css';

type Action = 'register'|'login'|'contact';
type Options = {enabled:boolean;site_key:string};
type WidgetOptions = {
  sitekey:string;action:Action;theme:'light';language:'fr';size:'flexible'|'compact';
  'response-field':false;'refresh-expired':'manual';retry:'never';
  callback:(token:string)=>void;'expired-callback':()=>void;
  'error-callback':()=>void;'timeout-callback':()=>void;
};
type Turnstile = {render:(container:HTMLElement,options:WidgetOptions)=>string;remove:(id:string)=>void};
declare global {interface Window {turnstile?:Turnstile;brtTurnstileReady?:()=>void}}
let providerPromise:Promise<Turnstile>|null=null;

function loadProvider():Promise<Turnstile> {
  if(providerPromise)return providerPromise;
  if(window.turnstile)return Promise.resolve(window.turnstile);
  providerPromise=new Promise<Turnstile>((resolve,reject)=>{
    const script=document.createElement('script');
    let settled=false;
    const fail=()=>{
      if(settled)return;settled=true;clearTimeout(timer);script.remove();
      reject(new Error('La vérification de sécurité n’a pas pu se charger.'));
    };
    const timer=window.setTimeout(fail,15000);
    window.brtTurnstileReady=()=>{
      if(settled)return;
      if(!window.turnstile){fail();return}
      settled=true;clearTimeout(timer);resolve(window.turnstile);
    };
    script.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=brtTurnstileReady';
    script.async=true;script.defer=true;script.onerror=fail;
    document.head.appendChild(script);
  }).catch(error=>{providerPromise=null;throw error});
  return providerPromise;
}

/** null blocks submission; '' means the server explicitly disabled CAPTCHA. */
export function AntiBot({action,onToken,resetKey=0}:{action:Action;onToken:(token:string|null)=>void;resetKey?:number|string}) {
  const id=useId(),container=useRef<HTMLDivElement>(null),callback=useRef(onToken);callback.current=onToken;
  const [options,setOptions]=useState<Options|null>(null),[error,setError]=useState(''),[status,setStatus]=useState('Chargement de la vérification…'),[retry,setRetry]=useState(0);
  useEffect(()=>{
    let active=true,widget:string|undefined,api:Turnstile|undefined;
    const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),8000);
    callback.current(null);setOptions(null);setError('');setStatus('Chargement de la vérification…');
    const failure=(message:string)=>{
      if(!active)return;
      callback.current(null);setStatus('');setError(message);
    };
    const start=async()=>{
      try {
        const response=await fetch('/api/security/options',{signal:controller.signal,cache:'no-store'});
        if(!response.ok)throw new Error();
        const configuration:unknown=await response.json();
        if(!configuration||typeof configuration!=='object'||typeof (configuration as Options).enabled!=='boolean'||typeof (configuration as Options).site_key!=='string')throw new Error();
        clearTimeout(timer);
        if(!active)return;
        const settings=configuration as Options;setOptions(settings);
        if(!settings.enabled){callback.current('');setStatus('');return}
        if(!settings.site_key){failure('La vérification de sécurité est momentanément indisponible.');return}
        api=await loadProvider();
        if(!active||!container.current)return;
        setStatus('Vérification de sécurité en cours…');
        widget=api.render(container.current,{
          sitekey:settings.site_key,action,theme:'light',language:'fr',size:container.current.clientWidth<300?'compact':'flexible',
          'response-field':false,'refresh-expired':'manual',retry:'never',
          callback:token=>{
            if(!active)return;
            if(!token||token.length>2048){failure('La vérification doit être recommencée.');return}
            callback.current(token);setError('');setStatus('Vérification effectuée.');
          },
          'expired-callback':()=>failure('La vérification a expiré. Recommencez-la avant d’envoyer le formulaire.'),
          'error-callback':()=>failure('La vérification a échoué. Vérifiez votre connexion puis réessayez.'),
          'timeout-callback':()=>failure('Le délai de vérification est dépassé. Recommencez-la.'),
        });
      } catch {
        failure('La vérification de sécurité n’a pas pu se charger. Réessayez.');
      } finally {clearTimeout(timer)}
    };
    void start();
    return()=>{
      active=false;controller.abort();clearTimeout(timer);
      if(api&&widget!==undefined){try{api.remove(widget)}catch{/* The provider may already have removed its frame. */}}
    };
  },[action,resetKey,retry]);
  if(options?.enabled===false)return null;
  return <div className="anti-bot" role="group" aria-labelledby={id}>
    <div className="anti-bot-label" id={id}><ShieldCheck size={16} aria-hidden="true"/>Vérification de sécurité</div>
    <div className="anti-bot-widget" ref={container}/>
    {status&&<p className="anti-bot-status" role="status" aria-live="polite">{status}</p>}
    {error&&<><p className="anti-bot-error" role="alert">{error}</p><button type="button" className="anti-bot-retry" onClick={()=>{callback.current(null);setRetry(value=>value+1)}}><RefreshCw size={14} aria-hidden="true"/>Recommencer la vérification</button></>}
  </div>;
}
