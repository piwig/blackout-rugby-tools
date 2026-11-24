import {useEffect,useRef,useState} from 'react';
import {ArrowRight,BarChart3,Check,ChevronLeft,ChevronRight,ClipboardList,FileUp,RefreshCw} from 'lucide-react';
import {request,type Actions} from './App';
import {localeTag,tr} from './i18n';
import {formatStatistic as fmt,labels} from './types';
import {useUnsavedChanges} from './navigation-guard';
import {counterChange,csrDelta,statisticsRows,trainingReportSummary,type CoachingBundle,type CoachingKind,type CoachingPreview,type CountCoverage,type CsrCoverage,type Instructions,type PlayerStatistics,type ReportPlayer,type SkillChange,type SourceInfo,type TrainingReport,type TrainingReportSummary} from './coaching-model';
import './coaching.css';

const counterLabels:Record<string,string>={tackles:'Plaquages réussis',missed_tackles:'Plaquages manqués',tries:'Essais',total_points:'Points inscrits',metres_gained:'Mètres gagnés',carries:'Portées de balle',line_breaks:'Franchissements',try_assists:'Passes décisives',turnovers_won:'Ballons récupérés',penalties_conceded:'Pénalités concédées',handling_errors:'Erreurs de manipulation',yellow_cards:'Cartons jaunes',red_cards:'Cartons rouges',kicks:'Coups de pied',league_caps:'Matchs de championnat',friendly_caps:'Matchs amicaux',cup_caps:'Matchs de coupe'};
const metricGroups:Record<string,string[]>={attack:['tries','metres_gained','carries','try_assists'],defense:['tackles','missed_tackles','turnovers_won','penalties_conceded'],discipline:['handling_errors','penalties_conceded','yellow_cards','red_cards']};
const knownName=(player:{player_id:string;player_name?:string|null})=>player.player_name||tr('Joueur #{id}',{id:player.player_id});
const at=(value:string,timeStyle:'short'|'medium'='short')=>new Date(value).toLocaleString(localeTag(),{dateStyle:'medium',timeStyle});
const skill=(value:string|null)=>value===null?tr('Créneau libre'):value==='unreported'?tr('Non renseigné'):tr(labels[value]||value);
const scopeLabel=(doc:PlayerStatistics)=>doc.scope==='league'?tr('Championnat · saison {season}',{season:doc.season??'—'}):tr('Carrière des joueurs');
const isMail=(provenance:SourceInfo|null|undefined)=>provenance?.source==='Classic email';
const reportSource=(provenance:SourceInfo|null|undefined)=>isMail(provenance)?
  tr('Mail Classic · {format}',{format:provenance?.source_format?.toUpperCase()??'—'}):tr('API Classic');
const reportPeriod=(report:TrainingReport)=>tr('Saison {season} · semaine {round}',{season:report.season,round:report.round});
const signedCsr=(delta:number|null)=>delta!==null&&delta>0?'+'+fmt(delta):fmt(delta);

function SourceStamp({observed_at,provenance,preview=false}:{observed_at:string;provenance?:SourceInfo|null;preview?:boolean}){
  if(isMail(provenance))return <p className="coaching-source">{reportSource(provenance)} · {tr(preview?'Analysé le {date}':'Importé le {date}',{date:at(observed_at)})}</p>;
  const date=provenance?.source_game_date;
  return <p className="coaching-source">{tr('Source : API Classic · relevé du {date}',{date:at(observed_at)})}{date&&<> · {tr('S{season} / semaine {round} / jour {day}',date)}</>}</p>;
}

export function InstructionsView({data}:{data:Instructions}){
  return <div className="coaching-document">
    <SourceStamp observed_at={data.observed_at} provenance={data.provenance}/>
    <p>{tr('Voici les consignes configurées dans Classic au moment de la lecture. Elles ne prouvent pas que les séances ont été réalisées.')}</p>
    <div className="coaching-instructions-grid">{[[tr('Entraînement collectif'),data.team_skills],[tr('Consignes de l’académie'),data.youth_skills]].map(([title,values],index)=><section key={index} className="coaching-slot-card"><h3>{title as string}</h3>{values===null?<p className="notice">{tr('Cette information n’a pas été fournie par Classic.')}</p>:<ol>{(values as (string|null)[]).map((value,i)=><li key={i}><span>{tr('Créneau {slot}',{slot:i+1})}</span><strong>{skill(value)}</strong></li>)}</ol>}</section>)}</div>
    <details><summary>{tr('Consignes individuelles')} · {data.individual?.length??'—'}</summary>{data.individual===null?<p>{tr('Cette information n’a pas été fournie par Classic.')}</p>:!data.individual.length?<p>{tr('Aucune consigne individuelle renvoyée dans ce relevé.')}</p>:<div className="table-scroll"><table><thead><tr><th>{tr('Joueur')}</th><th>{tr('Compétence')}</th><th>{tr('Créneaux')}</th></tr></thead><tbody>{data.individual.map((row,i)=><tr key={row.player_id+':'+i}><td>{knownName(row)}</td><td>{skill(row.skill)}</td><td>{fmt(row.sessions)}</td></tr>)}</tbody></table></div>}</details>
  </div>;
}

