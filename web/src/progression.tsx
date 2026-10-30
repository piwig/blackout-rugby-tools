import {useEffect, useId, useMemo, useRef, useState} from 'react';
import {ArrowRight, CalendarDays, ChartNoAxesCombined, ChevronLeft, ChevronRight, RefreshCw, Users} from 'lucide-react';
import {request, type Actions} from './App';
import {fmt, labels, skills} from './types';
import './progression.css';

type Metric = 'csr' | typeof skills[number];
type PlayerPoint = {values:Record<Metric,number|null>; conflicts:Metric[]; revealed:Metric[]; deltas:Partial<Record<Metric,number>>; presence_conflict:boolean};
type CollectiveMetric = {value:number|null; known_count:number; unknown_count:number; conflict_count:number; delta:number|null; comparison:string};
type Point = {at:string; sources:{observed_at:string;source:string;precision:'day'|'naive'|'instant'}[]; roster_count:number; roster_count_exact:boolean; roster_ids:string[]; roster_changed:boolean; roster_conflict:boolean; players_truncated:boolean; date_precision:boolean; entered:string[]; left:string[]; players:Record<string,PlayerPoint>; metrics:Record<Metric,CollectiveMetric>};
type Series = {points:Point[];players:{id:string;name:string}[];total_snapshots:number;snapshot_count:number;snapshot_limit:number;invalid_dates:number;invalid_payloads:number;invalid_players:number;history_truncated:boolean;excluded_boundary_snapshots:number;player_limit:number;player_point_limit:number;budget_truncated_snapshots:number;omitted_player_observations:number;from:string|null;to:string|null};
type Bundle = {team_id:string;metrics:Metric[];seniors:Series;academy:Series};
type ChartRow = {point:Point;value:number|null;delta:number|null;status:string;known:number;total:number;conflict:boolean};
const metricLabel = (metric:string) => metric === 'csr' ? 'CSR observé' : labels[metric] || metric;
const dayLabel = (value:string) => new Date(value).toLocaleDateString('fr-FR',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const preciseLabel = (value:string) => new Date(value).toLocaleString('fr-FR',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})+' UTC';
const axisNumber = (value:number) => new Intl.NumberFormat('fr-FR',{notation:Math.abs(value)>=10000?'compact':'standard',maximumFractionDigits:1}).format(value);
const comparisonLabels:Record<string,string> = {first_observation:'Premier repère',conflicting_observation:'Observations contradictoires',truncated_roster:'Effectif limité',date_precision:'Ordre incertain dans cette journée',roster_changed:'Effectif différent',coverage_changed:'Joueurs renseignés différents',unknown:'Valeur inconnue',comparable:'Même effectif et mêmes joueurs renseignés'};

/** Kept pure so the table and chart always agree on gaps and revelations. */
export function buildProgressionRows(points:Point[], metric:Metric, playerId:string):ChartRow[] {
  return points.map(point => {
    if (!playerId) {
      const value = point.metrics[metric];
      return {point,value:value.value,delta:value.delta,status:comparisonLabels[value.comparison]||value.comparison,known:value.known_count,total:point.roster_count,conflict:value.conflict_count>0||point.roster_conflict};
    }
    const player = point.players[playerId];
    if (!player) return {point,value:null,delta:null,status:point.players_truncated?'Joueur absent de la sélection limitée':'Absent de cette observation',known:0,total:1,conflict:false};
    const value = player.values[metric], conflict = player.conflicts.includes(metric)||player.presence_conflict;
    const delta = !conflict && !player.revealed.includes(metric) ? player.deltas[metric] ?? null : null;
    const status = conflict ? 'Observations contradictoires' : player.revealed.includes(metric) ? 'Dévoilement · aucun gain calculé' : value === null ? 'Valeur inconnue' : point.date_precision ? 'Ordre incertain dans cette journée' : delta === null ? 'Repère sans comparaison' : delta === 0 ? 'Valeur stable' : 'Variation numérique observée';
    return {point,value,delta,status,known:value===null?0:1,total:1,conflict};
  });
}

