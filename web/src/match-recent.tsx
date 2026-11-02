import {useEffect,useId,useRef,useState} from 'react';
import {Cloud,History,RefreshCw} from 'lucide-react';
import {tr,localeTag} from './i18n';
import {formatStatistic as fmt} from './types';
import {request} from './App';
import {isRecentComparison,recentFixtureLink,type RecentComparison,type RecentMatch} from './match-recent-model';
import './match-recent.css';

type Props={teamId:string;kind:number;fixtureId:string;participants:[string,string];csrf:string;busy:boolean};
const moment=(v:string|null)=>v?new Date(v).toLocaleString(localeTag(),{dateStyle:'medium',timeStyle:'short'}):tr('Date inconnue');
const ratingLabels=()=>({scrum:tr('Mêlée'),lineout:tr('Touche'),kicking:tr('Jeu au pied'),ruck:tr('Ruck'),maul:tr('Maul'),handling:tr('Dextérité'),attack:tr('Attaque'),defense:tr('Défense'),stamina:tr('Endurance'),pickandgo:tr('Pick and go'),driving:tr('Percussion'),expansive:tr('Large'),creative:tr('Créatif')});

export function RecentMatchComparison({teamId,kind,fixtureId,participants,csrf,busy}:Props){
 const id=useId(),live=useRef(true),operation=useRef(false);
 const [report,setReport]=useState<RecentComparison|null>(null),[pending,setPending]=useState(false),[error,setError]=useState('');
 useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
 const read=async()=>{
  if(busy||operation.current)return;operation.current=true;setPending(true);setError('');
  try{
   const value=await request('/match-sheet/recent',{team_id:teamId,match_type:kind,reference:fixtureId},csrf);
   if(!isRecentComparison(value,{team_id:teamId,match_type:kind,fixture_id:fixtureId,participants}))throw Error(tr('La comparaison récente ne correspond pas à ces équipes.'));
   if(live.current)setReport(value);
  }catch(cause){if(live.current)setError(cause instanceof Error?cause.message:tr('Lecture Classic impossible.'))}
  finally{operation.current=false;if(live.current)setPending(false)}
 };
 return <section className="card recent-comparison" aria-labelledby={id} aria-busy={pending}>
  <div className="card-heading"><div><span className="eyebrow">{tr('LES FAITS AVANT LE DUEL')}</span><h3 id={id}><History size={20}/>{tr('Leurs quatre derniers matchs, et les nôtres.')}</h3></div><button type="button" className="button secondary" disabled={busy||pending} onClick={()=>void read()}><RefreshCw size={16}/>{pending?tr('Lecture des derniers matchs…'):tr('Comparer les quatre derniers matchs')}</button></div>
  <p>{tr('Scores, météo fournie et notes collectives du reporter Classic. Les matchs sans rapport gardent leur place ; aucune ancienne rencontre ne les remplace.')}</p>
  {pending&&<p role="status">{tr('Lecture limitée à quatre matchs par équipe. Les requêtes Classic sont espacées : cela peut prendre une minute.')}</p>}
  {error&&<p className="notice warning" role="alert">{error}{report&&' '+tr('Le dernier rapport reste affiché avec sa date de lecture.')}</p>}
  {report&&<><p className="tiny">{tr('Lecture du {date}',{date:moment(report.retrieved_at)})} · {tr('Source : fixtures et reporter Classic')}</p><div className="recent-teams">{report.sides.map(side=><section key={side.team_id} aria-label={side.name||side.team_id}><h4>{side.name||`${tr('Équipe')} #${side.team_id}`}</h4>
   {side.matches.length?side.matches.map(match=><RecentMatchCard key={match.id} match={match} kind={kind}/>):<p>{tr('Aucune rencontre terminée et datée fournie dans cet historique.')}</p>}
   <p className="tiny">{tr('{count} rencontres examinées · {excluded} non retenues',{count:side.history_count,excluded:side.excluded_count})}</p>
  </section>)}</div><p className="tiny">{tr('Les notes décrivent le rapport du match, sans fréquence tactique ni pronostic. Leur échelle maximale n’est pas supposée. Les noms d’équipes sont ceux de cette lecture.')}</p></>}
 </section>;
}

export function RecentMatchCard({match:m,kind}:{match:RecentMatch;kind:number}){
 const labels=ratingLabels(),link=recentFixtureLink(m.id,kind);
 const state={available:null,unavailable:tr('Rapport indisponible'),inconsistent:tr('Notes du rapport incohérentes : masquées'),not_played:tr('Match entre bots : rapport non produit')}[m.report_state];
 return <article className="recent-match"><header><strong>{m.home_name||'#'+m.home_id} — {m.guest_name||'#'+m.guest_id}</strong><span className="recent-score">{fmt(m.home_score)} – {fmt(m.guest_score)}</span></header>
  <p>{moment(m.start_at)} · {m.competition}</p><p className="recent-weather"><Cloud size={15}/>{m.weather_code===null?tr('Météo non fournie'):tr('Code météo Classic : {code}',{code:m.weather_code})}</p>
  {state&&<p className="notice warning">{state}</p>}
  <dl><div><dt>{tr('Poids du pack')}</dt><dd>{fmt(m.pack_weight)}{m.pack_weight!==null?' kg':''}</dd></div><div><dt>{tr('Poids du XV')}</dt><dd>{fmt(m.xv_weight)}{m.xv_weight!==null?' kg':''}</dd></div><div><dt>{tr('CSR du XV dans le rapport')}</dt><dd>{fmt(m.starting_csr)}</dd></div></dl>
  <details><summary>{tr('Notes collectives observées')}</summary><div className="recent-ratings">{Object.entries(labels).map(([key,label])=><div key={key}><span>{label}</span><strong>{fmt(m.ratings[key])}</strong></div>)}</div></details>
  <footer><span>{m.report_state==='available'?tr('Reporter Classic'):tr('Notes non fournies')}{m.score_source==='match_score'?' · '+tr('Score confirmé par Classic'):''}</span>{link&&<a href={link} target="_blank" rel="noreferrer">{tr('Ouvrir le match Classic')} #{m.id}</a>}</footer>
 </article>;
}
