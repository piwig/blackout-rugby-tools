import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Calculator,ClipboardList,Plus,RefreshCw,Save,ShieldCheck,Trash2,Wallet} from 'lucide-react';
import {request,type Actions} from './App';
import {tr,localeTag} from './i18n';
import {date,fmt,labels} from './types';
import {useUnsavedChanges} from './navigation-guard';
import {roleNames,skillKeys} from './role-weights-model';
import {classicPlayerUrl,emptyCandidate,emptyInvestment,marketDraft,marketNumber,observedMarketSkill,toLocalDateTime,toObservedAt} from './market-model';
import type {MarketAnalysis,MarketCandidate,MarketComparison,MarketDocument,MarketDraft,MarketInvestment,MarketPlan,MarketScenario} from './market-types';
import './market.css';

const money=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?new Intl.NumberFormat(localeTag(),{maximumFractionDigits:2}).format(value):'—';
const newId=()=>crypto.randomUUID().replaceAll('-','');
const fieldLabels=():Record<string,string>=>({cash:tr('Trésorerie actuelle'),weekly_income:tr('Recettes par semaine'),weekly_expenses:tr('Dépenses par semaine'),reserve:tr('Réserve à préserver'),committed_bids:tr('Engagements non débités'),complete:tr('Budget vérifié complet'),observed_at:tr('Date du relevé'),price:tr('Prix envisagé'),weekly_salary:tr('Salaire supplémentaire / semaine'),fees:tr('Frais d’achat'),initial_cost:tr('Coût initial'),weekly_cost:tr('Coût supplémentaire / semaine')});
const warningLabels=():Record<string,string>=>({budget_incomplete:tr('Le budget doit être complété et confirmé.'),budget_undated:tr('Datez votre relevé avant de conclure.'),budget_future_dated:tr('La date du relevé est dans le futur.'),immediate_deficit:tr('La trésorerie immédiate ne préserve pas la réserve.'),projected_deficit:tr('La projection à quatre semaines ne préserve pas la réserve.'),squad_unavailable:tr('Aucun effectif disponible pour la comparaison.'),squad_undated:tr('La date de l’effectif est inconnue.'),skills_incomplete:tr('Des compétences utiles au rôle sont inconnues.'),squad_incomplete:tr('La comparaison couvre seulement les joueurs aux compétences connues.')});

function Warnings({missing=[],warnings=[]}:{missing?:string[];warnings?:string[]}){
  const fields=fieldLabels(),messages=warningLabels();
  return <>{missing.length>0&&<p className="market-missing">{tr('À renseigner : {fields}',{fields:missing.map(key=>fields[key]||key).join(' · ')})}</p>}{warnings.length>0&&<ul className="market-warnings">{[...new Set(warnings)].map(code=><li key={code}>{messages[code]||tr('Vérifiez les hypothèses de ce scénario.')}</li>)}</ul>}</>;
}
function NumericInput({name,label,value,onChange,min=0,max=1000000000000,step='0.01'}:{name?:string;label:string;value:number|null;onChange:(value:number|null)=>void;min?:number;max?:number;step?:string}){
  return <label>{label}<input name={name} type="number" min={min} max={max} step={step} value={value??''} placeholder={tr('Inconnu')} onChange={event=>{try{onChange(marketNumber(event.target.value))}catch{/* Keep the last valid number; never submit non-finite values. */}}}/></label>;
}

