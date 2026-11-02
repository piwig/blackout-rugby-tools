import {useEffect,useId,useRef,useState} from 'react';
import {ArrowRightLeft,CalendarRange,Flag,RefreshCw,Search,ShieldCheck,Users} from 'lucide-react';
import {request} from './App';
import {localeTag,tr} from './i18n';
import {formatStatistic as fmt,type State} from './types';
import {isSheetCalendar,isSheetReport,populationFor,referenceId,preparationWindow,sheetReadiness,type EnergyScale,type SheetCalendar,type SheetPlayer,type SheetReport,type SheetSide} from './match-sheet-model';
import './match-sheet.css';

const moment=(v:string|null)=>v?new Date(v).toLocaleString(localeTag(),{dateStyle:'medium',timeStyle:'short'}):tr('Non fournie');
const teamName=(side:SheetSide)=>side.name||`${tr('Équipe')} ${side.team_id}`;
const groupLabels=()=>({pack:tr('Pack'),first_row:tr('Première ligne'),second_row:tr('Deuxième ligne'),back_row:tr('Troisième ligne'),halves:tr('Charnière'),centres:tr('Centres'),back_three:tr('Triangle arrière'),xv:tr('XV titulaire'),bench:tr('Banc'),all:tr('Groupe complet')});
const metrics=()=>[
  ['weight_total',tr('Poids total'),'kg'],['height_average',tr('Taille moyenne'),'cm'],['csr_average',tr('CSR moyen'),''],
  ['adjusted_csr_average',tr('Indice ajusté moyen'),''],['form_average',tr('Forme moyenne'),'/11'],['energy_percent_average',tr('Énergie moyenne'),'%'],
  ['experience_average',tr('Expérience moyenne'),'/21'],['aggression_average',tr('Agressivité moyenne'),'/5'],['discipline_average',tr('Discipline moyenne'),'/5'],
];
const position=(slot:number)=>slot>15?tr('Remplaçant {number}',{number:slot-15}):[
  tr('Pilier gauche'),tr('Talonneur'),tr('Pilier droit'),tr('Deuxième ligne'),tr('Deuxième ligne'),tr('Troisième ligne aile'),tr('Troisième ligne aile'),tr('Numéro huit'),tr('Demi de mêlée'),tr('Demi d’ouverture'),tr('Ailier gauche'),tr('Premier centre'),tr('Deuxième centre'),tr('Ailier droit'),tr('Arrière'),
][slot-1];

export function MatchSheet(props:{d:State;busy?:boolean}){
  const [junior,setJunior]=useState(false);
  const kind=populationFor(props.d.current_team.id,junior);
  return <div className="match-sheet-page">
    <header className="sheet-hero"><span className="eyebrow">{tr('JOUR DE MATCH')}</span><h2>{tr('Les maillots sont sortis. À vous de lire le duel.')}</h2><p>{tr('Deux feuilles, les mêmes repères : préparez vos choix sans jongler entre les fiches.')}</p></header>
    {!props.d.current_team.id.includes(':')&&<div className="sheet-population" aria-label={tr('Groupe de joueurs')}>
      <button type="button" className={'button secondary'+(!junior?' active':'')} aria-pressed={!junior} onClick={()=>setJunior(false)}>{tr('Seniors')}</button>
      <button type="button" className={'button secondary'+(junior?' active':'')} aria-pressed={junior} onClick={()=>setJunior(true)}>{tr('Juniors')}</button>
    </div>}
    <ScopedMatchSheet key={JSON.stringify([props.d.user.username,props.d.csrf,props.d.current_team.id,kind])} {...props} kind={kind}/>
  </div>;
}

