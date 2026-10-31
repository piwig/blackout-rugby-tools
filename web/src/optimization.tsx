import {localeTag,tr} from './i18n';
import {useEffect, useRef, useState, type KeyboardEvent} from 'react';
import {ArrowRight, ArrowUpRight, BarChart3, Battery, CalendarRange, Check, ChevronDown, CircleAlert, Compass, Download, Info, Layers, RefreshCw, Save, ShieldCheck, SlidersHorizontal, Sprout, Target, Users, X} from 'lucide-react';
import type {Actions} from './App';
import {fmt, labels, short, skills, type State} from './types';
import type {OptimizationCategory, OptimizationObjective, OptimizationPriority, OptimizationReport} from './optimization-types';
import {LineupLab} from './lineup-lab';
import {CoachAdvice} from './coach-advice';
import {useNavigationGuard} from './navigation-guard';

const goals = [
  {id: 'balanced', label: 'Performance', detail: 'Donner la priorité aux affinités connues à chaque poste.', Icon: Target},
  {id: 'recovery', label: 'Récupération', detail: 'Favoriser les joueurs dont l’énergie connue est la plus élevée.', Icon: Battery},
  {id: 'development', label: 'Développement', detail: 'Donner davantage de poids aux jeunes profils.', Icon: Sprout},
] as const;
const categories: Record<OptimizationCategory, string> = {squad: 'Effectif', training: 'Entraînement', academy: 'Académie', season: 'Saison', stadium: 'Stade', data: 'Données'};
const priorities: Record<OptimizationPriority, string> = {high: 'Prioritaire', medium: 'À préparer', low: 'À explorer'};
const priorityOrder = {high: 0, medium: 1, low: 2};
const tabs = [
  {id: 'summary', label: 'Synthèse', Icon: Compass},
  {id: 'lineup', label: 'XV & banc', Icon: Users},
  {id: 'season', label: 'Saison & entraînement', Icon: CalendarRange},
  {id: 'matches', label: 'Matchs', Icon: BarChart3},
] as const;
type Tab = typeof tabs[number]['id'];
type Bundle = {reports: OptimizationReport[]; state: State; key: string};
type Confirmation = {kind: 'lineup' | 'training'; report: OptimizationReport};

