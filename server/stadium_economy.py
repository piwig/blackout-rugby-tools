"""Private, assumption-based stadium cash-flow comparisons (method v1)."""
import json
import re
from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from typing import Annotated, Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .storage import now, pack
from .team_identity import TeamId, require_club_id

PREFIX = 'stadium_economy:'
CATEGORIES = ('standing', 'uncovered', 'covered', 'members', 'corporate')


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Nombre décimal requis.')
    return value


Money = Annotated[Decimal, BeforeValidator(numeric), Field(ge=0, le=10**12, max_digits=17, decimal_places=4)]
Occupancy = Annotated[Decimal, BeforeValidator(numeric), Field(ge=0, le=100, decimal_places=4)]
Revision = Annotated[int, Field(strict=True, ge=0, le=2147483647)]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Seat(Model):
    capacity: Annotated[int, Field(strict=True, ge=0, le=10_000_000)] | None = None
    price: Money | None = None
    occupancy: Occupancy | None = None
    variable_cost: Money | None = None


class Seats(Model):
    standing: Seat
    uncovered: Seat
    covered: Seat
    members: Seat
    corporate: Seat


class Assumptions(Model):
    seats: Seats
    ancillary_revenue_per_spectator: Money | None = None
    ancillary_cost_per_spectator: Money | None = None
    ancillary_revenue_fixed: Money | None = None
    ancillary_cost_fixed: Money | None = None
    match_fixed_cost: Money | None = None
    weekly_upkeep: Money | None = None
    investment: Money | None = None
    source: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    observed_on: date | None = None


class Scenario(Model):
    id: Annotated[str, Field(strict=True, pattern=r'^[a-zA-Z0-9_-]{1,80}$')]
    name: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    current: Assumptions
    project: Assumptions
    matches: Annotated[int, Field(strict=True, ge=0, le=10000)] | None = None
    weeks: Annotated[int, Field(strict=True, ge=0, le=10000)] | None = None


