"""Deterministic preparation heuristics; no storage, network or game actions.

The caller supplies the report timestamp so the same inputs have the same output.
Unknown observations never become skill, energy or age measurements.
"""
from datetime import datetime, timezone

from .domain import SKILLS, SKILL_LABELS, number, player_metrics, stadium_plan
from .team_identity import is_selection,team_identity
from .role_weights import validate_weights


ROLES = ['Pilier', 'Talonneur', 'Pilier', 'Deuxième ligne', 'Deuxième ligne',
         'Troisième ligne', 'Troisième ligne', 'Troisième ligne', 'Demi de mêlée',
         'Demi d’ouverture', 'Ailier', 'Centre', 'Centre', 'Ailier', 'Arrière']


def maximum_assignment(weights):
    """Exact maximum-cardinality, then maximum-weight rectangular assignment.

    Hungarian algorithm, O(rows² * (columns + rows)). None is an unavailable
    edge; zero is a valid score. Dummy columns allow any role to remain vacant.
    Column order breaks ties deterministically without perturbing real scores.
    """
    n = len(weights)
    if not n:
        return []
    width = len(weights[0])
    if any(len(row) != width for row in weights):
        raise ValueError('Matrice d’affectation non rectangulaire.')
    largest = max((abs(x) for row in weights for x in row if x is not None), default=0)
    cardinality = (largest + 1) * (n + 1) * 2
    costs = [[cardinality if x is None else -cardinality-x for x in row] + [0]*n for row in weights]
    m = width+n
    u, v, matched, previous = [0]*(n+1), [0]*(m+1), [0]*(m+1), [0]*(m+1)
    for row in range(1, n+1):
        matched[0] = row
        column = 0
        minimum, used = [float('inf')]*(m+1), [False]*(m+1)
        while True:
            used[column] = True
            active = matched[column]
            delta, next_column = float('inf'), 0
            for j in range(1, m+1):
                if not used[j]:
                    cost = costs[active-1][j-1]-u[active]-v[j]
                    if cost < minimum[j]:
                        minimum[j], previous[j] = cost, column
                    if minimum[j] < delta:
                        delta, next_column = minimum[j], j
            for j in range(m+1):
                if used[j]:
                    u[matched[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            column = next_column
            if not matched[column]:
                break
        while column:
            predecessor = previous[column]
            matched[column] = matched[predecessor]
            column = predecessor
    result = [None]*n
    for j in range(1, width+1):
        if matched[j] and weights[matched[j]-1][j-1] is not None:
            result[matched[j]-1] = j-1
    return result


def injury_status(value, generated_at):
    """True only for explicit positive markers, False for explicit negatives."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower() if value is not None else ''
    if text.startswith('-001-11-30'):
        return False  # Classic's empty injury timestamp.
    if isinstance(value, str) and len(value) > 10 and value[10] in ('T', 't', ' '):
        try:
            ends = datetime.fromisoformat(value.replace('Z', '+00:00'))
            observed = date_value(generated_at)
            # A date without offset is not enough to infer the BRT timezone.
            return ends > observed if ends.tzinfo is not None and observed else None
        except ValueError:
            return None
    if text in ('false', 'no', 'non', 'n', 'healthy', 'fit'):
        return False
    if text in ('true', 'yes', 'oui', 'y', 'injured', 'blessé', 'blesse'):
        return True
    numeric = number(value)
    if numeric in (0, 1):
        return bool(numeric)
    if numeric is not None and numeric > 1:
        try:
            ends = datetime.fromtimestamp(numeric, tz=timezone.utc)
            observed = date_value(generated_at)
            return ends > observed if observed else None
        except (OverflowError, OSError, ValueError):
            return None
    return None


def energy_of(player, scale):
    value = number(player.get('energy'))
    if value is None:
        return None
    if scale == 'level':
        return value*10 if value.is_integer() and 1 <= value <= 11 else None
    if scale == 'percent':
        return value if 0 <= value <= 110 else None
    return None


def objective_bonus(player, objective, energy):
    if objective == 'recovery':
        return 3*energy/110 if energy is not None else 0
    if objective == 'development':
        age = number(player.get('age'))
        return max(0, min(3, (30-age)/3)) if age is not None and 0 < age <= 100 else 0
    return 0


def unique_players(players):
    found = {}
    for player in players:
        found.setdefault(str(player['id']), player)
    return [found[key] for key in sorted(found)]


def make_lineup(squad, saved, objective, energy_floor, energy_scale, generated_at, *,
                locks=None, starter_ids=None, excluded_ids=None, role_weights=None):
    # Optional constraints keep the historical/vacation callers compatible.
    squad = unique_players(squad)
    if role_weights is not None:
        role_weights = validate_weights(role_weights)
    locks, starter_ids, excluded_ids = dict(locks or {}), list(starter_ids or []), list(excluded_ids or [])
    known_ids = {str(player['id']) for player in squad}
    if (any(slot not in {str(i) for i in range(1, 16)} for slot in locks)
            or len(set(locks.values())) != len(locks)
            or len(set(starter_ids)) != len(starter_ids)
            or len(set(excluded_ids)) != len(excluded_ids)
            or len(starter_ids) > 15
            or not (set(locks.values()) | set(starter_ids) | set(excluded_ids)) <= known_ids
            or (set(locks.values()) | set(starter_ids)) & set(excluded_ids)):
        raise ValueError('Contraintes incohérentes : postes, doublons, exclusions ou joueurs absents de l’effectif.')
    candidates, excluded, low_energy, unknown_energy, unknown_injury = [], [], 0, 0, 0
    for player in squad:
        energy, injury = energy_of(player, energy_scale), injury_status(player.get('injured'), generated_at)
        low_energy += int(energy is not None and energy < energy_floor)
        unknown_energy += int(energy is None)
        unknown_injury += int(injury is None)
        scores = {r['name']: round(r['score']+objective_bonus(player, objective, energy), 2)
                  for r in player_metrics(player, role_weights=role_weights)['roles']}
        reasons = []
        if str(player['id']) in excluded_ids:
            reasons.append('Exclusion choisie par le manager.')
        if injury is True:
            reasons.append('Blessure explicitement signalée dans la source.')
        if energy is not None and energy < energy_floor:
            prefix = f'Niveau brut {player.get("energy")} converti approximativement en ' if energy_scale == 'level' else 'Énergie observée '
            reasons.append(prefix+f'{energy:g} %, sous le seuil {energy_floor:g} %.')
        if not scores:
            reasons.append('Aucune affinité calculable : compétences requises inconnues.')
        if reasons:
            excluded.append({'id': str(player['id']), 'name': player['name'], 'reason': ' '.join(reasons)})
        else:
            candidates.append({'player': player, 'energy': energy, 'scores': scores})
    by_index = {str(candidate['player']['id']): index for index, candidate in enumerate(candidates)}
    required = set(starter_ids) | set(locks.values())
    if not required <= set(by_index):
        raise ValueError('Un joueur imposé est indisponible ou ne possède aucune affinité calculable.')
    assignments = [None]*15
    for slot, identifier in locks.items():
        index = by_index[identifier]
        if ROLES[int(slot)-1] not in candidates[index]['scores']:
            raise ValueError('Affinité inconnue pour un poste verrouillé ; vérifiez les compétences du joueur.')
        assignments[int(slot)-1] = index
    free_positions = [position for position in range(15) if str(position+1) not in locks]
    free_candidates = [index for index in range(len(candidates)) if index not in assignments]
    # Prefer every required starter before the score; the assignment remains exact.
    # Validate feasibility afterwards instead of silently dropping a constraint.
    largest = max((abs(score) for c in candidates for score in c['scores'].values()), default=0)
    required_bonus = (largest+1)*32
    matrix = [[(candidate['scores'][ROLES[position]] +
                (required_bonus if str(candidate['player']['id']) in required else 0))
               if ROLES[position] in candidate['scores'] else None
               for candidate in (candidates[i] for i in free_candidates)] for position in free_positions]
    for position, choice in zip(free_positions, maximum_assignment(matrix)):
        if choice is not None:
            assignments[position] = free_candidates[choice]
    if not required <= {str(candidates[i]['player']['id']) for i in assignments if i is not None}:
        raise ValueError('Ces titulaires ne peuvent pas occuper ensemble les postes calculables ; libérez une contrainte.')
    selected, slots, used = [], {}, set()

    def select(index, slot, role, score, bench=False):
        candidate = candidates[index]
        player, energy = candidate['player'], candidate['energy']
        identifier = str(player['id'])
        slots[str(slot)] = identifier
        used.add(index)
        affinity = next(r['score'] for r in player_metrics(player, role_weights=role_weights)['roles'] if r['name'] == role)
        explanation = f'Affinité {role} : {affinity:g} ; bonus objectif : {objective_bonus(player, objective, energy):.2f}.'
        if role_weights is not None:
            weights = role_weights[role]
            terms = ' + '.join(f'{SKILL_LABELS[skill]}×{weight}' for skill, weight in weights.items() if weight)
            explanation += f' Indice personnel, moyenne pondérée : ({terms}) / {sum(weights.values())} ; toutes les compétences de poids positif sont connues.'
        if energy is None:
            explanation += f' Énergie inconnue ou échelle ambiguë (valeur brute : {player.get("energy", "absente")}), à vérifier.'
        elif energy_scale == 'level':
            explanation += f' Niveau brut {player.get("energy")}/11, converti approximativement en {energy:g} % (niveau ×10).'
        else:
            explanation += f' Énergie observée : {energy:g} % (maximum 110 %).'
        if injury_status(player.get('injured'), generated_at) is None:
            explanation += ' Disponibilité médicale non confirmée.'
        if bench:
            explanation += ' Banc choisi en priorité pour compléter les rôles couverts, puis selon la meilleure affinité.'
        elif str(slot) in locks:
            explanation += ' Poste verrouillé par le manager.'
        elif identifier in starter_ids:
            explanation += ' Titulaire imposé ; poste attribué par le calcul.'
        selected.append({'slot': slot, 'role': 'Réserve · '+role if bench else role,
                         'id': identifier, 'name': player['name'], 'score': score,
                         'energy': energy, 'reason': explanation,
                         'locked': str(slot) in locks, 'required': identifier in starter_ids})

    for position, index in enumerate(assignments):
        if index is not None:
            select(index, position+1, ROLES[position], candidates[index]['scores'][ROLES[position]])
    starters = len(selected)
    role_names = list(dict.fromkeys(ROLES))
    needs = {role: 2 if role == 'Pilier' else 1 for role in role_names}
    coverable = {}
    for index, candidate in enumerate(candidates):
        affinities = player_metrics(candidate['player'], role_weights=role_weights)['roles']
        best = max(r['score'] for r in affinities)
        coverable[index] = [r['name'] for r in affinities if r['score'] >= .8*best]
    coverage = {role: [] for role in role_names}
    remaining = {i for i in range(len(candidates)) if i not in used}
    reserves = []
    while remaining and len(reserves) < 8:
        index = min(remaining, key=lambda i: (
            -sum(len(coverage[role]) < needs[role] for role in coverable[i]),
            -max(candidates[i]['scores'].values()), str(candidates[i]['player']['id'])))
        reserves.append(index)
        remaining.remove(index)
        for role in coverable[index]:
            coverage[role].append(str(candidates[index]['player']['id']))
    for position, index in enumerate(reserves, 16):
        role = max(candidates[index]['scores'], key=candidates[index]['scores'].get)
        select(index, position, role, candidates[index]['scores'][role], bench=True)
        selected[-1]['covers'] = coverable[index]
    bench_coverage = {
        'roles': [{'role': role, 'player_ids': coverage[role], 'needed': needs[role],
                   'missing': max(0, needs[role]-len(coverage[role]))} for role in role_names],
        'gaps': [role for role in role_names if len(coverage[role]) < needs[role]],
        'method': 'Couverture indicative : affinité calculable au moins égale à 80 % de la meilleure affinité du remplaçant. Deux options recherchées au poste de pilier, une pour chaque autre rôle. Un joueur peut couvrir plusieurs rôles ; les remplacements simultanés et les qualifications de première ligne restent à vérifier.'}

    comparison = {'saved_score': None, 'proposed_score': None, 'delta': None}
    by_id = {str(c['player']['id']): c for c in candidates}
    saved_ids = [saved.get(str(i)) for i in range(1, 16)]
    if starters == 15 and len(set(saved_ids)) == 15 and all(identifier in by_id for identifier in saved_ids):
        saved_scores = [by_id[identifier]['scores'].get(role) for identifier, role in zip(saved_ids, ROLES)]
        if all(score is not None for score in saved_scores):
            saved_score = round(sum(saved_scores), 2)
            proposed_score = round(sum(p['score'] for p in selected if p['slot'] <= 15), 2)
            comparison = {'saved_score': saved_score, 'proposed_score': proposed_score,
                          'delta': round(proposed_score-saved_score, 2)}
    return ({'slots': slots, 'players': selected,
             'unfilled': [i+1 for i, index in enumerate(assignments) if index is None],
             'excluded': excluded, 'comparison': comparison, 'bench_coverage': bench_coverage},
            {'seniors': len(squad), 'eligible': len(candidates), 'selected': starters,
             'low_energy': low_energy, 'unknown_energy': unknown_energy}, unknown_injury)


def calendar_position(game_date, season):
    date = game_date or {}
    observed_season, week = number(date.get('season')), number(date.get('round'))
    if (observed_season is None or observed_season != int(observed_season)
            or not 1 <= observed_season <= 999 or week is None or week != int(week)
            or not 1 <= week <= 16):
        return 17, 'unknown'
    if season < observed_season:
        return 17, 'past'
    if season > observed_season:
        return 1, 'future'
    return int(week), 'current'


def training_plan(academy, saved_grid, start_week):
    # Inputs persisted by /api/plans already have this 4×16 shape.
    grid = [list(row) for row in saved_grid] if saved_grid else [['']*16 for _ in range(4)]
    priorities = []
    for skill in SKILLS:
        known = [number(p.get(skill)) for p in academy]
        known = [value for value in known if value is not None]
        if known:
            average = round(sum(known)/len(known), 2)
            priorities.append({'skill': skill, 'label': SKILL_LABELS[skill], 'average': average,
                               'count': len(known), 'reason': f'Académie : {len(known)}/{len(academy)} valeurs connues ; moyenne {average:g}. Les valeurs masquées sont exclues.'})
    priorities.sort(key=lambda p: (p['average'], SKILLS.index(p['skill'])))
    focus = priorities[:4]
    preserved, added = sum(bool(cell) for row in grid for cell in row), 0
    if focus:
        for week in range(start_week-1, 16):
            for row in range(4):
                if not grid[row][week]:
                    grid[row][week] = focus[(week-start_week+1+row) % len(focus)]['skill']
                    added += 1
    return {'priorities': priorities, 'grid': grid, 'added': added, 'preserved': preserved,
            'remaining_weeks': max(0, 17-start_week), 'start_week': start_week}


def match_reports(matches):
    results = []
    for match in matches:
        summary = match['summary']
        classified, total = summary['classified'], summary['total_events']
        coverage = round(100*classified/total, 1) if total else 0
        sides = []
        for side in ('home', 'away'):
            observed = summary[side]
            actions = observed['total']
            dominant, share = None, None
            evidence = [f'Bibliothèque privée du manager ; rattachement à ce club non établi.',
                        f'{classified}/{total} événements classés ({coverage:g} %) ; {actions} actions classées pour ce côté.',
                        f'{summary["inferred"]} événements portent une classification déduite des commentaires.']
            if actions < 20 or coverage < 60:
                advice = ['Il manque encore du jeu à observer pour dégager une tendance : réunissez au moins 20 actions de ce côté et 60 % de couverture.']
            else:
                attack, count = max(observed['attacks'].items(), key=lambda pair: pair[1])
                evidence.append(f'Attaque la plus observée : {attack}, {count}/{actions} actions classées de ce côté.')
                if count/actions >= .5:
                    dominant, share = attack, round(100*count/actions, 1)
                    advice = [f'Le jeu « {attack} » revient le plus souvent dans ces actions classées. Revoyez ces séquences sur plusieurs rencontres avant de préparer votre réponse.']
                    preparation = {
                        'Large': 'Pour préparer la largeur, comparez la Vitesse, l’Agilité et la Défense de vos arrières, puis vérifiez leur couverture du terrain.',
                        'Percussion': 'Au contact, regardez la Force, la Technique et la Défense de votre pack, puis revoyez les séquences concernées.',
                        'Pick and go': 'Autour des regroupements, comparez la Force, la Technique et la Défense de votre pack pour préparer vos options.',
                        'Créatif': 'Regardez la Dextérité et l’Attaque de vos joueurs de soutien, puis reprenez les séquences pour préciser votre préparation.',
                        'Jeu au pied': 'Examinez le Jeu au pied des profils disponibles et la couverture de votre arrière-garde pour préparer vos options.',
                    }
                    advice.append(preparation[attack]+' Cette piste de travail ne prouve pas qu’une réponse tactique sera efficace.')
                    zone, zone_attacks = max(observed['zones'].items(), key=lambda pair: sum(pair[1].values()))
                    zone_count = sum(zone_attacks.values())
                    evidence.append(f'Zone relative la plus représentée parmi les actions classées : {zone}, {zone_count}/{actions} actions ; égalités départagées par ordre des zones.')
                else:
                    advice = ['Les actions classées montrent plusieurs choix d’attaque, sans dominante nette. Comparez les zones et d’autres rencontres avant de choisir votre réponse.']
                advice.append('Ces observations décrivent le jeu ; elles ne suffisent pas à expliquer le score du match.')
            sides.append({'side': side, 'name': match[side], 'dominant': dominant, 'share': share,
                          'actions': actions, 'advice': advice, 'evidence': evidence})
        results.append({'id': str(match['id']), 'type': match['type'], 'home': match['home'], 'away': match['away'],
                        'coverage': coverage, 'classified': classified, 'total': total,
                        'inferred': summary['inferred'], 'sides': sides})
    return results


def date_value(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError, AttributeError):
        return None


def build_report(state, objective='balanced', energy_floor=60, season=None, *, generated_at, energy_scale='auto'):
    """Build one JSON-ready report from a private /api/state-shaped snapshot."""
    if (objective not in ('balanced', 'recovery', 'development') or number(energy_floor) is None
            or not 0 <= energy_floor <= 110 or energy_scale not in ('auto', 'percent', 'level')):
        raise ValueError('Objectif ou seuil d’énergie invalide.')
    date = state.get('game_date') or {}
    observed_season = number(date.get('season'))
    if season is None:
        season = int(observed_season) if observed_season is not None and observed_season.is_integer() and 1 <= observed_season <= 999 else 1
    if isinstance(season, bool) or not isinstance(season, int) or not 1 <= season <= 999:
        raise ValueError('Saison attendue entre 1 et 999.')
    selection = is_selection(state['current_team']['id'])
    squad = unique_players(state.get('squad', []))
    academy = [] if selection else unique_players(state.get('academy', []))
    actual_scale = energy_scale
    if energy_scale == 'auto':
        actual_scale = 'percent' if any(value is not None and 11 < value <= 110
                                        for value in (number(p.get('energy')) for p in squad)) else 'ambiguous'
    lineup, summary, unknown_injury = make_lineup(squad, state.get('lineup', {}), objective, energy_floor, actual_scale, generated_at)
    summary['academy'] = len(academy)
    start, period = calendar_position(date, season)
    training = ({'applicable': False, 'priorities': [], 'grid': [], 'added': 0, 'preserved': 0,
                 'remaining_weeks': 0, 'start_week': 17} if selection else
                {'applicable': True, **training_plan(academy, state.get('plans', {}).get(str(season)), start)})
    warnings, recommendations, sources = [], [], {}

    def recommend(identifier, category, priority, title, detail, evidence, page):
        if selection and (category in ('academy', 'training', 'stadium') or page in ('academy', 'training', 'stadium')):
            return
        recommendations.append({'id': identifier, 'category': category, 'priority': priority,
                                'title': title, 'detail': detail, 'evidence': evidence, 'page': page})

    groups = [('squad', 'Effectif de la sélection')] if selection else [('squad', 'Effectif senior'), ('academy', 'Académie')]
    for group, label in groups:
        source = state.get(group+'_source') or {}
        timestamp = source.get('observed_at')
        sources[group] = f'{source.get("source", "Source importée")} · {timestamp}' if timestamp else None
        observed, generated = date_value(timestamp), date_value(generated_at)
        age = (generated-observed).total_seconds()/86400 if generated and observed else None
        if age is None or age > 7 or age < -1:
            detail = (f'{label} : observation de plus de 7 jours ({int(age)} jours).' if age is not None and age > 7
                      else f'{label} : date d’observation absente ou incohérente.')
            warnings.append(detail)
            recommend('freshness-'+group, 'data', 'high', 'Actualiser '+label.lower(), detail,
                      [sources[group] or 'Aucun instantané daté disponible.'], 'settings')
    if len(squad) != len(state.get('squad', [])) or (not selection and len(academy) != len(state.get('academy', []))):
        warnings.append('Identifiants de joueurs répétés : seule la première observation de chaque identifiant est utilisée.')
    if summary['unknown_energy']:
        warnings.append(f'{summary["unknown_energy"]} seniors ont une énergie inconnue, hors limites ou ambiguë ; éligibles sous réserve, sans filtre ni bonus énergie.')
    if actual_scale == 'ambiguous' and squad:
        warnings.append('Échelle d’énergie ambiguë : aucune valeur exploitable supérieure à 11. Choisir pourcentage (0–110) ou niveau (1–11) ; filtre et bonus énergie inactifs en mode automatique pour ces observations.')
    elif actual_scale == 'level':
        warnings.append('Énergie en niveaux 1–11 : conversion approximative niveau ×10 en pourcentage pour le seuil et le bonus ; ce calcul ne reconstitue pas une mesure précise.')
    elif energy_scale == 'auto':
        warnings.append('Énergie : échelle pourcentage 0–110 retenue car au moins une observation dépasse 11. Vérifier le choix si l’import mélange plusieurs formats.')
    if any(p['count']*2 < len(academy) for p in training['priorities']):
        warnings.append('Certaines moyennes de l’académie couvrent moins de la moitié des jeunes ; priorités provisoires à réévaluer après de nouveaux dévoilements.')
    if unknown_injury:
        warnings.append(f'Disponibilité médicale non confirmée pour {unknown_injury} seniors ; vérifier avant de retenir le XV.')
    warnings.append('Banc : jusqu’à 8 réserves distinctes, choisies pour compléter les rôles couverts puis selon leur meilleure affinité ; qualifications de première ligne et remplacements simultanés à vérifier.')
    if not selection and period == 'unknown':
        warnings.append('Date de jeu absente ou invalide : aucun créneau ajouté ; sélectionner une saison ne confirme pas le calendrier actuel.')
    elif not selection:
        warnings.append(f'Horizon fondé sur la dernière date de jeu importée : saison {int(observed_season)}, semaine {int(number(date.get("round")))}. Le calendrier réel actuel reste à vérifier.')
    if lineup['unfilled']:
        recommend('lineup-incomplete', 'squad', 'high', 'Il reste des places à pourvoir',
                  'Certains postes n’ont pas de candidat disponible avec un profil calculable. Complétez les compétences manquantes ou vérifiez les disponibilités avant d’assouplir le seuil d’énergie.',
                  [f'{summary["selected"]}/15 titulaires proposés ; {summary["eligible"]} seniors éligibles.',
                   'Postes vacants : '+', '.join(map(str, lineup['unfilled']))], 'squad')
    else:
        recommend('lineup-review', 'squad', 'medium', 'Le XV se dessine : à vous de le relire',
                  'Les affinités connues ont permis d’attribuer les quinze postes ensemble. Vérifiez maintenant la disponibilité, le rôle réel de chacun et les solutions du banc avant d’enregistrer votre choix dans l’outil.',
                  [f'15 titulaires distincts ; {len(lineup["players"])-15} réserves.', f'Seuil minimal d’énergie connue : {energy_floor:g} %.'], 'squad')
    if summary['low_energy']:
        recommend('energy', 'squad', 'high' if objective == 'recovery' else 'medium', 'La rotation mérite un coup d’œil',
                  'Les joueurs sous votre seuil d’énergie sont écartés de cet aperçu. Actualisez leurs valeurs et comparez les solutions disponibles : ces données ne permettent pas de prévoir leur récupération.',
                  [f'{summary["low_energy"]}/{len(squad)} seniors sous {energy_floor:g} %.'], 'squad')
    if training['priorities']:
        first = training['priorities'][0]
        recommend('academy-training', 'training', 'medium', 'Où faire porter l’effort à l’académie ?',
                  'Les quatre moyennes connues les plus basses orientent les séances proposées dans les cases libres. Regardez combien de jeunes sont observés : si la couverture est faible, complétez d’abord vos repères.',
                  [f'{first["label"]} : moyenne {first["average"]:g}, {first["count"]}/{len(academy)} jeunes observés.',
                   f'{training["added"]} cases proposées ; {training["preserved"]} cases existantes conservées.'], 'training')
    hidden = sum(number(p.get(skill)) is None for p in academy for skill in SKILLS)
    if hidden or not academy:
        recommend('academy-observe', 'academy', 'high' if not training['priorities'] else 'medium',
                  'La relève a encore des choses à montrer',
                  'Importez l’académie et suivez les dévoilements pour préciser les profils avant de juger un niveau ou de décider une promotion. Une compétence masquée reste inconnue, jamais égale à zéro.',
                  [f'{len(academy)} jeunes ; {hidden}/{len(academy)*len(SKILLS)} compétences inconnues.'], 'academy')
    elif academy:
        recommend('academy-progress', 'academy', 'low', 'Les prochains relevés feront le point',
                  'Toutes les compétences sont connues dans cet effectif. Comparez-les aux prochains instantanés pour mesurer les évolutions et ajuster les séances ; aucun gain d’entraînement n’est prédit.',
                  [f'{len(academy)} jeunes avec leurs dix compétences connues.'], 'academy')
    actions = {
        'balanced': 'Revoyez les associations du XV et les rôles couverts par le banc.',
        'recovery': 'Actualisez les énergies, puis préparez les relais pour les joueurs sous le seuil.',
        'development': 'Comparez les jeunes seniors proposés à vos titulaires habituels, puis suivez leurs progrès observés.',
    }
    phases = []
    if selection:
        pass
    elif period in ('past', 'unknown'):
        phases.append({'phase': 'Bilan archivé' if period == 'past' else 'Calendrier à confirmer',
                       'weeks': f'Saison {season}',
                       'actions': ['Conserver les séances enregistrées ; aucun ajout automatique.',
                                   'Importer une date de jeu récente avant de préparer un nouvel horizon.']})
    else:
        for begin, end, label in [(1, 4, 'Préparer'), (5, 8, 'Observer'), (9, 12, 'Ajuster'), (13, 16, 'Faire le bilan')]:
            if end >= start:
                phases.append({'phase': label, 'weeks': f'S{max(begin, start)}–S{end}',
                               'actions': [actions[objective],
                                           'Comparer les observations de l’académie et les cases libres du plan.' if academy else 'Importer l’académie pour préparer ses séances.',
                                           'Relire les rencontres de la bibliothèque avec leur couverture ; confirmer le calendrier dans Classic.']})
    recommend('season-horizon', 'season', 'medium', 'Gardez le calendrier en ligne de mire',
              'Ces étapes vous aident à organiser la préparation. Vérifiez les rendez-vous dans Classic : ce découpage ne donne ni les dates des rencontres ni un calendrier officiel.',
              [f'Saison ciblée : {season} ; {training["remaining_weeks"]} semaines dans l’horizon importé.'], 'training')
    meta = state['current_team'].get('meta', {})
    members = number(meta.get('members'))
    sections = ['standing', 'uncovered', 'covered', 'members', 'corporate']
    seats = {key: number(meta.get('stadium_'+key)) for key in sections}
    if not selection and members is not None and 0 <= members <= 1_000_000 and all(value is not None and value >= 0 for value in seats.values()):
        stadium = stadium_plan(members, seats, 9)
        recommend('stadium-scenario', 'stadium', 'low', 'Le stade : un scénario à mettre à l’épreuve',
                  'Cette hypothèse prévoit 9 places par membre avec les ratios de l’outil stade. Comparez-la à l’affluence, aux coûts et à la trésorerie du jeu avant de décider ; elle ne recommande pas automatiquement de construire.',
                  [f'{members:g} membres ; {sum(seats.values()):g} places observées ; cible indicative {stadium["target_total"]:g}.',
                   f'{stadium["to_add"]:g} places supplémentaires dans ce scénario.',
                   'Date des données du club : '+str(meta.get('date_maj') or 'non renseignée')], 'stadium')
    methodology = [
        'Heuristique locale explicable, indépendante du moteur officiel de Blackout Rugby. Aucun pronostic de victoire, gain de compétence ou action dans le jeu.',
        'Affinités : moyennes pondérées existantes, calculées seulement si toutes les compétences du rôle sont connues. Pilier FOR×3 TEC×2 END ; talonneur DEX×2 FOR×2 TEC×2 ; deuxième ligne SAU×3 FOR×2 TEC ; troisième ligne DEF×2 TEC×2 END FOR ; demi de mêlée DEX×3 AGI×2 KIK ; ouverture DEX×2 KIK×2 ATT×2 ; centre ATT×2 DEF×2 FOR VIT ; ailier VIT×3 AGI×2 ATT ; arrière KIK×2 VIT×2 DEX×2. Chaque somme est divisée par la somme de ses poids.',
        'Équilibre = affinité ; récupération = affinité + 3×énergie/110 si connue ; développement = affinité + bonus âge : 3 à 21 ans ou moins, (30−âge)/3 entre 21 et 30 ans, 0 au-delà. Donnée absente : aucun bonus, sans lui attribuer une valeur observée.',
        f'Énergie connue admise de {energy_floor:g} à 110 % inclus. API Premium : pourcentages 0–110 ; API non Premium : niveaux 1–11. Auto détecte le pourcentage avec une valeur >11 et ≤110 ; sinon énergie ambiguë, filtre et bonus inactifs. Mode niveau : approximation niveau ×10, explicitée avec la valeur brute.',
        'Blessures : timestamp Unix (>1) ou ISO avec fuseau futur par rapport au bilan = indisponible ; date passée ou sentinelle Classic −001-11-30 = disponible selon cette observation. Marqueurs 1/True/oui exclus ; 0/False/non sont négatifs. Absence, date sans fuseau ou texte ambigu ne confirme aucune disponibilité.',
        'Référence API Classic consultée le 30 octobre 2026 : https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329 (énergie Premium/non Premium et injured). Les coefficients d’objectif sont des choix locaux, pas des règles officielles.',
        'Algorithme hongrois : maximiser le nombre de postes calculables puis la somme des scores du XV, sans doublon. L’atelier peut imposer des postes, titulaires et exclusions. Le banc complète en priorité les rôles couverts (affinité ≥80 % de la meilleure du remplaçant), puis favorise la meilleure affinité ; qualifications et remplacements simultanés restent à vérifier.',
        'Comparaison : somme des scores de deux XV complets, chaque joueur éligible et chaque rôle calculable avec le même objectif. Sinon scores et différence restent indisponibles.',
        'Académie uniquement pour le programme 4×16 : moyennes des valeurs connues, effectifs observés affichés ; rotation des quatre moyennes les plus basses. Conserver toutes les cases existantes et les semaines antérieures à la dernière date de jeu importée. Sans calendrier valide ou pour une saison passée : aucun ajout.',
        'Matchs de la bibliothèque privée du manager, sans rattachement automatique au club : couverture = événements classés / tous événements. Tendance descriptive seulement à partir de 60 % de couverture et 20 actions classées du côté étudié ; dominante si au moins 50 % de ces actions. Les inférences de commentaires sont comptées, aucune causalité avec le résultat.',
        'Fraîcheur : avertissement après 7 jours ou date absente/incohérente ; la date d’import ne prouve pas que les mesures sont actuelles. Saison et semaine sont les dernières observations importées, pas une horloge du jeu.',
    ]
    if selection:
        methodology = [line for line in methodology if not line.startswith('Académie uniquement')]
    return {'team': {**{k: state['current_team'][k] for k in ('id', 'name', 'country')}, **team_identity(state['current_team']['id'])},
            'objective': objective, 'season': season, 'generated_at': generated_at,
            'sources': sources, 'warnings': warnings, 'summary': summary, 'lineup': lineup,
            'recommendations': recommendations, 'training': training, 'season_plan': phases,
            'matches': match_reports(state.get('matches', [])), 'methodology': methodology}
