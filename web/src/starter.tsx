import {tr} from './i18n';
import {useEffect,useState,useSyncExternalStore} from 'react';
import {ArrowUpRight,ChevronDown,ChevronUp,FlagTriangleRight,LockKeyhole,RefreshCw,Save} from 'lucide-react';
import {request,type Actions} from './App';
import {useUnsavedChanges} from './navigation-guard';
import {createStarterController,isStarterDirty,type StarterState,type StarterStep} from './starter-state';
import './starter.css';

const steps:{id:StarterStep;title:string;advice:string;page:string;action:string}[]=[
  {id:'mentor',title:'Trouver un mentor',advice:'Choisissez librement un manager expérimenté avec qui échanger. Faites relire vos premières décisions et les règles de votre ligue.',page:'guide',action:'Retrouver les repères'},
  {id:'treasury',title:'Préserver la trésorerie',advice:'La dotation de départ évoquée est de 300 000 unités virtuelles : ce n’est pas votre solde actuel. Consultez les finances Classic et gardez une réserve avant toute dépense.',page:'stadium',action:'Comparer mon budget'},
  {id:'transfers',title:'Différer les transferts',advice:'Au démarrage, n’achetez pas de joueurs. Observez d’abord votre effectif et préparez un premier XV pour repérer les besoins réels.',page:'optimization',action:'Étudier mon effectif'},
  {id:'staff',title:'Limiter le staff initial',advice:'Priorité au recruteur de l’académie et au manager. Évitez les adjoints au démarrage ; vérifiez les postes et les salaires dans Classic avant de recruter.',page:'guide',action:'Relire les premiers pas'},
  {id:'stadium',title:'Dimensionner le stade',advice:'Étudiez la répartition proposée : 22 % debout, 39 % assis découvert, 30 % assis couvert, 8 % abonnés et 1 % loges. Comparez votre capacité cible au devis réel et à votre réserve.',page:'stadium',action:'Préparer un scénario'},
  {id:'economy',title:'Vérifier l’échéance économique',advice:'Le repère transmis est « mardi à minuit ». Vérifiez le jour exact et le fuseau dans le calendrier du jeu avant de planifier une dépense ou un rappel.',page:'season',action:'Ouvrir mon calendrier'},
  {id:'lineup',title:'Préparer une équipe-type',advice:'Avec vos joueurs disponibles, comparez les postes, l’énergie et les compétences connues. Préparez votre XV, puis vérifiez la composition dans Classic.',page:'optimization',action:'Préparer mon XV'},
];

/** The key isolates drafts immediately when the manager, authenticated session or club changes. */
export function StarterCard(props:Pick<Actions,'d'|'go'|'busy'>) {
  const {d}=props;
  return <StarterClubCard key={JSON.stringify([d.user.username,d.csrf,d.current_team.id])} {...props}/>;
}

function StarterClubCard({d,go,busy}:Pick<Actions,'d'|'go'|'busy'>) {
  const [controller]=useState(()=>createStarterController({username:d.user.username,csrf:d.csrf,teamId:d.current_team.id},request));
  const state=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  useUnsavedChanges(isStarterDirty(state)||state.pending==='save');
  useEffect(()=>{void controller.load();return()=>controller.stop()},[controller]);
  const reload=()=>{
    if(busy||state.pending)return;
    if((isStarterDirty(state)||state.conflict)&&!window.confirm(tr('Relire la version enregistrée abandonnera votre brouillon de démarrage. Continuer ?')))return;
    void controller.load(true);
  };
  return <StarterPanel clubName={d.current_team.name} state={state} busy={busy} onToggle={()=>controller.setCollapsed(!state.value?.collapsed)} onComplete={controller.setCompleted} onSave={()=>{if(!busy)void controller.save()}} onReload={reload} go={go}/>;
}

type PanelProps={clubName:string;state:StarterState;busy:boolean;onToggle:()=>void;onComplete:(step:StarterStep,checked:boolean)=>void;onSave:()=>void;onReload:()=>void;go:(page:string)=>void};