function sourceDate(value: string | null) {
  if (!value) return tr('Aucun instantané');
  const parsed = new Date(value.includes('T') ? value : value.replace(' ', 'T'));
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(localeTag(), {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'});
}

export function Optimization({d, act, go, busy, openPlayer}: Actions) {
  const navigationGuard=useNavigationGuard();
  const [objective, setObjective] = useState<OptimizationObjective>('balanced');
  const [energy, setEnergy] = useState('60');
  const [energyScale, setEnergyScale] = useState<'auto' | 'percent' | 'level'>('auto');
  const [season, setSeason] = useState(String(d.game_date?.season || Number(Object.keys(d.plans).sort((a, b) => Number(a) - Number(b)).at(-1)) || 62));
  const [scope, setScope] = useState<'current' | 'all'>('current');
  const [selectedTeam, setSelectedTeam] = useState(d.current_team.id);
  const [tab, setTab] = useState<Tab>('summary');
  const [category, setCategory] = useState('all');
  const [priority, setPriority] = useState('all');
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loadError, setLoadError] = useState<{key: string; state: State; message: string} | null>(null);
  const [revision, setRevision] = useState(0);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveConflict, setSaveConflict] = useState(false);
  const saveLock = useRef(false);

  const validOptions = energy.trim() !== '' && Number.isInteger(Number(energy)) && Number(energy) >= 0 && Number(energy) <= 110 && season.trim() !== '' && Number.isInteger(Number(season)) && Number(season) >= 1 && Number(season) <= 999;
  const params = new URLSearchParams({team_id: d.current_team.id, objective, energy_floor: energy, energy_scale: energyScale, season, scope});
  const query = params.toString();
  const key = `${query}:${revision}`;
  // State identity changes on every successful refresh. Invalidate during render,
  // before effects run, so an old preview cannot be saved with new options/data.
  const fresh = validOptions && !saveConflict && bundle?.key === key && bundle.state === d;
  const reports = fresh ? bundle.reports : [];
  const report = reports.find(r => r.team.id === selectedTeam) || reports.find(r => r.team.id === d.current_team.id) || reports[0];
  const currentError = loadError?.key === key && loadError.state === d ? loadError.message : '';
  const loading = validOptions && !saveConflict && !fresh && !currentError;
  const locked = busy || saving || saveConflict;
  const reportSelection = !!report?.team.id.includes(':');
  const canSave = !!report && report.team.id === d.current_team.id && !locked && fresh;
  const ownedIds = d.classic_account?.team_ids || [];

  useEffect(() => {
    setBundle(null);
    setLoadError(null);
    setConfirmation(null);
    if (!validOptions || saveConflict) return;
    const controller = new AbortController();
    let cancelled = false;
    let timedOut = false;
    const timer = window.setTimeout(() => {timedOut = true; controller.abort();}, 30000);
    async function load() {
      try {
        const response = await fetch('/api/optimization?' + query, {signal: controller.signal, credentials: 'same-origin', cache: 'no-store'});
        const doc = await response.json();
        if (!response.ok) throw new Error(typeof doc.detail === 'string' ? doc.detail : 'Le bilan est indisponible. Vérifiez les réglages puis réessayez.');
        if (!Array.isArray(doc.reports) || doc.reports.some((r: OptimizationReport) => !r.team || r.objective !== objective || r.season !== Number(season) || (scope === 'current' && r.team.id !== d.current_team.id))) throw new Error('Le bilan reçu ne correspond pas aux réglages demandés. Relancez le calcul.');
        if (!cancelled && !controller.signal.aborted) setBundle({reports: doc.reports, state: d, key});
      } catch (error) {
        if (!cancelled) setLoadError({key, state: d, message: timedOut ? 'Le calcul a pris trop de temps. Réessayez dans un instant.' : error instanceof Error ? error.message : 'Impossible de calculer le bilan.'});
      } finally {window.clearTimeout(timer);}
    }
    void load();
    return () => {cancelled = true; controller.abort(); window.clearTimeout(timer);};
  }, [d, query, key, validOptions, objective, season, scope, saveConflict]);

  function exportReport() {
    if (!fresh || !report || locked) return;
    // Explicit report fields only: never export the account state or its CSRF token.
    const exported = reports.map(({team, objective, season, generated_at, sources, warnings, summary, lineup, recommendations, training, season_plan, matches, methodology}) => ({team, objective, season, generated_at, sources, warnings, summary, lineup, recommendations, training, season_plan, matches, methodology}));
    const blob = new Blob([JSON.stringify({format: 'brt-optimization-v1', scope, energy_floor: Number(energy), energy_scale: energyScale, displayed_team: report.team.id, reports: exported}, null, 2)], {type: 'application/json;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `brt-optimisation-${scope === 'all' ? 'clubs' : report.team.id.replace(/[^a-z0-9_-]/gi, '')}-s${season}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function save() {
    if (saveLock.current || !canSave || !confirmation || confirmation.report !== report) return;
    const target = confirmation;
    if (target.kind === 'training' && (target.report.training.added < 1 || !trainingPreservesState(target.report, d))) {
      setConfirmation(null);
      setSaveError('Le programme a changé ou ne préserve pas toutes les cases existantes. Recalculez le bilan.');
      setRevision(value => value + 1);
      return;
    }
    saveLock.current = true;
    setSaving(true);
    setSaveError('');
    try {
      if (target.kind === 'lineup') {
        await act('/lineup', {team_id: target.report.team.id, slots: target.report.lineup.slots, expected_slots: d.lineup}, 'XV et banc enregistrés dans l’outil');
      } else {
        await act('/plans', {team_id: target.report.team.id, season: target.report.season, grid: target.report.training.grid, expected_grid: d.plans[String(target.report.season)] || Array.from({length: 4}, () => Array(16).fill(''))}, 'Programme enregistré dans l’outil');
      }
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Enregistrement impossible. Recalculez le bilan avant de réessayer.');
      if ((error as {status?: number})?.status === 409) setSaveConflict(true);
    } finally {
      saveLock.current = false;
      setSaving(false);
      setConfirmation(null);
      setRevision(value => value + 1);
    }
  }

  function changeTab(next:Tab) {
    if(next===tab)return true;
    if(!navigationGuard.confirmLeave())return false;
    setTab(next);
    return true;
  }

  function tabKeys(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex(item => item.id === tab);
    const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
    if (next < 0) return;
    event.preventDefault();
    if(!changeTab(tabs[next].id))return;
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  }

  return <div className="opt-workspace">
    <section className="opt-settings" aria-labelledby="opt-settings-title">
      <div className="opt-section-heading"><div><span className="eyebrow">{tr("AVANT DE CHOISIR LE XV")}</span><h2 id="opt-settings-title">{tr("Quel visage pour votre équipe ?")}</h2></div><SlidersHorizontal size={22} aria-hidden="true"/></div>
      <fieldset className="opt-goals" disabled={locked}><legend>{tr("Votre objectif pour le XV")}</legend>{goals.map(({id, label, detail, Icon}) => <label className={'opt-goal ' + (objective === id ? 'opt-selected' : '')} key={id}><input type="radio" name="optimization-objective" value={id} checked={objective === id} onChange={() => setObjective(id)}/><Icon size={21} aria-hidden="true"/><span><strong>{tr(label)}</strong><small>{tr(detail)}</small></span><Check className="opt-goal-check" size={17} aria-hidden="true"/></label>)}</fieldset>
      <div className="opt-controls">
        <label className="opt-energy">{tr("Seuil d’énergie normalisé ")}<span className="opt-range"><input type="range" min="0" max="110" disabled={locked} value={Number(energy) || 0} aria-label={tr("Seuil d’énergie normalisé, curseur de 0 à 110 pour cent")} onChange={e => setEnergy(e.target.value)}/><input type="number" min="0" max="110" step="1" aria-label={tr("Seuil d’énergie normalisé, de 0 à 110 pour cent")} value={energy} disabled={locked} onChange={e => setEnergy(e.target.value)}/><span>%</span></span></label>
        <label>{tr("Format des énergies")}<select value={energyScale} disabled={locked} onChange={e => setEnergyScale(e.target.value as 'auto' | 'percent' | 'level')}><option value="auto">{tr("Auto (détection)")}</option><option value="percent">{tr("Pourcentage (0–110)")}</option><option value="level">{tr("Niveau (1–11)")}</option></select></label>
        <label>{tr("Saison à préparer")}<input type="number" min="1" max="999" step="1" value={season} disabled={locked} onChange={e => setSeason(e.target.value)}/></label>
        <label>{tr("Périmètre")}<select value={scope} disabled={locked} onChange={e => {const next=e.target.value as 'current'|'all';if(tab==='lineup'&&next==='all'&&selectedTeam!==d.current_team.id&&!navigationGuard.confirmLeave())return;setScope(next);}}><option value="current">{tr("L’équipe courante")}</option><option value="all">{tr("Toutes les équipes de cet espace")}</option></select></label>
      </div>
      <p className="opt-helper"><Info size={15} aria-hidden="true"/>{tr("Le seuil écarte les joueurs sous cette énergie connue. ")}{energyScale === 'auto' ? tr("Si toutes les valeurs sont ≤ 11, le format est ambigu : choisissez leur échelle pour activer le seuil et le bonus d’énergie.") : energyScale === 'level' ? tr("Les niveaux de 1 à 11 sont convertis en pourcentages approximatifs (niveau × 10).") : tr("Les pourcentages Classic peuvent atteindre 110 %.")}{tr(" Une énergie inconnue reste signalée.")}</p>
      {!validOptions && <p className="opt-inline-error" role="alert">{tr("Choisissez une énergie entière entre 0 et 110 et une saison entière entre 1 et 999.")}</p>}
    </section>

    {saveError && <div className="opt-warning" role="alert"><CircleAlert size={19}/><div><strong>{saveConflict ? tr("Les données ont changé depuis cet aperçu.") : tr("L’enregistrement n’a pas pu être confirmé.")}</strong><p>{tr(saveError)}</p>{saveConflict && <><p>{tr("Rechargez les données, puis ouvrez à nouveau Optimisation pour préparer un bilan à jour.")}</p><button className="button secondary" disabled={busy || saving} onClick={() => window.location.reload()}><RefreshCw size={16}/>{tr("Recharger les données")}</button></>}</div></div>}
    <div className="opt-results" aria-busy={loading}>
      {loading && <div className="opt-state" role="status"><RefreshCw className="spin" size={26}/><h2>{tr("On fait le point sur votre équipe…")}</h2><p>{tr("Nous croisons les effectifs, les séances prévues et les matchs de votre bibliothèque.")}</p></div>}
      {currentError && <div className="opt-state opt-error" role="alert"><CircleAlert size={28}/><h2>{tr("Le bilan n’est pas disponible.")}</h2><p>{tr(currentError)}</p><button className="button primary" disabled={locked} onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/>{tr("Réessayer")}</button></div>}
      {fresh && !report && <div className="opt-state"><Layers size={28}/><h2>{tr("Le bilan commence avec votre club.")}</h2><p>{tr("Ajoutez votre club et importez ses joueurs pour voir les premiers repères se dessiner.")}</p><button className="button primary" onClick={() => go('settings')}>{tr("Ouvrir les données")}<ArrowRight size={16}/></button></div>}
      {report && <>
        {scope === 'all' && <section className="opt-club-overview" aria-label={tr("Bilans des clubs")}><div className="opt-overview-heading"><h2>{tr("Votre vue multi-clubs")}</h2><span>{reports.length}{reports.length > 1 ?tr(" clubs"):tr(" club")}{tr(" dans cet espace privé")}</span></div><div className="opt-clubs">{reports.map(item => <button key={item.team.id} className={'opt-club ' + (item.team.id === report.team.id ? 'opt-selected' : '')} aria-pressed={item.team.id === report.team.id} disabled={locked} onClick={() => {if(tab==='lineup'&&item.team.id!==selectedTeam&&item.team.id!==d.current_team.id&&!navigationGuard.confirmLeave())return;setSelectedTeam(item.team.id); setConfirmation(null);}}><span className="opt-club-type">{item.team.country} · {ownedIds.includes(item.team.id) ? tr("Club du compte Classic") : tr("Club suivi")}</span><strong>{item.team.name}</strong><span>{item.summary.eligible}/{item.summary.seniors}{tr(" seniors éligibles")}</span><small>{item.recommendations.filter(r => r.priority === 'high').length}{tr(" conseil(s) prioritaire(s)")}<ArrowUpRight size={14}/></small></button>)}</div><p className="opt-helper">{tr("Sélectionner un bilan ne change pas le club courant de l’atelier. Pour enregistrer un autre club, choisissez-le dans le sélecteur en haut de page.")}</p></section>}
        <div className="opt-report-heading"><div><span className="eyebrow">{tr(goals.find(goal => goal.id === report.objective)?.label||'').toUpperCase()}{tr(" / SAISON ")}{report.season}</span><h2>{report.team.name}<span className="opt-report-tag">{report.team.id === d.current_team.id ? tr("Club courant") : tr("Aperçu")}</span>{!ownedIds.includes(report.team.id) && <span className="opt-report-tag">{tr("Club suivi")}</span>}</h2><p>{tr("Calculé le ")}{sourceDate(report.generated_at)}</p></div><div className="opt-report-actions"><button className="button secondary" disabled={locked} onClick={() => setRevision(value => value + 1)} aria-label={tr("Recalculer le bilan")}><RefreshCw size={16}/><span>{tr("Recalculer")}</span></button><button className="button secondary" disabled={locked} onClick={exportReport}><Download size={16}/>{tr("Exporter JSON")}</button></div></div>
        <div className="opt-tabs" role="tablist" aria-label={tr("Contenu du bilan")} onKeyDown={tabKeys}>{tabs.map(({id, label, Icon}) => <button key={id} id={'opt-tab-' + id} role="tab" aria-selected={tab === id} aria-controls={'opt-panel-' + id} tabIndex={tab === id ? 0 : -1} onClick={() => changeTab(id)}><Icon size={17} aria-hidden="true"/>{tr(label)}</button>)}</div>
        <div id={'opt-panel-' + tab} role="tabpanel" aria-labelledby={'opt-tab-' + tab} tabIndex={0} className="opt-panel">
          {tab === 'summary' && <>
            {report.team.id===d.current_team.id&&<CoachAdvice d={d}/>}
            <div className="opt-stats">
              <article><Users size={20}/><span>{tr("Seniors éligibles")}</span><strong>{report.summary.eligible}<small> / {report.summary.seniors}</small></strong><p>{tr("Selon les critères connus")}</p></article>
              <article><Target size={20}/><span>{tr("Places proposées")}</span><strong>{report.lineup.players.filter(p => p.slot <= 15).length}<small> / 15</small></strong><p>{report.lineup.players.filter(p => p.slot > 15).length}{tr(" remplaçant(s) proposés")}</p></article>
              <article><Battery size={20}/><span>{tr("Sous le seuil d’énergie")}</span><strong>{report.summary.low_energy}</strong><p>{report.summary.unknown_energy}{tr(" énergie(s) inconnue(s)")}</p></article>
              {!reportSelection&&<article><Sprout size={20}/><span>{tr("Jeunes à développer")}</span><strong>{report.summary.academy}</strong><p>{tr("Dans l’académie importée")}</p></article>}
            </div>
            {report.warnings.length > 0 && <div className="opt-warning"><CircleAlert size={21}/><div><h3>{tr("Les points de vigilance")}</h3><ul>{report.warnings.map((warning, i) => <li key={i}>{tr(warning)}</li>)}</ul></div></div>}
            <div className="opt-recommendation-heading"><div><span className="eyebrow">{tr("VOS PROCHAINES DÉCISIONS")}</span><h2>{tr("Les choix qui méritent votre attention")}</h2></div><div className="opt-filters"><label><span className="opt-sr-only">{tr("Catégorie des conseils")}</span><select value={category} onChange={e => setCategory(e.target.value)}><option value="all">{tr("Tous les sujets")}</option>{Object.entries(categories).map(([id, label]) => <option key={id} value={id}>{tr(label)}</option>)}</select></label><label><span className="opt-sr-only">{tr("Priorité des conseils")}</span><select value={priority} onChange={e => setPriority(e.target.value)}><option value="all">{tr("Toutes les priorités")}</option>{Object.entries(priorities).map(([id, label]) => <option key={id} value={id}>{tr(label)}</option>)}</select></label></div></div>
            <Recommendations report={report} category={category} priority={priority} go={go}/>
            <div className="opt-sources"><span><ShieldCheck size={17}/>{tr("Les données derrière ce bilan")}</span><p>{tr("Effectif : ")}{sourceDate(report.sources.squad)}<br/>{tr("Académie : ")}{sourceDate(report.sources.academy)}</p><button className="text-button" onClick={() => go('settings')}>{tr("Actualiser mes sources")}<ArrowUpRight size={15}/></button></div>
          </>}
          {tab === 'lineup' && <details className="opt-excluded"><summary>{tr("Voir la proposition générale du bilan")}</summary><LineupPreview report={report} canSave={canSave} onSave={() => setConfirmation({kind: 'lineup', report})} go={go}/></details>}
          {tab === 'season' && (reportSelection ? <div className="notice">{tr("La formation des joueurs d’une sélection reste gérée par leurs clubs.")}</div> : <SeasonPreview report={report} d={d} canSave={canSave} onSave={() => setConfirmation({kind: 'training', report})} go={go}/>)}
          {tab === 'matches' && <MatchPreview reports={reports} go={go}/>}
        </div>
        <details className="opt-methodology"><summary><span><Info size={18}/>{tr("Comprendre les calculs et leurs limites")}</span><ChevronDown size={18}/></summary><div><p>{tr("Une aide à la préparation fondée sur les données importées. Ces indices et recommandations ne sont pas une simulation officielle de Blackout Rugby et ne prédisent pas le résultat d’un match.")}</p><ul>{report.methodology.map((method, i) => <li key={i}>{method}</li>)}</ul><p>{tr("Les sauvegardes concernent uniquement cet outil. Les choix définitifs restent à reporter dans le jeu.")}</p></div></details>
      </>}
    </div>
    {tab === 'lineup' && (scope === 'current' || selectedTeam === d.current_team.id) && <LineupLab key={d.current_team.id} d={d} act={act} go={go} busy={busy} openPlayer={openPlayer}/>}
    {confirmation && report === confirmation.report && fresh && <SaveConfirmation confirmation={confirmation} saving={locked} onCancel={() => {if (!locked) setConfirmation(null);}} onSave={save}/>}
  </div>;
}

function Recommendations({report, category, priority, go}: {report: OptimizationReport; category: string; priority: string; go: Actions['go']}) {
  const shown = report.recommendations.filter(item => (category === 'all' || item.category === category) && (priority === 'all' || item.priority === priority)).sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);
  return shown.length ? <div className="opt-recommendations">{shown.map(item => <article key={item.id} className={'opt-recommendation opt-priority-' + item.priority}><div className="opt-recommendation-tags"><span>{tr(categories[item.category])}</span><span className={'opt-priority-label opt-' + item.priority}>{tr(priorities[item.priority])}</span></div><h3>{tr(item.title)}</h3><p>{item.detail}</p><details className="opt-evidence"><summary>{tr("Sur quelles données ?")}</summary>{item.evidence.length ? <ul>{item.evidence.map((evidence, i) => <li key={i}>{evidence}</li>)}</ul> : <p>{tr("Aucune preuve complémentaire disponible.")}</p>}</details>{['squad', 'training', 'academy', 'stadium', 'settings', 'matches'].includes(item.page) && <button className="text-button" onClick={() => go(item.page)}>{tr("Ouvrir ")}{({squad: 'l’effectif', training: 'l’entraînement', academy: 'l’académie', stadium: 'le stade', settings: 'les données', matches: 'les matchs'} as Record<string, string>)[item.page]}<ArrowUpRight size={15}/></button>}</article>)}</div> : <div className="opt-state opt-compact"><Check size={24}/><h3>{tr("Aucun conseil pour cette sélection.")}</h3><p>{tr("Changez les filtres pour parcourir les autres sujets du bilan.")}</p></div>;
}

function LineupPreview({report, canSave, onSave, go}: {report: OptimizationReport; canSave: boolean; onSave: () => void; go: Actions['go']}) {
  const comparison = report.lineup.comparison;
  return <>
    <div className="opt-section-heading"><div><span className="eyebrow">{tr("COMPOSITION PROPOSÉE")}</span><h2>{tr("Un collectif à discuter.")}</h2><p>{tr("Chaque joueur apparaît une seule fois. Les indices servent à comparer les affinités connues. Enregistrez la proposition, puis ajustez-la dans Effectif & XV.")}</p></div><button className="button secondary" onClick={() => go('squad')}>{tr("Modifier dans Effectif & XV")}<ArrowUpRight size={16}/></button></div>
    <div className="opt-comparison"><Target size={25}/><div><strong>{comparison.delta === null ? tr("Comparaison au XV sauvegardé indisponible") : `${comparison.delta > 0 ? '+' : ''}${fmt(comparison.delta)} d’indice par rapport au XV sauvegardé`}</strong><p>{comparison.delta === null ? tr("Un écart n’est affiché que lorsque les compositions ont une couverture comparable.") : `Indice sauvegardé : ${fmt(comparison.saved_score)} · Indice proposé : ${fmt(comparison.proposed_score)}. Cet écart n’est pas une probabilité de victoire.`}</p></div></div>
    {[{name: 'Le quinze de départ', first: 1, last: 15}, {name: 'Le banc', first: 16, last: 23}].map(group => <section className="opt-lineup-section" key={group.first}><h3>{group.name}<span>{report.lineup.players.filter(player => player.slot >= group.first && player.slot <= group.last).length} / {group.last - group.first + 1}</span></h3><div className="opt-lineup-grid">{Array.from({length: group.last - group.first + 1}, (_, index) => index + group.first).map(slot => {
      const player = report.lineup.players.find(item => item.slot === slot);
      return <article className={'opt-player ' + (!player ? 'opt-unfilled' : '')} key={slot}><span className="opt-jersey">{slot}</span>{player ? <div><span className="opt-player-role">{player.role}</span><h4>{player.name}</h4><div className="opt-player-values"><span>{tr("Indice ")}<b>{fmt(player.score)}</b></span><span className={player.energy === null ? 'opt-unknown' : ''}><Battery size={13}/>{player.energy === null ? tr("Énergie inconnue") : `${fmt(player.energy)} %`}</span></div><p>{player.reason}</p></div> : <div><span className="opt-player-role">{slot <= 15 ? tr("Poste ") + slot : tr("Remplaçant")}</span><h4>{tr("Non pourvu")}</h4><p>{tr("Aucun joueur éligible proposé pour cette place.")}</p></div>}</article>;
    })}</div></section>)}
    {report.lineup.unfilled.length > 0 && <p className="opt-inline-note"><CircleAlert size={17}/>{tr("Places non pourvues : ")}{report.lineup.unfilled.join(', ')}{tr(". Vérifiez l’effectif avant d’utiliser cette composition.")}</p>}
    {report.lineup.excluded.length > 0 && <details className="opt-excluded"><summary>{tr("Joueurs écartés de la proposition (")}{report.lineup.excluded.length})</summary><ul>{report.lineup.excluded.map(player => <li key={player.id}><strong>{player.name}</strong><span>{player.reason}</span></li>)}</ul></details>}
    <div className="opt-save-bar"><div><strong>{tr("Conserver cette composition")}</strong><p>{canSave ? tr("Après confirmation, elle remplacera le XV et le banc sauvegardés dans l’outil.") : tr("La sauvegarde est réservée au club courant, après chargement complet du bilan.")}</p></div><button className="button primary" disabled={!canSave || report.lineup.players.length === 0} onClick={onSave}><Save size={16}/>{tr("Enregistrer le XV & banc")}</button></div>
  </>;
}