function ReportChanges({changes,drops=false,trainedSkill}:{changes?:SkillChange[]|null;drops?:boolean;trainedSkill?:string}){
  if(changes==null)return <small className="sub-cell">{drops?tr('Baisses de niveau non renseignées'):tr('Passages de niveau non renseignés')}</small>;
  if(!changes.length)return <small className="sub-cell">{drops?tr('Aucune baisse de niveau signalée'):tr('Aucun passage de niveau signalé')}</small>;
  return <>{changes.map(change=><small className="sub-cell" key={change.skill}>
    {change.skill!==trainedSkill&&<>{skill(change.skill)} · </>}
    {change.before_label??fmt(change.before)} → {change.after_label??fmt(change.after)}
  </small>)}</>;
}

function PlayerTrainingDetails({player,individual}:{player:ReportPlayer;individual:boolean}){
  return <>
    {individual&&(<>
      {player.skills==null?<small className="sub-cell">{tr('Liste de compétences non renseignée')}</small>:
        !player.skills.length?<small className="sub-cell">{tr('Aucune compétence entraînée indiquée')}</small>:
        <ul className="coaching-skill-list">{player.skills.map(item=><li key={item.skill}>
          <strong>{skill(item.skill)}</strong> · {item.sessions==null?tr('Séances non renseignées'):tr('{count} séances',{count:fmt(item.sessions)})}
          {item.trainer&&<small className="sub-cell">
            {item.trainer.name??tr('Entraîneur')}{item.trainer.level!=null&&<> · {tr('niveau {level}',{level:fmt(item.trainer.level)})}</>}
            {item.trainer.type&&<> · {labels[item.trainer.type]?tr(labels[item.trainer.type]):item.trainer.type}</>}
          </small>}
          <ReportChanges changes={item.pops} trainedSkill={item.skill}/>
        </li>)}</ul>}
    </>)}
    {(!individual||player.pops!=null||!player.skills?.length)&&<ReportChanges changes={player.pops}/>}
    <ReportChanges changes={player.drops} drops/>
  </>;
}

function ReportTable({title,players,continuous}:{title:string;players:ReportPlayer[]|null;continuous?:Map<string,number|null>}){
  const [page,setPage]=useState(0),size=25,last=Math.max(0,Math.ceil((players?.length??0)/size)-1),safePage=Math.min(page,last);
  return <section className="coaching-report-group"><h3>{title}</h3>{players===null?<p className="notice">{tr('Cette partie du rapport n’a pas été fournie.')}</p>:!players.length?<p>{tr('Aucun joueur dans cette partie du rapport.')}</p>:<>
    <div className="table-scroll"><table>
      <caption className="sr-only">{title}</caption>
      <thead><tr><th>{tr('Joueur')}</th><th>{tr('CSR avant → après')}</th>{continuous&&<th>{tr('CSR total continu')}</th>}
        <th>{tr('Énergie avant → après')}</th><th>{tr('Compétences signalées')}</th></tr></thead>
      <tbody>{players.slice(safePage*size,(safePage+1)*size).map(player=>{
        const delta=csrDelta(player.csr_before,player.csr_after);
        const energy=player.energy;
        const before=energy?energy.before:player.energy_before,after=energy?energy.after:player.energy_after;
        return <tr key={player.player_id}>
          <td><strong>{knownName(player)}</strong><small className="sub-cell">#{player.player_id}</small></td>
          <td>{fmt(player.csr_before)} → {fmt(player.csr_after)}{delta!==null&&<small className="sub-cell">{tr('Variation : ')}{signedCsr(delta)}</small>}</td>
          {continuous&&<td>{signedCsr(continuous.get(player.player_id)??null)}</td>}
          <td>{energy?.kind==='label'?before??'—':fmt(before)} → {energy?.kind==='label'?after??'—':fmt(after)}
            {(before!=null||after!=null)&&energy?.kind!=='label'&&<small className="sub-cell">{tr('Échelle non précisée')}</small>}
          </td>
          <td><PlayerTrainingDetails player={player} individual={Boolean(continuous)}/></td>
        </tr>;
      })}</tbody>
    </table></div>
    {players.length>size&&<Pager page={safePage} total={players.length} size={size} onPage={setPage} label={tr('Joueurs du rapport')}/>}
  </>}</section>;
}

