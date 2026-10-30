import {createContext,useContext,useEffect,useLayoutEffect,useMemo,useRef,type ReactNode} from 'react';
import {createDraftRegistry} from './draft-registry';

const DraftContext=createContext<ReturnType<typeof createDraftRegistry>|null>(null);
const message='Vous avez des modifications non enregistrées. Quitter cet écran et les abandonner ?';

export function NavigationGuardProvider({children}:{children:ReactNode}){
 const registry=useMemo(createDraftRegistry,[]);
 useEffect(()=>{
  const beforeUnload=(event:BeforeUnloadEvent)=>{
   if(!registry.hasChanges())return;
   event.preventDefault();
   event.returnValue='';
  };
  window.addEventListener('beforeunload',beforeUnload);
  return()=>window.removeEventListener('beforeunload',beforeUnload);
 },[registry]);
 return <DraftContext.Provider value={registry}>{children}</DraftContext.Provider>;
}
function useRegistry(){
 const registry=useContext(DraftContext);
 if(!registry)throw new Error('NavigationGuardProvider est requis.');
 return registry;
}
/** Register the real dirty/pending state of this mounted editor. */
export function useUnsavedChanges(active:boolean):void{
 const registry=useRegistry(),owner=useRef(Symbol('editor'));
 useLayoutEffect(()=>{
  registry.set(owner.current,active);
  return()=>registry.remove(owner.current);
 },[registry,active]);
}
export function useNavigationGuard(){
 const registry=useRegistry();
 return useMemo(()=>({
  confirmLeave:()=>registry.canLeave(()=>window.confirm(message)),
 }),[registry]);
}

