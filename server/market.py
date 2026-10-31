"""Private recruitment workbook. Local scenarios never submit Classic orders."""
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import number, player_metrics
from .role_weights import METHOD, SKILL_KEYS, default_weights
from .storage import now, pack
from .team_identity import TeamId, require_club_id
from .workbench import parse_date


HORIZON = 4
MONEY_FIELDS = ('cash', 'weekly_income', 'weekly_expenses', 'reserve', 'committed_bids')
Money = Annotated[int | float, Field(ge=0, le=1_000_000_000_000)]
Skill = Annotated[float, Field(strict=True, ge=0, le=21)]
Identifier = Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{32}$')]
Role = Literal['Pilier', 'Talonneur', 'Deuxième ligne', 'Troisième ligne', 'Demi de mêlée',
               'Demi d’ouverture', 'Centre', 'Ailier', 'Arrière']


class StrictDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False, str_strip_whitespace=True)


class Budget(StrictDocument):
    cash: Money | None = None
    weekly_income: Money | None = None
    weekly_expenses: Money | None = None
    reserve: Money | None = None
    committed_bids: Money | None = None
    complete: bool = False
    observed_at: str | None = Field(default=None, max_length=40)

    @field_validator('observed_at')
    @classmethod
    def dated_observation(cls, value):
        if value is None:
            return None
        date = parse_date(value)
        if date is None or 'T' not in value:
            raise ValueError('Date ISO avec fuseau requise.')
        return date.isoformat()


class Skills(StrictDocument):
    stamina: Skill | None = None
    handling: Skill | None = None
    attack: Skill | None = None
    defense: Skill | None = None
    technique: Skill | None = None
    strength: Skill | None = None
    jumping: Skill | None = None
    speed: Skill | None = None
    agility: Skill | None = None
    kicking: Skill | None = None


class NamedItem(StrictDocument):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    notes: str = Field(default='', max_length=1000)

    @field_validator('name')
    @classmethod
    def printable_name(cls, value):
        if any(ord(character) < 32 for character in value):
            raise ValueError('Nom invalide.')
        return value


class Candidate(NamedItem):
    classic_id: Annotated[str, Field(pattern=r'^[1-9][0-9]{0,14}$')] | None = None
    role: Role
    age: Annotated[int, Field(ge=16, le=60)] | None = None
    price: Money | None = None
    weekly_salary: Money | None = None
    fees: Money | None = None
    skills: Skills = Field(default_factory=Skills)
    status: Literal['watch', 'shortlist', 'dismissed'] = 'watch'


class Investment(NamedItem):
    initial_cost: Money | None = None
    weekly_cost: Money | None = None


class MarketSave(StrictDocument):
    team_id: TeamId
    expected_revision: Annotated[int, Field(ge=0, le=2_147_483_647)]
    plan: Budget
    candidates: list[Candidate] = Field(max_length=50)
    investments: list[Investment] = Field(max_length=20)

    @model_validator(mode='after')
    def unique_ids(self):
        for items in (self.candidates, self.investments):
            if len({item.id for item in items}) != len(items):
                raise ValueError('Identifiants en double.')
        return self


def decimal(value):
    return None if value is None else Decimal(str(value))


def plus(*values):
    return None if any(value is None for value in values) else sum(values, Decimal(0))


def minus(value, *costs):
    return None if value is None or any(cost is None for cost in costs) else value-sum(costs, Decimal(0))


def numeric(value):
    # Arithmetic and comparisons remain decimal until the JSON number boundary.
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def ceiling(immediate, projected, enabled):
    if not enabled or immediate is None or projected is None:
        return None
    return max(Decimal(0), min(immediate, projected))


def deficits(immediate, projected):
    return [code for value, code in ((immediate, 'immediate_deficit'), (projected, 'projected_deficit'))
            if value is not None and value < 0]


def role_comparison(candidate, squad):
    role, skills = candidate['role'], candidate['skills']
    required = [key for key, weight in default_weights()[role].items() if weight]
    missing = [key for key in required if skills.get(key) is None]
    score = next((item['score'] for item in player_metrics(skills)['roles'] if item['name'] == role), None)
    scores = []
    for player in squad:
        # Legacy/imported observations may be strings. Reject invalid skill levels.
        clean = {key: number(player.get(key)) for key in SKILL_KEYS}
        clean = {key: value if value is not None and 0 <= value <= 21 else None for key, value in clean.items()}
        value = next((item['score'] for item in player_metrics(clean)['roles'] if item['name'] == role), None)
        if value is not None:
            scores.append(value)
    best = max(scores) if scores else None
    return {'role': role, 'score': score, 'known_skills': sum(skills.get(key) is not None for key in SKILL_KEYS),
            'missing_skills': missing, 'squad_known': len(scores), 'squad_total': len(squad),
            'squad_best': best, 'squad_average': round(sum(scores)/len(scores), 2) if scores else None,
            'delta_best': round(score-best, 2) if score is not None and best is not None else None,
            'rank': 1+sum(value > score for value in scores) if score is not None and scores else None}


def analyze_market(plan, candidates, investments, squad=(), observed_at=None, snapshot_id=None):
    """Four independent weekly intervals; no replacement savings or timing guesses."""
    with localcontext() as context:
        context.prec = 350
        return _analyze_market(plan, candidates, investments, squad, observed_at, snapshot_id)


