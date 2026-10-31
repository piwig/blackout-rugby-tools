import {useEffect,useRef,useState} from 'react';
import {tr} from './i18n';
import {request} from './App';
import {fmt,labels,type Player} from './types';
import {useUnsavedChanges} from './navigation-guard';
import {changeRoleWeight,roleCoverage,roleNames,skillKeys,validRoleWeights,weightMethod,type RoleWeights,type WeightCriteria} from './role-weights-model';

type Profile = {id?:string;name:string;method:string;role_weights:RoleWeights};
type WeightDocument = {revision:number;profiles:Profile[];default:Profile};

export function RoleWeightsEditor({team,csrf,players,value,onChange,locked}:{team:string;csrf:string;players:Player[];value:WeightCriteria;onChange:(criteria:WeightCriteria)=>void;locked:boolean}) {
  const [doc,setDoc]=useState<WeightDocument|null>(null);
  const [selected,setSelected]=useState('');
  const [name,setName]=useState('');
  const [role,setRole]=useState<string>(roleNames[0]);
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [conflict,setConflict]=useState(false);
  const [reload,setReload]=useState(0);
  const alive=useRef(true), operation=useRef(false);
  const weights=value.role_weights||doc?.default.role_weights;
  const valid=!!weights&&validRoleWeights(weights);
  const coverage=weights?roleCoverage(players,weights[role]):null;
  const total=weights?Object.values(weights[role]).reduce((sum,w)=>sum+w,0):0;
  useUnsavedChanges(dirty||saving);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{
    let cancelled=false;
    request('/lineup-lab/weights?team_id='+encodeURIComponent(team)).then((value:WeightDocument)=>{
      if(!cancelled){setDoc(value);setConflict(false);setError('');}
    }).catch(reason=>{if(!cancelled)setError(reason.message);});
    return()=>{cancelled=true;};
  },[team,csrf,reload]);

  function choose(id:string) {
    if(!doc)return;
    const profile=id?doc.profiles.find(p=>p.id===id):doc.default;
    if(!profile)return;
    setSelected(id);setName(id?profile.name:'');setDirty(false);
    onChange({role_weights:structuredClone(profile.role_weights),weight_profile_name:id?profile.name:tr('Profil par défaut'),weight_method:weightMethod});
  }

  async function write(kind:'save'|'copy'|'delete') {
    if(!doc||operation.current||locked||conflict)return;
    operation.current=true;setSaving(true);setError('');
    const previousIds=new Set(doc.profiles.map(p=>p.id));
    try {
      const result:WeightDocument=await request('/lineup-lab/weights'+(kind==='delete'?'/delete':''),{
        team_id:team,expected_revision:doc.revision,
        ...(kind==='delete'?{id:selected}:{name:name.trim(),role_weights:weights,...(selected&&kind==='save'?{id:selected}:{})}),
      },csrf);
      if(!alive.current)return;
      setDoc(result);setDirty(false);
      if(kind==='delete'){setSelected('');setName('');return;}
      const id=kind==='save'&&selected?selected:result.profiles.find(p=>!previousIds.has(p.id))?.id||'';
      setSelected(id);
      onChange({role_weights:structuredClone(weights!),weight_profile_name:name.trim(),weight_method:weightMethod});
    } catch(reason) {
      if(alive.current){setError(reason instanceof Error?reason.message:tr('Enregistrement du profil impossible.'));if((reason as {status?:number}).status===409)setConflict(true);}
    } finally {operation.current=false;if(alive.current)setSaving(false);}
  }

  return <details className="lab-weight-panel"><summary>{tr('Vos critères de sélection')} · {value.weight_profile_name||tr('Profil par défaut')}</summary>
    <p className="lab-note">{tr('Indice personnel : une moyenne pondérée des compétences connues, sans pronostic de match. Les profils restent privés à ce club.')}</p>
    {error&&<p className="text-error" role="alert">{tr(error)}</p>}
    {conflict&&<button className="button secondary" disabled={saving||locked} onClick={()=>setReload(v=>v+1)}>{tr('Recharger les profils en conservant le brouillon')}</button>}
    {!doc&&!error&&<p role="status">{tr('Chargement des profils…')}</p>}
    {doc&&weights&&<>
      <div className="lab-controls"><label>{tr('Profil privé')}<select disabled={locked||saving} value={selected} onChange={e=>choose(e.target.value)}><option value="">{tr('Profil par défaut')}</option>{doc.profiles.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>{tr('Nom du profil')}<input maxLength={80} disabled={locked||saving} value={name} placeholder={tr('Ex. Priorité à la mobilité')} onChange={e=>{setName(e.target.value);setDirty(true);onChange({...value,role_weights:weights,weight_profile_name:e.target.value.trim()||tr('Critères personnalisés'),weight_method:weightMethod});}}/></label>
        <label>{tr('Rôle à ajuster')}<select value={role} disabled={locked||saving} onChange={e=>setRole(e.target.value)}>{roleNames.map(r=><option key={r} value={r}>{tr(r)}</option>)}</select></label></div>
      <div className="lab-weight-grid">{skillKeys.map(skill=>{const weight=weights[role][skill];return <label key={skill}><span>{tr(labels[skill])}</span><input type="number" min={0} max={10} step={1} value={Number.isFinite(weight)?weight:''} disabled={locked||saving} onChange={e=>{setDirty(true);onChange({role_weights:changeRoleWeight(weights,role,skill,e.target.value===''?NaN:Number(e.target.value)),weight_profile_name:name.trim()||tr('Critères personnalisés'),weight_method:weightMethod});}}/><span className="lab-weight-share">{Number.isFinite(total)&&total>0&&Number.isFinite(weight)?fmt(100*weight/total)+' %':'—'}</span></label>;})}</div>
      <p className="lab-note">{tr('Poids de 0 à 10 : 0 exclut la compétence ; tout poids positif exige une valeur connue. Moyenne = somme des compétences × poids, divisée par le total des poids du rôle.')}</p>
      <p className="lab-note">{tr('Couverture des compétences pour ce rôle : {known}/{total} joueurs observés. Énergie et disponibilité sont vérifiées séparément.',{known:coverage?.known||0,total:coverage?.total||0})}</p>
      {!valid&&<p className="text-error" role="alert">{tr('Chaque rôle exige dix poids entiers de 0 à 10 et au moins un poids positif.')}</p>}
      <div className="lab-inline-actions"><button className="button primary" disabled={locked||saving||conflict||!valid||!name.trim()} onClick={()=>void write('save')}>{selected?tr('Mettre à jour le profil'):tr('Enregistrer le profil')}</button>{selected&&<button className="button secondary" disabled={locked||saving||conflict||!valid||!name.trim()||doc.profiles.length>=10} onClick={()=>void write('copy')}>{tr('Créer un nouveau profil')}</button>}
        <button className="button secondary" disabled={locked||saving} onClick={()=>choose('')}>{tr('Réinitialiser les neuf rôles par défaut')}</button>
        {selected&&<button className="text-button lab-delete" disabled={locked||saving||conflict} onClick={()=>void write('delete')}>{tr('Supprimer ce profil privé')}</button>}<span className="lab-note">{doc.profiles.length}/10 · {dirty?tr('Brouillon de profil'):tr('Profils enregistrés')}</span></div>
    </>}
  </details>;
}