// The existing /plans route replaces a whole grid. Check every saved cell and
// every elapsed week before allowing the proposed academy programme to be sent.
function trainingPreservesState(report: OptimizationReport, d: State) {
  const grid = report.training.grid;
  if (grid.length !== 4 || grid.some(row => row.length !== 16)) return false;
  const existing = d.plans[String(report.season)];
  const pastWeeks = d.game_date ? report.season < d.game_date.season ? 16 : report.season === d.game_date.season ? Math.max(0, d.game_date.round - 1) : 0 : 0;
  return grid.every((row, i) => row.every((cell, j) => {
    const prior = existing?.[i]?.[j] || '';
    return (!prior || cell === prior) && (j >= pastWeeks || cell === prior);
  }));
}

function SeasonPreview({report, d, canSave, onSave, go}: {report: OptimizationReport; d: State; canSave: boolean; onSave: () => void; go: Actions['go']}) {
  const safeGrid = report.team.id !== d.current_team.id || trainingPreservesState(report, d);
  const relation = !d.game_date ? 'Date du jeu non disponible' : report.season < d.game_date.season ? 'Saison passée' : report.season === d.game_date.season ? 'Saison en cours' : 'Saison future';
  return <>
    <div className="opt-section-heading"><div><span className="eyebrow">{tr("SAISON ")}{report.season} / {relation.toUpperCase()}</span><h2>{tr("Donner un cap à la relève.")}</h2><p>{tr("Les moyennes connues de vos jeunes donnent une première direction. Servez-vous de ce calendrier pour préparer les séances, puis ajustez au fil des observations.")}</p></div><button className="button secondary" onClick={() => go('training')}>{tr("Ouvrir l’entraînement")}<ArrowUpRight size={16}/></button></div>
    <div className="opt-phases">{report.season_plan.map((phase, i) => <article key={i}><span className="opt-phase-number">{String(i + 1).padStart(2, '0')}</span><span className="opt-phase-weeks">{phase.weeks}</span><h3>{phase.phase}</h3><ul>{phase.actions.map((action, index) => <li key={index}>{action}</li>)}</ul></article>)}</div>
    <section className="opt-training-priorities"><div className="opt-section-heading"><div><span className="eyebrow">{tr("LES AXES À TRAVAILLER")}</span><h2>{tr("Où porter l’effort à l’entraînement ?")}</h2></div><Sprout size={24}/></div>{report.training.priorities.length ? <div className="opt-skill-priorities">{report.training.priorities.map(item => <article key={item.skill}><h3>{tr(item.label)}</h3><strong>{fmt(item.average)}<small> / 21</small></strong><span>{item.count} / {report.summary.academy}{tr(" jeune(s) avec une valeur connue")}</span><p>{tr(item.reason)}</p></article>)}</div> : <div className="opt-state opt-compact"><Info size={24}/><h3>{tr("Encore trop peu de repères pour choisir.")}</h3><p>{tr("Il manque des compétences connues pour proposer un programme à l’académie. Complétez les observations ; vos séances déjà enregistrées restent visibles.")}</p><button className="text-button" onClick={() => go('academy')}>{tr("Consulter l’académie")}<ArrowRight size={15}/></button></div>}</section>
    <section className="opt-planning"><div className="opt-section-heading"><div><span className="eyebrow">{tr("APERÇU DU PROGRAMME")}</span><h2>{tr("Quatre créneaux. Seize semaines.")}</h2><p>{report.training.added}{tr(" case(s) proposée(s) · ")}{report.training.preserved}{tr(" case(s) existante(s) conservée(s) · ")}{report.training.remaining_weeks}{tr(" semaine(s) restante(s)")}</p></div></div><div className="opt-grid-scroll" tabIndex={0} role="region" aria-label={tr("Programme d’entraînement, défilement horizontal")}><table className="opt-training-table"><caption className="opt-sr-only">{tr("Programme proposé pour l’académie, saison ")}{report.season}{tr(". Les cases ajoutées sont signalées par un signe plus.")}</caption><thead><tr><th scope="col">{tr("Créneau")}</th>{Array.from({length: 16}, (_, i) => <th scope="col" key={i}>{tr("S")}{i + 1}</th>)}</tr></thead><tbody>{report.training.grid.map((row, i) => <tr key={i}><th scope="row">{tr("T")}{i + 1}</th>{row.map((value, j) => {
      const isCurrent = report.team.id === d.current_team.id;
      const isExisting = isCurrent && !!d.plans[String(report.season)]?.[i]?.[j];
      const added = isCurrent && !!value && !isExisting;
      const skillIndex = skills.indexOf(value as typeof skills[number]);
      return <td key={j} className={isExisting ? 'opt-cell-existing' : added ? 'opt-cell-added' : value ? 'opt-cell-planned' : ''} title={`Créneau ${i + 1}, semaine ${j + 1} : ${labels[value] || value || 'Vide'}${added ? ' (proposition)' : isExisting ? ' (conservé)' : ''}`}><span>{value ? skillIndex >= 0 ? short[skillIndex] : value : '—'}{added && <sup aria-label={tr("proposition")}>+</sup>}</span></td>;
    })}</tr>)}</tbody></table></div><div className="opt-grid-legend"><span><i className="opt-legend-existing"/>{tr("Case conservée")}</span><span><i className="opt-legend-added"/>{tr("+ Proposition à enregistrer")}</span><span>{tr("Survolez une case pour le nom complet.")}</span></div><p className="opt-helper">{report.team.id === d.current_team.id ? tr("Les cases remplies et les semaines passées sont préservées.") : tr("Aperçu du programme de ce club. Sélectionnez-le comme club courant pour distinguer et enregistrer les ajouts.")} {report.training.remaining_weeks > 0 ? `Ajouts possibles à partir de la semaine ${report.training.start_week}.` : tr("Aucune semaine restante à compléter.")}</p></section>
    {!safeGrid && <p className="opt-inline-error" role="alert">{tr("Le programme proposé ne préserve pas toutes les cases actuelles. Recalculez le bilan avant de l’enregistrer.")}</p>}
    <div className="opt-save-bar"><div><strong>{tr("Ajouter ces séances au planning")}</strong><p>{report.training.added === 0 ? tr("Aucune nouvelle case à enregistrer.") : canSave ? `Saison ${report.season} de ${report.team.name} : ${report.training.added} case(s) ajoutée(s), les cases existantes restent conservées.` : tr("Choisissez ce club en haut de page pour enregistrer son programme.")}</p></div><button className="button primary" disabled={!canSave || !safeGrid || report.training.added < 1} onClick={onSave}><Save size={16}/>{tr("Enregistrer le programme")}</button></div>
  </>;
}

