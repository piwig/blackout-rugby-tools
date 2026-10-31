import {tr} from './i18n';
import {useEffect,useState,type CSSProperties} from 'react';
import {ArrowUpRight,Shield,Target,Zap,Camera} from 'lucide-react';
import {Modal} from './components';
import {rugbyClubs} from './rugby-clubs';

const sectionPhotos:Record<string,{src:string;alt:string;position:string}>={
  progression:{src:'/images/brt-banner-matchday.jpg',alt:'Un terrain de rugby sous les projecteurs',position:'65% 50%'},
  season:{src:'/images/rugby-matchday-v2.jpg',alt:'Stade de rugby éclairé avant la rencontre',position:'65% 50%'},
  vacation:{src:'/images/rugby-locker-v2.jpg',alt:'Ballon et équipement prêts dans un vestiaire de rugby',position:'70% 55%'},
  optimization:{src:'/images/rugby-matchday-v2.jpg',alt:'Illustration originale d’un stade de rugby avant le match',position:'65% 50%'},
  academy:{src:'/images/rugby-locker-v2.jpg',alt:'Ballon et équipement de rugby dans un vestiaire',position:'70% 55%'},
  squad:{src:'/images/siya-kolisi-2022.jpg',alt:'Siya Kolisi sur un terrain de rugby',position:'64% 27%'},
  matches:{src:'/images/antoine-dupont-2023.jpg',alt:'Antoine Dupont en action',position:'65% 42%'},
  training:{src:'/images/dan-carter-2015.jpg',alt:'Dan Carter lors de la Coupe du monde 2015',position:'66% 45%'},
  stadium:{src:'/images/rugby-matchday-v2.jpg',alt:'Illustration originale d’un stade de rugby avant le match',position:'65% 50%'},
  market:{src:'/images/rugby-locker-v2.jpg',alt:'Ballon et équipement de rugby dans un vestiaire',position:'70% 55%'},
  settings:{src:'/images/rugby-locker-v2.jpg',alt:'Ballon, maillots et crampons dans un vestiaire',position:'70% 60%'}
};

export function SectionPhoto({page}:{page:string}){const photo=sectionPhotos[page];return photo?<><img className={'section-photo section-photo-'+page} src={photo.src} alt={photo.alt} style={{objectPosition:photo.position}}/><span className="section-photo-shade" aria-hidden="true"/></>:null}

export function MatchdayHero({club,onExplore,banner='matchday'}:{club:string;onExplore:()=>void;banner?:'matchday'|'clubhouse'}){return <section className="matchday-hero"><img className="matchday-image" src={banner==='clubhouse'?'/images/brt-banner-clubhouse.jpg':'/images/brt-banner-matchday.jpg'} alt={banner==='clubhouse'?tr("Scène originale d’un vestiaire de rugby avant le match"):tr("Scène originale de joueurs entrant sur un terrain de rugby")} fetchPriority="high"/><div className="matchday-shade"/><div className="matchday-copy"><span className="matchday-label"><span/> {club.toUpperCase()}</span><h2>{tr("Le point avant")}<br/><em>{tr("le coup d’envoi.")}</em></h2><p>{tr("Votre effectif, ses points d’appui, les choix à préparer : prenez le temps de lire le jeu.")}</p><button className="button matchday-cta" onClick={onExplore}>{tr("Préparer mon XV")}<ArrowUpRight size={18}/></button></div><div className="matchday-edge"><span>{tr("BLACKOUT / CLASSIC")}</span><b>{tr("L’ESPRIT RUGBY.")}<br/>{tr("VOTRE VISION.")}</b></div></section>}

export function RugbyGallery({go}:{go:(page:string)=>void}){return <section className="rugby-editorial"><div className="editorial-heading"><div><span className="eyebrow">{tr("L’ESPRIT DU JEU")}</span><h2>{tr("Trois regards pour préparer le jeu.")}</h2></div><span>{tr("Trois regards sur le rugby")}</span></div><div className="rugby-cards">{[
  {name:'Antoine Dupont',tag:'L’INITIATIVE',title:'Lire avant les autres.',detail:'Étudiez les zones et les choix d’attaque.',src:'/images/antoine-dupont-2023.jpg',point:'38% 42%',page:'matches',Icon:Zap},
  {name:'Siya Kolisi',tag:'LE COLLECTIF',title:'Faire grandir le groupe.',detail:'Composez un quinze qui se complète.',src:'/images/siya-kolisi-2022.jpg',point:'50% 28%',page:'squad',Icon:Shield},
  {name:'Dan Carter',tag:'LA PRÉCISION',title:'Préparer le geste juste.',detail:'Donnez un cap à vos entraînements.',src:'/images/dan-carter-2015.jpg',point:'56% 48%',page:'training',Icon:Target}
].map(({Icon,...p})=><button className="rugby-card" style={{'--mobile-photo-position':p.point} as CSSProperties} key={p.name} onClick={()=>go(p.page)}><img src={p.src} alt={p.name+tr(" sur un terrain de rugby")} style={{objectPosition:p.point}} loading="lazy"/><div className="rugby-card-shade"/><span className="rugby-card-top"><span><Icon size={15}/>{p.tag}</span><ArrowUpRight size={20}/></span><div className="rugby-card-copy"><small>{p.name}</small><h3>{p.title}</h3><p>{p.detail}</p></div></button>)}</div></section>}

export function PhotoCredits(){
  const [open,setOpen]=useState(false),[credits,setCredits]=useState<any[]>([]),[error,setError]=useState('');
  useEffect(()=>{if(!open)return;let active=true;setError('');fetch('/image-credits.json').then(r=>{if(!r.ok)throw new Error();return r.json()}).then(data=>{if(active)setCredits(data)}).catch(()=>{if(active)setError('Les crédits ne sont pas disponibles pour le moment.')});return()=>{active=false}},[open]);
  return <><button className="text-button credits-button" onClick={()=>setOpen(true)}><Camera size={13}/>{tr("Images & crédits")}</button>{open&&<Modal title={tr("Images & esprit du rugby")} onClose={()=>setOpen(false)} wide><div className="prose"><p>{tr("Photos utilisées à titre d’illustration éditoriale. Les joueurs représentés ne sont pas affiliés à cet outil et ne le recommandent pas.")}</p>{error&&<p role="alert">{tr(error)}</p>}<div className="photo-credits">{credits.map(c=><article key={c.src}><img src={c.src} alt={c.name}/><div><h3>{c.name}</h3><p>{c.author}</p><p>{c.changes}</p>{c.sourceUrl&&<a href={c.sourceUrl} target="_blank" rel="noreferrer">{tr("Source originale ↗")}</a>}{c.licenseUrl?<a href={c.licenseUrl} target="_blank" rel="noreferrer">{c.license} ↗</a>:<small>{c.license}</small>}</div></article>)}</div><h3>{tr("Les clubs favoris")}</h3><p>{tr("Les emblèmes identifient les clubs choisis par les managers. Ils restent les marques de leurs propriétaires ; aucun partenariat ou soutien à BRT n’est revendiqué.")}</p><div className="club-credit-grid">{rugbyClubs.map(club=><a key={club.id} href={club.source} target="_blank" rel="noreferrer"><img src={club.logo} alt={tr("")}/><span>{club.name}<small>{tr("Source officielle ↗")}</small></span></a>)}</div></div></Modal>}</>;
}
