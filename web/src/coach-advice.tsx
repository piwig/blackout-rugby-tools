import {tr} from './i18n';
import {useEffect, useId, useState} from 'react';
import {Activity, ArrowDownRight, ArrowUpRight, BookOpen, CircleAlert, Eye, GraduationCap, HeartPulse, RefreshCw, ShieldCheck, Sparkles, Star, Target, Users} from 'lucide-react';
import {request} from './App';
import {date, fmt, type State} from './types';
import './coach-advice.css';

type SkillAdvice = {skill: string; label: string; average: number | null; known: number; total: number; coverage: number | null; comparable: boolean};
type PlayerAdvice = {
  id: string; name: string; age: number | null; stars: number | null; wc_projection: number | null; known_skills: number;
  profile: {name: string; score: number} | null; focus: {skill: string; label: string; value: number} | null;
  energy: number | null; form: number | null; injured: boolean | null;
  readiness: 'review' | 'verify' | 'recovery'; signals: string[]; age_context: string | null;
  watch: boolean; note: string | null;
};
type GroupAdvice = {
  count: number; known_skills: number; total_skills: number; coverage: number | null;
  skills: SkillAdvice[]; strengths: SkillAdvice[]; weaknesses: SkillAdvice[];
  priorities: PlayerAdvice[]; observe: PlayerAdvice[]; comparison_note: string;
  availability: {energy_scale: 'percent' | 'ambiguous'; injured: number; low_energy: number; unknown_injury: number; unknown_energy: number; unknown_form: number};
  source: {observed_at: string | null; name: string | null};
};
type CoachReport = {team: {id: string; name: string}; squad: GroupAdvice; academy: GroupAdvice; warnings: string[]; methodology: string[]};

function SkillHighlights({items, weakness}: {items: SkillAdvice[]; weakness?: boolean}) {
  const Icon = weakness ? ArrowDownRight : ArrowUpRight;
  return <div className={'coach-highlight ' + (weakness ? 'coach-highlight-work' : '')}>
    <h4><Icon size={17} aria-hidden="true"/>{weakness ? tr("Axes de travail dans cet effectif") : tr("Points d’appui dans cet effectif")}</h4>
    {items.length ? items.map(item => <div className="coach-skill" key={item.skill}>
      <strong>{tr(item.label)}<b>{fmt(item.average)}</b></strong>
      <span>{item.known}/{item.total}{tr(" joueurs observés · ")}{fmt(item.coverage)}{tr(" % de couverture")}</span>
    </div>) : <p>{tr("Les observations ne permettent pas encore de dégager un contraste fiable.")}</p>}
  </div>;
}

function PlayerCard({player, academy}: {player: PlayerAdvice; academy: boolean}) {
  const Icon = player.readiness === 'recovery' ? HeartPulse : player.readiness === 'verify' ? CircleAlert : Target;
  return <article className={'coach-player coach-player-' + player.readiness}>
    <header><div><strong>{player.name}</strong><span>{player.age === null ? tr("Âge inconnu") : fmt(player.age) + tr(" ans")}{academy && <><i>·</i><Star size={12} aria-hidden="true"/>{player.stars === null ? tr("Étoiles inconnues") : fmt(player.stars) + tr(" étoiles")}</>}</span></div>{player.watch && <span className="coach-watch" title={tr("Joueur marqué à suivre par le manager")}><Eye size={14} aria-hidden="true"/>{tr("Suivi")}</span>}</header>
    <div className="coach-player-profile"><span>{player.profile?.name ? tr(player.profile.name) : tr("Profil à documenter")}</span><small>{player.known_skills}{tr("/10 compétences connues")}</small></div>
    {academy && <p className="coach-generation"><GraduationCap size={14} aria-hidden="true"/>{player.wc_projection === null ? tr("Génération non déterminée") : tr("Génération indicative · S") + fmt(player.wc_projection)}</p>}
    <p className="coach-player-action"><Icon size={17} aria-hidden="true"/>{player.readiness === 'recovery' ? tr("Faites d’abord le point sur la récupération") : player.readiness === 'verify' ? tr("Confirmez sa disponibilité avant de choisir") : tr("Une piste pour la prochaine séance")}</p>
    {player.focus && <div className="coach-focus"><span>{player.readiness === 'recovery' ? tr("À reconsidérer après récupération") : tr("Le point à travailler pour ce profil")}</span><strong>{tr(player.focus.label)}<b>{fmt(player.focus.value)}</b></strong></div>}
    <dl className="coach-player-condition"><div><dt>{tr("Énergie")}</dt><dd>{player.energy === null ? tr("À confirmer") : fmt(player.energy) + ' %'}</dd></div><div><dt>{tr("Forme observée")}</dt><dd>{fmt(player.form)}</dd></div><div><dt>{tr("Blessure signalée")}</dt><dd>{player.injured === null ? tr("Inconnue") : player.injured ? tr("Oui") : tr("Non")}</dd></div></dl>
    {(player.signals.length > 0 || player.age_context || player.note) && <details className="coach-player-details"><summary>{tr("Ce qui éclaire ce conseil")}</summary>{player.signals.map(signal => <p key={tr(signal)}>{tr(signal)}</p>)}{player.age_context && <p>{tr(player.age_context)}</p>}{player.note && <blockquote><span>{tr("Note du manager")}</span>{player.note}</blockquote>}</details>}
  </article>;
}