type MarketProps=Actions&{onRefresh:()=>Promise<void>};
export function Market(props:MarketProps){
  return <MarketPanel key={JSON.stringify([props.d.user.username,props.d.csrf,props.d.current_team.id])} {...props}/>;
}
function MarketPanel({d,busy,onRefresh}:Pick<MarketProps,'d'|'busy'|'onRefresh'>){
  const [document,setDocument]=useState<MarketDocument|null>(null),[draft,setDraft]=useState<MarketDraft|null>(null);
  const [analysis,setAnalysis]=useState<MarketAnalysis|null>(null),[analysisSource,setAnalysisSource]=useState<number|null>(null);
  const [pending,setPending]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false),[notice,setNotice]=useState('');
  const mounted=useRef(false),generation=useRef(0),locked=useRef(false),form=useRef<HTMLFormElement>(null);
  const dirty=!!document&&!!draft&&JSON.stringify(draft)!==JSON.stringify(marketDraft(document));
  const sourceId=d.squad_source?.id??null;
  const shownAnalysis=analysis,squadOutdated=analysisSource!==sourceId;
  useUnsavedChanges(dirty||pending);
  useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;generation.current++;locked.current=false}},[]);

  async function operate(operation:()=>Promise<void>){
    if(locked.current||busy)return;
    locked.current=true;setPending(true);setError('');setNotice('');
    const ticket=++generation.current;
    try{await operation()}catch(caught){
      if(mounted.current&&ticket===generation.current){
        const stale=(caught as {status?:number}).status===409;
        if(stale)setConflict(true);
        setError(stale?'Une autre session a modifié ce carnet. Votre brouillon est conservé. Relevez vos changements avant de recharger la version enregistrée.':(caught as Error).message);
      }
    }finally{if(mounted.current&&ticket===generation.current){locked.current=false;setPending(false)}}
  }
  async function load(){
    if(locked.current||busy)return;
    if(dirty&&!window.confirm(tr('Recharger la version enregistrée et abandonner ce brouillon ?')))return;
    await operate(async()=>{
      const ticket=generation.current,result=await request('/market?team_id='+encodeURIComponent(d.current_team.id),undefined,d.csrf) as MarketDocument;
      if(!mounted.current||ticket!==generation.current)return;
      setDocument(result);setDraft(marketDraft(result));setAnalysis(result.analysis);setAnalysisSource(result.analysis.squad.snapshot_id);setConflict(false);
    });
  }
  function edit(next:MarketDraft){if(locked.current||busy)return;setDraft(next);setAnalysis(null);setNotice('')}
  async function run(save:boolean,refreshSquad=false){
    if(!draft||!document||locked.current||busy||(save&&conflict))return;
    if(form.current&&!form.current.reportValidity())return;
    const payload={team_id:d.current_team.id,expected_revision:document.revision,...draft};
    await operate(async()=>{
      const ticket=generation.current;
      if(refreshSquad){await onRefresh();if(!mounted.current||ticket!==generation.current)return;}
      const result=await request(save?'/market':'/market/analyze',payload,d.csrf);
      if(!mounted.current||ticket!==generation.current)return;
      setAnalysis(result.analysis);setAnalysisSource(result.analysis.squad.snapshot_id);
      if(save){setDocument(result);setDraft(marketDraft(result));setConflict(false);setNotice('Carnet privé enregistré. Aucun ordre envoyé à Classic.')}
      else setNotice('Scénarios recalculés à partir du brouillon affiché.');
    });
  }
  const fields=fieldLabels(),disabled=busy||pending;
  if(!draft||!document)return <section className="card market-loading" aria-busy={pending}>{error?<><p className="notice error" role="alert">{tr(error)}</p><button type="button" className="button secondary" disabled={disabled} onClick={()=>void load()}><RefreshCw size={16}/>{tr('Réessayer')}</button></>:<p role="status">{tr('Ouverture du carnet mercato…')}</p>}</section>;
  const changePlan=(patch:Partial<MarketPlan>)=>edit({...draft,plan:{...draft.plan,...patch}});
  const changeCandidate=(next:MarketCandidate)=>edit({...draft,candidates:draft.candidates.map(candidate=>candidate.id===next.id?next:candidate)});
  const changeInvestment=(next:MarketInvestment)=>edit({...draft,investments:draft.investments.map(investment=>investment.id===next.id?next:investment)});
  return <form ref={form} className="market-page" onSubmit={event=>{event.preventDefault();void run(true)}} aria-busy={pending}>
    <section className="market-intro">
      <div><span className="eyebrow">{tr('LE BON RENFORT, AU BON MOMENT')}</span><h2>{tr('Renforcer le collectif. Garder de la marge.')}</h2><p>{tr('Partez d’un besoin dans votre XV, comparez les compétences, puis regardez ce que le club peut supporter pendant quatre semaines.')}</p><div className="market-private"><ShieldCheck size={17}/>{tr('Carnet privé · préparation uniquement')}</div></div>
      <aside><Wallet size={25}/><span>{tr('Plafond prudent de dépense initiale')}</span><strong>{money(shownAnalysis?.base.purchase_ceiling)}</strong><small>{shownAnalysis?.confirmed?tr('Sous les hypothèses confirmées ci-dessous'):tr('À confirmer après un relevé complet et daté')}</small></aside>
    </section>
    <div className="market-toolbar"><div className="market-save-state"><span className={dirty?'market-dirty':''}>{dirty?tr('Brouillon non enregistré'):tr('Version enregistrée')}</span><small>{tr('Dernier enregistrement : {date}',{date:date(document.updated_at)})}</small></div><div className="market-actions"><button type="button" className="button secondary" disabled={disabled} onClick={()=>void run(false)}><Calculator size={16}/>{tr('Comparer les scénarios')}</button><button className="button primary" type="submit" disabled={disabled||conflict||!dirty}><Save size={16}/>{pending?tr('Patientez…'):tr('Enregistrer le carnet')}</button><button type="button" className="text-button" disabled={disabled} onClick={()=>void load()}><RefreshCw size={15}/>{tr('Recharger')}</button></div></div>
    {error&&<p className="notice error" role="alert">{tr(error)}</p>}{notice&&<p className="notice" role="status">{tr(notice)}</p>}
    {!shownAnalysis&&<p className="notice" role="status">{tr('Les données ont changé. Comparez de nouveau les scénarios pour lire des résultats à jour.')}</p>}
    {squadOutdated&&<div className="notice market-source-notice" role="status"><p>{tr('L’analyse et l’écran utilisent des relevés d’effectif différents. La comparaison sportive est masquée. Actualisez l’effectif affiché et recalculez ; votre brouillon sera conservé.')}</p><button type="button" className="button secondary" disabled={disabled} onClick={()=>void run(false,true)}><RefreshCw size={15}/>{tr('Actualiser l’effectif et recalculer')}</button></div>}
    <fieldset disabled={disabled} className="market-fieldset">
      <section className="card market-budget" aria-labelledby="market-budget-title"><div className="card-heading"><div><span className="eyebrow">{tr('01 / LES MOYENS DU CLUB')}</span><h2 id="market-budget-title"><Wallet size={20}/>{tr('Votre budget de départ')}</h2></div><span className="market-pill">{tr('Horizon fixe : 4 semaines')}</span></div><div className="market-card-body">
        <p>{tr('Saisissez les montants lus dans Classic, en monnaie du jeu. Un champ vide reste inconnu ; saisissez 0 seulement si le montant est bien nul.')}</p>
        <div className="market-fields">{(['cash','weekly_income','weekly_expenses','reserve','committed_bids'] as const).map(key=><label key={key}>{fields[key]}<input name={key} type="number" min="0" max="1000000000000" step="0.01" value={draft.plan[key]??''} placeholder={tr('Inconnu')} onChange={event=>{try{changePlan({[key]:marketNumber(event.target.value)})}catch{/* Invalid input does not become zero. */}}}/></label>)}<label>{fields.observed_at}<input type="datetime-local" value={toLocalDateTime(draft.plan.observed_at)} onChange={event=>changePlan({observed_at:toObservedAt(event.target.value)})}/></label></div>
        <p className="tiny">{tr('Dépenses : tous les coûts récurrents actuels. Engagements : uniquement les sommes restant à débiter. N’ajoutez pas une construction déjà payée ni une vente espérée. La date utilise votre fuseau local.')}</p>
        <label className="market-checkbox"><input type="checkbox" checked={draft.plan.complete} onChange={event=>changePlan({complete:event.target.checked})}/><span>{tr('J’ai vérifié toutes les recettes, dépenses et sommes engagées de ce relevé.')}</span></label>
        {shownAnalysis&&<><div className="market-metrics"><Metric label={tr('Solde hebdomadaire')} value={shownAnalysis.base.weekly_net}/><Metric label={tr('Trésorerie dans 4 semaines')} value={shownAnalysis.base.projected_cash}/><Metric label={tr('Marge immédiate après réserve')} value={shownAnalysis.base.immediate_headroom}/><Metric label={tr('Marge à 4 semaines après réserve')} value={shownAnalysis.base.projected_headroom}/></div><Warnings missing={shownAnalysis.missing_fields} warnings={shownAnalysis.warnings}/></>}
        <p className="market-method">{tr('Le plafond retient la plus petite marge entre aujourd’hui et la fin des quatre semaines. La réserve et les engagements sont protégés dans les deux cas. Les rentrées futures ne financent pas un achat immédiat.')}</p>
      </div></section>
      <section className="card market-shortlist" aria-labelledby="market-candidates-title"><div className="card-heading"><div><span className="eyebrow">{tr('02 / RENFORCER UN POSTE')}</span><h2 id="market-candidates-title"><ClipboardList size={20}/>{tr('Les joueurs à étudier')}</h2></div><button type="button" className="button secondary" disabled={draft.candidates.length>=50} onClick={()=>edit({...draft,candidates:[...draft.candidates,emptyCandidate(newId())]})}><Plus size={16}/>{tr('Ajouter un candidat')}</button></div><div className="market-card-body"><p>{tr('Reportez manuellement les informations d’un joueur repéré. Comparez-le à votre groupe, sans conclure sur le seul CSR. Le prix et les compétences peuvent évoluer : revérifiez-les dans Classic.')}</p><p className="tiny">{tr('Chaque candidat est un scénario indépendant. Son salaire s’ajoute intégralement : aucune économie de remplacement ni recette de revente n’est supposée.')}</p>
        {!draft.candidates.length?<div className="market-empty"><ClipboardList size={30}/><h3>{tr('D’abord un besoin, ensuite un nom.')}</h3><p>{tr('Identifiez le rôle à renforcer et ajoutez votre premier candidat. Aucune recherche ni enchère automatique n’est lancée.')}</p></div>:<div className="market-candidates">{draft.candidates.map((candidate,index)=><CandidateCard key={candidate.id} candidate={candidate} index={index} scenario={shownAnalysis?.candidates.find(item=>item.id===candidate.id)} squadOutdated={squadOutdated} d={d} change={changeCandidate} remove={()=>edit({...draft,candidates:draft.candidates.filter(item=>item.id!==candidate.id)})}/>)}</div>}
      </div></section>
      <section className="card market-investments" aria-labelledby="market-investments-title"><div className="card-heading"><div><span className="eyebrow">{tr('03 / PRÉPARER LA SUITE')}</span><h2 id="market-investments-title"><Calculator size={20}/>{tr('Staff et infrastructures')}</h2></div><button type="button" className="button secondary" disabled={draft.investments.length>=20} onClick={()=>edit({...draft,investments:[...draft.investments,emptyInvestment(newId())]})}><Plus size={16}/>{tr('Ajouter un projet')}</button></div><div className="market-card-body"><p>{tr('Comparez des projets indépendants, chacun avec son coût initial restant à payer et son coût récurrent supplémentaire. Un contrat plus long que quatre semaines reste à vérifier au-delà de cet horizon.')}</p>
        {!draft.investments.length?<div className="market-empty"><Calculator size={30}/><h3>{tr('Investir pour un usage précis.')}</h3><p>{tr('Un coach, une installation ou une extension : notez le besoin, le devis et ce que vous utiliserez réellement.')}</p></div>:<div className="market-projects">{draft.investments.map((investment,index)=><InvestmentCard key={investment.id} investment={investment} index={index} scenario={shownAnalysis?.investments.find(item=>item.id===investment.id)} change={changeInvestment} remove={()=>edit({...draft,investments:draft.investments.filter(item=>item.id!==investment.id)})}/>)}</div>}
      </div></section>
    </fieldset>
    <p className="market-footnote"><ShieldCheck size={18}/>{tr('Enregistrer ou comparer prépare votre décision dans BRT. Aucun joueur n’est acheté ou vendu, aucune enchère ni commande de staff ou d’infrastructure n’est envoyée à Classic. Les résultats sont des hypothèses, pas une prévision officielle.')}</p>
  </form>;
}

