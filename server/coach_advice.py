"""Read-only coaching heuristics built from one private state snapshot.

No clock, storage, network, game write, or prediction of individual progress.
"""
from .domain import SKILLS, SKILL_LABELS, number, player_metrics
from .optimization import energy_of, injury_status


# Same skill membership as domain.player_metrics, without redefining its weights.
ROLE_SKILLS = {
    'Pilier': ('strength', 'technique', 'stamina'),
    'Talonneur': ('handling', 'strength', 'technique'),
    'Deuxième ligne': ('jumping', 'strength', 'technique'),
    'Troisième ligne': ('defense', 'technique', 'stamina', 'strength'),
    'Demi de mêlée': ('handling', 'agility', 'kicking'),
    'Demi d’ouverture': ('handling', 'kicking', 'attack'),
    'Centre': ('attack', 'defense', 'strength', 'speed'),
    'Ailier': ('speed', 'agility', 'attack'),
    'Arrière': ('kicking', 'speed', 'handling'),
}


def observed_number(value):
    parsed = number(value)
    return parsed if parsed is not None and parsed >= 0 else None


def group_advice(players, source, notes, academy=False):
    unique = {}
    for player in players:
        unique.setdefault(str(player['id']), player)
    players = [unique[key] for key in sorted(unique)]
    count = len(players)
    skills = []
    for skill in SKILLS:
        values = [observed_number(player.get(skill)) for player in players]
        known = [value for value in values if value is not None]
        skills.append({'skill': skill, 'label': SKILL_LABELS[skill],
                       'average': round(sum(known)/len(known), 2) if known else None,
                       'known': len(known), 'total': count,
                       'coverage': round(100*len(known)/count, 1) if count else None,
                       'comparable': len(known) >= 3 and len(known) >= count*.6})
    comparable = [item for item in skills if item['comparable']]
    reference = sum(item['average'] for item in comparable)/len(comparable) if comparable else None
    strengths = sorted((item for item in comparable if item['average'] > reference + 1e-9),
                       key=lambda item: -item['average'])[:2]
    weaknesses = sorted((item for item in comparable if item['average'] < reference - 1e-9),
                        key=lambda item: item['average'])[:2]
    energy_scale = 'percent' if any(value is not None and 11 < value <= 110
                                    for value in (number(player.get('energy')) for player in players)) else 'ambiguous'
    availability = {'energy_scale': energy_scale, 'injured': 0, 'low_energy': 0,
                    'unknown_injury': 0, 'unknown_energy': 0, 'unknown_form': 0}
    priorities, observe = [], []
    for player in players:
        clean = {skill: observed_number(player.get(skill)) for skill in SKILLS}
        metrics = player_metrics(clean)
        roles = metrics['roles']
        profile = roles[0] if roles else None
        injury = injury_status(player.get('injured', player.get('injury')), source.get('observed_at'))
        energy, form = energy_of(player, energy_scale), observed_number(player.get('form'))
        low_energy = energy is not None and energy < 60
        availability['injured'] += int(injury is True)
        availability['unknown_injury'] += int(injury is None)
        availability['low_energy'] += int(low_energy)
        availability['unknown_energy'] += int(energy is None)
        availability['unknown_form'] += int(form is None)
        age, stars = observed_number(player.get('age')), observed_number(player.get('stars'))
        age = age if age is not None and 0 < age <= 100 else None
        generation = observed_number(player.get('wc_projection')) if academy else None
        generation = int(generation) if generation is not None and generation > 0 and generation.is_integer() else None
        note = notes.get(str(player['id'])) or {}
        readiness = ('recovery' if injury is True or low_energy else
                     'verify' if injury is None or energy is None or form is None else 'review')
        signals = []
        if injury is True:
            signals.append('Blessure signalée à la date de la source : vérifier la disponibilité avant toute séance ou sélection.')
        elif injury is None:
            signals.append('Disponibilité médicale non confirmée.')
        if low_energy:
            signals.append(f'Énergie observée de {energy:g} % : examiner la récupération et la charge avant de renforcer l’entraînement.')
        elif energy is None:
            signals.append('Énergie inconnue ou échelle ambiguë : vérifier dans Classic.')
        if form is None:
            signals.append('Forme non renseignée : vérifier avant de choisir les priorités de la semaine.')
        focus = None
        if profile:
            skill = min(ROLE_SKILLS[profile['name']], key=lambda key: clean[key])
            focus = {'skill': skill, 'label': SKILL_LABELS[skill], 'value': clean[skill]}
        age_context = ('À partir de 29 ans, suivre les évolutions observées : une baisse du CSR est possible, '
                       'sans âge de bascule fixe ; une progression peut encore être observée à 33 ans. '
                       'L’âge seul ne retire pas ce joueur des pistes d’entraînement.' if age is not None and age >= 29 else None)
        item = {'id': str(player['id']), 'name': str(player.get('name') or 'Joueur sans nom'),
                'age': age, 'stars': stars, 'wc_projection': generation, 'known_skills': metrics['known_skills'],
                'profile': profile, 'focus': focus, 'energy': energy, 'form': form,
                'injured': injury, 'readiness': readiness, 'signals': signals,
                'age_context': age_context, 'watch': note.get('watch') is True,
                'note': note.get('text') if isinstance(note.get('text'), str) and note['text'].strip() else None}
        (priorities if profile else observe).append(item)

    def priority(item):
        availability_rank = {'review': 0, 'verify': 1, 'recovery': 2}[item['readiness']]
        age = item['age']
        if academy:
            return (availability_rank, -(item['stars'] if item['stars'] is not None else -1),
                    item['wc_projection'] if item['wc_projection'] is not None else float('inf'),
                    -item['profile']['score'], item['id'])
        return (availability_rank, 0 if age is not None and age <= 23 else 1,
                -item['profile']['score'], item['id'])

    priorities.sort(key=priority)
    known_skills = sum(item['known'] for item in skills)
    return {'count': count, 'known_skills': known_skills, 'total_skills': count*len(SKILLS),
            'coverage': round(100*known_skills/(count*len(SKILLS)), 1) if count else None,
            'skills': skills, 'strengths': strengths, 'weaknesses': weaknesses,
            'priorities': priorities, 'observe': observe, 'availability': availability,
            'source': {'observed_at': source.get('observed_at'), 'name': source.get('source')},
            'comparison_note': ('Lecture indicative des compétences les mieux couvertes, à l’intérieur de cet effectif. '
                                'Elle ne mesure ni l’efficacité en match ni le niveau des adversaires.' if strengths or weaknesses else
                                'Pas de contraste suffisamment documenté : au moins 3 observations et 60 % de couverture '
                                'par compétence sont nécessaires ; des moyennes identiques ne révèlent pas de faiblesse.')}


