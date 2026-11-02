import {Clock,Database,FlaskConical} from 'lucide-react';
import {tr,localeTag} from './i18n';
import {type State} from './types';
import {basisForPage,sourceMoment} from './data-basis-model';
import './data-basis.css';

export function DataBasis({d,page}:{d:State;page:string}){
 const basis=basisForPage(page);if(!basis)return null;
 const title={facts:tr('Observations enregistrées'),mixed:tr('Observations et simulations'),model:tr('Modèles personnels BRT')}[basis.kind];
 const detail={facts:tr('Ces valeurs viennent de relevés datés. Les données manquantes restent inconnues ; la date d’import ne remplace pas la date d’observation.'),
  mixed:tr('Les relevés décrivent une observation. Les projections, budgets et objectifs dépendent de vos hypothèses : ce ne sont pas des résultats acquis.'),
  model:tr('Les indices, profils et priorités sont des modèles personnels. Ils ne reproduisent pas le moteur officiel et ne prédisent ni victoire ni gain d’entraînement.')}[basis.kind];
 const sources=basis.sources==='none'?[]:basis.sources==='squad'?[[tr('Effectif'),d.squad_source] as const]:basis.sources==='academy'?[[tr('Juniors'),d.academy_source] as const]:[[tr('Effectif'),d.squad_source] as const,[tr('Juniors'),d.academy_source] as const];
 const Icon=basis.kind==='model'?FlaskConical:Database;
 return <details className="data-basis"><summary><Icon size={15}/><strong>{title}</strong><span>{tr('D’où viennent ces chiffres ?')}</span></summary><p>{detail}</p>
  {sources.map(([label,source])=><p key={label} className="data-basis-source"><Clock size={13}/><strong>{label}</strong> · {source?sourceMoment(source.observed_at,localeTag())||tr('Horodatage à confirmer'):tr('Pas de relevé disponible')}{source?' · '+source.source:''}</p>)}
  {basis.kind!=='model'&&<p className="tiny">{tr('Une énergie brute de 1 à 11 peut être un niveau ou un pourcentage. Vérifiez le format avant d’y lire une fatigue.')}</p>}
 </details>;
}