function MatchPreview({reports, go}: {reports: OptimizationReport[]; go: Actions['go']}) {
  const [selected, setSelected] = useState('');
  const matches = Array.from(new Map(reports.flatMap(report => report.matches).map(match => [`${match.type}:${match.id}`, match])).values());
  const match = matches.find(item => `${item.type}:${item.id}` === selected) || matches[0];
  return <>
    <div className="opt-section-heading"><div><span className="eyebrow">{tr("BIBLIOTHÈQUE DU MANAGER")}</span><h2>{tr("Lire les tendances des deux camps.")}</h2><p>{tr("Ces matchs appartiennent à votre bibliothèque privée. Leur présence ne prouve aucun lien avec le club ou la saison du bilan.")}</p></div><button className="button secondary" onClick={() => go('matches')}>{tr("Ouvrir l’analyse des matchs")}<ArrowUpRight size={16}/></button></div>
    {!match ? <div className="opt-state"><BarChart3 size={28}/><h3>{tr("Le premier match donnera matière à l’analyse.")}</h3><p>{tr("Importez les événements d’une rencontre pour examiner les choix d’attaque, en gardant un œil sur la part des actions connues.")}</p><button className="button primary" onClick={() => go('matches')}>{tr("Ajouter un match")}<ArrowRight size={16}/></button></div> : <>
      <label className="opt-match-select">{tr("Match à observer")}<select value={`${match.type}:${match.id}`} onChange={e => setSelected(e.target.value)}>{matches.map(item => <option value={`${item.type}:${item.id}`} key={`${item.type}:${item.id}`}>{item.home} — {item.away} · {['Club', 'U20', 'National'][item.type] || tr("Type ") + item.type} #{item.id}</option>)}</select></label>
      <div className="opt-match-coverage"><div><span className="eyebrow">{tr("COUVERTURE DES ÉVÉNEMENTS")}</span><strong>{fmt(match.coverage)}<small> %</small></strong></div><div><b>{fmt(match.classified)}{tr(" action(s) classée(s) / ")}{fmt(match.total)}{tr(" événement(s)")}</b><p>{fmt(match.inferred)}{tr(" action(s) inférée(s) par reconnaissance des commentaires. Les tendances portent uniquement sur les actions classées.")}</p><div className="opt-coverage-track" aria-hidden="true"><span style={{width: `${Math.max(0, Math.min(100, match.coverage))}%`}}/></div></div></div>
      <div className="opt-match-sides">{match.sides.map(side => <article key={side.side}><span className="eyebrow">{side.side === 'home' ? tr("DOMICILE") : tr("EXTÉRIEUR")}</span><h3>{side.name}</h3><div className="opt-side-dominant"><BarChart3 size={21}/><div><strong>{side.dominant || tr("Tendance non concluante")}</strong><span>{side.share === null ? tr("Répartition insuffisante") : `${fmt(side.share)} % des actions classées de ce côté`} · {side.actions}{tr(" action(s)")}</span></div></div><ul className="opt-advice">{side.advice.map((advice, i) => <li key={i}>{advice}</li>)}</ul><details className="opt-evidence"><summary>{tr("Voir les observations sources")}</summary><ul>{side.evidence.map((evidence, i) => <li key={i}>{evidence}</li>)}</ul></details></article>)}</div>
      <p className="opt-inline-note"><Info size={17}/>{tr("Un faible échantillon appelle davantage d’observation. Une répartition d’attaques ne démontre ni une faiblesse adverse, ni la cause d’un résultat.")}</p>
    </>}
  </>;
}

function SaveConfirmation({confirmation, saving, onCancel, onSave}: {confirmation: Confirmation; saving: boolean; onCancel: () => void; onSave: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const {kind, report} = confirmation;
  useEffect(() => {const element = dialog.current; element?.showModal(); return () => {element?.close();};}, []);
  return <dialog ref={dialog} className="opt-confirm-dialog" aria-labelledby="opt-confirm-title" aria-describedby="opt-confirm-description" onCancel={event => {event.preventDefault(); if (!saving) onCancel();}}><div className="opt-confirm-header"><span className="opt-confirm-icon"><Save size={24}/></span><button className="icon-button" disabled={saving} aria-label={tr("Annuler l’enregistrement")} onClick={onCancel}><X size={20}/></button></div><span className="eyebrow">{tr("ENREGISTREMENT DANS L’OUTIL")}</span><h2 id="opt-confirm-title">{kind === 'lineup' ? tr("Remplacer la composition sauvegardée ?") : tr("Compléter ce programme ?")}</h2><p id="opt-confirm-description">{kind === 'lineup' ? <>{tr("Pour ")}<strong>{report.team.name}</strong>{tr(", les ")}{report.lineup.players.filter(p => p.slot <= 15).length}{tr(" titulaires et ")}{report.lineup.players.filter(p => p.slot > 15).length}{tr(" remplaçants proposés remplaceront le XV et le banc actuellement sauvegardés. Les places non pourvues resteront vides.")}</> : <>{tr("Pour ")}<strong>{report.team.name}{tr(", saison ")}{report.season}</strong>{tr(", le programme ajoutera ")}<strong>{report.training.added}{tr(" case(s)")}</strong>{tr(" et conservera ")}{report.training.preserved}{tr(" case(s) existante(s). Les semaines passées ne seront pas modifiées.")}</>}</p><div className="opt-confirm-detail"><ShieldCheck size={18}/><span>{tr("Cette action enregistre votre préparation dans Blackout Rugby Tools. Aucune modification n’est envoyée au jeu.")}</span></div><div className="opt-confirm-actions"><button className="button secondary" disabled={saving} onClick={onCancel} autoFocus>{tr("Revenir à l’aperçu")}</button><button className="button primary" disabled={saving} onClick={onSave}>{saving ? <RefreshCw className="spin" size={16}/> : <Save size={16}/>} {saving ? tr("Enregistrement…") : kind === 'lineup' ? tr("Remplacer le XV & banc") : tr("Ajouter les séances")}</button></div></dialog>;
}
