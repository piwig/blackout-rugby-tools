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
  'before-interactive-callback':()=>void;'after-interactive-callback':()=>void;
  'unsupported-callback':()=>void;
};
type Turnstile = {render:(container:HTMLElement,options:WidgetOptions)=>string|undefined;remove:(id:string)=>void};
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
    let active=true,failed=false,verified=false,widget:string|undefined,api:Turnstile|undefined;
    let watchdog:number|undefined,renderedHost:HTMLElement|undefined;
    const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),8000);
    callback.current(null);setOptions(null);setError('');setStatus('Chargement de la vérification…');
    const clearWatchdog=()=>{if(watchdog!==undefined){clearTimeout(watchdog);watchdog=undefined}};
    const removeWidget=()=>{
      const previous=widget;widget=undefined;
      if(api&&previous!==undefined){try{api.remove(previous)}catch{/* Remove our DOM even if provider cleanup fails. */}}
      renderedHost?.replaceChildren();renderedHost=undefined;
    };
    const failure=(message:string)=>{
      if(!active||failed)return;
      failed=true;clearWatchdog();removeWidget();
      callback.current(null);setStatus('');setError(message);
    };
    const armWatchdog=()=>{
      clearWatchdog();
      if(active&&!failed&&!verified)watchdog=window.setTimeout(()=>failure('La vérification ne répond pas. Recommencez-la pour obtenir un nouveau contrôle.'),45000);
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
        if(!active)return;
        setStatus('Vérification de sécurité en cours…');
        armWatchdog();
        // loadProvider resolves from the script's onload callback; render directly.
        const host=container.current;
        if(!host?.isConnected){failure('Le formulaire a changé. Recommencez la vérification.');return}
        renderedHost=host;
        try {
          widget=api.render(host,{
            sitekey:settings.site_key,action,theme:'light',language:'fr',size:host.clientWidth<300?'compact':'flexible',
            'response-field':false,'refresh-expired':'manual',retry:'never',
            callback:token=>{
              if(!active||failed)return;
              if(!token||token.length>2048){failure('La vérification doit être recommencée.');return}
              verified=true;clearWatchdog();callback.current(token);setError('');setStatus('Vérification effectuée.');
            },
            'before-interactive-callback':()=>{
              if(!active||failed)return;
              verified=false;clearWatchdog();callback.current(null);setStatus('Terminez la vérification affichée ci-dessus.');
            },
            'after-interactive-callback':()=>{if(active&&!failed&&!verified){setStatus('Vérification de sécurité en cours…');armWatchdog()}},
            'expired-callback':()=>failure('La vérification a expiré. Recommencez-la avant d’envoyer le formulaire.'),
            'error-callback':()=>failure('La vérification a échoué. Vérifiez votre connexion puis réessayez.'),
            'timeout-callback':()=>failure('Le délai de vérification est dépassé. Recommencez-la.'),
            'unsupported-callback':()=>failure('La vérification ne fonctionne pas dans ce navigateur. Réessayez avec un navigateur à jour.'),
          });
          // A synchronous provider callback may already have failed the attempt.
          if(failed)removeWidget();
          else if(typeof widget!=='string'||!widget)failure('La vérification n’a pas démarré. Recommencez-la.');
        } catch {failure('La vérification n’a pas pu démarrer. Réessayez.')}
      } catch {
        failure('La vérification de sécurité n’a pas pu se charger. Réessayez.');
      } finally {clearTimeout(timer)}
    };
    void start();
    return()=>{
      active=false;controller.abort();clearTimeout(timer);clearWatchdog();removeWidget();
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