function useProgression(d:Actions['d']) {
  const scope = d.user.username+':'+d.csrf+':'+d.current_team.id;
  const version = d.snapshots.map(snapshot=>snapshot.id).join(',');
  const [attempt,setAttempt]=useState(0);
  const [result,setResult]=useState<{scope:string;bundle:Bundle|null;error:string}|null>(null);
  useEffect(()=>{
    let active=true;
    setResult(null);
    if(!d.current_team.id)return ()=>{active=false;};
    request('/progression?team_id='+encodeURIComponent(d.current_team.id)).then((bundle:Bundle)=>{
      if(active && bundle.team_id === d.current_team.id)setResult({scope,bundle,error:''});
    }).catch((error:Error)=>{if(active)setResult({scope,bundle:null,error:error.message});});
    return ()=>{active=false;};
  },[scope,version,attempt]);
  return {bundle:result?.scope===scope?result.bundle:null,error:result?.scope===scope?result.error:'',reload:()=>setAttempt(value=>value+1)};
}

function ProgressionStatus({model}:{model:ReturnType<typeof useProgression>}) {
  return model.error ? <div className="notice error" role="alert">{model.error}<button className="text-button" onClick={model.reload}><RefreshCw size={15}/>Réessayer</button></div> : !model.bundle ? <p className="muted" role="status">Lecture des observations privées…</p> : null;
}

function Limits({series}:{series:Series}) {
  return <div className="progression-limits">
    <p>{series.snapshot_count} instantané(s) exploitable(s) affiché(s) sur {series.total_snapshots} conservé(s) · {series.points.length} dates distinctes.{series.from&&series.to&&<> Du {dayLabel(series.from)} au {dayLabel(series.to)}.</>}</p>
    {series.history_truncated&&<p className="notice">Affichage limité à {series.snapshot_limit} instantanés récents et {fmt(series.player_point_limit)} présences joueur détaillées.{series.budget_truncated_snapshots>0&&<> {series.budget_truncated_snapshots} instantané(s) plus ancien(s) écarté(s) pour respecter ce budget ; les dates conservées restent complètes.</>}{series.excluded_boundary_snapshots>0&&<> Un groupe de même date était incomplet à la limite : {series.excluded_boundary_snapshots} instantané(s) supplémentaire(s) écarté(s).</>}</p>}
    {series.invalid_dates>0&&<p className="notice">{series.invalid_dates} instantané(s) sans date exploitable exclu(s) des courbes.</p>}
    {series.invalid_payloads+series.invalid_players>0&&<p className="notice">{series.invalid_payloads} instantané(s) illisible(s) ou trop volumineux et {series.invalid_players} entrée(s) joueur invalide(s). Les observations concernées interrompent les comparaisons.</p>}
    {series.omitted_player_observations>0&&<p className="notice">Au plus {series.player_limit} joueurs détaillés par date ; au moins {series.omitted_player_observations} présence(s) au-delà de cette limite. Les identifiants sont sélectionnés dans un ordre fixe. Moyennes et variations collectives indisponibles sur ces dates ; un effectif précédé de ≥ est une borne minimale.</p>}
  </div>;
}

