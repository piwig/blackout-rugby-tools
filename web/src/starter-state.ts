export const starterSteps = ['mentor','treasury','transfers','staff','stadium','economy','lineup'] as const;
export type StarterStep = typeof starterSteps[number];
export type StarterValues = {completed:StarterStep[];collapsed:boolean};
export type StarterDocument = StarterValues & {team_id:string;revision:number;updated_at:string|null};
export type StarterScope = {username:string;csrf:string;teamId:string};
export type StarterState = {document:StarterDocument|null;value:StarterValues|null;pending:'load'|'save'|null;error:string;conflict:boolean;saved:boolean};
export type StarterRequest = (path:string,body?:unknown,csrf?:string)=>Promise<unknown>;

export function isStarterDirty(state:StarterState):boolean {
  const {document,value}=state;
  return !!(document&&value&&(document.collapsed!==value.collapsed||document.completed.length!==value.completed.length||document.completed.some(step=>!value.completed.includes(step))));
}

function readDocument(input:unknown,teamId:string):StarterDocument {
  const doc=input as Partial<StarterDocument>|null;
  if(!doc||typeof doc!=='object'||doc.team_id!==teamId||!Number.isSafeInteger(doc.revision)||(doc.revision??-1)<0||typeof doc.collapsed!=='boolean'||!Array.isArray(doc.completed)||doc.completed.some(step=>!starterSteps.includes(step))||(doc.updated_at!==null&&typeof doc.updated_at!=='string')){
    throw new Error('Le suivi reçu est invalide ou appartient à un autre club. Rechargez ce parcours.');
  }
  return {team_id:teamId,revision:doc.revision!,updated_at:doc.updated_at,completed:starterSteps.filter(step=>doc.completed!.includes(step)),collapsed:doc.collapsed};
}

/** One controller belongs to one authenticated club; unmount invalidates every pending response. */
export function createStarterController(scope:StarterScope,request:StarterRequest) {
  let state:StarterState={document:null,value:null,pending:null,error:'',conflict:false,saved:false};
  let generation=0;
  const listeners=new Set<()=>void>();
  const path='/workbench/starter/'+encodeURIComponent(scope.teamId);
  const publish=(next:StarterState)=>{state=next;listeners.forEach(listener=>listener())};
  const accept=(document:StarterDocument,saved:boolean)=>publish({document,value:{completed:[...document.completed],collapsed:document.collapsed},pending:null,error:'',conflict:false,saved});
  const fail=(error:unknown)=>{
    const conflict=state.conflict||(typeof error==='object'&&error!==null&&'status'in error&&error.status===409);
    publish({...state,pending:null,conflict,saved:false,error:conflict?'Une autre session a modifié ce parcours. Votre brouillon est conservé. Relisez la version enregistrée avant de continuer.':error instanceof Error?error.message:'Le suivi est indisponible. Votre brouillon est conservé.'});
  };
  const edit=(value:StarterValues)=>{if(!state.pending&&state.value)publish({...state,value,saved:false})};
  return {
    getSnapshot:()=>state,
    subscribe:(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}},
    load:async(discard=false)=>{
      if(state.pending||(!discard&&(isStarterDirty(state)||state.conflict)))return false;
      const ticket=++generation;
      publish({...state,pending:'load',error:'',saved:false});
      try{
        const result=await request(path,undefined,scope.csrf);
        if(ticket!==generation)return false;
        accept(readDocument(result,scope.teamId),false);return true;
      }catch(error){if(ticket===generation)fail(error);return false}
    },
    save:async()=>{
      if(state.pending||state.conflict||!state.document||!state.value||!isStarterDirty(state))return false;
      const body={expected_revision:state.document.revision,completed:[...state.value.completed],collapsed:state.value.collapsed};
      const ticket=++generation;
      publish({...state,pending:'save',error:'',saved:false});
      try{
        const result=await request(path,body,scope.csrf);
        if(ticket!==generation)return false;
        accept(readDocument(result,scope.teamId),true);return true;
      }catch(error){if(ticket===generation)fail(error);return false}
    },
    setCompleted:(step:StarterStep,checked:boolean)=>{
      if(!state.value||!starterSteps.includes(step))return;
      edit({...state.value,completed:starterSteps.filter(id=>id===step?checked:state.value!.completed.includes(id))});
    },
    setCollapsed:(collapsed:boolean)=>{if(state.value)edit({...state.value,collapsed})},
    stop:()=>{generation++;if(state.pending)publish({...state,pending:null})},
  };
}
