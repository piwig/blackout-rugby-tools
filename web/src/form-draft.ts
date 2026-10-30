export type DraftState<T> = {value:T;baseline:T;saving:boolean;error:string;conflict:boolean};
export type DraftAction<T> = {type:'edit'|'replace'|'refresh';value:T}|{type:'begin'|'saved'}|{type:'failed';error:string;conflict:boolean};
type FormScope = {user:{username:string};csrf:string;current_team:{id:string}};
export function sameFormScope(expected:FormScope,actual:FormScope):boolean {
  return expected.user.username===actual.user?.username&&expected.csrf===actual.csrf&&expected.current_team.id===actual.current_team?.id;
}
export function createDraft<T>(value:T):DraftState<T> {return {value:structuredClone(value),baseline:structuredClone(value),saving:false,error:'',conflict:false}}
export function sameFormValue(a:unknown,b:unknown):boolean {
  if(a===b)return true;
  if(a===null||b===null||typeof a!=='object'||typeof b!=='object')return false;
  if(Array.isArray(a)!==Array.isArray(b))return false;
  const first=a as Record<string,unknown>,second=b as Record<string,unknown>,keys=Object.keys(first);
  return keys.length===Object.keys(second).length&&keys.every(key=>Object.hasOwn(second,key)&&sameFormValue(first[key],second[key]));
}
export function isDraftDirty<T>(state:DraftState<T>):boolean {return !sameFormValue(state.value,state.baseline)}
export function changeDraft<T>(state:DraftState<T>,action:DraftAction<T>):DraftState<T> {
  switch(action.type){
    case 'edit':return state.saving?state:{...state,value:action.value};
    case 'begin':return {...state,saving:true,error:''};
    case 'saved':return state.saving?createDraft(state.value):state;
    case 'failed':return {...state,saving:false,error:action.error,conflict:action.conflict};
    case 'refresh':return state.saving||state.conflict||isDraftDirty(state)?state:createDraft(action.value);
    case 'replace':return createDraft(action.value);
  }
}