function CsrSummary({coverage}:{coverage:CsrCoverage}){
  const {delta,population,known,positive,negative,stable}=coverage;
  return <>
    <p className="coaching-csr-value"><strong>{signedCsr(delta)}</strong> CSR</p>
    <p>{population===null?tr('Population non fournie'):tr('{known}/{total} joueurs avec un écart CSR calculable',{known:fmt(known),total:fmt(population)})}</p>
    {known>0&&<p>{tr('{positive} en hausse · {negative} en baisse · {stable} stables',{positive:fmt(positive),negative:fmt(negative),stable:fmt(stable)})}</p>}
  </>;
}

function TrainingCount({label,value,unit}:{label:string;value:CountCoverage;unit:'players'|'skills'}){
  const args={known:fmt(value.known),total:fmt(value.entries)};
  return <div><dt>{label}</dt><dd><strong>{fmt(value.total)}</strong> · {unit==='skills'?
    tr('{known}/{total} entrées de compétence renseignées',args):tr('{known}/{total} joueurs renseignés',args)}</dd></div>;
}

function PhaseSummary({title,phase,individual=false}:{title:string;phase:TrainingReportSummary['team'];individual?:boolean}){
  return <section className="coaching-summary-card">
    <h4>{title}</h4>
    <CsrSummary coverage={phase.csr}/>
    {phase.csr.population!==null&&<dl className="coaching-training-counts">
      {phase.sessions&&<TrainingCount label={tr('Séances observées')} value={phase.sessions} unit="skills"/>}
      {phase.rises&&<TrainingCount label={tr('Passages de niveau observés')} value={phase.rises} unit={individual?'skills':'players'}/>}
      {phase.drops&&<TrainingCount label={tr('Baisses de niveau observées')} value={phase.drops} unit="players"/>}
    </dl>}
    {Boolean(phase.sessions?.missingSkillLists)&&<p>{tr('Listes de compétences manquantes pour {count} joueur(s)',{count:fmt(phase.sessions?.missingSkillLists)})}</p>}
  </section>;
}