def build_coach_advice(state: dict) -> dict:
    """Return a JSON-ready report; missing observations remain missing."""
    team = state.get('current_team') or {}
    notes = state.get('notes') or {}
    groups = {name: group_advice(state.get(name) or [], state.get(name+'_source') or {}, notes,
                                academy=name == 'academy') for name in ('squad', 'academy')}
    warnings = []
    for name, label in (('squad', 'Seniors'), ('academy', 'Académie')):
        group = groups[name]
        if group['count'] != len(state.get(name) or []):
            warnings.append(f'{label} : identifiants répétés ; seule la première observation est conservée.')
        if group['count'] and not group['source']['observed_at']:
            warnings.append(f'{label} : date d’observation absente ; actualiser avant une décision.')
    return {'team': {'id': str(team['id']) if team.get('id') is not None else None, 'name': team.get('name')},
            **groups, 'warnings': warnings,
            'methodology': [
                'Conseils indicatifs, calculés sur les dernières observations importées. Aucune action dans le jeu, aucun gain garanti. Actualiser les données avant une décision.',
                'Points d’appui et axes de travail : moyennes des valeurs connues, avec au moins 3 joueurs et 60 % de couverture par compétence. Comparaison à la moyenne des compétences ainsi retenues ; les effectifs observés peuvent différer. Une valeur inconnue ne vaut jamais zéro.',
                'Profils : affinités pondérées de l’outil, calculées seulement lorsque toutes les compétences du rôle sont connues. La compétence connue la plus basse du meilleur profil est une piste à discuter, pas un poste ni un programme imposés.',
                'Seniors : disponibilité à vérifier en premier, puis profils de 23 ans ou moins et meilleure affinité connue. Aucun joueur n’est écarté pour son âge ; le CSR n’entre pas dans ce classement.',
                'Académie : un profil calculable est nécessaire, puis disponibilité, nombre d’étoiles de recrutement, génération indicative la plus proche et affinité départagent les pistes. Les étoiles indiquent le cumul de recrutement observé. Le repère de génération déjà calculé dans l’outil est une cohorte indicative, pas une garantie de sélection U20. L’âge ne départage pas ce classement. Les jeunes aux compétences masquées restent à observer ; les étoiles seules ne prouvent pas un potentiel.',
                'Énergie : le pourcentage 0–110 est supposé seulement si une valeur du même groupe dépasse 11 ; vérifier les imports mêlant plusieurs formats. Sinon aucune alerte de fatigue. Sous 60 %, la récupération est à examiner, seuil local indicatif.',
                'Blessures datées : état à la date d’observation de la source, pas disponibilité actuelle garantie. Forme : valeur brute affichée sans conversion ni seuil, car son échelle et son contexte restent à confirmer.',
                'À partir de 29 ans, une baisse du CSR peut survenir sans âge fixe ; progresser à 33 ans reste possible. Comparer les observations individuelles et les compétences avant de conclure. Les notes du manager sont reprises telles quelles, sans objectif déduit.',
            ]}
