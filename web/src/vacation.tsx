import {localeTag,tr} from './i18n';
import {useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode} from 'react';
import {ArrowRight, CalendarRange, Check, CircleAlert, Clock, FileCheck2, History, Info, Pause, RefreshCw, Save, Send, ShieldCheck, SlidersHorizontal, Users, X} from 'lucide-react';
import {request, type Actions} from './App';
import type {Player, State} from './types';
import {CoachAdvice} from './coach-advice';
import type {VacationEnergyScale, VacationFixture, VacationObjective, VacationOptions, VacationPreview, VacationRule, VacationStatus} from './vacation-types';

type Choices = {objective: VacationObjective; energy_floor: string; energy_scale: VacationEnergyScale; excluded_ids: string[]; captain_id: string; kicker_id: string};
type RuleForm = Choices & {enabled: boolean; mode: 'prepare' | 'automatic'; start_at: string; end_at: string; lead_hours: string; manage_existing: boolean};
type PreviewBundle = {preview: VacationPreview; state: State; key: string};
type Confirmation = {kind: 'send'; preview: VacationPreview} | {kind: 'reconcile'; preview: VacationPreview} | {kind: 'rule'; rule: VacationRule};
const tabs = [{id: 'prepare', label: 'Préparer un envoi', Icon: Users}, {id: 'rules', label: 'Règles vacances', Icon: CalendarRange}, {id: 'journal', label: 'Journal & alertes', Icon: History}] as const;
type Tab = typeof tabs[number]['id'];
const previewLabels: Record<string, string> = {ready: 'Prêt à vérifier', blocked: 'Envoi bloqué', sending: 'Envoi en cours', confirmed: 'Envoi vérifié', uncertain: 'Contrôle nécessaire', cancelled: 'Annulé', expired: 'Aperçu expiré', conflict: 'Données modifiées', reconciled: 'État Classic conservé'};
const eventLabels: Record<string, string> = {preview: 'Aperçu', ready: 'Proposition prête', prepared: 'Préparation', blocked: 'Blocage', sending: 'Envoi démarré', confirmed: 'Envoi vérifié', uncertain: 'Résultat incertain', stopped: 'Arrêt', stop: 'Arrêt', rule: 'Règle', rule_saved: 'Règle enregistrée', error: 'Erreur', conflict: 'Conflit', cancelled: 'Annulation', skipped: 'Non traité', reconciled: 'Contrôle effectué'};
const objectives: Record<VacationObjective, string> = {balanced: 'Performance', recovery: 'Récupération', development: 'Développement'};
const defaultChoices: Choices = {objective: 'balanced', energy_floor: '60', energy_scale: 'auto', excluded_ids: [], captain_id: '', kicker_id: ''};

function localDate(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function displayDate(value?: string | null) {
  if (!value) return 'Non renseignée';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Date indisponible' : date.toLocaleString(localeTag(), {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'});
}
function toChoices(value: VacationOptions): Choices {return {objective: value.objective, energy_scale: value.energy_scale, excluded_ids: value.excluded_ids, energy_floor: String(value.energy_floor), captain_id: value.captain_id || '', kicker_id: value.kicker_id || ''};}
function toOptions(value: Choices): VacationOptions {return {objective: value.objective, energy_scale: value.energy_scale, excluded_ids: value.excluded_ids, energy_floor: Number(value.energy_floor), captain_id: value.captain_id || null, kicker_id: value.kicker_id || null};}
function choicesValid(value: Choices) {return value.energy_floor.trim() !== '' && Number.isInteger(Number(value.energy_floor)) && Number(value.energy_floor) >= 0 && Number(value.energy_floor) <= 110;}
function blankRule(teamId: string): VacationRule {return {...toOptions(defaultChoices), team_id: teamId, enabled: false, mode: 'prepare', start_at: null, end_at: null, lead_hours: 24, manage_existing: false, revision: 0, paused_reason: null};}
function toForm(rule: VacationRule): RuleForm {return {...toChoices(rule), enabled: rule.enabled, mode: rule.mode, start_at: localDate(rule.start_at), end_at: localDate(rule.end_at), lead_hours: String(rule.lead_hours), manage_existing: rule.manage_existing};}
function previewKey(teamId: string, fixtureId: string, source: string, choices: Choices, revision: number) {return JSON.stringify([teamId, fixtureId, source, toOptions(choices), revision]);}
function errorMessage(error: unknown) {return error instanceof Error ? error.message : 'L’opération n’a pas pu être confirmée.';}