class Save(Model):
    team_id: TeamId
    context: Literal['club'] = 'club'
    expected_revision: Revision
    scenarios: list[Scenario] = Field(max_length=50)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({s.id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError('Identifiants de scénarios en double.')
        return self


class Calculate(Model):
    team_id: TeamId
    context: Literal['club'] = 'club'
    scenario: Scenario


def money(value):
    return None if value is None else str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def ratio(value):
    return None if value is None else str(value.quantize(Decimal('.0001'), rounding=ROUND_HALF_UP))


def match_values(side, occupancy=None):
    """Keep internal Decimal amounts unrounded until the presentation boundary."""
    missing = []
    attendance = 0
    tickets = Decimal(0)
    variable = Decimal(0)
    for key in CATEGORIES:
        seat = getattr(side.seats, key)
        required = ['capacity'] if seat.capacity == 0 else ['capacity', 'price', 'variable_cost'] + ([] if occupancy is not None else ['occupancy'])
        missing.extend(key+'.'+f for f in required if getattr(seat, f) is None)
        rate = occupancy if occupancy is not None else seat.occupancy
        if seat.capacity == 0:
            continue
        if any(getattr(seat, f) is None for f in required):
            continue
        count = int((Decimal(seat.capacity)*rate/100).to_integral_value(rounding=ROUND_FLOOR))
        attendance += count
        tickets += count*seat.price
        variable += count*seat.variable_cost
    fields = ('ancillary_revenue_per_spectator', 'ancillary_cost_per_spectator',
              'ancillary_revenue_fixed', 'ancillary_cost_fixed', 'match_fixed_cost', 'source', 'observed_on')
    missing.extend(f for f in fields if getattr(side, f) is None)
    if missing:
        return {'attendance': None, 'ticket_revenue': None, 'ancillary_revenue': None,
                'match_costs': None, 'net_match': None, 'missing': missing}
    ancillary = attendance*side.ancillary_revenue_per_spectator+side.ancillary_revenue_fixed
    costs = variable+attendance*side.ancillary_cost_per_spectator+side.ancillary_cost_fixed+side.match_fixed_cost
    return {'attendance': attendance, 'ticket_revenue': tickets, 'ancillary_revenue': ancillary,
            'match_costs': costs, 'net_match': tickets+ancillary-costs, 'missing': []}


def projected(side, scenario, occupancy=None):
    raw = match_values(side, occupancy)
    missing = list(raw['missing'])
    missing.extend(f for f in ('matches','weeks') if getattr(scenario, f) is None)
    if side.weekly_upkeep is None:
        missing.append('weekly_upkeep')
    projection = None if missing else raw['net_match']*scenario.matches-side.weekly_upkeep*scenario.weeks
    return {**raw, 'net_projection': projection, 'projection_missing': missing,
            'cash_after_investment': None if projection is None or side.investment is None else projection-side.investment}


def public_values(raw):
    return {k: money(v) if isinstance(v, Decimal) else v for k, v in raw.items()}


def side_report(side, scenario):
    threshold = None
    reason = 'missing'
    if not match_values(side, Decimal(0))['missing']:
        reason = 'unreachable'
        # Exhaustive bounded grid handles integer entry steps even with negative margins.
        for point in range(10001):
            rate = Decimal(point)/100
            if match_values(side, rate)['net_match'] >= 0:
                threshold, reason = str(rate.quantize(Decimal('.01'))), 'found'
                break
    return {'custom': public_values(projected(side, scenario)),
            'occupancies': [{'occupancy': rate, **public_values(projected(side, scenario, Decimal(rate)))} for rate in range(50,101,10)],
            'break_even_occupancy': threshold, 'break_even_reason': reason}


def compare(scenario):
    # Declared bounds can yield a 30-digit ROI (tiny investment, large horizon).
    # Keep both the calculation and its final quantization in a sufficient context.
    with localcontext() as context:
        context.prec = 60
        return _compare(scenario)


def _compare(scenario):
    baseline = projected(scenario.current, scenario)
    project = projected(scenario.project, scenario)
    extra = None if baseline['net_projection'] is None or project['net_projection'] is None else project['net_projection']-baseline['net_projection']
    investment = None if scenario.current.investment is None or scenario.project.investment is None else scenario.project.investment-scenario.current.investment
    # Horizon-average match gain includes the explicit weekly delta once.
    gain = extra/Decimal(scenario.matches) if extra is not None and scenario.matches else None
    recovery = None if gain is None or gain <= 0 or investment is None else max(Decimal(0),investment)/gain
    roi = (extra-investment)/investment*100 if extra is not None and extra > 0 and investment is not None and investment > 0 else None
    return {'method': 'stadium-economy-v1', 'current': side_report(scenario.current, scenario),
            'project': side_report(scenario.project, scenario),
            'incremental': {'net_projection': money(extra), 'investment': money(investment),
                            'gain_per_match': money(gain), 'payback_matches': ratio(recovery), 'roi_percent': ratio(roi)}}


def read_document(db, team_id):
    row = db.execute('SELECT value FROM kv WHERE key=?', (PREFIX+team_id,)).fetchone()
    return json.loads(row['value']) if row else {'team_id':team_id, 'revision':0, 'scenarios':[], 'updated_at':None}


def initial_current(team):
    """Only explicitly sourced, dated capacity metadata is eligible for initialization."""
    try:
        meta = json.loads(team['meta'])
        source = meta.get('stadium_source')
        observed = date.fromisoformat(meta.get('stadium_observed_on',''))
        if not isinstance(source, str) or not source.strip():
            return None
        def capacity(key):
            value = meta.get('stadium_'+key)
            # Classic serializes integer capacities as strings. Conversion is
            # lossless; decimals, booleans and out-of-range values still fail.
            return int(value) if isinstance(value,str) and re.fullmatch(r'[0-9]{1,8}',value) else value
        seats = {key:{'capacity': capacity(key)} for key in CATEGORIES}
        return Assumptions(seats=seats, source=source, observed_on=observed).model_dump(mode='json')
    except (ValueError, TypeError):
        return None


def register_stadium_economy(app, store, auth, require_team):
    def checked(team_id):
        require_club_id(team_id)
        return require_team(team_id)

    @app.get('/api/stadium-economy', dependencies=[Depends(auth)])
    @app.get('/api/stadium-economy/export', dependencies=[Depends(auth)])
    def load(team_id: TeamId, context: Literal['club'] = 'club'):
        team = checked(team_id)
        with store.db() as db:
            return {**read_document(db,team_id), 'method':'stadium-economy-v1', 'initial_current':initial_current(team)}

    @app.post('/api/stadium-economy', dependencies=[Depends(auth)])
    def save(body: Save):
        checked(body.team_id)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # The team may have been removed while waiting for this write lock.
            team = db.execute('SELECT meta FROM teams WHERE id=?',(body.team_id,)).fetchone()
            if not team:
                raise HTTPException(404,'Club introuvable.')
            document = read_document(db,body.team_id)
            if document['revision'] != body.expected_revision:
                raise HTTPException(409,'Le scénario a changé. Rechargez les données avant de réessayer ; votre brouillon est conservé.')
            document.update(revision=document['revision']+1, updated_at=now(),
                            scenarios=[s.model_dump(mode='json') for s in body.scenarios])
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(PREFIX+body.team_id,pack(document)))
        return {**document, 'method':'stadium-economy-v1', 'initial_current':initial_current(team)}

    @app.post('/api/stadium-economy/calculate', dependencies=[Depends(auth)])
    def calculate(body: Calculate):
        checked(body.team_id)
        return {'team_id':body.team_id, **compare(body.scenario)}