def _analyze_market(plan, candidates, investments, squad, observed_at, snapshot_id):
    amounts = {key: decimal(plan[key]) for key in MONEY_FIELDS}
    missing = [key for key in MONEY_FIELDS if amounts[key] is None]
    warnings = []
    if not plan['complete']:
        missing.append('complete')
    if missing:
        warnings.append('budget_incomplete')
    date = parse_date(plan['observed_at'])
    if date is None:
        missing.append('observed_at')
        warnings.append('budget_undated')
    elif date > datetime.now(timezone.utc):
        missing.append('observed_at')
        warnings.append('budget_future_dated')
    confirmed = not missing
    net = minus(amounts['weekly_income'], amounts['weekly_expenses'])
    four_week_net = net*HORIZON if net is not None else None
    projected_cash = minus(plus(amounts['cash'], four_week_net), amounts['committed_bids'])
    immediate = minus(amounts['cash'], amounts['reserve'], amounts['committed_bids'])
    projected = minus(projected_cash, amounts['reserve'])
    warnings.extend(deficits(immediate, projected))
    if not squad:
        warnings.append('squad_unavailable')
    if parse_date(observed_at) is None:
        warnings.append('squad_undated')

    def scenario(item, initial_fields, weekly_field):
        absent = [field for field in (*initial_fields, weekly_field) if item[field] is None]
        initial = plus(*(decimal(item[field]) for field in initial_fields))
        weekly = decimal(item[weekly_field])
        recurring = weekly*HORIZON if weekly is not None else None
        cost = plus(initial, recurring)
        current_left = minus(immediate, initial)
        later_cash = minus(projected_cash, cost)
        later_left = minus(projected, cost)
        # Candidate fees are paid upfront; ceiling is the price alone. Investment
        # ceiling is the upfront project cost. Every row is an independent scenario.
        fees = decimal(item['fees']) if 'fees' in initial_fields else Decimal(0)
        limit = ceiling(minus(immediate, fees), minus(projected, fees, recurring), confirmed and not absent)
        status = 'unknown' if not confirmed or absent else (
            'affordable' if current_left >= 0 and later_left >= 0 else 'over_budget')
        return {'id': item['id'], 'status': status, 'missing_fields': missing+absent,
                'warnings': list(dict.fromkeys(warnings+deficits(current_left, later_left))),
                'initial_cost': numeric(initial), 'four_week_cost': numeric(cost),
                'immediate_headroom': numeric(current_left), 'projected_cash': numeric(later_cash),
                'projected_headroom': numeric(later_left), 'purchase_ceiling': numeric(limit)}

    candidate_results = []
    for candidate in candidates:
        result = scenario(candidate, ('price', 'fees'), 'weekly_salary')
        comparison = role_comparison(candidate, squad)
        result['comparison'] = comparison
        if comparison['missing_skills']:
            result['warnings'].append('skills_incomplete')
        if comparison['squad_known'] < comparison['squad_total']:
            result['warnings'].append('squad_incomplete')
        candidate_results.append(result)
    return {'horizon_weeks': HORIZON, 'confirmed': confirmed, 'missing_fields': missing, 'warnings': warnings,
            'base': {'weekly_net': numeric(net), 'projected_cash': numeric(projected_cash),
                     'immediate_headroom': numeric(immediate), 'projected_headroom': numeric(projected),
                     'purchase_ceiling': numeric(ceiling(immediate, projected, confirmed))},
            'squad': {'snapshot_id': snapshot_id, 'observed_at': observed_at,
                      'total': len(squad), 'criteria_method': METHOD},
            'candidates': candidate_results,
            'investments': [scenario(item, ('initial_cost',), 'weekly_cost') for item in investments]}


def register_market(app, store, auth, require_team):
    def club(team_id):
        require_club_id(team_id)
        require_team(team_id)

    def document(team_id):
        return store.get('market:'+team_id, {'revision': 0, 'updated_at': None,
                        'plan': Budget().model_dump(), 'candidates': [], 'investments': []})

    def analysis(team_id, doc):
        with store.db() as db:
            row = db.execute('SELECT id,observed_at,payload FROM snapshots WHERE team_id=? AND youth=0 ORDER BY id DESC LIMIT 1',
                             (team_id,)).fetchone()
        squad = json.loads(row['payload']) if row else []
        return analyze_market(doc['plan'], doc['candidates'], doc['investments'], squad,
                              row['observed_at'] if row else None, row['id'] if row else None)

    @app.get('/api/market')
    def get_market(team_id: TeamId = Query(), session=Depends(auth)):
        club(team_id)
        doc = document(team_id)
        return {**doc, 'analysis': analysis(team_id, doc)}

    @app.post('/api/market/analyze')
    def preview_market(body: MarketSave, session=Depends(auth)):
        club(body.team_id)
        return {'analysis': analysis(body.team_id, body.model_dump())}

    @app.post('/api/market')
    def save_market(body: MarketSave, session=Depends(auth)):
        club(body.team_id)
        content = body.model_dump(exclude={'team_id', 'expected_revision'})
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM kv WHERE key=?', ('market:'+body.team_id,)).fetchone()
            revision = json.loads(row['value'])['revision'] if row else 0
            if revision != body.expected_revision:
                raise HTTPException(409, 'Ce projet a changé dans un autre onglet. Rechargez avant de réessayer.')
            doc = {'revision': revision+1, 'updated_at': now(), **content}
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('market:'+body.team_id, pack(doc)))
        return {**doc, 'analysis': analysis(body.team_id, doc)}