function AdviceGroup({group, academy, selection}: {group: GroupAdvice; academy?: boolean; selection?: boolean}) {
  const [expanded, setExpanded] = useState(false);
  const Icon = academy ? GraduationCap : Users;
  const availability = group.availability;
  const visiblePlayers = expanded ? group.priorities : group.priorities.slice(0, 4);
  return <section className="coach-group">
    <header className="coach-group-heading"><span className="coach-group-icon"><Icon size={22} aria-hidden="true"/></span><div><h3>{academy ? tr("Centre de formation") : selection ? tr("Effectif de la sélection") : tr("Effectif senior")}</h3><p>{group.count} {academy ? tr("jeunes") : tr("joueurs")} · {group.known_skills}/{group.total_skills}{tr(" compétences connues")}</p></div>{group.coverage !== null && <span className="coach-coverage">{fmt(group.coverage)} %<small>{tr("de couverture")}</small></span>}</header>
    {!group.count ? <div className="coach-empty"><BookOpen size={22} aria-hidden="true"/><p>{academy ? tr("La relève se lit d’abord dans ses profils. Importez l’académie pour préparer les prochaines séances.") : tr("Importez vos seniors : leurs compétences donneront les premiers repères pour préparer l’équipe.")}</p></div> : <>
      <div className="coach-source">{group.source.name || tr("Source non renseignée")}{tr(" · Observation : ")}{date(group.source.observed_at)}</div>
      <div className="coach-highlights"><SkillHighlights items={group.strengths}/><SkillHighlights items={group.weaknesses} weakness/></div>
      <p className="coach-comparison-note">{tr(group.comparison_note)}</p>
      <details className="coach-skill-details"><summary>{tr("Voir les 10 moyennes et leur couverture")}</summary><div className="coach-skill-grid">{group.skills.map(skill => <div key={skill.skill}><span>{tr(skill.label)}</span><strong>{fmt(skill.average)}</strong><small>{skill.known}/{skill.total}{tr(" connus")}</small><meter min={0} max={100} value={skill.coverage || 0} aria-label={tr("Couverture ") + skill.label + ' : ' + fmt(skill.coverage) + ' %'}/></div>)}</div></details>
      <div className="coach-readiness"><h4><Activity size={17} aria-hidden="true"/>{tr("Avant les prochaines séances")}</h4><div className="coach-condition-tags"><span className={availability.injured ? 'attention' : ''}>{availability.injured}{availability.injured > 1 ?tr(" blessures"):tr(" blessure")}{availability.injured > 1 ?tr(" signalées"):tr(" signalée")}</span><span className={availability.low_energy ? 'attention' : ''}>{availability.low_energy}{availability.low_energy > 1 ?tr(" énergies"):tr(" énergie")}{tr(" sous 60 %")}</span><span>{availability.unknown_form}{availability.unknown_form > 1 ?tr(" formes"):tr(" forme")}{availability.unknown_form > 1 ?tr(" inconnues"):tr(" inconnue")}</span></div><p>{availability.unknown_injury}{tr(" disponibilités médicales et ")}{availability.unknown_energy}{tr(" énergies à confirmer. ")}{availability.energy_scale === 'ambiguous' ? tr("Échelle d’énergie indéterminée : aucune alerte de fatigue calculée.") : tr("Énergie supposée en pourcentage ; confirmer le format dans Classic.")}{tr(" La forme est affichée dans son échelle d’origine.")}</p></div>
      <div className="coach-priority-heading"><h4><Target size={17} aria-hidden="true"/>{academy ? tr("Profils à accompagner") : tr("Les profils à regarder pour les séances")}</h4><p>{academy ? tr("Après vérification du profil et de la disponibilité : étoiles cumulées, génération indicative la plus proche, puis affinité. Ce repère de cohorte ne garantit aucune sélection U20.") : tr("Commencez par vérifier qui est disponible. Les compétences du profil et la place des jeunes seniors dans le développement du groupe guident ensuite cette lecture.")}</p></div>
      {visiblePlayers.length ? <div className="coach-players">{visiblePlayers.map(player => <PlayerCard key={player.id} player={player} academy={!!academy}/>)}</div> : <p className="coach-no-profile">{tr("Il manque encore des compétences pour dégager un profil complet. Observez ces joueurs davantage avant de choisir vos priorités.")}</p>}
      {group.priorities.length > 4 && <button type="button" className="text-button coach-more" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>{expanded ? tr("Réduire la liste") : tr("Voir les ") + group.priorities.length + tr(" profils calculables")}</button>}
      {group.observe.length > 0 && <details className="coach-observe"><summary><Eye size={16} aria-hidden="true"/>{group.observe.length}{group.observe.length > 1 ?tr(" profils"):tr(" profil")}{tr(" à documenter")}</summary><p>{tr("Les compétences masquées restent inconnues. ")}{academy ? tr("Un jeune étoilé ne devient pas automatiquement une priorité sans profil suffisamment observé.") : tr("Aucune priorité de poste n’est attribuée sans les compétences nécessaires.")}</p><ul>{group.observe.map(player => <li key={player.id}><strong>{player.name}</strong><span>{player.known_skills}{tr("/10 compétences connues")}{academy && player.stars !== null ? ' · ' + fmt(player.stars) + tr(" étoiles") : ''}</span></li>)}</ul></details>}
    </>}
  </section>;
}

