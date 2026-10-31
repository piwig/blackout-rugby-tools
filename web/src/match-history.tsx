import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,ChevronLeft,ChevronRight,RefreshCw} from 'lucide-react';
import {request,type Actions} from './App';
import {Empty,Pill} from './components';
import {tr} from './i18n';
import {fmt,type Match} from './types';
import './match-review.css';

type HistoryTotals={matches:number;scored_matches:number;events:number;classified:number;unclassified:number;non_attack:number;manual:number;inferred:number;coverage_pct:number|null;points_total:number;points_per_match:number|null};
type HistoryBucket={name:string;count:number;percent:number|null};
type MatchHistoryReport={options:{seasons:number[];teams:string[];types:number[]};mixed_types:boolean;total_stored:number;total_filtered:number;matches:Match[];totals:HistoryTotals;attacks:HistoryBucket[];zones:HistoryBucket[];by_season:{season:number|null;matches:number;scored_matches:number;points_total:number;classified:number;events:number;coverage_pct:number|null}[];team_record:{played:number;scored_matches:number;won:number;drawn:number;lost:number;points_for:number;points_against:number;win_pct:number|null}|null};

export function MatchHistory({d,busy,selected,onSelect}:Pick<Actions,'d'|'busy'>&{selected:Match|null;onSelect:(match:Match)=>void}) {
  const [kind,setKind]=useState('all'),[season,setSeason]=useState('all'),[team,setTeam]=useState(''),[page,setPage]=useState(0),[refresh,setRefresh]=useState(0);
  const [report,setReport]=useState<MatchHistoryReport|null>(null),[loadedKey,setLoadedKey]=useState(''),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const generation=useRef(0),scope=d.user.username+':'+d.csrf,current=useRef(scope);current.current=scope;
  const query=new URLSearchParams({offset:String(page*20),limit:'20'});if(kind!=='all')query.set('type',kind);if(season!=='all')query.set('season',season);if(team&&kind!=='all')query.set('team',team);
  const queryKey=query.toString();
  useEffect(()=>{
    const ticket=++generation.current;setLoading(true);setError('');
    request('/matches/history?'+queryKey).then((result:MatchHistoryReport)=>{
      if(ticket!==generation.current||current.current!==scope)return;
      if(page>0&&page*20>=result.total_filtered){setPage(Math.max(0,Math.ceil(result.total_filtered/20)-1));return}
      setReport(result);setLoadedKey(queryKey);
    }).catch(e=>{if(ticket===generation.current&&current.current===scope)setError((e as Error).message)}).finally(()=>{if(ticket===generation.current&&current.current===scope)setLoading(false)});
    return()=>{generation.current++};
  },[queryKey,refresh,d.matches,scope]);
  const visible=loadedKey===queryKey?report:null,totals=visible?.totals,record=visible?.team_record;
  const pageCount=Math.max(1,Math.ceil((visible?.total_filtered??0)/20));
  const options=report?.options;
  return <section className="card match-history" aria-labelledby="match-history-title" aria-busy={loading}>
    <div className="card-heading"><div><span className="eyebrow">{tr("VOS MATCHS CONSERVÉS")}</span><h2 id="match-history-title">{tr("Retrouvez vos anciennes rencontres.")}</h2><p>{tr("Explorez toute votre bibliothèque privée et les statistiques réellement disponibles, par type, saison et équipe.")}</p></div><button className="button secondary" disabled={loading||busy} onClick={()=>setRefresh(value=>value+1)}><RefreshCw size={15}/>{tr("Actualiser les statistiques")}</button></div>
    <div className="match-history-filters"><label>{tr("Type du match")}<select value={kind} disabled={busy} onChange={e=>{setKind(e.target.value);setTeam('');setPage(0)}}><option value="all">{tr("Tous les types")}</option><option value="0">{tr("Clubs")}</option><option value="1">{tr("U20")}</option><option value="2">{tr("Nationales")}</option></select></label><label>{tr("Saison")}<select value={season} disabled={busy} onChange={e=>{setSeason(e.target.value);setPage(0)}}><option value="all">{tr("Toutes les saisons")}</option>{options?.seasons.map(value=><option key={value} value={value}>{tr('Saison {season}',{season:value})}</option>)}</select></label><label>{tr("Équipe")}<select value={team} disabled={busy||kind==='all'} onChange={e=>{setTeam(e.target.value);setPage(0)}}><option value="">{kind==='all'?tr("Choisissez d’abord un type"):tr("Toutes les équipes")}</option>{options?.teams.map(value=><option key={value} value={value}>{value}</option>)}</select></label></div>
    {error&&<p className="notice error" role="alert">{tr(error)}</p>}
    {loading&&<p role="status" className="match-history-loading">{tr("Lecture de votre historique…")}</p>}
    {!loading&&!error&&visible&&totals&&<>
      <p className="match-history-count" role="status">{tr('{filtered} matchs sélectionnés sur {total} matchs conservés',{filtered:visible.total_filtered,total:visible.total_stored})}</p>
      {visible.mixed_types&&<p className="notice">{tr("Cette vue rassemble plusieurs types de rencontres. Ces totaux décrivent la bibliothèque ; ils ne comparent pas les performances des clubs et des sélections.")}</p>}
      {team&&<p className="tiny">{tr("Le filtre utilise le nom exact importé. Deux noms différents ne sont pas regroupés comme une seule équipe.")}</p>}
      <div className="match-review-metrics match-history-metrics"><div><strong>{totals.matches}</strong><span>{tr("Rencontres")}</span><small>{tr('{count} scores connus',{count:totals.scored_matches})}</small></div><div><strong>{fmt(totals.coverage_pct)}{totals.coverage_pct!==null?' %':''}</strong><span>{tr("Couverture des attaques")}</span><small>{tr('{classified} sur {events} événements',{classified:totals.classified,events:totals.events})}</small></div><div><strong>{totals.unclassified}</strong><span>{tr("Événements à relire")}</span><small>{tr('{count} événements hors attaque',{count:totals.non_attack})}</small></div><div><strong>{totals.scored_matches?fmt(totals.points_per_match):'—'}</strong><span>{tr("Points par match")}</span><small>{tr("Deux équipes réunies, scores connus uniquement")}</small></div></div>
      {record&&<section className="match-history-record" aria-label={tr('Bilan de {team}',{team})}><h3>{team}</h3><div><span><strong>{record.won}</strong>{tr("Victoires")}</span><span><strong>{record.drawn}</strong>{tr("Nuls")}</span><span><strong>{record.lost}</strong>{tr("Défaites")}</span><span><strong>{record.scored_matches?fmt(record.win_pct)+' %':'—'}</strong>{tr("Taux de victoire")}</span><span><strong>{record.scored_matches?record.points_for:'—'}</strong>{tr("Points marqués")}</span><span><strong>{record.scored_matches?record.points_against:'—'}</strong>{tr("Points encaissés")}</span></div><p className="tiny">{tr('Bilan calculé sur {scored} scores connus parmi {played} rencontres.',{scored:record.scored_matches,played:record.played})}</p></section>}
      {totals.matches>0&&<>
        <div className="match-history-distributions"><HistoryDistribution title={tr("Types d’attaque")} values={visible.attacks}/><HistoryDistribution title={tr("Zones de jeu")} values={visible.zones}/></div>
        <p className="tiny">{tr('Répartition parmi {count} attaques avec côté et zone connus, pour les deux équipes. Dont {manual} classements manuels et {inferred} estimations textuelles.',{count:totals.classified,manual:totals.manual,inferred:totals.inferred})}</p>
        {visible.by_season.length>0&&<details className="match-history-seasons"><summary>{tr("Voir les repères par saison")}</summary><div className="table-scroll"><table><thead><tr><th scope="col">{tr("SAISON")}</th><th scope="col">{tr("MATCHS")}</th><th scope="col">{tr("SCORES CONNUS")}</th><th scope="col">{tr("POINTS CUMULÉS")}</th><th scope="col">{tr("ATTAQUES / ÉVÉNEMENTS")}</th><th scope="col">{tr("COUVERTURE")}</th></tr></thead><tbody>{visible.by_season.map(row=><tr key={row.season??'unknown'}><th scope="row">{row.season??tr("Saison inconnue")}</th><td>{row.matches}</td><td>{row.scored_matches}</td><td>{row.scored_matches?row.points_total:'—'}</td><td>{row.classified} / {row.events}</td><td>{row.coverage_pct===null?'—':fmt(row.coverage_pct)+' %'}</td></tr>)}</tbody></table></div></details>}
      </>}
      {visible.matches.length?<div className="match-grid match-history-grid">{visible.matches.map(m=><button className={'card match-card '+(String(selected?.id)===String(m.id)&&selected?.type===m.type?'selected':'')} key={m.type+':'+m.id} disabled={busy} onClick={()=>onSelect(m)} aria-label={tr('Ouvrir {home} contre {away}, match {id}',{home:m.home,away:m.away,id:m.id})}><div><Pill tone="neutral">{tr(['Club','U20','National'][m.type])}</Pill><span>#{m.id}</span></div><div className="match-teams"><strong>{m.home}</strong><b>{m.home_score??'—'} <span>:</span> {m.away_score??'—'}</b><strong>{m.away}</strong></div><p className="tiny">{tr('Saison {season} · Tour {round}',{season:m.season??'—',round:m.round??'—'})}</p><div className="match-card-foot"><span>{tr('Actions classées : {classified} · Événements : {count}',{classified:m.summary.classified??0,count:m.event_count??m.summary.total_events??0})}</span><ArrowUpRight size={17}/></div></button>)}</div>:<Empty title={tr("Aucun match dans cette sélection")}>{visible.total_stored?tr("Modifiez les filtres pour retrouver vos rencontres."):tr("Importez une rencontre depuis Classic pour commencer votre historique.")}</Empty>}
      {pageCount>1&&<nav className="match-review-pagination" aria-label={tr("Pagination de l’historique des matchs")}><button className="button secondary" disabled={page===0||busy} onClick={()=>setPage(value=>value-1)}><ChevronLeft size={16}/>{tr("Précédent")}</button><span>{tr('Page {page} sur {pages} · {count} matchs',{page:page+1,pages:pageCount,count:visible.total_filtered})}</span><button className="button secondary" disabled={page>=pageCount-1||busy} onClick={()=>setPage(value=>value+1)}>{tr("Suivant")}<ChevronRight size={16}/></button></nav>}
    </>}
  </section>;
}

export function HistoryDistribution({title,values}:{title:string;values:HistoryBucket[]}) {
  const names:Record<string,string>={'22':'Nos 22 m','40':'Notre moitié','40A':'Moitié adverse','22A':'Leurs 22 m'};
  return <section className="match-history-distribution"><h3>{title}</h3><ul>{values.map(row=><li key={row.name}><div><span>{tr(names[row.name]??row.name)}</span><strong>{row.count}<small>{row.percent===null?'—':fmt(row.percent)+' %'}</small></strong></div><div className="match-history-track" aria-hidden="true"><i style={{width:Math.max(0,Math.min(100,row.percent??0))+'%'}}/></div></li>)}</ul></section>;
}