export function TrainingReportView({data,preview=false}:{data:TrainingReport;preview?:boolean}){
  const {team,individual,continuous}=trainingReportSummary(data);
  const collectiveSkills=data.team?.skills;
  return <div className="coaching-document">
    <div className="coaching-report-heading"><h3>{reportPeriod(data)}</h3><SourceStamp observed_at={data.observed_at} provenance={data.provenance} preview={preview}/></div>
    {isMail(data.provenance)&&data.provenance?.club_name&&<p>{tr('Club déclaré dans le fichier')} · <strong>{data.provenance.club_name}</strong>
      {data.provenance.club_id&&<> · #{data.provenance.club_id}</>}</p>}
    {data.source_disagreement&&<p className="notice">{tr('Des rapports enregistrés pour cette période diffèrent sur des valeurs communes.')}</p>}
    <p>{tr('Ce bilan utilise les valeurs du rapport sélectionné. Un écart CSR peut être visible même sans passage de niveau.')}</p>
    <div className="coaching-report-summaries">
      <PhaseSummary title={tr('Collectif')} phase={team}/>
      <PhaseSummary title={tr('Individuel')} phase={individual} individual/>
      <section className="coaching-summary-card">
        <h4>{tr('CSR total continu')}</h4>
        <CsrSummary coverage={continuous.csr}/>
        {Boolean(continuous.csr.unknown)&&<p>{tr('Joueurs exclus du total continu · {count}',{count:fmt(continuous.csr.unknown)})}</p>}
        <p>{tr('Le total utilise les joueurs dont les deux phases ont un CSR complet et un raccord identique.')}</p>
        {continuous.populationIncomplete&&<p className="notice">{tr('Population totale partielle. Au moins une liste de joueurs est absente.')}</p>}
      </section>
    </div>
    {continuous.discontinuities.length>0&&<details className="coaching-breaks">
      <summary>{tr('Ruptures de continuité du CSR · {count}',{count:fmt(continuous.discontinuities.length)})}</summary>
      <ul>{continuous.discontinuities.map(row=><li key={row.player_id}>
        <strong>{knownName(row)}</strong> · {tr('Fin du collectif {before} · début de l’individuel {after}',{before:fmt(row.team_after),after:fmt(row.individual_before)})}
      </li>)}</ul>
    </details>}
    <p>{tr('Compétences collectives : ')}{collectiveSkills==null?tr('Non renseigné'):
      collectiveSkills.length?collectiveSkills.map(skill).join(' · '):tr('Aucune compétence indiquée')}</p>
    <ReportTable key={data.key+':team'} title={tr('Résultats collectifs')} players={data.team?.players??null}/>
    <ReportTable key={data.key+':individual'} title={tr('Résultats individuels')} players={data.individual?.players??null} continuous={continuous.players}/>
  </div>;
}

function Pager({page,total,size,onPage,label,disabled=false}:{page:number;total:number;size:number;onPage:(page:number)=>void;label:string;disabled?:boolean}){
  return <nav className="coaching-pagination" aria-label={label}><span>{tr('{from}–{to} sur {count}',{from:total?page*size+1:0,to:Math.min((page+1)*size,total),count:total})}</span><button className="button secondary" disabled={disabled||page===0} onClick={()=>onPage(page-1)}><ChevronLeft size={16}/>{tr('Précédent')}</button><button className="button secondary" disabled={disabled||(page+1)*size>=total} onClick={()=>onPage(page+1)}>{tr('Suivant')}<ChevronRight size={16}/></button></nav>;
}

export function PlayerStatisticsView({data,history=[]}:{data:PlayerStatistics;history?:PlayerStatistics[]}){
  const [query,setQuery]=useState(''),[group,setGroup]=useState('attack'),[metric,setMetric]=useState('tries'),[descending,setDescending]=useState(true),[page,setPage]=useState(0),[compareKey,setCompareKey]=useState('');
  const rows=statisticsRows(data.players,query,metric,descending),size=25,safePage=Math.min(page,Math.max(0,Math.ceil(rows.length/size)-1));
  const previous=history.filter(row=>row.scope===data.scope&&row.season===data.season&&Date.parse(row.observed_at)<Date.parse(data.observed_at));
  const base=previous.find(row=>row.key===compareKey);
  const columns=[...new Set([...metricGroups[group],metric])];
  const known=data.players.filter(row=>typeof row.counters[metric]==='number').length;
  useEffect(()=>setPage(0),[query,group,metric,descending]);
  return <div className="coaching-document"><SourceStamp observed_at={data.observed_at} provenance={data.provenance}/><p className="notice">{tr('Ces compteurs concernent les joueurs de l’effectif au moment de la collecte. Leur carrière peut inclure d’autres clubs. Classic ne fournit ici ni les minutes jouées ni les postes : aucun taux par 80 minutes n’est calculé.')}</p>
    <div className="coaching-metrics"><div><span>{tr('Périmètre')}</span><strong>{scopeLabel(data)}</strong></div><div><span>{tr('Joueurs renseignés')}</span><strong>{data.players.length} / {data.requested_count}</strong></div><div><span>{tr(counterLabels[metric])}</span><strong>{tr('{known}/{total} valeurs connues',{known,total:data.players.length})}</strong></div></div>
    {data.missing_player_ids.length>0&&<p className="notice">{tr('{count} joueurs demandés n’ont pas été renvoyés. Leurs valeurs restent inconnues.',{count:data.missing_player_ids.length})}</p>}
    <div className="coaching-filters"><label>{tr('Rechercher un joueur')}<input value={query} onChange={e=>setQuery(e.target.value)} placeholder={tr('Nom ou identifiant')}/></label><label>{tr('Lecture du jeu')}<select value={group} onChange={e=>{setGroup(e.target.value);setMetric(metricGroups[e.target.value][0])}}><option value="attack">{tr('Attaque')}</option><option value="defense">{tr('Défense')}</option><option value="discipline">{tr('Discipline')}</option></select></label><label>{tr('Trier sur')}<select value={metric} onChange={e=>setMetric(e.target.value)}>{Object.entries(counterLabels).map(([key,label])=><option key={key} value={key}>{tr(label)}</option>)}</select></label><label>{tr('Ordre')}<select value={descending?'desc':'asc'} onChange={e=>setDescending(e.target.value==='desc')}><option value="desc">{tr('Décroissant')}</option><option value="asc">{tr('Croissant')}</option></select></label></div>
    {previous.length>0&&<label className="coaching-compare">{tr('Comparer avec un relevé antérieur du même périmètre')}<select value={base?.key??''} onChange={e=>setCompareKey(e.target.value)}><option value="">{tr('Sans comparaison')}</option>{previous.map(row=><option key={row.key} value={row.key}>{at(row.observed_at)} · {row.players.length} {tr('joueurs')}</option>)}</select></label>}
    {!rows.length?<p className="coaching-empty">{tr('Aucun joueur ne correspond à cette sélection.')}</p>:<div className="table-scroll"><table><caption className="sr-only">{scopeLabel(data)}</caption><thead><tr><th>{tr('Joueur')}</th>{columns.map(key=><th key={key}>{tr(counterLabels[key])}</th>)}{group==='defense'&&<th>{tr('Plaquages réussis (%)')}</th>}{base&&<th>{tr('Écart observé')} · {tr(counterLabels[metric])}</th>}</tr></thead><tbody>{rows.slice(safePage*size,(safePage+1)*size).map(player=>{
      const old=base?.players.find(row=>row.player_id===player.player_id),change=base?counterChange(base,data,old?.counters[metric],player.counters[metric]):null;
      return <tr key={player.player_id}><td><strong>{knownName(player)}</strong><small className="sub-cell">#{player.player_id}</small></td>{columns.map(key=><td key={key}>{fmt(player.counters[key])}</td>)}{group==='defense'&&<td>{player.tackle_success_rate===null||player.tackle_success_rate===undefined?'—':fmt(player.tackle_success_rate)+' %'}</td>}{base&&<td>{change?.delta!==null?`${change!.delta!>0?'+':''}${fmt(change!.delta)}`:change?.reason==='counter_reset'?tr('Compteur revu à la baisse'):'—'}</td>}</tr>;
    })}</tbody></table></div>}
    {rows.length>size&&<Pager page={safePage} total={rows.length} size={size} onPage={setPage} label={tr('Pagination des statistiques individuelles')}/>}
    <p className="tiny">{tr('Une valeur absente reste « — ». Le pourcentage de plaquages utilise réussis ÷ (réussis + manqués), uniquement si les deux compteurs sont connus et leur somme positive. Les écarts comparent des relevés cumulés de même périmètre, sans attribuer la variation à un match précis.')}</p>
  </div>;
}

export function ClassicCoaching(props:Actions&{mode:'training'|'statistics'}){
  const {d,mode}=props;
  if(d.current_team.kind==='u20'||d.current_team.kind==='nt')return <section className="card prose"><h2>{tr('Rapports réservés aux clubs')}</h2><p>{tr('Les rapports d’entraînement et ces statistiques individuelles sont disponibles ici pour les clubs liés à votre compte Classic.')}</p></section>;
  return <CoachingPanel key={d.user.username+':'+d.csrf+':'+d.current_team.id+':'+mode} {...props}/>;
}

type CoachingOperation='classic'|'file'|'confirm';

function CoachingPanel({d,busy,go,mode}:Actions&{mode:'training'|'statistics'}){
  const [kind,setKind]=useState<CoachingKind>(mode==='statistics'?'statistics':'instructions'),[scope,setScope]=useState('career'),[latest,setLatest]=useState(true),[season,setSeason]=useState(d.game_date?String(d.game_date.season):''),[round,setRound]=useState(d.game_date?String(d.game_date.round):'');
  const [bundle,setBundle]=useState<CoachingBundle|null>(null),[preview,setPreview]=useState<CoachingPreview|null>(null);
  const [file,setFile]=useState<File|null>(null),[pending,setPending]=useState<CoachingOperation|null>(null);
  const [error,setError]=useState(''),[loadError,setLoadError]=useState(''),[message,setMessage]=useState('');
  const [loading,setLoading]=useState(true),[reload,setReload]=useState(0),[offset,setOffset]=useState(0),[selected,setSelected]=useState('');
  const mounted=useRef(true),operation=useRef<{id:number;type:CoachingOperation}|null>(null);
  const ticket=useRef(0),loadGeneration=useRef(0),fileInput=useRef<HTMLInputElement>(null);
  const identity=d.user.username+':'+d.csrf+':'+d.current_team.id+':'+mode,current=useRef(identity);
  current.current=identity;
  const base='/clubs/'+encodeURIComponent(d.current_team.id)+'/coaching';
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;ticket.current++}},[]);
  useEffect(()=>{
    let active=true;
    const generation=++loadGeneration.current;
    const matches=()=>active&&generation===loadGeneration.current&&current.current===identity;
    setLoading(true);
    setLoadError('');
    const query=new URLSearchParams({report_offset:String(mode==='training'?offset:0),statistics_offset:String(mode==='statistics'?offset:0)});
    request(base+'?'+query,undefined,d.csrf)
      .then((result:CoachingBundle)=>{if(matches()&&result.team_id===d.current_team.id)setBundle(result)})
      .catch((e:Error)=>{if(matches())setLoadError(e.message)})
      .finally(()=>{if(matches())setLoading(false)});
    return()=>{active=false};
  },[base,d.csrf,mode,offset,reload,identity]);
  useUnsavedChanges(pending!==null||preview!==null||file!==null);
  const locked=busy||pending!==null,hasAccess=Boolean(d.classic_account?.team_ids.includes(d.current_team.id)&&d.settings.developer_ready);
  const classicDisabled=locked||preview!==null;
  const fileLocked=busy||pending==='confirm'||pending==='classic'||(preview!==null&&!preview.identity);
  const needsSeason=kind==='statistics'&&scope==='league'||kind==='report'&&!latest;
  const valid=!needsSeason||/^\d+$/.test(season)&&Number(season)>=1&&Number(season)<=999&&(kind!=='report'||/^\d+$/.test(round)&&Number(round)>=1&&Number(round)<=16);
  const run=async(type:CoachingOperation,action:(matches:()=>boolean)=>Promise<void>)=>{
    if(busy||operation.current)return;
    const id=++ticket.current;
    operation.current={id,type};
    const matches=()=>mounted.current&&current.current===identity&&ticket.current===id;
    setPending(type);
    setError('');
    setMessage('');
    try{
      await action(matches);
    }catch(e){
      if(matches()){
        const failure=e as Error&{status?:number};
        setError(failure.message);
        if(type==='confirm'&&preview?.identity&&failure.status===409)setPreview(null);
      }
    }finally{
      if(operation.current?.id===id){
        operation.current=null;
        if(matches())setPending(null);
      }
    }
  };
  const clearFile=()=>{
    setFile(null);
    if(fileInput.current)fileInput.current.value='';
  };
  const selectFile=(next:File|null)=>{
    if(fileLocked||(operation.current&&operation.current.type!=='file'))return;
    if(operation.current?.type==='file'){
      ticket.current++;
      operation.current=null;
      setPending(null);
    }
    if(next)setFile(next);
    else clearFile();
    setPreview(null);
    setError('');
    setMessage('');
  };
  const preparePreview=(type:'classic'|'file',path:string,body:unknown)=>void run(type,async matches=>{
    const result=await request(base+path,body,d.csrf) as CoachingPreview;
    if(matches()&&result.team_id===d.current_team.id)setPreview(result);
  });
  const read=()=>{
    if(!hasAccess||!valid||preview)return;
    const period=kind==='statistics'?{scope,...(scope==='league'?{season:Number(season)}:{})}:
      kind==='report'&&!latest?{season:Number(season),round:Number(round)}:{};
    preparePreview('classic','/preview',{kind,...period});
  };
  const upload=()=>{
    if(!file||preview)return;
    const form=new FormData();
    form.append('file',file);
    preparePreview('file','/import-preview',form);
  };
  const confirm=()=>{
    if(!preview)return;
    void run('confirm',async matches=>{
      const result=await request(base+'/confirm',{preview_id:preview.preview_id,expected_revision:preview.expected_revision},d.csrf);
      if(!matches()||result.bundle.team_id!==d.current_team.id)return;
      loadGeneration.current++;
      setLoading(false);
      setLoadError('');
      setBundle(result.bundle);
      setPreview(null);
      if(preview.identity)clearFile();
      setSelected(preview.data.key);
      setOffset(0);
      setMessage(result.unchanged?'unchanged':'saved');
    });
  };
  const cancel=()=>{
    if(locked||operation.current)return;
    ticket.current++;
    if(preview?.identity)clearFile();
    setPreview(null);
    setError('');
  };
  const history=mode==='statistics'?bundle?.statistics:bundle?.reports;
  const document=history?.find(item=>item.key===selected)||history?.[0];
  const total=(mode==='statistics'?bundle?.statistics_total:bundle?.report_total)??0,size=bundle?.history_limit??20;
  return <section className="card coaching-panel" aria-label={tr(mode==='statistics'?'Statistiques individuelles':'Rapports d’entraînement Classic')}>
    <div className="card-heading"><div><span className="eyebrow">{tr('LE CARNET DU STAFF')}</span><h2>{mode==='statistics'?<BarChart3 size={24}/>:<ClipboardList size={24}/>} {tr(mode==='statistics'?'Les chiffres derrière les actions':'Consignes et rapports d’entraînement')}</h2><p>{tr(mode==='statistics'?'Relisez les performances des joueurs, avec le périmètre et les valeurs disponibles.':'Consultez les consignes du jeu et conservez ses rapports, sans confondre prévu et réalisé.')}</p></div><button className="button secondary" disabled={classicDisabled||loading} onClick={()=>setReload(n=>n+1)}><RefreshCw size={16}/>{tr('Relire mes relevés')}</button></div>
    <div className="coaching-body">
      {!hasAccess&&<div className="notice"><span>{tr(mode==='training'?'La lecture par l’API nécessite le compte Classic propriétaire. Vous pouvez importer un fichier ci-dessous.':'Reliez le compte Classic propriétaire de ce club pour lire ses rapports.')}</span><button className="text-button" onClick={()=>go('settings')}>{tr('Connexion & données')}<ArrowRight size={16}/></button></div>}
      <form className="coaching-import" aria-label={tr('Lecture par l’API Classic')} onSubmit={e=>{e.preventDefault();read()}}>
        {mode==='training'&&<label>{tr('Que voulez-vous lire ?')}<select value={kind} disabled={classicDisabled} onChange={e=>{setKind(e.target.value as CoachingKind);setError('');setMessage('')}}><option value="instructions">{tr('Consignes actuelles')}</option><option value="report">{tr('Rapport d’entraînement')}</option></select></label>}
        {kind==='report'&&<label>{tr('Période du rapport')}<select value={latest?'latest':'period'} disabled={classicDisabled} onChange={e=>setLatest(e.target.value==='latest')}><option value="latest">{tr('Dernier rapport disponible')}</option><option value="period">{tr('Choisir une semaine')}</option></select></label>}
        {kind==='statistics'&&<label>{tr('Périmètre des compteurs')}<select value={scope} disabled={classicDisabled} onChange={e=>setScope(e.target.value)}><option value="career">{tr('Carrière des joueurs')}</option><option value="league">{tr('Championnat · une saison')}</option></select></label>}
        {needsSeason&&<label>{tr('Saison')}<input type="number" min="1" max="999" step="1" required value={season} disabled={classicDisabled} onChange={e=>setSeason(e.target.value)}/></label>}
        {kind==='report'&&!latest&&<label>{tr('Semaine')}<input type="number" min="1" max="16" step="1" required value={round} disabled={classicDisabled} onChange={e=>setRound(e.target.value)}/></label>}
        <button className="button primary" disabled={classicDisabled||!valid||!hasAccess}><RefreshCw size={16} className={pending==='classic'?'spin':''}/>{tr(pending==='classic'?'Lecture en cours…':'Lire Classic et voir l’aperçu')}</button>
      </form>
      <p className="tiny">{tr('La lecture démarre uniquement avec ce bouton. Vérifiez l’aperçu avant de le conserver ; aucune consigne n’est envoyée au jeu.')}</p>
      {mode==='training'&&<form className="coaching-import coaching-file-import" aria-label={tr('Importer un rapport reçu par mail')} onSubmit={e=>{e.preventDefault();upload()}}>
        <div className="coaching-file-intro"><h3>{tr('Importer un rapport reçu par mail')}</h3>
          <p>{tr('Rapport Classic en anglais, au format HTML ou EML, de 2 Mio maximum.')}</p></div>
        <label>{tr('Fichier du rapport')}<input ref={fileInput} type="file" accept=".html,.eml" disabled={fileLocked}
          onChange={e=>selectFile(e.currentTarget.files?.[0]??null)}/></label>
        <button className="button primary" disabled={locked||!file||preview!==null}><FileUp size={16}/>{tr(pending==='file'?'Analyse du fichier…':'Voir l’aperçu du fichier')}</button>
        {file&&<button className="button secondary" type="button" disabled={fileLocked} onClick={()=>selectFile(null)}>{tr('Retirer le fichier')}</button>}
      </form>}
      {error&&<p className="notice error" role="alert">{tr(error)}</p>}{message&&<p className="notice success" role="status"><Check size={17}/>{message==='unchanged'?tr('Ce relevé était déjà conservé. Aucun doublon n’a été ajouté.'):tr('Relevé conservé dans votre espace privé.')}</p>}
      {preview&&<section className="coaching-preview" aria-label={tr(preview.identity?'Aperçu du fichier':'Aperçu du relevé Classic')}>
        <div className="coaching-preview-heading"><span className="eyebrow">{tr('À VÉRIFIER AVANT CONSERVATION')}</span><p>{tr('Cet aperçu expire le {date}.',{date:at(preview.expires_at)})}</p></div>
        <p>{tr('Destination')} · <strong>{d.current_team.name}</strong></p>
        {preview.identity&&<p>{tr('{known}/{total} joueurs figurent dans le dernier effectif senior enregistré.',{
          known:fmt(preview.identity.roster_match_count),total:fmt(preview.identity.player_count)})}</p>}
        {preview.already_imported&&<p className="notice">{tr('Ce relevé est déjà présent dans votre historique.')}</p>}{preview.warnings.map((warning,i)=><p className="notice" key={i}>{tr(warning)}</p>)}
        {preview.kind==='instructions'?<InstructionsView data={preview.data as Instructions}/>:preview.kind==='report'?<TrainingReportView data={preview.data as TrainingReport} preview/>:<PlayerStatisticsView key={preview.preview_id} data={preview.data as PlayerStatistics}/>}
        <div className="coaching-preview-actions"><button className="button primary" disabled={locked} onClick={confirm}><Check size={17}/>{tr(pending==='confirm'?'Conservation en cours…':'Conserver ce relevé')}</button><button className="button secondary" disabled={locked} onClick={cancel}>{tr('Annuler cet aperçu')}</button></div>
      </section>}
      {loading&&<p role="status">{tr('Lecture de vos relevés conservés…')}</p>}
      {loadError&&<p className="notice error" role="alert">{tr(loadError)}</p>}
      {bundle&&!loading&&<div className="coaching-saved"><h3>{tr('Dans votre carnet privé')}</h3>
        {mode==='training'&&bundle.instructions&&<details className="coaching-current" open><summary>{tr('Dernières consignes conservées')}</summary><InstructionsView data={bundle.instructions}/></details>}
        {history?.length?<><label>{tr(mode==='statistics'?'Choisir un relevé statistique':'Choisir un rapport conservé')}<select value={document?.key||''} onChange={e=>setSelected(e.target.value)}>{history.map(item=><option key={item.key} value={item.key}>
          {mode==='statistics'?scopeLabel(item as PlayerStatistics):<>{reportPeriod(item as TrainingReport)} · {reportSource(item.provenance)}</>} · {at(item.observed_at,mode==='training'?'medium':'short')}
        </option>)}</select></label>{mode==='statistics'&&total>size&&<p className="tiny">{tr('La comparaison utilise les observations de cette page. Changez de page pour consulter le reste de l’historique.')}</p>}{document&&(mode==='statistics'?<PlayerStatisticsView key={document.key} data={document as PlayerStatistics} history={bundle.statistics}/>:<TrainingReportView key={document.key} data={document as TrainingReport}/>)}<Pager disabled={classicDisabled} page={Math.floor(offset/size)} total={total} size={size} onPage={page=>{if(!locked&&!preview){setSelected('');setOffset(page*size)}}} label={tr('Pagination des relevés conservés')}/></>:<div className="coaching-empty"><ClipboardList size={26}/><p>{tr(mode==='statistics'?'Votre historique statistique commencera avec le premier relevé conservé.':'Aucun rapport conservé pour le moment. Un refus de Classic ne signifie pas que les joueurs n’ont pas progressé.')}</p></div>}
      </div>}
    </div>
  </section>;
}
