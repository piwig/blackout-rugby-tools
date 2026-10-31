"""Private, local lineup scenarios. Never issues a Classic request."""
import json
import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import number
from .optimization import make_lineup, unique_players
from .storage import now, pack
from .team_identity import TeamId


Identifier = Annotated[str, Field(strict=True, pattern=r'^\d{1,15}$')]
ScenarioId = Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{32}$')]
Revision = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Options(Model):
    objective: Literal['balanced', 'recovery', 'development'] = 'balanced'
    energy_floor: Annotated[int, Field(strict=True, ge=0, le=110)] = 60
    energy_scale: Literal['auto', 'percent', 'level'] = 'auto'
    locks: dict[Annotated[str, Field(pattern=r'^(?:[1-9]|1[0-5])$')], Identifier] = Field(default_factory=dict, max_length=15)
    starter_ids: list[Identifier] = Field(default_factory=list, max_length=15)
    excluded_ids: list[Identifier] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def consistent(self):
        required = set(self.locks.values()) | set(self.starter_ids)
        if (len(set(self.locks.values())) != len(self.locks)
                or len(set(self.starter_ids)) != len(self.starter_ids)
                or len(set(self.excluded_ids)) != len(self.excluded_ids)
                or len(required) > 15 or required & set(self.excluded_ids)):
            raise ValueError('Verrouillages, titulaires et exclusions incohérents.')
        return self


class Preview(Model):
    team_id: TeamId
    options: Options = Field(default_factory=Options)


class ScenarioSave(Preview):
    id: ScenarioId | None = None
    expected_revision: Revision
    expected_source_id: Annotated[int, Field(strict=True, ge=1)] | None = None
    name: Annotated[str, Field(strict=True, min_length=1, max_length=80)]

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError('Nom de scénario invalide.')
        return value


class ScenarioDelete(Model):
    team_id: TeamId
    id: ScenarioId
    expected_revision: Revision


class LineupApply(Preview):
    expected_source_id: Annotated[int, Field(strict=True, ge=1)] | None
    expected_slots: dict[Annotated[str, Field(pattern=r'^(?:[1-9]|1[0-9]|2[0-3])$')],
                         Annotated[str, Field(strict=True, pattern=r'^\d{0,15}$')]] = Field(max_length=23)


def calculate(snapshot, options):
    generated_at = now()
    squad = unique_players(snapshot.get('squad', []))
    actual_scale = options.energy_scale
    if actual_scale == 'auto':
        actual_scale = 'percent' if any(value is not None and 11 < value <= 110
                                      for value in (number(p.get('energy')) for p in squad)) else 'ambiguous'
    lineup, summary, unknown_injury = make_lineup(
        squad, snapshot.get('lineup', {}), options.objective, options.energy_floor,
        actual_scale, generated_at, locks=options.locks,
        starter_ids=options.starter_ids, excluded_ids=options.excluded_ids)
    warnings = []
    if actual_scale == 'ambiguous':
        warnings.append('Échelle d’énergie ambiguë : aucun filtre ni bonus énergie appliqué. Choisissez le format de la source.')
    if summary['unknown_energy']:
        warnings.append(f'{summary["unknown_energy"]} énergie(s) inconnue(s) ou ambiguë(s) ; joueurs éligibles sous réserve.')
    if unknown_injury:
        warnings.append(f'{unknown_injury} disponibilité(s) médicale(s) non confirmée(s).')
    if lineup['unfilled']:
        warnings.append('XV incomplet : certains postes n’ont aucun candidat calculable.')
    return {'generated_at': generated_at, 'source': snapshot.get('squad_source'),
            'energy_scale': actual_scale, 'lineup': lineup, 'summary': summary,
            'score': round(sum(p['score'] for p in lineup['players'] if p['slot'] <= 15), 2)
                     if not lineup['unfilled'] else None,
            'warnings': warnings}


def compare_scenarios(left, right):
    a, b = left['preview'], right['preview']
    reasons = []
    # Objective scores are different measures; do not imply a gain across them.
    if any(left['options'][key] != right['options'][key]
           for key in ('objective', 'energy_floor', 'energy_scale')):
        reasons.append('Objectifs ou critères d’énergie différents : scores non directement comparables.')
    if a.get('source') != b.get('source'):
        reasons.append('Observations de l’effectif différentes ; les valeurs décrivent leur date de sauvegarde.')
    if a['score'] is None or b['score'] is None:
        reasons.append('Au moins un XV est incomplet : différence de score indisponible.')
    changes = [{'slot': i, 'left': a['lineup']['slots'].get(str(i)),
                'right': b['lineup']['slots'].get(str(i))} for i in range(1, 24)
               if a['lineup']['slots'].get(str(i)) != b['lineup']['slots'].get(str(i))]
    def values(scenario):
        preview = scenario['preview']
        return {'id': scenario['id'], 'name': scenario['name'], 'score': preview['score'],
                'starters': preview['summary']['selected'],
                'bench_gaps': preview['lineup']['bench_coverage']['gaps'],
                'generated_at': preview['generated_at']}
    return {'left': values(left), 'right': values(right), 'changes': changes,
            'delta': None if reasons else round(b['score']-a['score'], 2), 'warnings': reasons,
            'explanation': 'Indices locaux d’affinité et bonus expliqués par joueur ; aucune prévision du résultat d’un match.'}