function ScopedCoachAdvice({d}: {d: State}) {
  const selection=d.current_team.id.includes(':');
  const headingId = useId();
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{snapshot: State; revision: number; report: CoachReport | null; error: string} | null>(null);
  useEffect(() => {
    let active = true;
    request('/coach-advice?team_id=' + encodeURIComponent(d.current_team.id), undefined, d.csrf).then((report: CoachReport) => {
      if (report.team?.id !== d.current_team.id || !Array.isArray(report.squad?.priorities) || !Array.isArray(report.academy?.priorities) || !Array.isArray(report.methodology)) throw new Error('Les conseils reçus sont incomplets. Relancez leur lecture.');
      if (active) setResult({snapshot: d, revision, report, error: ''});
    }).catch((error: unknown) => {
      if (active) setResult({snapshot: d, revision, report: null, error: error instanceof Error ? error.message : 'Les conseils sont indisponibles.'});
    });
    return () => {active = false;};
  }, [d, revision]);
  const fresh = result?.snapshot === d && result.revision === revision;
  const report = fresh ? result.report : null;
  const error = fresh ? result.error : '';
  const loading = !fresh;
  return <section className="coach-advice" aria-labelledby={headingId} aria-busy={loading}>
    <header className="coach-heading"><div className="coach-title"><span className="coach-symbol"><Sparkles size={23} aria-hidden="true"/></span><div><span className="eyebrow">{tr("LE REGARD DU COACH")}</span><h2 id={headingId}>{tr("Ce que raconte votre effectif")}</h2><p>{selection ? tr("Qui associer, quels profils retenir, quelles évolutions suivre ? Comparez vos joueurs pour préparer le XV de la sélection dans cet espace privé. Les entraînements, l’académie et les finances restent gérés par leurs clubs.") : tr("Sur quoi vous appuyer, où porter l’effort et quels profils accompagner : le point sur vos seniors et votre relève.")}</p></div></div><button type="button" className="button secondary" disabled={loading} onClick={() => setRevision(value => value + 1)}><RefreshCw size={15} aria-hidden="true"/>{tr("Relire les données")}</button></header>
    {loading && <p className="coach-loading" role="status">{tr("On passe les observations du club en revue…")}</p>}
    {error && <div className="coach-error" role="alert"><CircleAlert size={20} aria-hidden="true"/><p>{tr(error)}</p><button type="button" className="button secondary" onClick={() => setRevision(value => value + 1)}>{tr("Réessayer")}</button></div>}
    {report && <><div className="coach-intro"><ShieldCheck size={18} aria-hidden="true"/><p>{tr("Voici une première lecture des observations importées. Avant de trancher, confirmez la forme, l’énergie et les blessures dans Classic. Ces conseils ne lancent aucune action dans le jeu.")}</p></div>{report.warnings.length > 0 && <div className="coach-warnings">{report.warnings.map(warning => <p key={tr(warning)}><CircleAlert size={15} aria-hidden="true"/>{tr(warning)}</p>)}</div>}<AdviceGroup group={report.squad} selection={selection}/>{!d.current_team.id.includes(':')&&<AdviceGroup group={report.academy} academy/>}<div className="coach-age-note"><HeartPulse size={19} aria-hidden="true"/><p><strong>{tr("L’âge donne un contexte, pas une date de fin.")}</strong>{tr(" Le CSR peut baisser dès 29 ans sans règle d’âge fixe ; une progression reste possible à 33 ans. Suivez les compétences et les évolutions individuelles avant d’arbitrer l’entraînement.")}</p></div><details className="coach-methodology"><summary><BookOpen size={17} aria-hidden="true"/>{tr("Comment lire ces conseils")}</summary><ul>{report.methodology.map(item => <li key={item}>{tr(item)}</li>)}</ul></details></>}
  </section>;
}

export function CoachAdvice({d}: {d: State}) {
  // A club/session change unmounts pending requests; snapshot identity also hides
  // old observations immediately while a refresh for the same club is pending.
  return <ScopedCoachAdvice key={JSON.stringify([d.user.username, d.csrf, d.current_team.id])} d={d}/>;
}