function ScopedMatchSheet({d,busy=false,kind}:{d:State;busy?:boolean;kind:number}){
  const id=useId(),live=useRef(true),operation=useRef(false);
  const [calendar,setCalendar]=useState<SheetCalendar|null>(null),[reference,setReference]=useState(''),[report,setReport]=useState<SheetReport|null>(null);
  const [pending,setPending]=useState<'calendar'|'sheet'|null>(null),[error,setError]=useState('');
  const [homeScale,setHomeScale]=useState<EnergyScale>('auto'),[guestScale,setGuestScale]=useState<EnergyScale>('auto');
  useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
  const locked=busy||pending!==null;
  const run=async(action:'calendar'|'sheet')=>{
    if(operation.current||busy||action==='sheet'&&!reference.trim())return;
    operation.current=true;setPending(action);setError('');
    const wanted=referenceId(reference);
    try{
      if(action==='calendar'){
        const result=await request('/match-sheet/fixtures',{team_id:d.current_team.id,match_type:kind},d.csrf);
        if(!isSheetCalendar(result,d.current_team.id,kind))throw Error(tr('Le calendrier reçu ne correspond pas à l’équipe affichée.'));
        if(live.current){setCalendar(result);setReference(old=>old||result.fixtures[0]?.id||'')}
      }else{
        const result=await request('/match-sheet/read',{team_id:d.current_team.id,match_type:kind,reference,home_energy_scale:homeScale,guest_energy_scale:guestScale},d.csrf);
        if(!isSheetReport(result,d.current_team.id,kind,wanted))throw Error(tr('La feuille reçue ne correspond pas à la rencontre choisie.'));
        if(live.current)setReport(result);
      }
    }catch(cause){if(live.current)setError(cause instanceof Error?cause.message:tr('La lecture Classic a échoué. Réessayez.'))}
    finally{operation.current=false;if(live.current)setPending(null)}
  };
  const scaleControl=(side:'home'|'guest',scale:EnergyScale,set:(v:EnergyScale)=>void)=><label htmlFor={id+side}>{side==='home'?tr('Énergie domicile'):tr('Énergie extérieur')}<select id={id+side} value={scale} disabled={locked} onChange={e=>set(e.target.value as EnergyScale)}>
    <option value="auto">{tr('Auto : valeurs ambiguës inconnues')}</option><option value="percent">{tr('Pourcentage (0–110 %)')}</option><option value="level">{tr('Niveau (1–11, approximation)')}</option>
  </select></label>;
  return <>
    <section className="card sheet-controls" aria-busy={pending!==null} aria-labelledby={id+'title'}>
      <div className="card-heading"><h2 id={id+'title'}><CalendarRange size={22}/>{tr('Choisir la rencontre')}</h2><span className="sheet-pop-tag">{kind===3?tr('Juniors'):kind===1?'U20':kind===2?tr('Sélection nationale'):tr('Seniors')}</span></div>
      <p>{tr('Lisez le calendrier ou collez un lien Classic. Seules les feuilles fournies par le jeu seront affichées.')}</p>
      <div className="sheet-calendar-row"><button className="button secondary" disabled={locked} onClick={()=>void run('calendar')}><RefreshCw size={16} className={pending==='calendar'?'sheet-spin':''}/>{pending==='calendar'?tr('Lecture du calendrier…'):tr('Lire le calendrier Classic')}</button>
        {calendar&&<label htmlFor={id+'fixture'}>{tr('Rencontres à venir')}<select id={id+'fixture'} value={calendar.fixtures.some(f=>f.id===reference)?reference:''} disabled={locked} onChange={e=>setReference(e.target.value)}><option value="">{tr('Choisir une rencontre')}</option>{calendar.fixtures.map(f=><option key={f.id} value={f.id}>{moment(f.start_at)} · {f.competition} · #{f.id}</option>)}</select></label>}
      </div>
      {calendar?.partial&&<p role="status" className="notice warning">{tr('Classic n’a pas fourni le calendrier junior complet. Les rencontres affichées ont été vérifiées ; vous pouvez aussi saisir un lien.')}</p>}
      {calendar&&!calendar.fixtures.length&&<p role="status">{tr('Aucune rencontre à venir fournie. Vous pouvez saisir un identifiant.')}</p>}
      <form onSubmit={e=>{e.preventDefault();void run('sheet')}}>
        <label htmlFor={id+'reference'}>{tr('Identifiant ou lien officiel Classic')}<input id={id+'reference'} value={reference} maxLength={2000} disabled={locked} onChange={e=>setReference(e.target.value)} placeholder="12345678" required/></label>
        <details className="sheet-scale-options"><summary>{tr('Échelle de l’énergie')}</summary><p>{tr('En auto, chaque valeur de 0 à 11 reste ambiguë. Choisissez une échelle seulement si vous connaissez le format, puis relisez les feuilles.')}</p><div className="sheet-scale-grid">{scaleControl('home',homeScale,setHomeScale)}{scaleControl('guest',guestScale,setGuestScale)}</div></details>
        <button type="submit" className="button primary" disabled={locked||!reference.trim()}><Search size={17} className={pending==='sheet'?'sheet-spin':''}/>{pending==='sheet'?tr('Lecture des deux feuilles…'):tr('Comparer les deux feuilles')}</button>
      </form>
      <p className="sheet-footnote"><ShieldCheck size={15}/>{tr('Lecture seule. Vos compositions et vos tactiques ne sont pas modifiées. Une lecture peut prendre quelques dizaines de secondes.')}</p>
      {error&&<div role="alert" className="notice warning">{error}{report&&<p>{tr('Le dernier rapport reste affiché avec sa date de lecture.')}</p>}</div>}
      {pending&&<p role="status" aria-live="polite">{tr('Classic prépare la réponse. Vous pouvez patienter sur cet écran.')}</p>}
    </section>
    {report?<SheetReportView report={report}/>:<section className="card sheet-empty"><Users size={36}/><h3>{tr('Un poste, deux joueurs, un duel à lire.')}</h3><p>{tr('La comparaison apparaîtra ici après lecture. Avant la publication adverse, certains noms peuvent manquer.')}</p></section>}
  </>;
}

function PlayerCard({player:p,team}:{player:SheetPlayer;team:string}){
  return <article aria-label={`${team} · #${p.slot} · ${p.name||tr('Joueur non fourni')}`} className={'sheet-player '+(p.status!=='available'?'sheet-player-unknown':'')}>
    <h4>{p.name||(p.status==='missing_player'?tr('Fiche non fournie'):tr('Joueur non fourni'))}</h4>
    {p.player_id&&<small>#{p.player_id}</small>}
    {(p.captain||p.kicker)&&<div className="sheet-roles">{p.captain&&<span><Flag size={12}/>{tr('Capitaine')}</span>}{p.kicker&&<span>{tr('Buteur')}</span>}</div>}
    <dl>{[[tr('CSR'),p.csr,''],[tr('Indice ajusté'),p.adjusted_csr,''],[tr('Poids'),p.weight,'kg'],[tr('Taille'),p.height,'cm'],[tr('Forme'),p.form,'/11'],[tr('Expérience'),p.experience,'/21'],[tr('Agressivité'),p.aggression,'/5'],[tr('Discipline'),p.discipline,'/5']].map(([label,value,unit])=><div key={String(label)}><dt>{label}</dt><dd>{fmt(value)}{value!==null&&unit?<small> {unit}</small>:null}</dd></div>)}
      <div><dt>{tr('Énergie')}</dt><dd>{fmt(p.energy_raw)}{p.energy_scale==='percent'?' %':p.energy_scale==='level'?'/11':''}</dd></div>
    </dl>
    <small className="sheet-energy-note">{p.energy_scale==='unknown'?tr('Échelle inconnue'):p.energy_scale==='level'?tr('Niveau × 10 : estimation en %'):tr('Pourcentage confirmé par la valeur ou le choix du format')}</small>
  </article>;
}

export function SheetReportView({report:r}:{report:SheetReport}){
  const [group,setGroup]=useState('pack'),[filter,setFilter]=useState('all'),id=useId();
  const labels=groupLabels(),homeGroup=r.home.groups.find(g=>g.key===group),guestGroup=r.guest.groups.find(g=>g.key===group);
  const slots=r.home.players.filter(p=>filter==='all'||filter==='xv'&&p.slot<=15||filter==='bench'&&p.slot>15);
  const ready=sheetReadiness(r),window=preparationWindow(r);
  const phase={lineup:tr('Les 23 peuvent encore être préparés'),tactics:tr('XV verrouillé : place aux tactiques'),
    closed:tr('Échéances indiquées dépassées'),lineup_closed:tr('XV verrouillé ; échéance tactique à confirmer'),unknown:tr('Horaires à confirmer dans Classic')}[window.stage];
  return <div className="sheet-report">
    <section className="card sheet-scoreboard"><span className="eyebrow">{tr('LE FACE-À-FACE')} · #{r.fixture.id}</span>
      <div className="sheet-team-heads"><div><span>{tr('Domicile')}</span><h3>{teamName(r.home)}</h3></div><ArrowRightLeft aria-hidden="true"/><div><span>{tr('Extérieur')}</span><h3>{teamName(r.guest)}</h3></div></div>
      <p>{r.fixture.competition} · {moment(r.fixture.start_at)}</p><p className="sheet-footnote">{tr('Lecture du {date}',{date:moment(r.retrieved_at)})} · {Intl.DateTimeFormat().resolvedOptions().timeZone}</p>
      <p className="sheet-footnote">{tr('Les caractéristiques sont celles de cette lecture, y compris pour un ancien match.')}</p>
      {[r.home,r.guest].filter(s=>s.lineup_state!=='available').map(s=><div className="notice warning" key={s.team_id}>{teamName(s)} : {s.lineup_state==='unavailable'?tr('Lecture impossible pour cette feuille. Réessayez ; elle peut ne pas être encore publiée.'):tr('Feuille non fournie par Classic')}</div>)}
    </section>
    <section className="card sheet-deadlines"><h3><ShieldCheck size={18}/> {tr('Notre contrôle avant match')}</h3><strong>{phase}</strong>
      <p className="sheet-footnote">{tr('Selon les échéances fournies pour notre équipe, à la date de lecture. Relisez Classic avant toute modification.')}</p>
      <div className="sheet-scale-grid"><dl><div><dt>{tr('Titulaires identifiés')}</dt><dd>{ready.starters}/15</dd></div><div><dt>{tr('Remplaçants identifiés')}</dt><dd>{ready.bench}/8</dd></div></dl>
      <dl><div><dt>{tr('Capitaine dans le XV')}</dt><dd>{ready.captain?tr('Oui'):tr('À vérifier')}</dd></div><div><dt>{tr('Buteur dans le XV')}</dt><dd>{ready.kicker?tr('Oui'):tr('À vérifier')}</dd></div></dl></div>
      {ready.duplicates>0&&<p className="notice warning">{tr('Doublons à corriger')}</p>}
      <ol><li>{tr('Avant le verrouillage : comparez plusieurs XV et vérifiez banc, blessures, forme et énergie.')}</li>
      <li>{tr('Après la publication adverse : relisez les duels et les conditions, puis ajustez les tactiques encore ouvertes.')}</li>
      <li>{tr('Après le match : confrontez le plan aux faits et préparez le prochain adversaire.')}</li></ol>
      <p className="sheet-footnote">{tr('Ce contrôle ne confirme pas une nouvelle sauvegarde. Les secours et la couverture après remplacements restent à vérifier dans le jeu.')}</p>
    </section>
    <section className="card sheet-deadlines"><h3>{tr('Le chronomètre du staff')}</h3>
      <div className="sheet-scale-grid">{[r.home,r.guest].map(s=><div key={s.team_id}><h4>{teamName(s)}</h4><dl><div><dt>{tr('Composition — échéance fournie')}</dt><dd>{moment(s.deadline_at)}</dd></div><div><dt>{tr('Tactiques — échéance fournie')}</dt><dd>{moment(s.tactics_deadline_at)}</dd></div></dl></div>)}</div>
      <details><summary>{tr('Repères indicatifs')}</summary><p>{tr('Ces horaires sont des repères calculés, pas une confirmation de verrouillage par Classic.')}</p><dl>{[[tr('Composition : H−3 h 05'),r.timing.indicative.lineup_at],[tr('Publication : H−3 h'),r.timing.indicative.publication_at],[tr('Tactiques : H−2 h 05'),r.timing.indicative.tactics_at]].map(([label,value])=><div key={label!}><dt>{label}</dt><dd>{moment(value)}</dd></div>)}</dl></details>
    </section>
    <section className="card sheet-summary"><div className="card-heading"><h3>{tr('La bataille des lignes')}</h3><label htmlFor={id+'group'} className="sr-only">{tr('Groupe à comparer')}</label><select id={id+'group'} value={group} onChange={e=>setGroup(e.target.value)}>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></div>
      <p className="sheet-footnote">{tr('Chaque chiffre indique sa couverture. Une moyenne partielle décrit seulement les joueurs connus.')}</p>
      <div className="sheet-metric-heading"><span>{teamName(r.home)}</span><span>{teamName(r.guest)}</span></div>
      <div className="sheet-metrics">{metrics().map(([key,label,unit])=><div className="sheet-metric" key={key}><h4>{label}</h4><div>{[homeGroup,guestGroup].map((g,i)=>{const m=g?.metrics[key];return <div key={i} role="group" aria-label={`${label} · ${teamName(i===0?r.home:r.guest)}`}><strong>{fmt(m?.value)}{m?.value!=null&&unit&&<small> {unit}</small>}</strong><small>{m?`${m.known}/${m.expected} ${tr('valeurs connues')}`:tr('Non fourni')}</small></div>})}</div></div>)}</div>
    </section>
    <section className="sheet-pairs" aria-labelledby={id+'pairs'}><div className="sheet-pairs-title"><h3 id={id+'pairs'}>{tr('Le duel poste par poste')}</h3><label className="sr-only" htmlFor={id+'filter'}>{tr('Joueurs affichés')}</label><select id={id+'filter'} value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">{tr('Les 23 joueurs')}</option><option value="xv">{tr('XV titulaire')}</option><option value="bench">{tr('Banc')}</option></select></div>
      <div className="sheet-metric-heading sheet-pair-teams"><span>{teamName(r.home)}</span><span>{teamName(r.guest)}</span></div>
      {slots.map(p=><section key={p.slot} className="sheet-pair" data-jersey={p.slot} aria-label={`${p.slot} · ${position(p.slot)}`}><h3><span>{p.slot}</span>{position(p.slot)}</h3><div className="sheet-player-pair"><PlayerCard player={p} team={teamName(r.home)}/><PlayerCard player={r.guest.players[p.slot-1]} team={teamName(r.guest)}/></div></section>)}
    </section>
    <details className="card sheet-method"><summary>{tr('Indice personnel : comprendre les calculs')}</summary><p>{tr('Cet indice non officiel reprend une formule personnelle : CSR × (1 + 0,07 × (forme − 7)) × (1 + 0,02 × (expérience − 7)) × énergie en % / 100.')}</p><p>{tr('Le résultat est tronqué par joueur, puis la moyenne des indices connus est arrondie à l’entier inférieur. Une donnée manquante laisse l’indice inconnu. Le poids total exige tous les poids du groupe.')}</p><p>{tr('Le niveau d’énergie multiplié par dix reste une approximation. Un indice, un poids ou un CSR supérieur ne garantit aucun avantage tactique ni résultat.')}</p></details>
  </div>;
}