function Metric({label,value}:{label:string;value:number|null|undefined}){return <div className={'market-metric'+(typeof value==='number'&&value<0?' is-negative':'')}><span>{label}</span><strong>{money(value)}</strong></div>}
function Scenario({scenario,candidate=false}:{scenario:MarketScenario|undefined;candidate?:boolean}){
  if(!scenario)return <p className="market-analysis-prompt">{tr('Comparez les scénarios après votre saisie.')}</p>;
  const status=scenario.status==='affordable'?tr('Compatible avec ce budget confirmé'):scenario.status==='over_budget'?tr('Dépasse la marge prévue'):tr('À compléter avant de conclure');
  return <div className={'market-scenario status-'+scenario.status}><strong className="market-status">{status}</strong><div className="market-metrics"><Metric label={tr('Décaissement initial')} value={scenario.initial_cost}/><Metric label={tr('Coût total sur 4 semaines')} value={scenario.four_week_cost}/><Metric label={candidate?tr('Prix maximum du joueur'):tr('Coût initial maximum')} value={scenario.purchase_ceiling}/><Metric label={tr('Marge immédiate après achat')} value={scenario.immediate_headroom}/><Metric label={tr('Trésorerie dans 4 semaines')} value={scenario.projected_cash}/><Metric label={tr('Marge à 4 semaines après réserve')} value={scenario.projected_headroom}/></div><Warnings missing={scenario.missing_fields} warnings={scenario.warnings}/></div>;
}
function Comparison({comparison}:{comparison:MarketComparison}){
  return <div className="market-comparison"><div className="market-metrics"><Metric label={tr('Indice du candidat au rôle')} value={comparison.score}/><Metric label={tr('Meilleur indice de l’effectif')} value={comparison.squad_best}/><Metric label={tr('Écart au meilleur indice')} value={comparison.delta_best}/></div><p className="tiny">{tr('Effectif comparable : {known}/{total} joueurs. Compétences connues du candidat : {skills}/10.',{known:comparison.squad_known,total:comparison.squad_total,skills:comparison.known_skills})}</p>{comparison.missing_skills.length>0&&<p className="market-missing">{tr('Compétences requises manquantes : {skills}',{skills:comparison.missing_skills.map(skill=>tr(labels[skill]||skill)).join(' · ')})}</p>}</div>;
}
function CandidateCard({candidate,index,scenario,squadOutdated,d,change,remove}:{candidate:MarketCandidate;index:number;scenario:(MarketScenario&{comparison:MarketComparison})|undefined;squadOutdated:boolean;d:Actions['d'];change:(value:MarketCandidate)=>void;remove:()=>void}){
  const [reference,setReference]=useState('');
  const senior=squadOutdated?undefined:d.squad.find(player=>player.id===reference),link=classicPlayerUrl(candidate.classic_id),fields=fieldLabels();
  return <article className="market-candidate"><div className="market-item-heading"><span className="market-number">{String(index+1).padStart(2,'0')}</span><h3>{candidate.name||tr('Nouveau candidat')}</h3>{link&&<a href={link} target="_blank" rel="noreferrer" className="text-button">{tr('Ouvrir Classic')}<ArrowUpRight size={14}/></a>}<button type="button" className="icon-button" aria-label={tr('Retirer le candidat {name}',{name:candidate.name||String(index+1)})} onClick={remove}><Trash2 size={16}/></button></div>
    <div className="market-fields"><label>{tr('Nom du candidat')}<input required maxLength={100} value={candidate.name} onChange={event=>change({...candidate,name:event.target.value})}/></label><label>{tr('Identifiant Classic (facultatif)')}<input inputMode="numeric" pattern="[1-9][0-9]{0,14}" maxLength={15} value={candidate.classic_id??''} onChange={event=>change({...candidate,classic_id:event.target.value||null})}/></label><label>{tr('Rôle recherché')}<select value={candidate.role} onChange={event=>change({...candidate,role:event.target.value as MarketCandidate['role']})}>{roleNames.map(role=><option key={role} value={role}>{tr(role)}</option>)}</select></label><NumericInput label={tr('Âge')} min={16} max={60} step="1" value={candidate.age} onChange={age=>change({...candidate,age})}/><label>{tr('Votre suivi')}<select value={candidate.status} onChange={event=>change({...candidate,status:event.target.value as MarketCandidate['status']})}><option value="watch">{tr('À observer')}</option><option value="shortlist">{tr('Retenu pour comparaison')}</option><option value="dismissed">{tr('Écarté')}</option></select></label></div>
    <div className="market-fields market-cost-fields">{(['price','fees','weekly_salary'] as const).map(key=><NumericInput key={key} label={fields[key]} value={candidate[key]} onChange={value=>change({...candidate,[key]:value})}/>)}</div>
    <details className="market-skills"><summary>{tr('Compétences et comparaison avec un senior')}</summary>{!squadOutdated&&<><label>{tr('Senior de référence (facultatif)')}<select value={reference} onChange={event=>setReference(event.target.value)}><option value="">{tr('Choisir un joueur de l’effectif')}</option>{d.squad.map(player=><option key={player.id} value={player.id}>{player.name}</option>)}</select></label><p className="tiny">{tr('Effectif observé le {date}',{date:date(d.squad_source?.observed_at)})}</p></>}<div className="table-scroll"><table><caption>{tr('Niveaux observés, de 0 à 21. Laissez vide toute compétence inconnue.')}</caption><thead><tr><th scope="col">{tr('Compétence')}</th><th scope="col">{tr('Candidat')}</th>{!squadOutdated&&<th scope="col">{senior?.name||tr('Senior de référence')}</th>}</tr></thead><tbody>{skillKeys.map(skill=><tr key={skill}><th scope="row">{tr(labels[skill])}</th><td><input aria-label={tr('{skill} du candidat {name}',{skill:tr(labels[skill]),name:candidate.name||String(index+1)})} type="number" min="0" max="21" step="0.01" value={candidate.skills[skill]??''} placeholder="—" onChange={event=>{try{change({...candidate,skills:{...candidate.skills,[skill]:marketNumber(event.target.value)}})}catch{/* Never replace invalid skills with zero. */}}}/></td>{!squadOutdated&&<td>{fmt(observedMarketSkill(senior?.[skill]))}</td>}</tr>)}</tbody></table></div></details>
    <label>{tr('Besoin, sources et points à vérifier')}<textarea maxLength={1000} rows={2} value={candidate.notes} onChange={event=>change({...candidate,notes:event.target.value})}/></label>
    {scenario&&!squadOutdated&&<><Comparison comparison={scenario.comparison}/><p className="tiny">{tr('Indice local au rôle, avec les coefficients par défaut de BRT. Les joueurs incomplets sont exclus du repère : ce classement ne mesure ni la disponibilité, ni la forme, ni une probabilité de victoire.')}</p></>}
    <Scenario scenario={scenario} candidate/>
  </article>;
}
function InvestmentCard({investment,index,scenario,change,remove}:{investment:MarketInvestment;index:number;scenario:MarketScenario|undefined;change:(value:MarketInvestment)=>void;remove:()=>void}){
  const fields=fieldLabels();
  return <article className="market-project"><div className="market-item-heading"><span className="market-number">{String(index+1).padStart(2,'0')}</span><h3>{investment.name||tr('Nouveau projet')}</h3><button type="button" className="icon-button" aria-label={tr('Retirer le projet {name}',{name:investment.name||String(index+1)})} onClick={remove}><Trash2 size={16}/></button></div><div className="market-fields"><label>{tr('Nom du projet')}<input required maxLength={100} value={investment.name} onChange={event=>change({...investment,name:event.target.value})}/></label>{(['initial_cost','weekly_cost'] as const).map(key=><NumericInput key={key} label={fields[key]} value={investment[key]} onChange={value=>change({...investment,[key]:value})}/>)}</div><label>{tr('Usage prévu, devis et durée d’engagement')}<textarea maxLength={1000} rows={2} value={investment.notes} onChange={event=>change({...investment,notes:event.target.value})}/></label><Scenario scenario={scenario}/></article>;
}
