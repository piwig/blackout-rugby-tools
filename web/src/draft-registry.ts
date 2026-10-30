/** One entry per mounted editor; no draft content is persisted here. */
export function createDraftRegistry(){
 const entries=new Set<symbol>();
 return {
  set(owner:symbol,active:boolean){if(active)entries.add(owner);else entries.delete(owner)},
  remove(owner:symbol){entries.delete(owner)},
  hasChanges(){return entries.size>0},
  canLeave(confirm:()=>boolean){return entries.size===0||confirm()},
 };
}

