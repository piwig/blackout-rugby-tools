import {localeTag,tr} from './i18n';
import {useEffect, useRef, useState} from 'react';
import {Check, CircleAlert, LockKeyhole, RefreshCw, Save, Trash2, Unlock, Users} from 'lucide-react';
import {request, type Actions} from './App';
import {fmt} from './types';
import './lineup-lab.css';
import {RoleWeightsEditor} from './role-weights';
import {validRoleWeights,type WeightCriteria,type RoleWeights} from './role-weights-model';
import {useUnsavedChanges} from './navigation-guard';

const roles = ['Pilier', 'Talonneur', 'Pilier', 'Deuxième ligne', 'Deuxième ligne', 'Troisième ligne', 'Troisième ligne', 'Troisième ligne', 'Demi de mêlée', 'Demi d’ouverture', 'Ailier', 'Centre', 'Centre', 'Ailier', 'Arrière'];
const rows = [[1, 2, 3], [4, 5], [6, 8, 7], [9, 10], [11, 12, 13, 14], [15]];
const objectives = {balanced: 'Performance', recovery: 'Récupération', development: 'Développement'};
type Options = WeightCriteria & {objective: keyof typeof objectives; energy_floor: number; energy_scale: 'auto' | 'percent' | 'level'; locks: Record<string, string>; starter_ids: string[]; excluded_ids: string[]};
type Selected = {slot: number; role: string; id: string; name: string; score: number; energy: number | null; reason: string; covers?: string[]};
type Preview = {criteria?: {name:string;method:string;role_weights:RoleWeights}; generated_at: string; source: {id: number; observed_at: string; source: string} | null; score: number | null; warnings: string[]; summary: {selected: number; eligible: number}; lineup: {slots: Record<string, string>; players: Selected[]; unfilled: number[]; excluded: {id: string; name: string; reason: string}[]; bench_coverage: {roles: {role: string; player_ids: string[]; needed: number; missing: number}[]; gaps: string[]; method: string}}};
type Scenario = {id: string; name: string; options: Options; preview: Preview};
type Document = {revision: number; scenarios: Scenario[]};
type Comparison = {left: {name: string; score: number | null; starters: number; bench_gaps: string[]}; right: Comparison['left']; delta: number | null; warnings: string[]; changes: {slot: number; left: string | null; right: string | null}[]; explanation: string};
const defaults = (): Options => ({weight_profile_name:tr('Profil par défaut'),objective: 'balanced', energy_floor: 60, energy_scale: 'auto', locks: {}, starter_ids: [], excluded_ids: []});
const localDate = (value?: string) => value ? new Date(value).toLocaleString(localeTag()) : tr('Non datée');

export function LineupLab(props:Actions) {
  return <ScopedLineupLab key={props.d.user.username+':'+props.d.csrf+':'+props.d.current_team.id} {...props}/>;
}