def register_lineup_lab(app, store, auth, require_team, state):
    """Register against the request's PrivateStore; no client-provided tenant."""
    def document(team_id, db=None):
        if db is None:
            return store.get('lineup_lab:'+team_id, {'revision': 0, 'scenarios': []})
        row = db.execute('SELECT value FROM kv WHERE key=?', ('lineup_lab:'+team_id,)).fetchone()
        return json.loads(row['value']) if row else {'revision': 0, 'scenarios': []}

    def preview(body, session):
        require_team(body.team_id)
        try:
            return calculate(state(body.team_id, session), body.options)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def find(doc, identifier):
        found = next((item for item in doc['scenarios'] if item['id'] == identifier), None)
        if found is None:
            raise HTTPException(404, 'Scénario introuvable dans ce club.')
        return found

    def write(body, operation):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            doc = document(body.team_id, db)
            if doc['revision'] != body.expected_revision:
                raise HTTPException(409, 'Les scénarios ont changé dans un autre onglet. Rechargez la liste avant de réessayer.')
            operation(doc)
            doc['revision'] += 1
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('lineup_lab:'+body.team_id, pack(doc)))
        return doc

    @app.get('/api/lineup-lab/scenarios')
    def scenarios(team_id: TeamId = Query(), session=Depends(auth)):
        require_team(team_id)
        return document(team_id)

    @app.post('/api/lineup-lab/preview')
    def calculate_preview(body: Preview, session=Depends(auth)):
        return preview(body, session)

    @app.post('/api/lineup-lab/scenarios')
    def save_scenario(body: ScenarioSave, session=Depends(auth)):
        result = preview(body, session)
        if ('expected_source_id' in body.model_fields_set
                and (result.get('source') or {}).get('id') != body.expected_source_id):
            raise HTTPException(409, 'L’effectif a changé depuis votre aperçu. Rechargez les données et recalculez le XV.')
        def operation(doc):
            if body.id:
                old = find(doc, body.id)
                created_at = old['created_at']
                index = doc['scenarios'].index(old)
            else:
                if len(doc['scenarios']) >= 20:
                    raise HTTPException(422, 'Vingt scénarios maximum par club ; supprimez un ancien scénario.')
                created_at, index = now(), len(doc['scenarios'])
            item = {'id': body.id or uuid.uuid4().hex, 'name': body.name,
                    'created_at': created_at, 'updated_at': now(),
                    'options': body.options.model_dump(), 'preview': result}
            if index < len(doc['scenarios']):
                doc['scenarios'][index] = item
            else:
                doc['scenarios'].append(item)
        return write(body, operation)

    @app.post('/api/lineup-lab/apply')
    def apply_lineup(body: LineupApply, session=Depends(auth)):
        require_team(body.team_id)
        with store.db() as db:
            # Reserve the writer before reading both source and existing lineup.
            # No import or other lineup write can slip between these comparisons.
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM kv WHERE key=?', ('lineup:'+body.team_id,)).fetchone()
            current = json.loads(row['value']) if row else {}
            if current != body.expected_slots:
                raise HTTPException(409, 'Le XV a changé depuis cet aperçu. Rechargez les données avant de confirmer.')
            snapshot = state(body.team_id, session)
            if (snapshot.get('squad_source') or {}).get('id') != body.expected_source_id:
                raise HTTPException(409, 'L’effectif a changé depuis votre aperçu. Rechargez les données et recalculez le XV.')
            try:
                result = calculate(snapshot, body.options)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            if not result['lineup']['slots']:
                raise HTTPException(422, 'Aucun joueur calculable pour cette composition.')
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',
                       ('lineup:'+body.team_id, pack(result['lineup']['slots'])))
        return {'ok': True, 'preview': result}

    @app.post('/api/lineup-lab/delete')
    def delete_scenario(body: ScenarioDelete, session=Depends(auth)):
        require_team(body.team_id)
        def operation(doc):
            doc['scenarios'].remove(find(doc, body.id))
        return write(body, operation)

    @app.get('/api/lineup-lab/compare')
    def compare(team_id: TeamId = Query(), left_id: ScenarioId = Query(),
                right_id: ScenarioId = Query(), session=Depends(auth)):
        require_team(team_id)
        doc = document(team_id)
        return compare_scenarios(find(doc, left_id), find(doc, right_id))
