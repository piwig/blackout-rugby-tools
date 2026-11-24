import {useEffect,useLayoutEffect,useState} from 'react';
import {getAudienceChoice,setAudienceDisabled,setAudienceView,subscribeAudienceChoice} from './audience';
import {tr} from './i18n';
import './audience.css';

export function useAudienceView(screen:string|null,admin:boolean){
  useLayoutEffect(()=>{
    setAudienceView(screen,admin);
    return()=>setAudienceView(null,false);
  },[screen,admin]);
}

export function AudiencePreferences(){
  const [choice,setChoice]=useState(getAudienceChoice);
  useEffect(()=>{
    const update=()=>setChoice(getAudienceChoice());
    const unsubscribe=subscribeAudienceChoice(update);update();return unsubscribe;
  },[]);
  return <details className="audience-preferences">
    <summary>{tr('Audience et confidentialité')}</summary>
    <p>{tr('Pour comprendre les visites, BRT mesure les rubriques consultées et le site de provenance, sans cookie ni données de votre compte. Umami traite techniquement les requêtes, IP et User-Agent pour produire des statistiques agrégées.')}</p>
    <label><input type="checkbox" checked={!choice.disabled&&!choice.doNotTrack} disabled={choice.doNotTrack||!choice.storageAvailable} onChange={event=>setAudienceDisabled(!event.currentTarget.checked)}/><span>{tr('Autoriser la mesure d’audience')}</span></label>
    <p>{tr('Ce choix s’applique à ce navigateur. Les administrateurs connectés sont exclus.')}</p>
    {choice.doNotTrack&&<p role="status">{tr('Do Not Track est activé : aucune mesure n’est envoyée.')}</p>}
    {!choice.storageAvailable&&<p role="status">{tr('Le stockage local est indisponible : la mesure reste désactivée.')}</p>}
  </details>;
}
