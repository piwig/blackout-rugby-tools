import {useEffect,useRef,useState} from 'react';
import {request,type Actions} from './App';
import {tr,localeTag} from './i18n';
import {useUnsavedChanges} from './navigation-guard';
import './transfer-ledger.css';

type Entry={id:string;player_id:string;player_name:string;kind:'buy'|'sell';occurred_at:string;season:string;amount:string;fees:string;counterparty:string;source:string;notes:string;status:'active'|'cancelled';cancellation_reason:string};
type Version={version:number;at:string;operation:string;reason:string;entry:Entry};
type Row=Entry&{version:number;versions:Version[]};
type RecordValue={id:string;player_id:string;player_name:string;amount:string};
type Statistics={count:number;cancelled_count:number;buy_count:number;sell_count:number;purchases:string;sales:string;fees:string;balance:string;average_buy_gross:string|null;average_sell_gross:string|null;largest_purchase_gross:RecordValue|null;largest_sale_gross:RecordValue|null;largest_sale_net:RecordValue|null};
type Report={revision:number;updated_at:string|null;entries:Row[];statistics:Statistics;by_season:(Statistics&{season:string})[];by_player:(Statistics&{player_id:string;player_name:string})[];seasons:string[];total:number;total_stored:number;offset:number;limit:number};
type ImportPreview={preview_id:string;revision:number;expires_at:number;entries:Entry[];statistics:Statistics;added:number;corrected:number;duplicates:number};
type Filters={season:string;search:string;start:string;end:string};
type Editor={entry:Entry;revision:number;action:'create'|'correct'|'cancel'|'restore';reason:string};
const blankFilters:Filters={season:'',search:'',start:'',end:''};
const amount=(value:string|null|undefined)=>value==null?'—':new Intl.NumberFormat(localeTag(),{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value));
const stamp=(value:string|null)=>value?new Date(value).toLocaleString(localeTag()):'—';
function localDate(value:string){const date=new Date(value);return Number.isNaN(date.getTime())?'':new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}
function newEntry():Entry{return {id:crypto.randomUUID(),player_id:'',player_name:'',kind:'buy',occurred_at:new Date().toISOString(),season:'',amount:'',fees:'',counterparty:'',source:'',notes:'',status:'active',cancellation_reason:''}}
function portable(row:Entry):Entry {const {id,player_id,player_name,kind,occurred_at,season,amount,fees,counterparty,source,notes,status,cancellation_reason}=row;return {id,player_id,player_name,kind,occurred_at,season,amount,fees,counterparty,source,notes,status,cancellation_reason}}
function download(value:{content:string;filename:string;format:string}){const url=URL.createObjectURL(new Blob([value.content],{type:value.format==='csv'?'text/csv;charset=utf-8':'application/json;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=value.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
const operationLabel=(operation:string)=>({create:tr('Saisie'),import:tr('Import'),correct:tr('Correction'),cancel:tr('Annulation'),restore:tr('Restauration')}[operation]||operation);

export function TransferLedger(props:Actions){return <TransferLedgerPanel key={JSON.stringify([props.d.user.username,props.d.csrf,props.d.current_team.id])} {...props}/>}
function TransferLedgerPanel({d,busy}:Actions){
  const [report,setReport]=useState<Report|null>(null),[editor,setEditor]=useState<Editor|null>(null);
  const [filters,setFilters]=useState<Filters>(blankFilters),[applied,setApplied]=useState<Filters>(blankFilters);
  const [content,setContent]=useState(''),[format,setFormat]=useState<'csv'|'json'>('csv'),[mode,setMode]=useState<'append'|'correct'>('append'),[importReason,setImportReason]=useState(''),[preview,setPreview]=useState<ImportPreview|null>(null);
  const [pending,setPending]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const mounted=useRef(false),generation=useRef(0),locked=useRef(false),editorForm=useRef<HTMLFormElement>(null);
  const dirty=!!editor||!!content||!!importReason||!!preview,disabled=busy||pending;
  useUnsavedChanges(dirty||pending);
  useEffect(()=>{mounted.current=true;void execute(valid=>read(valid,blankFilters));return()=>{mounted.current=false;generation.current++;locked.current=false}},[]);
  async function execute(work:(valid:()=>boolean)=>Promise<void>){
    if(locked.current)return;
    const ticket=++generation.current;locked.current=true;setPending(true);setError('');setNotice('');
    const valid=()=>mounted.current&&ticket===generation.current;
    try{await work(valid)}catch(caught){if(valid())setError((caught as Error).message)}finally{if(valid()){locked.current=false;setPending(false)}}
  }
  async function read(valid:()=>boolean,criteria=applied,offset=0){
    const query=new URLSearchParams({team_id:d.current_team.id,offset:String(offset)});
    for(const [key,value] of Object.entries(criteria))if(value)query.set(key,value);
    const result=await request('/transfer-ledger?'+query,undefined,d.csrf) as Report;
    if(valid()){setReport(result);setApplied({...criteria})}
  }
  function discardEditor(){if(!editor||window.confirm(tr('Abandonner ce brouillon d’opération ?')))setEditor(null)}
  function edit(row?:Row,action:Editor['action']='create'){
    if(disabled||!report)return;
    if(editor&&!window.confirm(tr('Abandonner ce brouillon d’opération ?')))return;
    setEditor({entry:row?portable(row):newEntry(),revision:report.revision,action,reason:''});setError('');setNotice('');
  }
  function changeEntry(patch:Partial<Entry>){if(editor&&!disabled)setEditor({...editor,entry:{...editor.entry,...patch}})}
  async function save(){
    if(!editor||!report||disabled)return;
    if(editorForm.current&&!editorForm.current.reportValidity())return;
    const captured=editor;
    await execute(async valid=>{
      const status=captured.action==='cancel'||captured.action==='restore';
      await request('/transfer-ledger'+(status?'/'+captured.action:''),{
        team_id:d.current_team.id,expected_revision:captured.revision,
        ...(status?{id:captured.entry.id,reason:captured.reason}:{action:captured.action,reason:captured.reason,entry:captured.entry})},d.csrf);
      if(!valid())return;
      setEditor(null);setPreview(null);
      await read(valid);
      if(valid())setNotice('Opération enregistrée dans le registre privé.');
    });
  }
  async function reload(){
    if(dirty&&!window.confirm(tr('Recharger le registre et abandonner les brouillons et l’aperçu ?')))return;
    await execute(async valid=>{await read(valid);if(valid()){setEditor(null);setContent('');setPreview(null);setImportReason('')}});
  }
  async function getFile(template:boolean){
    await execute(async valid=>{const result=await request('/transfer-ledger/'+(template?'template':'export')+'?'+new URLSearchParams({team_id:d.current_team.id,format}),undefined,d.csrf);if(valid())download(result)});
  }
  async function loadFile(file:File|undefined){
    if(!file)return;
    if(file.size>4000000){setError('Fichier limité à 4 Mo.');return}
    await execute(async valid=>{const text=await file.text();if(valid()){setContent(text);setFormat(file.name.toLowerCase().endsWith('.json')?'json':'csv');setPreview(null)}});
  }
  async function analyzeImport(){
    if(!report||disabled)return;
    await execute(async valid=>{
      const result=await request('/transfer-ledger/preview',{team_id:d.current_team.id,expected_revision:report.revision,format,content,mode,reason:importReason},d.csrf) as ImportPreview;
      if(valid())setPreview(result);
    });
  }
  async function confirmImport(){
    if(!preview||disabled)return;
    const captured=preview;
    await execute(async valid=>{
      await request('/transfer-ledger/confirm',{team_id:d.current_team.id,expected_revision:captured.revision,preview_id:captured.preview_id},d.csrf);
      if(!valid())return;
      setPreview(null);setContent('');setImportReason('');await read(valid);
      if(valid())setNotice('Import confirmé dans le registre privé.');
    });
  }
  if(!report)return <section className="card transfer-ledger" aria-busy={pending}><h2>{tr('Registre des transferts réalisés')}</h2>{error?<><p className="notice error" role="alert">{tr(error)}</p><button className="button secondary" disabled={disabled} onClick={()=>void reload()}>{tr('Réessayer')}</button></>:<p role="status">{tr('Ouverture du registre…')}</p>}</section>;
  const s=report.statistics,entry=editor?.entry,statusAction=editor?.action==='cancel'||editor?.action==='restore';
  return <section className="card transfer-ledger" aria-busy={pending}>
    <div className="transfer-heading"><div><span className="eyebrow">{tr('OPÉRATIONS RÉALISÉES')}</span><h2>{tr('Registre des transferts réalisés')}</h2><p>{tr('Monnaie virtuelle du jeu. Le registre ne modifie pas votre trésorerie actuelle.')}</p></div><div className="transfer-balance"><span>{tr('Balance nette')}</span><strong>{amount(s.balance)}</strong><small>{tr('Ventes − achats − tous les frais')}</small></div></div>
    <details className="transfer-workspace" open><summary>{tr('Consulter et compléter le registre')} <span className="tiny">({report.total_stored})</span></summary>
      <div className="transfer-toolbar"><button type="button" className="button primary" disabled={disabled} onClick={()=>edit()}>{tr('Ajouter une opération')}</button><button type="button" className="button secondary" disabled={disabled} onClick={()=>void reload()}>{tr('Recharger')}</button><small>{tr('Dernier enregistrement : {date}',{date:stamp(report.updated_at)})}</small></div>
      {error&&<p className="notice error" role="alert">{tr(error)}</p>}{notice&&<p className="notice" role="status">{tr(notice)}</p>}
      <p className="tiny">{tr('Saisissez uniquement des achats et ventes terminés. Les candidats du carnet mercato restent des projets distincts.')}</p>
      <form className="transfer-filters" onSubmit={event=>{event.preventDefault();void execute(valid=>read(valid,filters))}}>
        <label>{tr('Saison déclarée')}<select name="filter_season" disabled={disabled} value={filters.season} onChange={event=>setFilters({...filters,season:event.target.value})}><option value="">{tr('Toutes les saisons')}</option>{report.seasons.map(season=><option key={season}>{season}</option>)}</select></label>
        <label>{tr('Joueur : nom ou identifiant')}<input disabled={disabled} maxLength={100} value={filters.search} onChange={event=>setFilters({...filters,search:event.target.value})}/></label>
        <label>{tr('Du (UTC)')}<input type="date" disabled={disabled} value={filters.start} onChange={event=>setFilters({...filters,start:event.target.value})}/></label>
        <label>{tr('Au (UTC)')}<input type="date" disabled={disabled} min={filters.start||undefined} value={filters.end} onChange={event=>setFilters({...filters,end:event.target.value})}/></label>
        <button className="button secondary" disabled={disabled}>{tr('Appliquer les filtres')}</button>
      </form>
      {JSON.stringify(filters)!==JSON.stringify(applied)&&<p className="tiny" role="status">{tr('Appliquez les filtres pour actualiser le bilan affiché.')}</p>}
      <div className="transfer-metrics"><Metric label={tr('Achats bruts')} value={s.purchases} count={s.buy_count}/><Metric label={tr('Ventes brutes')} value={s.sales} count={s.sell_count}/><Metric label={tr('Tous les frais')} value={s.fees}/><Metric label={tr('Balance nette')} value={s.balance}/></div>
      <p className="tiny">{tr('{count} opérations actives · {cancelled} annulées, exclues du bilan.',{count:s.count,cancelled:s.cancelled_count})}</p>
      <details className="transfer-method"><summary>{tr('Moyennes, records et bilans par saison ou joueur')}</summary>
        <p>{tr('Les montants bruts excluent les frais. Le record de vente nette déduit les frais de cette vente seulement. La balance joueur est un flux de trésorerie cumulé ; elle ne comprend pas les salaires et ne constitue pas un bénéfice achat-revente.')}</p>
        <div className="transfer-metrics"><Metric label={tr('Achat moyen brut')} value={s.average_buy_gross}/><Metric label={tr('Vente moyenne brute')} value={s.average_sell_gross}/></div>
        <ul>{[[tr('Plus gros achat brut'),s.largest_purchase_gross],[tr('Plus grosse vente brute'),s.largest_sale_gross],[tr('Plus grosse vente nette'),s.largest_sale_net]].map(([label,value])=><li key={String(label)}>{String(label)} : {value?(value as RecordValue).player_name+' · '+amount((value as RecordValue).amount):'—'}</li>)}</ul>
        <GroupTable label={tr('Bilan par saison')} groups={report.by_season.map(group=>({...group,label:group.season}))}/><GroupTable label={tr('Flux par joueur')} groups={report.by_player.map(group=>({...group,label:group.player_name+' (#'+group.player_id+')'}))}/>
      </details>
      {editor&&entry&&<form ref={editorForm} data-ledger-editor className="transfer-editor" onSubmit={event=>{event.preventDefault();void save()}}>
        <h3>{editor.action==='create'?tr('Nouvelle opération réalisée'):editor.action==='correct'?tr('Corriger l’opération'):editor.action==='cancel'?tr('Annuler l’opération'):tr('Rétablir l’opération')}</h3>
        <fieldset disabled={disabled}>
          {statusAction?<p>{entry.player_name} · {entry.kind==='buy'?tr('Achat'):tr('Vente')} · {amount(entry.amount)}</p>:<>
            <div className="transfer-fields"><label>{tr('Nom du joueur')}<input name="player_name" required maxLength={100} value={entry.player_name} onChange={event=>changeEntry({player_name:event.target.value})}/></label><label>{tr('Identifiant du joueur')}<input name="player_id" required inputMode="numeric" pattern="[1-9][0-9]{0,14}" maxLength={15} value={entry.player_id} onChange={event=>changeEntry({player_id:event.target.value})}/></label><label>{tr('Type d’opération')}<select name="kind" value={entry.kind} onChange={event=>changeEntry({kind:event.target.value as Entry['kind']})}><option value="buy">{tr('Achat')}</option><option value="sell">{tr('Vente')}</option></select></label>
              <label>{tr('Date réalisée (fuseau local)')}<input name="occurred_at" type="datetime-local" required max={localDate(new Date().toISOString())} value={localDate(entry.occurred_at)} onChange={event=>changeEntry({occurred_at:event.target.value?new Date(event.target.value).toISOString():''})}/></label>
              <label>{tr('Saison déclarée')}<input name="season" required maxLength={30} value={entry.season} onChange={event=>changeEntry({season:event.target.value})}/></label><label>{tr('Montant brut')}<input name="amount" type="number" min="0" max="1000000000000" step="0.01" required value={entry.amount} onChange={event=>changeEntry({amount:event.target.value})}/></label><label>{tr('Frais de l’opération')}<input name="fees" type="number" min="0" max="1000000000000" step="0.01" required value={entry.fees} placeholder={tr('0 si aucun frais')} onChange={event=>changeEntry({fees:event.target.value})}/></label><label>{tr('Club contrepartie (facultatif)')}<input name="counterparty" maxLength={160} value={entry.counterparty} onChange={event=>changeEntry({counterparty:event.target.value})}/></label></div>
            <label>{tr('Source de l’opération')}<input name="source" required maxLength={500} value={entry.source} onChange={event=>changeEntry({source:event.target.value})}/></label><label>{tr('Notes')}<textarea name="notes" rows={2} maxLength={1000} value={entry.notes} onChange={event=>changeEntry({notes:event.target.value})}/></label><small>{tr('Identifiant de l’opération')} : {entry.id}</small>
            <p className="tiny">{tr('La date saisie utilise votre fuseau local ; le registre et les filtres stockent des instants UTC. La saison reste votre déclaration.')}</p>
          </>}
          {editor.action!=='create'&&<label>{tr('Motif obligatoire')}<textarea name="reason" required maxLength={500} rows={2} value={editor.reason} onChange={event=>setEditor({...editor,reason:event.target.value})}/></label>}
          <div className="transfer-toolbar"><button type="submit" className="button primary">{editor.action==='create'?tr('Enregistrer l’opération'):editor.action==='correct'?tr('Enregistrer la correction'):editor.action==='cancel'?tr('Confirmer l’annulation'):tr('Confirmer la restauration')}</button><button type="button" className="button secondary" onClick={discardEditor}>{tr('Abandonner le brouillon')}</button></div>
        </fieldset>
      </form>}
      <div className="transfer-list">
        <h3>{tr('Opérations de la période affichée')} ({report.total})</h3>
        {!report.entries.length?<p>{tr('Aucune opération pour ces filtres.')}</p>:report.entries.map(row=><article key={row.id} className={'transfer-row '+(row.status==='cancelled'?'is-cancelled':'')}>
          <div className="transfer-row-heading"><div><strong>{row.player_name}</strong><span>#{row.player_id} · {row.season} · {row.kind==='buy'?tr('Achat'):tr('Vente')}</span><small>{stamp(row.occurred_at)}</small></div><div><strong>{amount(row.amount)}</strong><small>{tr('Frais : {amount}',{amount:amount(row.fees)})}</small><span className="transfer-status">{row.status==='cancelled'?tr('Annulée'):tr('Active')}</span></div></div>
          {row.status==='cancelled'&&<p>{row.cancellation_reason}</p>}
          <div className="transfer-toolbar"><button type="button" className="text-button" disabled={disabled} onClick={()=>edit(row,'correct')}>{tr('Corriger')}</button><button type="button" className="text-button" disabled={disabled} onClick={()=>edit(row,row.status==='cancelled'?'restore':'cancel')}>{row.status==='cancelled'?tr('Rétablir'):tr('Annuler cette opération')}</button></div>
          <details className="transfer-audit"><summary>{tr('Source et historique')} · {tr('{count} versions',{count:row.versions.length})}</summary><p>{row.source}</p>{row.counterparty&&<p>{tr('Contrepartie')} : {row.counterparty}</p>}{row.notes&&<p className="transfer-notes">{row.notes}</p>}
            <ol>{row.versions.map(version=><li key={version.version}><strong>{operationLabel(version.operation)} · {stamp(version.at)}</strong>{version.reason&&<p>{version.reason}</p>}<Snapshot entry={version.entry}/></li>)}</ol>
          </details>
        </article>)}
        <div className="transfer-toolbar"><button type="button" className="button secondary" disabled={disabled||report.offset===0} onClick={()=>void execute(valid=>read(valid,applied,Math.max(0,report.offset-report.limit)))}>{tr('Précédent')}</button><span>{tr('{from}–{to} sur {total}',{from:report.total?report.offset+1:0,to:Math.min(report.offset+report.limit,report.total),total:report.total})}</span><button type="button" className="button secondary" disabled={disabled||report.offset+report.limit>=report.total} onClick={()=>void execute(valid=>read(valid,applied,report.offset+report.limit))}>{tr('Suivant')}</button></div>
      </div>
      <details className="transfer-import"><summary>{tr('Importer, exporter ou télécharger un modèle')}</summary>
        <p>{tr('Export intégral du club, annulations incluses. Le modèle contient un exemple à remplacer. Aucun fichier ne devient une opération avant confirmation de son aperçu.')}</p>
        <p className="tiny">{tr('Pour garder les exports réimportables, chaque modification doit laisser les fichiers CSV et JSON du club sous 4 Mo. Si la limite est atteinte, raccourcissez les notes avant d’ajouter des opérations.')}</p>
        <div className="transfer-toolbar"><label>{tr('Format')}<select disabled={disabled} value={format} onChange={event=>{setFormat(event.target.value as 'csv'|'json');setPreview(null)}}><option value="csv">CSV</option><option value="json">JSON</option></select></label><button type="button" className="button secondary" disabled={disabled} onClick={()=>void getFile(true)}>{tr('Télécharger le modèle')}</button><button type="button" className="button secondary" disabled={disabled} onClick={()=>void getFile(false)}>{tr('Exporter le registre')}</button></div>
        <form data-ledger-import onSubmit={event=>{event.preventDefault();void analyzeImport()}}>
          <fieldset disabled={disabled}>
            <label>{tr('Fichier CSV ou JSON (4 Mo maximum)')}<input type="file" accept=".csv,.json,text/csv,application/json" onChange={event=>{void loadFile(event.target.files?.[0]);event.target.value=''}}/></label>
            <label>{tr('Contenu à importer')}<textarea name="import_content" required rows={5} maxLength={4000000} value={content} onChange={event=>{setContent(event.target.value);setPreview(null)}}/></label>
            <label>{tr('Traitement des identifiants existants')}<select value={mode} onChange={event=>{setMode(event.target.value as 'append'|'correct');setPreview(null)}}><option value="append">{tr('Ajouter et ignorer les doublons identiques')}</option><option value="correct">{tr('Corriger explicitement les contenus différents')}</option></select></label>
            {mode==='correct'&&<label>{tr('Motif obligatoire')}<textarea name="import_reason" required maxLength={500} rows={2} value={importReason} onChange={event=>{setImportReason(event.target.value);setPreview(null)}}/></label>}
            <button className="button secondary" disabled={!content}>{tr('Préparer l’aperçu')}</button>
          </fieldset>
        </form>
        {preview&&<div className="transfer-preview" role="region" aria-label={tr('Aperçu de l’import')}><h3>{tr('Aperçu de l’import')}</h3><p>{tr('{added} ajouts · {corrected} corrections · {duplicates} doublons ignorés',{added:preview.added,corrected:preview.corrected,duplicates:preview.duplicates})}</p><p className="tiny">{tr('L’aperçu expire après 15 minutes et devient invalide si le registre, le club ou la session change.')}</p>
          <h4>{tr('Bilan du club après cet import')}</h4><div className="transfer-metrics"><Metric label={tr('Achats bruts')} value={preview.statistics.purchases}/><Metric label={tr('Ventes brutes')} value={preview.statistics.sales}/><Metric label={tr('Tous les frais')} value={preview.statistics.fees}/><Metric label={tr('Balance nette')} value={preview.statistics.balance}/></div>
          <div className="transfer-preview-list">{preview.entries.map((row,index)=><details key={index}><summary>{row.player_name} (#{row.player_id}) · {row.season} · {row.kind==='buy'?tr('Achat'):tr('Vente')} · {amount(row.amount)} · {row.status==='cancelled'?tr('Annulée'):tr('Active')}</summary><Snapshot entry={row}/></details>)}</div>
          <button type="button" className="button primary" disabled={disabled} onClick={()=>void confirmImport()}>{tr('Confirmer cet import')}</button><button type="button" className="text-button" disabled={disabled} onClick={()=>{setPreview(null);setContent('');setImportReason('')}}>{tr('Abandonner cet import')}</button>
        </div>}
      </details>
    </details>
  </section>;
}
function Metric({label,value,count}:{label:string;value:string|null;count?:number}){return <div><span>{label}</span><strong>{amount(value)}</strong>{count!==undefined&&<small>{tr('{count} opérations',{count})}</small>}</div>}
function GroupTable({label,groups}:{label:string;groups:(Statistics&{label:string})[]}){return <div className="table-scroll"><table><caption>{label}</caption><thead><tr><th scope="col">{tr('Groupe')}</th><th scope="col">{tr('Achats')}</th><th scope="col">{tr('Ventes')}</th><th scope="col">{tr('Tous les frais')}</th><th scope="col">{tr('Balance nette')}</th></tr></thead><tbody>{groups.map(group=><tr key={group.label}><th scope="row">{group.label}</th><td>{group.buy_count} · {amount(group.purchases)}</td><td>{group.sell_count} · {amount(group.sales)}</td><td>{amount(group.fees)}</td><td>{amount(group.balance)}</td></tr>)}</tbody></table></div>}
function Snapshot({entry}:{entry:Entry}){return <dl className="transfer-snapshot"><div><dt>{tr('Joueur')}</dt><dd>{entry.player_name} (#{entry.player_id})</dd></div><div><dt>{tr('Type d’opération')}</dt><dd>{entry.kind==='buy'?tr('Achat'):tr('Vente')}</dd></div><div><dt>{tr('Date réalisée')}</dt><dd>{stamp(entry.occurred_at)} · {entry.season}</dd></div><div><dt>{tr('Montant brut')}</dt><dd>{amount(entry.amount)}</dd></div><div><dt>{tr('Frais de l’opération')}</dt><dd>{amount(entry.fees)}</dd></div><div><dt>{tr('Source de l’opération')}</dt><dd>{entry.source}</dd></div><div><dt>{tr('Contrepartie')}</dt><dd>{entry.counterparty||'—'}</dd></div><div><dt>{tr('Notes')}</dt><dd>{entry.notes||'—'}</dd></div><div><dt>{tr('Statut')}</dt><dd>{entry.status==='cancelled'?tr('Annulée'):tr('Active')}{entry.cancellation_reason&&' · '+entry.cancellation_reason}</dd></div></dl>}
