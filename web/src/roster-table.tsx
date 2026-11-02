import {ArrowUpDown,MessageSquare,Star} from 'lucide-react';
import {tr} from './i18n';
import {skills,labels,fmt,type Player,type State} from './types';
import {Skill} from './components';
import {rosterColumns,rosterDelta,rosterValue} from './roster-table-model';
import './roster-table.css';

type Props={players:Player[];notes:State['notes'];youth:boolean;complete:boolean;sort:string;descending:boolean;busy:boolean;compare:string[];
  onSort:(key:string)=>void;onOpen:(player:Player)=>void;onWatch:(id:string)=>void;onCompare:(id:string)=>void};
const headers=()=>({name:tr('Joueur'),age:tr('Âge'),stars:tr('Étoiles de recrutement'),csr:tr('CSR'),salary:tr('Salaire saisonnier'),
 height:tr('Taille'),weight:tr('Poids'),hand:tr('Main'),foot:tr('Pied'),form:tr('Forme'),energy:tr('Énergie'),
 aggression:tr('Agressivité'),discipline:tr('Discipline'),leadership:tr('Leadership'),experience:tr('Expérience'),
 total:tr('Total connu'),generation:tr('Génération indicative'),nationality:tr('Nationalité'),nat:tr('Sélection nationale'),u20:tr('Sélection U20'),...Object.fromEntries(skills.map(k=>[k,tr(labels[k])]))});

export function RosterTable({players,notes,youth,complete,sort,descending,busy,compare,onSort,onOpen,onWatch,onCompare}:Props){
 const columns=rosterColumns(youth,complete),titles=headers();
 const heading=(key:string)=><th key={key} scope="col" aria-sort={sort===key?(descending?'descending':'ascending'):undefined}>
   <button type="button" onClick={()=>onSort(key)} title={titles[key as keyof typeof titles]}>{titles[key as keyof typeof titles]}<ArrowUpDown size={12}/></button></th>;
 const cell=(p:Player,key:string)=>{
  if(key==='generation')return p.wc_projection?tr('S{season}',{season:p.wc_projection}):'—';
  const raw=rosterValue(p,key),change=rosterDelta(p,key);
  const value=skills.includes(key as typeof skills[number])?<Skill value={p[key]}/>:<span>{fmt(raw)}</span>;
  return <>{value}{change&&<small className="roster-delta" title={tr('Avant : {before} · Après : {after}',{before:change.before,after:change.after})}>
    {change.kind==='numeric'?`${change.delta>0?'+':''}${fmt(change.delta)}`:tr('Dévoilé')}</small>}</>;
 };
 return <table className={'players-table roster-table'+(complete?' roster-complete':'')}><thead><tr>
  <th scope="col" className="sticky-col" aria-sort={sort==='name'?(descending?'descending':'ascending'):undefined}><button onClick={()=>onSort('name')}>{tr('Joueur')}<ArrowUpDown size={12}/></button></th>
  {columns.map(heading)}<th scope="col">{tr('Suivi')}</th><th scope="col">{tr('Comparer')}</th><th scope="col">{tr('Commentaires')}</th>
 </tr></thead><tbody>{players.map(p=><tr key={p.id}>
  <td className="sticky-col"><button className="player-cell" onClick={()=>onOpen(p)}><span className="player-avatar">{p.name.split(' ').map(s=>s[0]).slice(0,2).join('')}</span><span><strong>{p.name}</strong><small>#{p.id}</small></span></button></td>
  {columns.map(key=><td key={key} className="numeric">{cell(p,key)}</td>)}
  <td><button className={'icon-button watch '+(notes[p.id]?.watch?'watched':'')} aria-label={tr(notes[p.id]?.watch?'Ne plus suivre {name}':'Suivre {name}',{name:p.name})} disabled={busy} onClick={()=>onWatch(p.id)}><Star size={16}/></button></td>
  <td><input aria-label={tr('Comparer {name}',{name:p.name})} type="checkbox" checked={compare.includes(p.id)} disabled={busy||!compare.includes(p.id)&&compare.length>=3} onChange={()=>onCompare(p.id)}/></td>
  <td className="roster-note">{notes[p.id]?.text?<p>{notes[p.id].text}</p>:<span className="muted">{tr('Aucune note')}</span>}<button type="button" className="text-button" disabled={busy} aria-label={tr('Modifier la note de {name}',{name:p.name})} onClick={()=>onOpen(p)}><MessageSquare size={13}/>{tr('Modifier la note')}</button></td>
 </tr>)}</tbody></table>;
}