function HistoryChart({rows,title,collective}:{rows:ChartRow[];title:string;collective:boolean}) {
  const id=useId();
  const container=useRef<HTMLElement|null>(null),[chartWidth,setChartWidth]=useState(640);
  useEffect(()=>{
    if(!container.current)return;
    const element=container.current;
    const resize=()=>setChartWidth(Math.max(280,element.clientWidth));
    resize();
    const observer=new ResizeObserver(resize);observer.observe(element);
    return()=>observer.disconnect();
  },[rows.length>0&&rows.some(row=>row.value!==null)]);
  const known=rows.filter(row=>row.value!==null);
  if(!known.length)return <div className="progression-empty"><ChartNoAxesCombined size={30}/><h3>Aucune valeur exploitable sur cette sélection</h3><p>Choisissez une autre métrique, un autre joueur ou une période plus large. Les valeurs inconnues restent vides.</p></div>;
  const width=chartWidth,height=290,left=58,right=18,top=24,bottom=48;
  const values=known.map(row=>row.value as number),lo=Math.min(...values),hi=Math.max(...values);
  const pad=Math.max((hi-lo)*.12,hi===lo?Math.max(1,hi*.05):.1),min=Math.max(0,lo-pad),max=hi+pad;
  const first=Date.parse(rows[0].point.at),last=Date.parse(rows[rows.length-1].point.at);
  const x=(row:ChartRow)=>first===last?(left+width-right)/2:left+(Date.parse(row.point.at)-first)/(last-first)*(width-left-right);
  const y=(value:number)=>height-bottom-(value-min)/(max-min)*(height-top-bottom);
  const ticks=Array.from({length:4},(_,i)=>min+(max-min)*i/3);
  const dateIndices=Array.from(new Set(width<500?[0,rows.length-1]:[0,Math.floor((rows.length-1)/2),rows.length-1]));
  return <figure className="progression-chart" ref={container}>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={id+'-title '+id+'-description'}>
      <title id={id+'-title'}>{title} : {known.length} valeur(s) observée(s)</title>
      <desc id={id+'-description'}>Dates espacées selon le temps écoulé. Les points représentent les observations réelles ; les segments relient seulement deux observations successives comparables. Les valeurs et sources sont disponibles dans le tableau qui suit.</desc>
      {ticks.map((tick,i)=><g key={i}><line className="progression-gridline" x1={left} x2={width-right} y1={y(tick)} y2={y(tick)}/><text className="progression-axis" x={left-12} y={y(tick)+4} textAnchor="end">{axisNumber(tick)}</text></g>)}
      {rows.map((row,i)=>i>0&&row.value!==null&&rows[i-1].value!==null&&row.delta!==null&&!row.conflict&&!rows[i-1].conflict?<line key={'line'+i} className="progression-line" x1={x(rows[i-1])} y1={y(rows[i-1].value as number)} x2={x(row)} y2={y(row.value)}/>:null)}
      {known.map(row=><circle key={row.point.at} className={'progression-dot'+(row.conflict?' uncertain':'')} cx={x(row)} cy={y(row.value as number)} r={known.length===1?6:4}><title>{preciseLabel(row.point.at)} : {fmt(row.value)} · {row.status}</title></circle>)}
      {dateIndices.map((index,i)=><text key={index} className="progression-axis" x={x(rows[index])} y={height-14} textAnchor={dateIndices.length===1?'middle':i===0?'start':i===dateIndices.length-1?'end':'middle'}>{dayLabel(rows[index].point.at)}</text>)}
    </svg>
    <figcaption><span className="progression-legend-dot"/> Valeur observée <span className="progression-legend-line"/> Observations successives comparables.{collective&&' Les ruptures d’effectif ou de couverture ne sont pas reliées.'} {known.length===1?'Un seul point : aucune tendance calculable.':'Les segments sont des repères visuels, sans estimation entre deux dates.'}</figcaption>
  </figure>;
}

export function Progression(props:Actions) {
  return <ProgressionPanel key={props.d.user.username+':'+props.d.csrf+':'+props.d.current_team.id} {...props}/>;
}