function ScopedLineupLab({d, act, busy, openPlayer}: Actions) {
  const team = d.current_team.id;
  const [options, rawSetOptions] = useState<Options>(defaults);
  const [dirty,setDirty] = useState(false);
  const [criteriaEpoch,setCriteriaEpoch] = useState(0);
  const setOptions = (next:Options|((previous:Options)=>Options)) => {setDirty(true);rawSetOptions(next);};
  const [energyInput, setEnergyInput] = useState('60');
  const [slot, setSlot] = useState(1);
  const [search, setSearch] = useState('');
  const [preview, setPreview] = useState<{key: string; result: Preview; historical: boolean} | null>(null);
  const [document, setDocument] = useState<Document | null>(null);
  const [selectedScenario, setSelectedScenario] = useState('');
  const [name, setName] = useState('');
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [reload, setReload] = useState(0);
  const mounted = useRef(true);
  const operationLock = useRef(false);
  const key = JSON.stringify([team, options, d.squad_source]);
  const currentKey = useRef(key);
  currentKey.current = key;
  const result = preview?.result;
  const locked = busy || working;
  const validWeights = !options.role_weights || validRoleWeights(options.role_weights);
  const validEnergy = energyInput.trim() !== '' && Number.isInteger(Number(energyInput)) && Number(energyInput) >= 0 && Number(energyInput) <= 110;
  const fresh = preview?.key === key && !preview.historical && validEnergy && validWeights;
  useUnsavedChanges(dirty||working);
  const selectedPlayer = result?.lineup.players.find(player => player.slot === slot);
  const playerAtSlot = options.locks[String(slot)] || (fresh ? result?.lineup.slots[String(slot)] : undefined) || '';
  const knownName = (id: string | null) => id ? d.squad.find(player => player.id === id)?.name || result?.lineup.players.find(player => player.id === id)?.name || `Joueur ${id}` : 'Place vide';

  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useEffect(() => {
    let cancelled = false;
    setDocument(null);
    request('/lineup-lab/scenarios?team_id='+encodeURIComponent(team)).then(value => {
      if (!cancelled) setDocument(value);
    }).catch(reason => {if (!cancelled) setError(reason.message);});
    return () => {cancelled = true;};
  }, [team, d, reload]);
  useEffect(() => {setConfirmApply(false);}, [key]);
  useEffect(() => {
    setComparison(null);
    if (!leftId || !rightId || !document) return;
    let cancelled = false;
    request('/lineup-lab/compare?'+new URLSearchParams({team_id: team, left_id: leftId, right_id: rightId})).then(value => {
      if (!cancelled) setComparison(value);
    }).catch(reason => {if (!cancelled) setError(reason.message);});
    return () => {cancelled = true;};
  }, [team, leftId, rightId, document]);

  async function run(operation: () => Promise<void>) {
    if (operationLock.current || busy) return;
    operationLock.current = true;
    setWorking(true); setError('');
    try {await operation();}
    catch (reason) {if (mounted.current) {setError(reason instanceof Error ? reason.message : 'Opération impossible.'); if ((reason as {status?: number}).status === 409) setReload(value => value+1);}}
    finally {operationLock.current = false; if (mounted.current) setWorking(false);}
  }

  function playerStatus(id: string, status: string) {
    setOptions(previous => ({...previous,
      locks: status === 'excluded' ? Object.fromEntries(Object.entries(previous.locks).filter(([, value]) => value !== id)) : previous.locks,
      starter_ids: [...previous.starter_ids.filter(value => value !== id), ...(status === 'starter' ? [id] : [])],
      excluded_ids: [...previous.excluded_ids.filter(value => value !== id), ...(status === 'excluded' ? [id] : [])],
    }));
  }

  function lockSlot(id: string) {
    setOptions(previous => ({...previous,
      locks: {...Object.fromEntries(Object.entries(previous.locks).filter(([position, value]) => position !== String(slot) && value !== id)), ...(id ? {[String(slot)]: id} : {})},
      excluded_ids: previous.excluded_ids.filter(value => value !== id),
    }));
  }

  function loadScenario(id: string) {
    if(dirty&&!window.confirm(tr('Abandonner les modifications du scénario pour ouvrir cette préparation ?')))return;
    const scenario = document?.scenarios.find(item => item.id === id);
    setSelectedScenario(id); setComparison(null); setConfirmApply(false);
    if (!scenario) {setName(''); setPreview(null); return;}
    setName(scenario.name); rawSetOptions(scenario.options); setEnergyInput(String(scenario.options.energy_floor));
    setDirty(false);setCriteriaEpoch(value=>value+1);
    setPreview({key: '', result: scenario.preview, historical: true});
  }

  async function calculate() {
    if (!validEnergy || !validWeights) return;
    const sentKey = key;
    await run(async () => {
      const value = await request('/lineup-lab/preview', {team_id: team, options}, d.csrf);
      if (mounted.current && currentKey.current === sentKey) setPreview({key: sentKey, result: value, historical: false});
    });
  }

  async function save(asNew: boolean) {
    if (!document || !fresh || !name.trim()) return;
    const sentKey=key;
    await run(async () => {
      const value: Document = await act('/lineup-lab/scenarios', {team_id: team, options, name: name.trim(), expected_revision: document.revision, expected_source_id: result?.source?.id ?? null,
        ...(selectedScenario && !asNew ? {id: selectedScenario} : {})}, 'Scénario conservé dans votre espace privé');
      if (!mounted.current) return;
      setDocument(value);
      if(currentKey.current===sentKey)setDirty(false);
      if (asNew || !selectedScenario) setSelectedScenario(value.scenarios.at(-1)?.id || '');
    });
  }

  return <section className="lineup-lab" aria-labelledby="lineup-lab-title">
    <div className="lab-heading"><div><span className="eyebrow">{tr("VOTRE ATELIER DU XV · ")}{d.current_team.name}</span><h2 id="lineup-lab-title">{tr("Composez avec vos choix.")}</h2><p>{tr("Fixez vos titulaires, écartez les joueurs à ménager, puis optimisez les places libres. Les scénarios restent dans votre espace privé.")}</p></div><Users size={26} aria-hidden="true"/></div>
    {error && <div className="notice error" role="alert">{tr(error)}<button className="text-button" disabled={locked} onClick={() => setReload(value => value+1)}>{tr("Recharger les scénarios")}</button></div>}
    <fieldset className="lab-controls" disabled={locked}><legend>{tr("Critères de cet atelier")}</legend>
      <label>{tr("Objectif")}<select value={options.objective} onChange={event => setOptions({...options, objective: event.target.value as Options['objective']})}>{Object.entries(objectives).map(([id, label]) => <option key={id} value={id}>{tr(label)}</option>)}</select></label>
      <label>{tr("Seuil d’énergie (%)")}<input type="number" min="0" max="110" step="1" value={energyInput} onChange={event => {setEnergyInput(event.target.value); setOptions({...options, energy_floor: Number(event.target.value)});}}/></label>
      <label>{tr("Échelle de la source")}<select value={options.energy_scale} onChange={event => setOptions({...options, energy_scale: event.target.value as Options['energy_scale']})}><option value="auto">{tr("Détection automatique")}</option><option value="percent">{tr("Pourcentage · 0 à 110")}</option><option value="level">{tr("Niveau · 1 à 11")}</option></select></label>
      <button className="button primary" disabled={!validEnergy || !validWeights || !d.squad.length} onClick={() => void calculate()}><RefreshCw size={16} className={working ? 'spin' : ''}/>{tr("Optimiser les places libres")}</button>
    </fieldset>
    <RoleWeightsEditor key={criteriaEpoch} team={team} csrf={d.csrf} players={d.squad} value={options} locked={locked} onChange={criteria=>setOptions(previous=>({...previous,...criteria}))}/>
    {!validEnergy && <p className="text-error" role="alert">{tr("Le seuil doit être un entier entre 0 et 110.")}</p>}
    {!d.squad.length && <p className="muted">{tr("Importez un effectif senior pour commencer à composer.")}</p>}
    <div className="lab-layout">
      <div className="lab-pitch" role="group" aria-label={tr("Terrain interactif : choisir un poste pour le verrouiller")}>
        <div className="lab-pitch-heading"><span>{tr("LE QUINZE")}</span><span>{Object.keys(options.locks).length}{tr(" poste(s) verrouillé(s)")}</span></div>
        {rows.map((row, index) => <div className="lab-pitch-row" key={index}>{row.map(position => {
          const assigned = options.locks[String(position)] || result?.lineup.slots[String(position)];
          const isLocked = !!options.locks[String(position)];
          return <button key={position} type="button" className={'lab-position '+(slot === position ? 'selected ' : '')+(isLocked ? 'locked' : '')} aria-pressed={slot === position} aria-label={`${position}, ${tr(roles[position-1])}, ${knownName(assigned || null)}${isLocked ? ', verrouillé' : ''}`} onClick={() => setSlot(position)}>
            <span className="lab-shirt">{position}{isLocked && <LockKeyhole size={11}/>}</span><span className="lab-position-role">{tr(roles[position-1])}</span><strong>{assigned ? knownName(assigned) : tr("À pourvoir")}</strong>
          </button>;
        })}</div>)}
        <span className="lab-pitch-note">{tr("Sélectionnez un poste pour fixer son joueur.")}</span>
      </div>
      <div className="lab-editor">
        <h3>{tr("Poste ")}{slot} · {tr(roles[slot-1])}</h3>
        <label>{tr("Joueur verrouillé à ce poste")}<select disabled={locked} value={options.locks[String(slot)] || ''} onChange={event => lockSlot(event.target.value)}><option value="">{tr("Laisser le calcul choisir")}</option>{d.squad.map(player => <option key={player.id} value={player.id}>{player.name}{Object.entries(options.locks).some(([position, id]) => id === player.id && position !== String(slot)) ? tr(" · déplacer ici") : ''}</option>)}</select></label>
        <div className="lab-inline-actions"><button className="button secondary" disabled={locked || !playerAtSlot} onClick={() => options.locks[String(slot)] ? lockSlot('') : lockSlot(playerAtSlot)}>{options.locks[String(slot)] ? <Unlock size={15}/> : <LockKeyhole size={15}/>} {options.locks[String(slot)] ? tr("Libérer ce poste") : tr("Verrouiller ce joueur")}</button>
          {playerAtSlot && <button className="text-button" onClick={() => {const player = d.squad.find(item => item.id === playerAtSlot); if (player) openPlayer(player);}}>{tr("Fiche joueur")}</button>}</div>
        {selectedPlayer && <div className="lab-player-detail"><strong>{selectedPlayer.name}{tr(" · indice ")}{fmt(selectedPlayer.score)}</strong><p>{selectedPlayer.reason}</p></div>}
        <p className="lab-note">{tr("Un verrou impose ce joueur à ce poste. Un titulaire imposé laisse son poste au calcul. Une blessure connue ou une énergie sous le seuil bloque un joueur imposé.")}</p>
        <details className="lab-constraints"><summary>{tr("Choisir les titulaires et exclusions ")}<span>{options.starter_ids.length}{tr(" imposé(s) · ")}{options.excluded_ids.length}{tr(" exclu(s)")}</span></summary>
          <label>{tr("Rechercher un joueur")}<input value={search} onChange={event => setSearch(event.target.value)} placeholder={tr("Nom du joueur")} type="search"/></label>
          <div className="lab-roster">{d.squad.filter(player => player.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(player => <label className="lab-roster-row" key={player.id}><span>{player.name}{Object.values(options.locks).includes(player.id) && <small>{tr("Poste verrouillé")}</small>}</span><select aria-label={tr("Participation de ")+player.name} disabled={locked} value={options.excluded_ids.includes(player.id) ? 'excluded' : options.starter_ids.includes(player.id) ? 'starter' : 'available'} onChange={event => playerStatus(player.id, event.target.value)}><option value="available">{tr("Au choix du calcul")}</option><option value="starter">{tr("Titulaire imposé")}</option><option value="excluded">{tr("Exclu de ce scénario")}</option></select></label>)}</div>
        </details>
      </div>
    </div>
    {result && <>
      <div className={'lab-result-heading '+(!fresh ? 'lab-stale' : '')}><strong>{preview?.historical ? tr("Scénario enregistré") : fresh ? tr("Aperçu calculé") : tr("Aperçu à recalculer")} · {result.summary.selected}{tr("/15 titulaires · indice ")}{fmt(result.score)}</strong><p>{tr("Critères conservés : ")}{result.criteria?.name||tr("Profil par défaut")}{tr(" · Moyenne pondérée des compétences connues")}</p><p>{localDate(result.generated_at)}{tr(" · Source : ")}{result.source?.source || tr("Aucune observation")} · {localDate(result.source?.observed_at)}</p>{!fresh && <p>{tr("Recalculez avec les critères et l’effectif actuels avant de sauvegarder ou d’utiliser ce XV.")}</p>}</div>
      {result.warnings.length > 0 && <div className="lab-warning" role="status"><CircleAlert size={18}/><ul>{result.warnings.map(warning => <li key={warning}>{tr(warning)}</li>)}</ul></div>}
      <section className="lab-bench" aria-labelledby="lab-bench-title"><h3 id="lab-bench-title">{tr("Le banc et les rôles couverts")}</h3><div className="lab-reserves">{result.lineup.players.filter(player => player.slot > 15).map(player => <article key={player.slot}><span>{player.slot}</span><div><strong>{player.name}</strong><small>{tr("Indice ")}{fmt(player.score)}{tr(" · énergie ")}{player.energy === null ? tr("inconnue") : fmt(player.energy)+' %'}</small><p>{player.covers?.join(' · ')}</p><details><summary>{tr("Pourquoi ce joueur")}</summary><p>{player.reason}</p></details></div></article>)}</div>
        {result.lineup.players.every(player => player.slot <= 15) && <p>{tr("Aucun remplaçant disponible.")}</p>}
        <div className="lab-coverage">{result.lineup.bench_coverage.roles.map(role => <div className={role.missing ? 'missing' : ''} key={role.role}><strong>{role.missing ? <CircleAlert size={14}/> : <Check size={14}/>} {role.role}</strong><span>{role.player_ids.length}{tr(" option(s) · ")}{role.needed}{tr(" recherchée(s)")}</span><small>{role.missing ? `${role.missing} option(s) manquante(s)` : role.player_ids.map(id => knownName(id)).join(', ')}</small></div>)}</div><p className="lab-note">{result.lineup.bench_coverage.method}</p>
      </section>
      {result.lineup.excluded.length > 0 && <details className="lab-excluded"><summary>{tr("Joueurs écartés (")}{result.lineup.excluded.length})</summary><ul>{result.lineup.excluded.map(player => <li key={player.id}><strong>{player.name}</strong> · {player.reason}</li>)}</ul></details>}
      <div className="lab-apply"><p>{tr("Ce XV peut remplacer la composition locale du club après confirmation.")}</p>{!confirmApply ? <button className="button secondary" disabled={locked || !fresh || !Object.keys(result.lineup.slots).length} onClick={() => setConfirmApply(true)}>{tr("Utiliser ce XV dans l’outil")}</button> : <div role="group" aria-label={tr("Confirmer le remplacement du XV")}><p><strong>{tr("Remplacer le XV et le banc sauvegardés de ")}{d.current_team.name} ?</strong>{tr(" Les places non pourvues seront vides.")}</p><div className="lab-inline-actions"><button className="button secondary" disabled={locked} onClick={() => setConfirmApply(false)}>{tr("Annuler")}</button><button className="button primary" disabled={locked || !fresh} onClick={() => void run(async () => {const applied = await act('/lineup-lab/apply', {team_id: team, options, expected_source_id: result.source?.id ?? null, expected_slots: d.lineup}, 'XV et banc enregistrés dans l’outil'); if (mounted.current) {setConfirmApply(false); setPreview({key, result: applied.preview, historical: false});}})}>{tr("Confirmer le remplacement local")}</button></div></div>}</div>
    </>}
    <section className="lab-scenarios" aria-labelledby="lab-scenarios-title"><div className="lab-heading"><div><span className="eyebrow">{tr("VOS PRÉPARATIONS CONSERVÉES")}</span><h3 id="lab-scenarios-title">{tr("Scénarios nommés")}</h3></div><span>{document?.scenarios.length || 0}/20</span></div>
      <div className="lab-controls"><label>{tr("Ouvrir un scénario")}<select value={selectedScenario} disabled={locked || !document} onChange={event => loadScenario(event.target.value)}><option value="">{tr("Nouvelle préparation")}</option>{document?.scenarios.map(scenario => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label><label>{tr("Nom de la préparation")}<input maxLength={80} value={name} disabled={locked} onChange={event => {setDirty(true);setName(event.target.value);}} placeholder={tr("Ex. Réception de samedi")}/></label><div className="lab-inline-actions"><button className="button primary" disabled={locked || !document || !fresh || !name.trim()} onClick={() => void save(false)}><Save size={15}/>{selectedScenario ? tr("Mettre à jour") : tr("Conserver")}</button>{selectedScenario && <button className="button secondary" disabled={locked || !document || !fresh || !name.trim()} onClick={() => void save(true)}>{tr("Créer une copie")}</button>}</div></div>
      {selectedScenario && <button className="text-button lab-delete" disabled={locked || !document} onClick={() => void run(async () => {if (!document) return; const value = await act('/lineup-lab/delete', {team_id: team, id: selectedScenario, expected_revision: document.revision}, 'Scénario supprimé'); if (mounted.current) {setDocument(value); setSelectedScenario(''); setName(''); if (leftId === selectedScenario) setLeftId(''); if (rightId === selectedScenario) setRightId('');}})}><Trash2 size={14}/>{tr("Supprimer ce scénario")}</button>}
      {!document?.scenarios.length && <p className="muted">{tr("Calculez un premier XV, donnez-lui un nom, puis conservez-le pour préparer vos variantes.")}</p>}
      {!!document?.scenarios.length && <><div className="lab-compare-controls"><label>{tr("Scénario de référence")}<select value={leftId} onChange={event => setLeftId(event.target.value)}><option value="">{tr("Choisir…")}</option>{document.scenarios.map(scenario => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label><label>{tr("Scénario à comparer")}<select value={rightId} onChange={event => setRightId(event.target.value)}><option value="">{tr("Choisir…")}</option>{document.scenarios.map(scenario => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label></div>
        {comparison && <div className="lab-comparison" aria-live="polite"><div className="lab-table-scroll" role="region" tabIndex={0} aria-label={tr("Comparaison des scénarios")}><table><thead><tr><th scope="col">{tr("Valeur enregistrée")}</th><th scope="col">{comparison.left.name}</th><th scope="col">{comparison.right.name}</th></tr></thead><tbody><tr><th scope="row">{tr("Indice du XV")}</th><td>{fmt(comparison.left.score)}</td><td>{fmt(comparison.right.score)}</td></tr><tr><th scope="row">{tr("Titulaires")}</th><td>{comparison.left.starters}/15</td><td>{comparison.right.starters}/15</td></tr><tr><th scope="row">{tr("Couverture manquante")}</th><td>{comparison.left.bench_gaps.join(', ') || tr("Aucune")}</td><td>{comparison.right.bench_gaps.join(', ') || tr("Aucune")}</td></tr></tbody></table></div><p><strong>{tr("Écart d’indice : ")}{fmt(comparison.delta)}</strong> · {comparison.changes.length}{tr(" place(s) différente(s).")}</p>{comparison.warnings.map(warning => <p key={warning} className="lab-note">{tr(warning)}</p>)}<p className="lab-note">{comparison.explanation}</p>{comparison.changes.length > 0 && <details><summary>{tr("Voir les changements de joueurs")}</summary><ul>{comparison.changes.map(change => <li key={change.slot}>{tr("Poste ")}{change.slot} : {knownName(change.left)} → {knownName(change.right)}</li>)}</ul></details>}</div>}
      </>}
      <p className="lab-note">{tr("Les scénarios conservent leurs observations et explications au moment du calcul. Aucun ordre n’est envoyé dans Classic depuis cet atelier.")}</p>
    </section>
  </section>;
}
