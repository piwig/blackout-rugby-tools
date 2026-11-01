import {useId,useState,type ReactNode} from 'react';
import {tr} from './i18n';
import {useNavigationGuard} from './navigation-guard';
import './manager-workspace.css';

type WorkspaceTab={id:string;label:string;description:string;content:ReactNode};

/** Only the selected editor is mounted; leaving it uses the shared draft guard. */
export function ManagerWorkspace({label,tabs,busy=false}:{label:string;tabs:WorkspaceTab[];busy?:boolean}){
  const prefix=useId(),[selected,setSelected]=useState(tabs[0].id),{confirmLeave}=useNavigationGuard();
  const current=tabs.find(tab=>tab.id===selected)??tabs[0];
  const choose=(id:string)=>{if(id===current.id||busy||!confirmLeave())return false;setSelected(id);return true};
  return <div className="manager-workspace">
    <div className="workspace-tabs" role="tablist" aria-label={tr(label)}>{tabs.map((tab,index)=><button key={tab.id} id={prefix+'-'+tab.id} type="button" role="tab" aria-selected={tab.id===current.id} aria-controls={prefix+'-panel'} tabIndex={tab.id===current.id?0:-1} disabled={busy} onClick={()=>choose(tab.id)} onKeyDown={event=>{
      const delta=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0;
      const target=event.key==='Home'?0:event.key==='End'?tabs.length-1:delta?(index+delta+tabs.length)%tabs.length:-1;
      if(target<0)return;event.preventDefault();if(choose(tabs[target].id))document.getElementById(prefix+'-'+tabs[target].id)?.focus();
    }}>{tr(tab.label)}</button>)}</div>
    <p className="workspace-intro">{tr(current.description)}</p>
    <div id={prefix+'-panel'} role="tabpanel" aria-labelledby={prefix+'-'+current.id} key={current.id}>{current.content}</div>
  </div>;
}