export function StarterPanel({clubName,state,busy,onToggle,onComplete,onSave,onReload,go}:PanelProps) {
  const {document,value,pending,error,conflict,saved}=state;
  const locked=busy||!!pending,collapsed=value?.collapsed??false,dirty=isStarterDirty(state);
  const status=pending==='load'?'Lecture du suivi privé…':pending==='save'?'Enregistrement en cours…':dirty?'Modifications non enregistrées : cases et affichage.':saved?'Votre suivi a été enregistré pour ce club.':error?'Le suivi n’a pas pu être actualisé.':document?'Votre suivi est à jour.':'Chargement du parcours…';
  return <section className={'card starter-card'+(collapsed?' starter-collapsed':'')} aria-labelledby="starter-heading">
    <header className="starter-header">
      <span className="starter-emblem" aria-hidden="true"><FlagTriangleRight size={25}/></span>
      <div className="starter-title"><span className="eyebrow">{tr("LES PREMIERS REPÈRES DU CLUB")}</span><h2 id="starter-heading">{tr("Bien démarrer")}</h2><p>{tr("Prendre les commandes de ")}{clubName}{tr(", une décision à la fois.")}</p></div>
      <button type="button" className="button secondary starter-disclosure" aria-expanded={!collapsed} aria-controls="starter-content" disabled={locked||!value} onClick={onToggle}>{collapsed?<ChevronDown size={17} aria-hidden="true"/>:<ChevronUp size={17} aria-hidden="true"/>}{collapsed?tr("Déplier"):tr("Replier")}<span className="sr-only">{tr(" le parcours Bien démarrer")}</span></button>
    </header>
    <div className="starter-summary">
      <span><LockKeyhole size={14} aria-hidden="true"/>{tr("Suivi déclaratif privé · ce club")}</span>
      {value&&<div className="starter-progress"><span><strong>{value.completed.length} / 7</strong>{tr(" repères pris en compte")}</span><progress value={value.completed.length} max={7} aria-label={tr("Repères déclarés pris en compte")}/></div>}
    </div>
    <div id="starter-content" hidden={collapsed}>
      {!collapsed&&value&&<>
        <div className="starter-context"><p>{tr("Conseils de Franck · ")}<time dateTime="2026-10-31">{tr("31 octobre 2026")}</time>{tr(". À adapter à votre club et aux règles en vigueur.")}</p><p>{tr("Les cases « Pris en compte » sont vos déclarations. Elles ne confirment aucune action dans Classic.")}</p></div>
        <ol className="starter-steps">{steps.map((step,index)=><li key={step.id} className={value.completed.includes(step.id)?'starter-acknowledged':''}>
          <span className="starter-step-number" aria-hidden="true">{String(index+1).padStart(2,'0')}</span>
          <div className="starter-step-content"><h3 id={'starter-title-'+step.id}>{tr(step.title)}</h3><p>{tr(step.advice)}</p>
            <div className="starter-step-actions"><label className="starter-check"><input type="checkbox" aria-labelledby={'starter-label-'+step.id+' starter-title-'+step.id} checked={value.completed.includes(step.id)} disabled={locked} onChange={event=>onComplete(step.id,event.target.checked)}/><span id={'starter-label-'+step.id}>{tr("Pris en compte")}</span></label><button type="button" className="text-button" disabled={locked} onClick={()=>go(step.page)}>{tr(step.action)}<ArrowUpRight size={14} aria-hidden="true"/></button></div>
          </div>
        </li>)}</ol>
        <p className="starter-data-note">{tr("Les données du jeu vous manquent ? ")}<button type="button" className="text-button" disabled={locked} onClick={()=>go('settings')}>{tr("Connexion & données")}<ArrowUpRight size={14} aria-hidden="true"/></button></p>
      </>}
    </div>
    {error&&<div className="starter-error" role="alert"><p>{tr(error)}</p>{conflict&&<small>{tr("Votre sélection reste visible en dépliant le parcours. La relecture demande confirmation avant de la remplacer.")}</small>}</div>}
    <footer className="starter-footer"><div><p className={saved?'starter-saved':''} role="status" aria-live="polite">{tr(status)}</p>{collapsed&&value&&<small>{tr("Vous pouvez retrouver les sept étapes ici à tout moment.")}</small>}</div><div className="starter-buttons">
      {value&&<button type="button" className="button primary" disabled={locked||conflict||!dirty} onClick={onSave}><Save size={16} aria-hidden="true"/>{pending==='save'?tr("Enregistrement…"):tr("Enregistrer mon suivi")}</button>}
      <button type="button" className="text-button" disabled={locked} onClick={onReload}><RefreshCw size={14} aria-hidden="true"/>{conflict?tr("Relire la version enregistrée"):error&&!value?tr("Réessayer"):tr("Recharger le suivi")}</button>
    </div></footer>
  </section>;
}