function ProgressionPanel({d,go}:Actions) {
  const model=useProgression(d);
  const [population,setPopulation]=useState<'seniors'|'academy'>('seniors'),[metric,setMetric]=useState<Metric>('csr'),[playerId,setPlayerId]=useState('');
  const [period,setPeriod]=useState('all'),[from,setFrom]=useState(''),[to,setTo]=useState(''),[page,setPage]=useState(0);
  const series=model.bundle?.[population];
  useEffect(()=>{setPage(0);},[population,metric,playerId,period,from,to]);
  const points=useMemo(()=>{
    if(!series)return [];
    const latest=series.to?Date.parse(series.to):0;
    return series.points.filter(point=>{
      if(period==='custom')return (!from||point.at.slice(0,10)>=from)&&(!to||point.at.slice(0,10)<=to);
      return period==='all'||Date.parse(point.at)>=latest-Number(period)*86400000;
    });
  },[series,period,from,to]);
  const rows=useMemo(()=>buildProgressionRows(points,metric,playerId),[points,metric,playerId]);
  const playerName=series?.players.find(player=>player.id===playerId)?.name;
  const known=rows.filter(row=>row.value!==null),last=rows[rows.length-1];
  const pageSize=30,lastPage=Math.max(0,Math.ceil(rows.length/pageSize)-1),safePage=Math.min(page,lastPage);
  const tableRows=[...rows].reverse().slice(safePage*pageSize,(safePage+1)*pageSize);
  return <section className="card progression-panel" aria-label="Progression dans le temps">
    <div className="card-heading"><div><span className="eyebrow">OBSERVATIONS DATÉES</span><h2><ChartNoAxesCombined size={23}/>Votre effectif, dans le temps</h2><p className="muted">{d.current_team.name} · Les faits conservés, leurs variations et leurs limites.</p></div><button className="button secondary" onClick={()=>go('settings')}>Importer une observation<ArrowRight size={16}/></button></div>
    <div className="progression-body"><ProgressionStatus model={model}/>{series&&<>
      <div className="progression-filters">
        <label>Effectif<select value={population} onChange={event=>{const next=event.target.value as 'seniors'|'academy';setPopulation(next);setPlayerId('');setMetric(next==='academy'?'strength':'csr');}}><option value="seniors">Seniors</option><option value="academy">Académie</option></select></label>
        <label>Vue<select value={playerId} onChange={event=>setPlayerId(event.target.value)}><option value="">Collectif · moyenne des valeurs connues</option>{series.players.map(player=><option key={player.id} value={player.id}>{player.name} · #{player.id}</option>)}</select></label>
        <label>Métrique<select value={metric} onChange={event=>setMetric(event.target.value as Metric)}>{['csr',...skills].map(key=><option key={key} value={key}>{metricLabel(key)}</option>)}</select></label>
        <label>Période<select value={period} onChange={event=>setPeriod(event.target.value)}><option value="all">Tout l’historique retenu</option><option value="30">30 jours jusqu’au dernier relevé</option><option value="90">90 jours jusqu’au dernier relevé</option><option value="365">365 jours jusqu’au dernier relevé</option><option value="custom">Dates personnalisées (UTC)</option></select></label>
      </div>
      {period==='custom'&&<div className="progression-dates"><label>Du<input type="date" value={from} max={to||undefined} onChange={event=>setFrom(event.target.value)}/></label><label>Au<input type="date" value={to} min={from||undefined} onChange={event=>setTo(event.target.value)}/></label>{from&&to&&from>to&&<p className="text-error" role="alert">La date de fin doit suivre la date de début.</p>}</div>}
      <div className="progression-overview"><div><span>{playerId?playerName||'Joueur sélectionné':'Moyenne collective observée'}</span><strong>{metricLabel(metric)}</strong><p>{playerId?'Les variations décrivent deux observations successives, sans attribuer leur cause.':'Une moyenne peut changer avec les joueurs présents ou renseignés. Elle ne mesure pas à elle seule l’effet de l’entraînement.'}</p></div><div className="progression-stat"><span>Dernière date sélectionnée</span><strong>{last?fmt(last.value):'—'}</strong><small>{last?dayLabel(last.point.at):'Aucune date'} · {last?`${last.known}/${!playerId&&!last.point.roster_count_exact?'≥':''}${last.total} valeur(s) connue(s)`:'Aucune couverture'}</small></div><div className="progression-stat"><span>Points renseignés</span><strong>{known.length}<small> / {rows.length}</small></strong><small>Dans la sélection actuelle</small></div></div>
      <HistoryChart rows={rows} title={`${playerName||'Collectif'} · ${metricLabel(metric)}`} collective={!playerId}/>
      {!series.points.length&&<p className="notice">L’historique commence avec vos imports. Conservez plusieurs observations datées du même effectif pour pouvoir les comparer.</p>}
      <Limits series={series}/>
      {rows.length>0&&<details className="progression-table-section" open><summary>Valeurs, couverture et sources · {rows.length} date(s)</summary><div className="table-scroll"><table><caption className="progression-sr-only">{metricLabel(metric)} · {playerName||'Collectif'} · dates les plus récentes en premier</caption><thead><tr><th scope="col">Date et source</th><th scope="col">Valeur observée</th><th scope="col">Comparaison au relevé précédent</th><th scope="col">Couverture / effectif</th></tr></thead><tbody>{tableRows.map(row=><tr key={row.point.at}><td><time dateTime={row.point.at}>{dayLabel(row.point.at)}</time><details className="progression-sources"><summary>{row.point.sources.length} source(s) · date exacte</summary>{row.point.sources.map((source,index)=><p key={index}><strong>{source.source||'Source non renseignée'}</strong><small>{source.observed_at}{source.precision==='day'?' · date seule':source.precision==='naive'?' · fuseau absent, tri UTC':''}</small></p>)}</details></td><td><strong>{fmt(row.value)}</strong>{row.delta!==null&&<small className="sub-cell">Variation : {row.delta>0?'+':''}{fmt(row.delta)}</small>}</td><td><span className={row.conflict?'progression-tag warning':'progression-tag'}>{row.status}</span></td><td>{row.known}/{!playerId&&!row.point.roster_count_exact?'≥':''}{row.total} valeur(s) connue(s){!playerId&&<><small className="sub-cell">{!row.point.roster_count_exact?'≥':''}{row.point.roster_count} joueur(s) observé(s)</small>{row.point.roster_changed&&!row.point.players_truncated&&row.status!=='Effectif limité'&&<small className="sub-cell">{row.point.entered.length} arrivée(s) · {row.point.left.length} absence(s)</small>}{row.point.roster_conflict&&<small className="sub-cell">Listes d’effectif contradictoires ou incomplètes</small>}</>}</td></tr>)}</tbody></table></div><div className="progression-pagination"><span>{safePage*pageSize+1}–{Math.min((safePage+1)*pageSize,rows.length)} sur {rows.length} dates</span><button className="button secondary" disabled={safePage===0} onClick={()=>setPage(safePage-1)} aria-label="Dates plus récentes"><ChevronLeft size={17}/></button><button className="button secondary" disabled={safePage===lastPage} onClick={()=>setPage(safePage+1)} aria-label="Dates plus anciennes"><ChevronRight size={17}/></button></div></details>}
      <details className="progression-method"><summary>Comment lire cette progression ?</summary><p>Chaque point provient d’un instantané réellement conservé. Le CSR affiché vient de la source ; il n’est pas recalculé. Les compétences sont retenues entre 0 et 21. Une valeur inconnue n’est jamais remplacée par zéro.</p><p>Un dévoilement rend une valeur visible, sans mesurer un gain. Des valeurs contradictoires au même instant restent vides. L’absence d’un joueur ou une observation inexploitable interrompt sa comparaison. Aucun point intermédiaire et aucune prévision ne sont produits.</p><p>Le collectif est la moyenne des valeurs connues à chaque date. Une variation collective n’est affichée que si l’effectif et les identités des joueurs renseignés sont identiques, sans conflit. Même ainsi, aucune cause d’entraînement n’est déduite.</p><p>Les dates seules et les heures sans fuseau sont triées en UTC et signalées dans les sources. Les imports identiques peuvent être dédupliqués : une période sans point ne prouve ni absence d’activité ni stabilité.</p></details>
    </>}</div>
  </section>;
}

export function ProgressionSummary({d,go}:Actions) {
  const model=useProgression(d),bundle=model.bundle;
  return <section className="card progression-summary" aria-label="Repères de progression"><div className="card-heading"><div><span className="eyebrow">PRENDRE DU RECUL</span><h2><ChartNoAxesCombined size={21}/>Vos repères dans le temps</h2></div><button className="text-button" onClick={()=>go('progression')}>Explorer la progression<ArrowRight size={16}/></button></div><div className="progression-body"><ProgressionStatus model={model}/>{bundle&&<><div className="progression-summary-grid">{([['seniors','Seniors'],['academy','Académie']] as const).map(([kind,label])=>{const series=bundle[kind],count=series.points.length;return <button className="progression-summary-item" key={kind} onClick={()=>go('progression')}><Users size={20}/><span><strong>{label}</strong><small>{count?`${count} date${count>1?'s':''} conservée${count>1?'s':''}`:'Historique à commencer'}{series.history_truncated?' · sélection limitée':''}</small><small>{count>1?`${dayLabel(series.from!)} → ${dayLabel(series.to!)}`:count===1?'Un premier repère ; un autre relevé permettra une comparaison.':'Importez un effectif daté depuis Connexion & données.'}</small></span><ArrowRight size={17}/></button>;})}</div><p className="progression-summary-note"><CalendarDays size={15}/>Courbes issues des observations conservées, avec leurs sources et leur couverture.</p></>}</div></section>;
}