export function Vacation({d, go, busy}: Actions) {
  const teamId = d.current_team.id;
  const [tab, setTab] = useState<Tab>('prepare');
  const [status, setStatus] = useState<VacationStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusError, setStatusError] = useState('');
  const [operation, setOperation] = useState('');
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [target, setTarget] = useState<'default' | 'match'>('default');
  const [fixtureId, setFixtureId] = useState('');
  const [fixtures, setFixtures] = useState<VacationFixture[]>([]);
  const [fixturesLoaded, setFixturesLoaded] = useState(false);
  const [fixturesLoading, setFixturesLoading] = useState(false);
  const [fixtureError, setFixtureError] = useState('');
  const [source, setSource] = useState<'optimized' | 'saved'>('optimized');
  const [choices, setChoices] = useState<Choices>(defaultChoices);
  const [bundle, setBundle] = useState<PreviewBundle | null>(null);
  const [form, setForm] = useState<RuleForm>(() => toForm(blankRule(teamId)));
  const [formRevision, setFormRevision] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [inspectedPreviewId, setInspectedPreviewId] = useState('');
  const [now, setNow] = useState(Date.now());
  const mounted = useRef(false), statusTicket = useRef(0), operationLock = useRef(false), stopLock = useRef(false), dirtyRef = useRef(false);
  dirtyRef.current = dirty;
  const owned = !!d.classic_account?.team_ids.includes(teamId);
  const currentRule = status?.rules.find(rule => rule.team_id === teamId) || blankRule(teamId);
  const ruleConflict = !!status && dirty && currentRule.revision !== formRevision;
  const selectedFixtureId = target === 'default' ? '0' : fixtureId;
  const key = previewKey(teamId, selectedFixtureId, source, choices, currentRule.revision);
  const fresh = bundle?.key === key && bundle.state === d;
  const preview = fresh ? status?.previews.find(item => item.id === bundle.preview.id) || bundle.preview : null;
  const expired = !!preview && new Date(preview.expires_at).getTime() <= now;
  const periodEnded = !!currentRule.end_at && new Date(currentRule.end_at).getTime() <= now;
  const periodAhead = !!currentRule.start_at && new Date(currentRule.start_at).getTime() > now;
  const locked = busy || !!operation;
  const canSend = !!preview && preview.status === 'ready' && preview.can_send && preview.revision === currentRule.revision && !expired && !!status?.write_ready && !statusError && owned && !locked && !stopping;
  const fixture = fixtures.find(item => item.id === selectedFixtureId);
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const ruleStart = new Date(form.start_at).getTime(), ruleEnd = new Date(form.end_at).getTime();
  const validRule = choicesValid(form) && Number.isFinite(ruleStart) && Number.isFinite(ruleEnd) && ruleEnd > ruleStart && ruleEnd - ruleStart <= 56 * 86400000 && form.lead_hours.trim() !== '' && Number.isInteger(Number(form.lead_hours)) && Number(form.lead_hours) >= 2 && Number(form.lead_hours) <= 168 && (!form.enabled || ruleEnd > now) && !(form.enabled && form.mode === 'automatic' && form.energy_scale === 'auto');

  const reloadStatus = useCallback(async (showLoading = false) => {
    const ticket = ++statusTicket.current;
    if (showLoading && mounted.current) setLoading(true);
    try {
      const result = await request('/vacation/status?team_id=' + encodeURIComponent(teamId)) as VacationStatus;
      if (!Array.isArray(result.rules) || !Array.isArray(result.events) || !Array.isArray(result.previews)) throw new Error('Le statut reçu est incomplet. Actualisez pour réessayer.');
      if (!mounted.current || ticket !== statusTicket.current) return;
      setStatus(result); setStatusError(''); setNow(Date.now());
      if (!dirtyRef.current) {const rule = result.rules.find(item => item.team_id === teamId) || blankRule(teamId); setForm(toForm(rule)); setFormRevision(rule.revision);}
    } catch (cause) {if (mounted.current && ticket === statusTicket.current) setStatusError(errorMessage(cause));}
    finally {if (mounted.current && ticket === statusTicket.current) setLoading(false);}
  }, [teamId]);

  useEffect(() => {
    mounted.current = true;
    void reloadStatus(true);
    const interval = window.setInterval(() => {if (document.visibilityState === 'visible') {setNow(Date.now()); void reloadStatus();}}, 30000);
    const visible = () => {if (document.visibilityState === 'visible') void reloadStatus();};
    document.addEventListener('visibilitychange', visible);
    return () => {mounted.current = false; statusTicket.current++; window.clearInterval(interval); document.removeEventListener('visibilitychange', visible);};
  }, [reloadStatus]);

  const loadFixtures = useCallback(async () => {
    setFixturesLoading(true); setFixtureError('');
    try {const result = await request('/vacation/fixtures?team_id=' + encodeURIComponent(teamId)); if (!Array.isArray(result.fixtures)) throw new Error('Calendrier indisponible.'); if (mounted.current) {setFixtures(result.fixtures); setFixturesLoaded(true);}}
    catch (cause) {if (mounted.current) setFixtureError(errorMessage(cause));}
    finally {if (mounted.current) setFixturesLoading(false);}
  }, [teamId]);
  useEffect(() => {if (target === 'match' && owned && !fixturesLoaded && !fixturesLoading && !fixtureError) void loadFixtures();}, [target, owned, fixturesLoaded, fixturesLoading, fixtureError, loadFixtures]);
  useEffect(() => {setConfirmation(null); setInspectedPreviewId('');}, [d, key]);

  function editForm(next: RuleForm) {setForm(next); setDirty(true); dirtyRef.current = true; setConfirmation(null); setBundle(null);}
  function resetForm() {setForm(toForm(currentRule)); setFormRevision(currentRule.revision); setDirty(false); dirtyRef.current = false; setConfirmation(null);}
  function targetLabel(id: string) {const match = fixtures.find(item => item.id === id); return id === '0' ? 'Composition par défaut' : `Match #${id}${match ? ' · ' + displayDate(match.match_start) : ''}`;}
  function selectPreview(item: VacationPreview) {
    if (item.team_id !== teamId || locked) return;
    const nextChoices = toChoices(item.rule);
    setChoices(nextChoices); setSource(item.source); setTarget(item.fixture_id === '0' ? 'default' : 'match'); setFixtureId(item.fixture_id === '0' ? '' : item.fixture_id);
    setBundle({preview: item, state: d, key: previewKey(teamId, item.fixture_id, item.source, nextChoices, currentRule.revision)}); setTab('prepare'); setConfirmation(null); setError('');
  }
  async function calculate() {
    if (operationLock.current || locked || !owned || !selectedFixtureId || !choicesValid(choices)) return;
    operationLock.current = true; setOperation('preview'); setError(''); setMessage(''); setBundle(null); setConfirmation(null);
    const capturedKey = key, capturedState = d;
    try {
      const result = await request('/vacation/preview', {team_id: teamId, fixture_id: selectedFixtureId, source, options: toOptions(choices)}, d.csrf) as VacationPreview;
      if (result.team_id !== teamId || result.fixture_id !== selectedFixtureId || !Array.isArray(result.players) || !Array.isArray(result.blocking_reasons)) throw new Error('L’aperçu reçu ne correspond pas à cette demande. Recalculez-le.');
      if (mounted.current) {setBundle({preview: result, state: capturedState, key: capturedKey}); setNow(Date.now()); await reloadStatus();}
    } catch (cause) {if (mounted.current) setError(errorMessage(cause));}
    finally {operationLock.current = false; if (mounted.current) setOperation('');}
  }
  function prepareRuleSave() {
    if (!validRule || !status || locked || ruleConflict) return;
    const rule: VacationRule = {...toOptions(form), team_id: teamId, enabled: form.enabled, mode: form.mode, start_at: new Date(form.start_at).toISOString(), end_at: new Date(form.end_at).toISOString(), lead_hours: Number(form.lead_hours), manage_existing: form.manage_existing, revision: formRevision, paused_reason: currentRule.paused_reason};
    if (rule.enabled) setConfirmation({kind: 'rule', rule}); else void saveRule(rule);
  }
  async function saveRule(rule: VacationRule) {
    if (operationLock.current || locked || ruleConflict) return;
    operationLock.current = true; setOperation('rules'); setConfirmation(null); setError(''); setMessage(''); setBundle(null);
    try {
      const {revision: _revision, paused_reason: _pausedReason, ...ruleInput} = rule;
      await request('/vacation/rules', {rule: ruleInput, expected_revision: formRevision}, d.csrf);
      if (mounted.current) {setDirty(false); dirtyRef.current = false; setMessage(rule.enabled ? 'Règle enregistrée et activée pour la période choisie.' : 'Règle enregistrée, désactivée.'); await reloadStatus();}
    } catch (cause) {if (mounted.current) {setError(errorMessage(cause)); await reloadStatus();}}
    finally {operationLock.current = false; if (mounted.current) setOperation('');}
  }
  async function send(item: VacationPreview) {
    if (operationLock.current || !canSend || item.id !== preview?.id || new Date(item.expires_at).getTime() <= Date.now()) {setConfirmation(null); return;}
    operationLock.current = true; setOperation('send'); setConfirmation(null); setError(''); setMessage(''); setBundle(null);
    try {
      const result = await request('/vacation/send', {preview_id: item.id}, d.csrf) as VacationPreview;
      if (mounted.current) {setMessage(result.status === 'confirmed' ? 'Composition envoyée à Classic et vérifiée par relecture.' : 'L’envoi demande un contrôle. Consultez le journal avant toute nouvelle action.'); setTab('journal'); await reloadStatus();}
    } catch (cause) {if (mounted.current) {setError(errorMessage(cause) + ' Consultez le journal et Classic avant de préparer un nouvel envoi.'); setTab('journal'); await reloadStatus();}}
    finally {operationLock.current = false; if (mounted.current) setOperation('');}
  }
  async function reconcile(item: VacationPreview, acceptCurrent = false) {
    if (operationLock.current || locked || stopping || item.status !== 'uncertain' || (acceptCurrent && (!item.current_payload || (inspectedPreviewId !== item.id && !item.reconciliation_required)))) return;
    operationLock.current = true; setOperation('reconcile'); setConfirmation(null); setError(''); setMessage('');
    try {
      const result = await request('/vacation/reconcile', {preview_id: item.id, accept_current: acceptCurrent}, d.csrf) as VacationPreview;
      if (mounted.current) {
        if (result.status === 'uncertain') {setInspectedPreviewId(result.current_payload ? item.id : ''); setBundle({preview: result, state: d, key}); setMessage(result.current_payload ? 'La composition actuelle diffère de la proposition. Relisez le résultat du contrôle ci-dessous avant de décider de la conserver.' : 'La composition actuelle reste indisponible dans Classic. La suspension est conservée.');}
        else {setBundle(null); setInspectedPreviewId(''); setTab('journal'); setMessage(result.status === 'confirmed' ? 'L’envoi a été confirmé par relecture. Le club reste désactivé ; une nouvelle activation sera nécessaire.' : 'L’état actuel de Classic a été conservé et la suspension levée. Le relais reste désactivé.');}
        await reloadStatus();
      }
    } catch (cause) {if (mounted.current) setError('Contrôle non confirmé : ' + errorMessage(cause));}
    finally {operationLock.current = false; if (mounted.current) setOperation('');}
  }
  async function stop(all: boolean) {
    if (stopLock.current) return;
    stopLock.current = true; setStopping(true); setConfirmation(null); setError(''); setMessage(''); setBundle(null);
    try {
      await request('/vacation/stop', all ? {} : {team_id: teamId}, d.csrf);
      if (mounted.current) {setDirty(false); dirtyRef.current = false; setMessage(all ? 'Règles désactivées pour tous vos clubs. Les requêtes déjà transmises ne peuvent pas être annulées.' : 'Règle désactivée pour ce club. Une requête déjà transmise ne peut pas être annulée.'); await reloadStatus();}
    } catch (cause) {if (mounted.current) setError('Arrêt non confirmé : ' + errorMessage(cause));}
    finally {stopLock.current = false; if (mounted.current) setStopping(false);}
  }
  function tabKeys(event: KeyboardEvent<HTMLDivElement>) {const index = tabs.findIndex(item => item.id === tab), next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1; if (next >= 0) {event.preventDefault(); setTab(tabs[next].id); event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();}}

  return <div className="vac-workspace">
    <CoachAdvice d={d}/>
    <section className="vac-command" aria-label={tr("État et arrêt du relais")}><div><span className="eyebrow">{tr("LE RELAIS DU CLUB")}</span><strong><span className={'vac-dot ' + (currentRule.enabled && !currentRule.paused_reason && !periodEnded && !periodAhead ? 'active' : '')}/>{currentRule.paused_reason ? tr("Relais suspendu") : currentRule.enabled && periodEnded ? tr("Période terminée") : currentRule.enabled && periodAhead ? tr("Relais programmé") : currentRule.enabled ? currentRule.mode === 'automatic' ? tr("Envois automatiques activés") : tr("Préparations activées") : tr("Relais désactivé")}</strong><small>{d.current_team.name} · {currentRule.enabled ? `${displayDate(currentRule.start_at)} → ${displayDate(currentRule.end_at)}` : tr("Aucune activation par défaut")}</small></div><div className="vac-stop-actions"><button className="button secondary" disabled={stopping} onClick={() => void stop(false)}><Pause size={15}/>{stopping ? tr("Arrêt…") : tr("Arrêter ce club")}</button><button className="button vac-stop-all" disabled={stopping} onClick={() => void stop(true)}>{tr("Tout arrêter")}</button></div><p>{tr("Une requête déjà transmise à Classic ne peut pas être annulée.")}</p></section>
    <div className="vac-status-row"><div><ShieldCheck size={18}/><span>{!status ? tr("Vérification de la connexion…") : status.write_ready ? tr("Connexion prête pour les envois") : tr("Envois indisponibles")}<small>{status?.write_ready ? tr("Chaque envoi est contrôlé puis relu dans Classic.") : status?.write_blocked_reason || tr("Vérifiez les clés et le paramètre développeur IV.")}</small></span></div><div><button className="text-button" onClick={() => go('settings')}>{tr("Connexion & données")}<ArrowRight size={14}/></button><button className="icon-button" disabled={loading} aria-label={tr("Actualiser le statut et le journal")} onClick={() => void reloadStatus(true)}><RefreshCw size={17} className={loading ? 'spin' : ''}/></button></div></div>
    {statusError && <div className="notice error" role="alert">{statusError}{tr(" Le dernier état affiché peut être ancien.")}<button className="text-button" onClick={() => void reloadStatus(true)}>{tr("Réessayer")}</button></div>}
    {error && <div className="notice error" role="alert"><CircleAlert size={18}/><span>{tr(error)}</span></div>}
    {message && <div className="notice success" role="status"><Check size={18}/><span>{tr(message)}</span></div>}
    {operation === 'send' && <div className="notice" role="status"><RefreshCw size={18} className="spin"/>{tr("Envoi et vérification en cours. Le résultat sera conservé dans le journal.")}</div>}
    {currentRule.paused_reason && <div className="notice error" role="alert"><CircleAlert size={19}/><span><strong>{tr("Contrôle requis dans Classic.")}</strong> {currentRule.paused_reason}{tr(" Consultez le journal avant de réactiver une règle. ")}{status?.previews.some(item => item.status === 'uncertain') && <button className="text-button" disabled={locked} onClick={() => {const item = status.previews.find(item => item.status === 'uncertain'); if (item) selectPreview(item);}}>{tr("Ouvrir le contrôle")}<ArrowRight size={14}/></button>}</span></div>}
    {!owned && <div className="notice"><Info size={19}/><span>{tr("Ce club est suivi dans votre atelier. Seul un club rattaché à votre compte Classic peut recevoir une composition ou une règle active.")}</span></div>}

    <div className="vac-tabs" role="tablist" aria-label={tr("Mode vacances")} onKeyDown={tabKeys}>{tabs.map(({id, label, Icon}) => <button id={'vac-tab-' + id} key={id} role="tab" aria-selected={tab === id} aria-controls={'vac-panel-' + id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)}><Icon size={17}/>{tr(label)}</button>)}</div>
    <div className="vac-panel" id={'vac-panel-' + tab} role="tabpanel" aria-labelledby={'vac-tab-' + tab} tabIndex={0}>
      {tab === 'prepare' && <>
        <section className="card vac-card"><div className="vac-heading"><div><span className="eyebrow">{tr("01 / CHOISIR LA RENCONTRE")}</span><h2>{tr("Préparez le XV qui prendra le relais.")}</h2><p>{tr("Passez la composition en revue : titulaires, banc et changements proposés. Vous déciderez ensuite de l’envoyer au jeu.")}</p></div><FileCheck2 size={25}/></div>
          <fieldset className="vac-targets" disabled={locked}><legend>{tr("Destination dans Classic")}</legend><label className={target === 'default' ? 'selected' : ''}><input type="radio" name="vac-target" checked={target === 'default'} onChange={() => setTarget('default')}/><span><strong>{tr("Composition par défaut")}</strong><small>{tr("La base utilisée par votre club.")}</small></span></label><label className={target === 'match' ? 'selected' : ''}><input type="radio" name="vac-target" checked={target === 'match'} onChange={() => setTarget('match')}/><span><strong>{tr("Un match futur")}</strong><small>{tr("Une composition pour cette rencontre.")}</small></span></label></fieldset>
          {target === 'match' && <div className="vac-fixtures"><label>{tr("Rencontre à préparer")}<select value={fixtureId} disabled={locked || fixturesLoading || !owned} onChange={event => setFixtureId(event.target.value)}><option value="">{fixturesLoading ? tr("Lecture du calendrier…") : tr("Choisir un match")}</option>{fixtureId && !fixtures.some(item => item.id === fixtureId) && <option value={fixtureId}>{tr("Match #")}{fixtureId}</option>}{fixtures.map(item => <option key={item.id} value={item.id}>#{item.id} · {displayDate(item.match_start)} · {item.home_team_id} — {item.away_team_id}{item.competition ? ' · ' + item.competition : ''}</option>)}</select></label><button className="button secondary" disabled={fixturesLoading || locked || !owned} onClick={() => void loadFixtures()}><RefreshCw size={16} className={fixturesLoading ? 'spin' : ''}/>{tr("Calendrier")}</button>{fixtureError && <p className="text-error" role="alert">{fixtureError}</p>}{fixturesLoaded && !fixtures.length && <p>{tr("Aucun match futur disponible pour ce club.")}</p>}<p className="vac-helper"><Info size={15}/>{tr("Sans échéance officielle fiable, l’envoi reste bloqué. Enregistrez d’abord une composition pour ce match dans Classic, puis recalculez.")}</p></div>}
          <label className="vac-source">{tr("Composition à utiliser")}<select value={source} disabled={locked} onChange={event => setSource(event.target.value as 'optimized' | 'saved')}><option value="optimized">{tr("Proposition optimisée avec mes critères")}</option><option value="saved">{tr("XV sauvegardé dans l’outil")}</option></select></label>
          {source === 'saved' && <p className="vac-helper">{tr("La composition enregistrée dans Effectif & XV sera contrôlée avec les critères ci-dessous. Ses places ne seront pas réaffectées.")}</p>}
          <ChoiceFields choices={choices} onChange={setChoices} players={d.squad} disabled={locked} prefix="prepare"/>
          <div className="vac-form-footer"><p><ShieldCheck size={17}/>{tr("Le calcul enregistre un aperçu dans l’outil. Aucun envoi au jeu à cette étape.")}</p><button className="button primary" disabled={locked || !owned || !status || !selectedFixtureId || !choicesValid(choices)} onClick={() => void calculate()}>{operation === 'preview' ? <RefreshCw size={17} className="spin"/> : <FileCheck2 size={17}/>} {operation === 'preview' ? tr("Calcul de l’aperçu…") : tr("Calculer l’aperçu")}</button></div>
        </section>
        {preview ? <PreviewDetails preview={preview} expired={expired} players={d.squad} title={targetLabel(preview.fixture_id)} canSend={canSend} onSend={() => setConfirmation({kind: 'send', preview})} saving={operation === 'send'} reconciling={operation === 'reconcile'} canReconcile={!locked && !stopping && !statusError} inspected={!!preview.current_payload && (inspectedPreviewId === preview.id || !!preview.reconciliation_required)} onReconcile={() => void reconcile(preview)} onAcceptCurrent={() => setConfirmation({kind: 'reconcile', preview})}/> : <div className="vac-placeholder"><Users size={28}/><div><h3>{tr("Le XV proposé prendra place ici.")}</h3><p>{bundle ? tr("Les réglages ou les données ont changé. Recalculez avant tout envoi.") : tr("Vous pourrez relire les titulaires, le banc au format Classic et les changements proposés.")}</p></div></div>}
      </>}

      {tab === 'rules' && <section className="card vac-card"><div className="vac-heading"><div><span className="eyebrow">{tr("UN RELAIS À VOTRE MESURE")}</span><h2>{tr("Passez le relais avec des consignes claires.")}</h2><p>{tr("Fixez la période, les critères et ce que le relais peut faire pour ce club. Vos changements prendront effet après enregistrement.")}</p></div><SlidersHorizontal size={24}/></div>
        <div className="vac-worker"><Clock size={18}/><div><strong>{status?.worker_enabled ? tr("Relais serveur actif · passage toutes les 15 minutes") : tr("Relais serveur inactif")}</strong><p>{status?.worker_enabled ? `Dernier passage : ${displayDate(status.worker_last_run)}. Vous pouvez fermer votre navigateur.` : tr("Les règles peuvent être préparées ; leur exécution planifiée nécessite le relais serveur.")}</p>{status?.worker_error && <p className="text-error">{status.worker_error}</p>}</div></div>
        {dirty && <div className="vac-note" role="status">{tr("Modifications non enregistrées. ")}{currentRule.enabled ? tr("La règle enregistrée reste active ; utilisez Arrêter ce club pour la suspendre immédiatement.") : tr("Le relais conserve son état enregistré.")}</div>}
        {ruleConflict && <div className="notice error" role="alert"><span>{tr("La règle a changé depuis votre saisie. Rechargez sa dernière version avant de l’enregistrer.")}</span><button className="button secondary" onClick={resetForm}>{tr("Recharger la règle")}</button></div>}
        <form onSubmit={event => {event.preventDefault(); prepareRuleSave();}}>
          <fieldset disabled={locked || !status} className="vac-form-fields"><legend className="vac-sr-only">{tr("Règle vacances de ")}{d.current_team.name}</legend>
            <div className="vac-grid"><label>{tr("Début de la période")}<input type="datetime-local" required value={form.start_at} onChange={event => editForm({...form, start_at: event.target.value})}/></label><label>{tr("Fin de la période")}<input type="datetime-local" required value={form.end_at} onChange={event => editForm({...form, end_at: event.target.value})}/></label></div><p className="vac-helper">{tr("Heures locales : ")}{timeZone}{tr(". Les dates sont enregistrées avec leur décalage horaire puis traitées en UTC. Durée maximale : 56 jours.")}</p>
            <div className="vac-grid"><label>{tr("Action pendant mon absence")}<select value={form.mode} onChange={event => editForm({...form, mode: event.target.value as 'prepare' | 'automatic'})}><option value="prepare">{tr("Préparer uniquement dans l’outil")}</option><option value="automatic">{tr("Envoyer automatiquement à Classic")}</option></select></label><label>{tr("Anticipation avant le match (2 à 168 heures)")}<input type="number" required min="2" max="168" step="1" value={form.lead_hours} onChange={event => editForm({...form, lead_hours: event.target.value})}/></label></div>
            <div className={'vac-mode-note ' + (form.mode === 'automatic' ? 'automatic' : '')}><Info size={19}/><p>{form.mode === 'automatic' ? tr("Cette règle pourra modifier les compositions des matchs éligibles dans Classic, pendant la période choisie. La composition par défaut reste un envoi manuel.") : tr("Le relais prépare des propositions et les conserve dans le journal. Vous décidez ensuite de chaque envoi.")}</p></div>
            <ChoiceFields choices={form} onChange={next => editForm({...form, ...next})} players={d.squad} disabled={locked} prefix="rules"/>
            <label className="vac-check"><input type="checkbox" checked={form.manage_existing} onChange={event => editForm({...form, manage_existing: event.target.checked})}/><span><strong>{tr("Autoriser le traitement des matchs déjà composés")}</strong><small>{tr("Le relais peut préparer leur première proposition à partir de la composition existante. Une intervention ultérieure dans Classic reste contrôlée avant tout envoi.")}</small></span></label>
            <label className="vac-check vac-enable"><input type="checkbox" checked={form.enabled} onChange={event => editForm({...form, enabled: event.target.checked})}/><span><strong>{tr("Activer cette règle pour ")}{d.current_team.name}</strong><small>{tr("L’activation sera confirmée au prochain écran. La fin de période limite automatiquement le relais.")}</small></span></label>
          </fieldset>
          <p className="vac-helper">{tr("Vérifiez que cet usage est autorisé par les règles de Classic. L’autorisation de l’automatisation par l’éditeur n’est pas confirmée. Continuez à vous connecter régulièrement au jeu.")}</p>
          {form.enabled && form.mode === 'automatic' && form.energy_scale === 'auto' && <p className="text-error" role="alert">{tr("Choisissez explicitement Pourcentage ou Niveau pour activer les envois automatiques.")}</p>}
          {!!form.start_at && !!form.end_at && ruleEnd <= ruleStart && <p className="text-error" role="alert">{tr("La fin doit se situer après le début de la période.")}</p>}
          {ruleEnd - ruleStart > 56 * 86400000 && <p className="text-error" role="alert">{tr("La période ne peut pas dépasser 56 jours.")}</p>}
          {form.enabled && Number.isFinite(ruleEnd) && ruleEnd <= now && <p className="text-error" role="alert">{tr("Cette période est terminée. Choisissez une nouvelle date de fin avant l’activation.")}</p>}
          <div className="vac-form-footer"><span className="vac-helper">{tr("Version enregistrée : ")}{currentRule.revision} · {currentRule.enabled ? tr("Activée") : tr("Désactivée")}</span><div><button type="button" className="button secondary" disabled={locked || !dirty} onClick={resetForm}>{tr("Annuler la saisie")}</button><button className="button primary" disabled={locked || stopping || !status || !validRule || ruleConflict || !owned || (form.enabled && form.mode === 'automatic' && !status.write_ready)}>{operation === 'rules' ? <RefreshCw className="spin" size={16}/> : <Save size={16}/>} {operation === 'rules' ? tr("Enregistrement…") : form.enabled ? tr("Vérifier l’activation") : tr("Enregistrer sans activer")}</button></div></div>
        </form>
      </section>}

      {tab === 'journal' && <section className="card vac-card"><div className="vac-heading"><div><span className="eyebrow">{tr("LE FIL DES DÉCISIONS")}</span><h2>{tr("Le journal de ")}{d.current_team.name}.</h2><p>{tr("Alertes et résultats dans votre espace privé. Aucun courriel n’est envoyé.")}</p></div><button className="button secondary" disabled={loading} onClick={() => void reloadStatus(true)}><RefreshCw size={16} className={loading ? 'spin' : ''}/>{tr("Actualiser")}</button></div>
        {!!status?.previews.filter(item => item.team_id === teamId).length && <div className="vac-recent"><h3>{tr("Dernières propositions")}</h3>{status.previews.filter(item => item.team_id === teamId).map(item => <button key={item.id} className="vac-preview-row" disabled={locked} onClick={() => selectPreview(item)}><span className={'vac-state ' + item.status}>{previewLabels[item.status] || item.status}</span><span><strong>{targetLabel(item.fixture_id)}</strong><small>{displayDate(item.created_at)} · {item.automatic ? tr("Relais planifié") : tr("Préparation manuelle")}</small></span><ArrowRight size={17}/></button>)}</div>}
        {loading && !status ? <p role="status">{tr("Chargement du journal…")}</p> : !status?.events.filter(event => event.team_id === teamId).length ? <div className="vac-placeholder"><History size={27}/><div><h3>{tr("Aucune action à revoir pour le moment.")}</h3><p>{tr("Les préparations, les règles, les arrêts et les résultats d’envoi apparaîtront ici.")}</p></div></div> : <ol className="vac-journal">{status.events.filter(event => event.team_id === teamId).map(event => <li key={event.id}><span className={'vac-event-dot ' + event.kind}/><div><div className="vac-event-heading"><strong>{eventLabels[event.kind] || tr("Événement du relais")}</strong><time dateTime={event.created_at}>{displayDate(event.created_at)}</time></div><p>{event.message}</p>{event.preview_id && status.previews.some(item => item.id === event.preview_id) && <button className="text-button" disabled={locked} onClick={() => {const item = status.previews.find(item => item.id === event.preview_id); if (item) selectPreview(item);}}>{tr("Voir la proposition")}<ArrowRight size={14}/></button>}</div></li>)}</ol>}
        <p className="vac-helper">{tr("Affichage des 100 derniers événements et des 20 dernières propositions. Actualisation toutes les 30 secondes lorsque cette page est visible.")}</p>
      </section>}
    </div>
    {confirmation && <ConfirmDialog confirmation={confirmation} teamName={d.current_team.name} teamId={teamId} targetLabel={targetLabel} disabled={locked || stopping || (confirmation.kind === 'send' && !canSend)} onClose={() => setConfirmation(null)} onConfirm={() => confirmation.kind === 'send' ? void send(confirmation.preview) : confirmation.kind === 'reconcile' ? void reconcile(confirmation.preview, true) : void saveRule(confirmation.rule)}/>} 
    {fixture && target === 'match' && tab === 'prepare' && <p className="vac-helper">{tr("Heure du match indiquée par le calendrier : ")}{displayDate(fixture.match_start)}{tr(". L’échéance d’envoi est vérifiée séparément.")}</p>}
  </div>;
}

function ChoiceFields({choices, onChange, players, disabled, prefix}: {choices: Choices; onChange: (value: Choices) => void; players: Player[]; disabled: boolean; prefix: string}) {
  const [search, setSearch] = useState('');
  const visiblePlayers = players.filter(player => player.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const missingExcluded = choices.excluded_ids.filter(id => !players.some(player => player.id === id));
  return <fieldset className="vac-choices" disabled={disabled}><legend>{tr("Critères et responsables")}</legend><div className="vac-grid vac-three"><label>{tr("Objectif")}<select value={choices.objective} onChange={event => onChange({...choices, objective: event.target.value as VacationObjective})}>{Object.entries(objectives).map(([id, label]) => <option key={id} value={id}>{tr(label)}</option>)}</select></label><label>{tr("Énergie minimale normalisée (%)")}<input type="number" min="0" max="110" step="1" required value={choices.energy_floor} onChange={event => onChange({...choices, energy_floor: event.target.value})}/></label><label>{tr("Format des énergies")}<select value={choices.energy_scale} onChange={event => onChange({...choices, energy_scale: event.target.value as VacationEnergyScale})}><option value="auto">{tr("Auto · format à confirmer")}</option><option value="percent">{tr("Pourcentage (0–110)")}</option><option value="level">{tr("Niveau (1–11)")}</option></select></label></div><p className="vac-helper">{tr("Le seuil est en pourcentage ; les niveaux sont convertis ×10. Une énergie ou une blessure inconnue bloque l’envoi. ")}{choices.energy_scale === 'auto' && tr("Choisissez explicitement Pourcentage ou Niveau pour permettre un envoi ; Classic ne confirme pas automatiquement le format du compte.")}</p>
    <div className="vac-grid">{(['captain_id', 'kicker_id'] as const).map(field => <label key={field}>{field === 'captain_id' ? tr("Capitaine souhaité") : tr("Buteur souhaité")}<select value={choices[field]} onChange={event => onChange({...choices, [field]: event.target.value})}><option value="">{tr("Conserver le responsable dans Classic")}</option>{choices[field] && !players.some(player => player.id === choices[field]) && <option value={choices[field]}>{tr("Joueur #")}{choices[field]}{tr(" · absent de l’instantané")}</option>}{players.map(player => <option key={player.id} value={player.id}>{player.name}</option>)}</select></label>)}</div>
    <details className="vac-exclusions"><summary>{tr("Joueurs à exclure ")}<span>{choices.excluded_ids.length}{tr(" sélectionné(s)")}</span></summary><label className="vac-search">{tr("Rechercher dans l’effectif")}<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder={tr("Nom d’un joueur")}/></label><div className="vac-exclusion-list" role="group" aria-label={tr("Joueurs exclus de la proposition")}>{visiblePlayers.map(player => <label key={player.id} className="vac-exclude-player"><input type="checkbox" name={prefix + '-excluded'} value={player.id} checked={choices.excluded_ids.includes(player.id)} onChange={event => onChange({...choices, excluded_ids: event.target.checked ? [...choices.excluded_ids, player.id] : choices.excluded_ids.filter(id => id !== player.id)})}/><span>{player.name}<small>#{player.id}</small></span></label>)}{!visiblePlayers.length && <p>{tr("Aucun joueur correspondant dans l’instantané local.")}</p>}{missingExcluded.map(id => <label key={id} className="vac-exclude-player"><input type="checkbox" checked onChange={() => onChange({...choices, excluded_ids: choices.excluded_ids.filter(value => value !== id)})}/><span>{tr("Joueur #")}{id}<small>{tr("Absent de l’instantané local")}</small></span></label>)}</div></details>
    {!choicesValid(choices) && <p className="text-error" role="alert">{tr("Le seuil doit être un entier entre 0 et 110.")}</p>}
  </fieldset>;
}

function PreviewDetails({preview, title, players, expired, canSend, onSend, saving, reconciling, canReconcile, inspected, onReconcile, onAcceptCurrent}: {preview: VacationPreview; title: string; players: Player[]; expired: boolean; canSend: boolean; onSend: () => void; saving: boolean; reconciling: boolean; canReconcile: boolean; inspected: boolean; onReconcile: () => void; onAcceptCurrent: () => void}) {
  const benchSize = preview.bench_size === 8 ? 8 : 7;
  const showExpired = expired && preview.status === 'ready';
  const name = (value: string | null) => value === null || value === '' ? '—' : preview.players.find(player => player.id === value)?.name || players.find(player => player.id === value)?.name || value;
  const fieldLabel = (field: string) => /^\d+$/.test(field) ? 'Titulaire ' + field : /^p\d+$/.test(field) ? 'Titulaire ' + field.slice(1) : /^b\d+$/.test(field) ? 'Remplaçant ' + field.slice(1) : /^player\d+$/.test(field) ? 'Place ' + field.replace('player', '') : ({captain: 'Capitaine', captain_id: 'Capitaine', kicker: 'Buteur', kicker_id: 'Buteur', captain1: 'Capitaine suppléant 1', captain2: 'Capitaine suppléant 2', kicker1: 'Buteur suppléant 1', kicker2: 'Buteur suppléant 2', mode: 'Mode tactique', defense: 'Défense', intensity: 'Intensité', dropgoals: 'Tentatives de drop', pickandgo: 'Pick and go', driving: 'Percussion', expansive: 'Jeu au large', creative: 'Jeu créatif', kicking: 'Jeu au pied', kickfortouch: 'Touche au pied', upandunder: 'Chandelles', discipline: 'Discipline'} as Record<string, string>)[field] || field;
  return <section className="card vac-card vac-preview"><div className="vac-heading"><div><span className="eyebrow">{tr("02 / RELIRE AVANT L’ENVOI")}</span><h2>{title}</h2><p>{tr("Calculé le ")}{displayDate(preview.created_at)}{tr(" · valable jusqu’au ")}{displayDate(preview.expires_at)}</p></div><span className={'vac-state ' + (showExpired ? 'expired' : preview.status)}>{showExpired ? tr("Aperçu expiré") : previewLabels[preview.status]}</span></div>
    <div className="vac-preview-facts"><div><span>{tr("Composition Classic")}</span><strong>{preview.players.filter(player => player.slot <= 15).length}{tr(" titulaires · ")}{preview.players.filter(player => player.slot > 15 && player.slot <= 15 + benchSize).length}{tr(" remplaçants")}</strong></div><div><span>{preview.fixture_id === '0' ? tr("Destination") : tr("Échéance officielle")}</span><strong>{preview.fixture_id === '0' ? tr("Équipe par défaut du club") : displayDate(preview.deadline)}</strong></div></div>
    {!!preview.blocking_reasons.length && <div className="notice error" role="alert"><CircleAlert size={20}/><div><strong>{tr("L’envoi est bloqué.")}</strong><ul>{preview.blocking_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div></div>}
    {!!preview.warnings.length && <div className="notice"><Info size={20}/><div><strong>{tr("À vérifier")}</strong><ul>{preview.warnings.map((warning, index) => <li key={index}>{tr(warning)}</li>)}</ul></div></div>}
    {showExpired && <p className="text-error">{tr("Cet aperçu a expiré. Recalculez-le pour relire les données actuelles de Classic.")}</p>}
    <div className="vac-roster">{[{title: 'Le quinze', from: 1, to: 15}, {title: 'Le banc Classic', from: 16, to: 15 + benchSize}].map(group => <div key={group.title}><h3>{group.title}</h3><ol start={group.from}>{Array.from({length: group.to - group.from + 1}, (_, index) => group.from + index).map(slot => {const player = preview.players.find(item => item.slot === slot); return <li key={slot}><span className="vac-shirt">{slot}</span><div><strong>{player?.name || tr("Place non pourvue")}</strong><small>{player?.role || (slot > 15 ? tr("Remplaçant") : tr("Titulaire"))}{player?.reason ? ' · ' + player.reason : ''}</small></div><span className="vac-energy">{typeof player?.energy === 'number' ? player.energy + ' %' : tr("Énergie ?")}</span></li>;})}</ol></div>)}</div>
    <p className="vac-helper"><Info size={16}/>{tr("Le nombre de remplaçants suit le format renvoyé par Classic : ")}{benchSize}{tr(" ici (7 ou 8 selon le format). ")}{benchSize === 7 ? tr("La place locale 23 n’est pas transmise ; son éventuel joueur écarté est signalé dans les avertissements.") : tr("La place locale 23 est incluse dans ce banc.")}</p>
    {preview.verification_required && <div className="notice"><Info size={19}/><span>{tr("Ce format doit d’abord être vérifié par un envoi manuel confirmé et relu dans Classic. Les envois automatiques restent bloqués jusqu’à cette vérification pour ce club.")}</span></div>}
    <details className="vac-diff" open><summary>{tr("Changements calculés lors de l’aperçu ")}<span>{preview.changes.length}</span></summary>{preview.changes.length ? <div className="vac-table-scroll" role="region" aria-label={tr("Différences de composition, défilement horizontal")} tabIndex={0}><table><caption className="vac-sr-only">{tr("Composition actuelle et composition proposée")}</caption><thead><tr><th scope="col">{tr("Élément")}</th><th scope="col">{tr("Dans Classic")}</th><th scope="col">{tr("Proposition")}</th></tr></thead><tbody>{preview.changes.map((change, index) => <tr key={index}><th scope="row">{fieldLabel(change.field)}</th><td>{name(change.before)}</td><td>{name(change.after)}</td></tr>)}</tbody></table></div> : <p>{tr("Aucun changement de composition signalé.")}</p>}</details>
    <div className="vac-preserved"><ShieldCheck size={19}/><p>{tr("Les tactiques de Classic sont conservées. Capitaine, buteur et références de remplacements doivent rester cohérents avec ce XV ; un conflit bloque l’envoi et doit être corrigé dans le jeu.")}</p></div>
    {preview.status === 'uncertain' && preview.current_payload && <details className="vac-diff vac-current-state" open><summary>{tr("Dernier état relu dans Classic")}</summary><div className="vac-table-scroll" role="region" aria-label={tr("Comparaison du dernier état Classic avec la proposition")} tabIndex={0}><table><caption className="vac-sr-only">{tr("Dernière composition relue et proposition d’envoi incertaine")}</caption><thead><tr><th scope="col">{tr("Élément")}</th><th scope="col">{tr("État Classic relu")}</th><th scope="col">{tr("Proposition")}</th></tr></thead><tbody>{Object.entries(preview.current_payload).filter(([field, value]) => /^\d+$/.test(field) || /^b\d+$/.test(field) || ['captain', 'kicker'].includes(field) || value !== preview.payload[field]).map(([field, value]) => <tr key={field}><th scope="row">{fieldLabel(field)}</th><td>{name(value)}</td><td>{name(preview.payload[field] || null)}{value !== preview.payload[field] && <span className="vac-difference">{tr("Différent")}</span>}</td></tr>)}</tbody></table></div></details>}
    {preview.status === 'uncertain' && <div className="vac-reconcile"><div><h3>{tr("Vérifier le résultat avant toute reprise.")}</h3><p>{tr("La relecture ne modifie pas Classic. Si son état diffère, vous pourrez choisir de le conserver. Le relais restera désactivé après le contrôle.")}</p></div><div><button className="button secondary" disabled={!canReconcile || reconciling} onClick={onReconcile}><RefreshCw size={16} className={reconciling ? 'spin' : ''}/>{reconciling ? tr("Contrôle en cours…") : tr("Vérifier le résultat dans Classic")}</button>{inspected && <button className="button primary" disabled={!canReconcile || reconciling} onClick={onAcceptCurrent}>{tr("Conserver l’état actuel et lever la suspension")}</button>}</div></div>}
    <div className="vac-form-footer"><p>{tr("La confirmation suivante modifie la composition dans Blackout Rugby Classic.")}</p><button className="button primary" disabled={!canSend || saving} onClick={onSend}><Send size={16}/>{saving ? tr("Envoi en cours…") : tr("Vérifier et envoyer au jeu")}</button></div>
  </section>;
}

function ConfirmDialog({confirmation, teamName, teamId, targetLabel, disabled, onClose, onConfirm}: {confirmation: Confirmation; teamName: string; teamId: string; targetLabel: (id: string) => string; disabled: boolean; onClose: () => void; onConfirm: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {const previous = document.activeElement as HTMLElement | null, element = dialog.current; element?.showModal(); return () => {element?.close(); previous?.focus();};}, []);
  let body: ReactNode;
  if (confirmation.kind === 'send') body = <><p>{tr("Vous allez modifier ")}<strong>{targetLabel(confirmation.preview.fixture_id)}</strong>{tr(" pour ")}<strong>{teamName} (#{teamId})</strong>.</p><div className="vac-confirm-target"><strong>{tr("15 titulaires et ")}{confirmation.preview.bench_size}{tr(" remplaçants dans Classic")}</strong><span>{confirmation.preview.fixture_id === '0' ? tr("Cette équipe remplacera la composition par défaut du club.") : tr("Échéance officielle : ") + displayDate(confirmation.preview.deadline)}</span><span>{tr("Tactiques conservées · aperçu du ")}{displayDate(confirmation.preview.created_at)}</span></div><p>{tr("Cette action envoie la composition au jeu. Une requête déjà transmise ne pourra pas être annulée.")}</p></>;
  else if (confirmation.kind === 'rule') body = <><p>{tr("La règle de ")}<strong>{teamName} (#{teamId})</strong>{tr(" sera activée du ")}<strong>{displayDate(confirmation.rule.start_at)}</strong>{tr(" au ")}<strong>{displayDate(confirmation.rule.end_at)}</strong>.</p><div className="vac-confirm-target"><strong>{confirmation.rule.mode === 'automatic' ? tr("Envois automatiques à Classic") : tr("Préparations conservées dans l’outil")}</strong><span>{tr(objectives[confirmation.rule.objective])}{tr(" · énergie minimale ")}{confirmation.rule.energy_floor}{tr(" % · anticipation ")}{confirmation.rule.lead_hours}{tr(" h")}</span><span>{confirmation.rule.excluded_ids.length}{tr(" joueur(s) exclu(s) · matchs déjà composés ")}{confirmation.rule.manage_existing ? tr("autorisés") : tr("préservés")}</span></div><p>{confirmation.rule.mode === 'automatic' ? tr("Cette activation autorise le relais à modifier les compositions des matchs éligibles pendant cette période, sans nouvelle confirmation pour chaque match.") : tr("Le relais calculera des propositions. Chaque envoi au jeu demandera encore votre confirmation.")}</p><p className="vac-helper">{tr("Vérifiez que cet usage est autorisé par les règles de Classic. Les résultats et les alertes seront disponibles dans le journal.")}</p></>;
  else body = <><p>{tr("Pour ")}<strong>{teamName} (#{teamId})</strong>{tr(", vous choisissez de conserver ")}<strong>{tr("l’état actuel de ")}{targetLabel(confirmation.preview.fixture_id)}</strong>{tr(" relu dans Classic.")}</p><div className="vac-confirm-target"><strong>{tr("La composition ne sera pas renvoyée au jeu.")}</strong><span>{tr("La proposition incertaine sera close. La suspension sera levée et le relais restera désactivé.")}</span></div><p>{tr("Vérifiez la composition directement dans Classic avant de confirmer. Une éventuelle réactivation des règles demandera une action distincte.")}</p></>;
  return <dialog ref={dialog} className="vac-confirm" aria-labelledby="vac-confirm-title" onCancel={event => {event.preventDefault(); onClose();}}><div className="vac-confirm-header"><span className="eyebrow">{confirmation.kind === 'send' ? tr("CONFIRMER L’ENVOI AU JEU") : confirmation.kind === 'reconcile' ? tr("CLORE LE RÉSULTAT INCERTAIN") : tr("CONFIRMER LE RELAIS")}</span><button className="icon-button" aria-label={tr("Fermer la confirmation")} onClick={onClose}><X size={21}/></button></div><h2 id="vac-confirm-title">{confirmation.kind === 'send' ? tr("Envoyer cette composition ?") : confirmation.kind === 'reconcile' ? tr("Conserver l’état actuel de Classic ?") : tr("Activer cette règle datée ?")}</h2>{body}<div className="vac-confirm-actions"><button autoFocus className="button secondary" onClick={onClose}>{tr("Revenir à la préparation")}</button><button className="button primary" disabled={disabled} onClick={onConfirm}>{confirmation.kind === 'send' ? <Send size={16}/> : <Check size={16}/>} {confirmation.kind === 'send' ? tr("Confirmer l’envoi à Classic") : confirmation.kind === 'reconcile' ? tr("Conserver l’état et lever la suspension") : tr("Confirmer l’activation")}</button></div></dialog>;
}
