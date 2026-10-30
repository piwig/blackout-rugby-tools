import {useEffect,useRef,useState} from 'react';
import {changeDraft,createDraft,isDraftDirty,type DraftAction} from './form-draft';

/** A server baseline belongs to the loaded draft, never to an unrelated state refresh. */
export function useFormDraft<T>(saved:T,scope:string) {
  const [state,setState]=useState(()=>createDraft(saved));
  const latest=useRef(state),current=useRef(scope),mounted=useRef(false),generation=useRef(0);
  current.current=scope;
  const update=(action:DraftAction<T>)=>{const next=changeDraft(latest.current,action);latest.current=next;setState(next)};
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++}},[]);
  useEffect(()=>{update({type:'refresh',value:saved})},[saved]);
  const run=async(operation:()=>Promise<T|undefined>,replace:boolean)=>{
    if(latest.current.saving)return false;
    const ticket=++generation.current;
    update({type:'begin'});
    const active=()=>mounted.current&&current.current===scope&&generation.current===ticket;
    try{const value=await operation();if(!active())return false;update(replace?{type:'replace',value:value as T}:{type:'saved'});return true}
    catch(e){if(active()){const conflict=typeof e==='object'&&e!==null&&'status'in e&&e.status===409;update({type:'failed',conflict,error:conflict?'Une autre session a modifié ces données. Votre brouillon est conservé. Rechargez la version enregistrée pour repartir de celle-ci.':e instanceof Error?e.message:'L’enregistrement a échoué. Votre brouillon est conservé.'})}return false}
  };
  return {...state,dirty:isDraftDirty(state),edit:(value:T)=>update({type:'edit',value}),replace:(value:T)=>{if(!latest.current.saving)update({type:'replace',value})},
    save:(operation:(value:T,baseline:T)=>Promise<unknown>)=>{const {value,baseline}=latest.current;return run(async()=>{await operation(value,baseline);return undefined},false)},
    reload:(read:()=>Promise<T>)=>run(read,true)};
}
