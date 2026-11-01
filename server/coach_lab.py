"""Private Staff & tactics documents, transactional previews and local application."""
import hashlib
import json
import time
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .coach_engine import ATTRIBUTES, calculate, defaults
from .player_performance import read_ledger
from .storage import now, pack
from .team_identity import TeamId

Revision = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
PlayerId = Annotated[str, Field(strict=True, pattern=r'^[0-9]{1,15}$')]
Shirt = Annotated[str, Field(pattern=r'^(?:[1-9]|1[0-5])$')]
Slot = Annotated[str, Field(pattern=r'^(?:[1-9]|1[0-9]|2[0-3])$')]
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]
Cohort = Literal['club', 'youth', 'u20', 'nt']


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Reference(Model):
    min: Annotated[float, Field(strict=True, ge=-1000, le=1000)]
    max: Annotated[float, Field(strict=True, ge=-1000, le=1000)]
    direction: Literal['higher', 'lower']

    @model_validator(mode='after')
    def ordered(self):
        if self.min >= self.max:
            raise ValueError('Les bornes doivent être strictement croissantes.')
        return self


class Conditions(Model):
    weather: Literal['unknown', 'dry', 'wet'] = 'unknown'
    wind: Literal['unknown', 'calm', 'strong'] = 'unknown'


class Opponent(Model):
    name: str = Field(min_length=1, max_length=100)
    observed_at: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    source: str = Field(min_length=1, max_length=500)
    exposure: Literal['driving', 'pickandgo', 'expansive', 'creative']

    @field_validator('observed_at')
    @classmethod
    def valid_date(cls,value):
        parsed=date.fromisoformat(value)
        if not 2000 <= parsed.year <= 2100:raise ValueError('Date hors limites.')
        return value


class Config(Model):
    weights: dict[str, dict[str, Annotated[float, Field(strict=True, ge=0, le=10)]]]
    references: dict[str, Reference]
    energy_scale: Literal['percent', 'level']
    energy_floor: Annotated[int, Field(strict=True, ge=0, le=110)]
    energy_penalty: Percent
    mode: Literal['skills', 'mean', 'best', 'hybrid']
    rating_scale: str = Field(max_length=80)
    position_scope: Literal['exact', 'role']
    position_basis: Literal['observed', 'report_start']
    minimum_notes: Annotated[int, Field(strict=True, ge=1, le=100)]
    skill_share: Percent
    locks: dict[Shirt, PlayerId] = Field(max_length=15)
    excluded_ids: list[PlayerId] = Field(max_length=500)
    objective: Literal['balanced', 'recovery', 'development']
    conditions: Conditions
    opponent: Opponent | None

    @model_validator(mode='after')
    def coherent(self):
        if set(self.weights) != {*(str(i) for i in range(1,16)), 'captain', 'kicker'} or set(self.references)!=set(ATTRIBUTES):
            raise ValueError('Chaque maillot et responsable nécessite les attributs et références complets.')
        if any(set(weights)!=set(ATTRIBUTES) or not sum(weights.values()) for weights in self.weights.values()):
            raise ValueError('Chaque rôle nécessite les attributs complets et un poids positif.')
        if self.position_scope=='exact' and self.position_basis=='report_start':
            raise ValueError('Le rapport de départ décrit un rôle large, pas un maillot exact.')
        if self.mode!='skills' and not self.rating_scale:
            raise ValueError('Choisissez une échelle de performances.')
        if len(set(self.excluded_ids))!=len(self.excluded_ids):
            raise ValueError('Exclusions en double.')
        return self


class Tactics(Model):
    attacks: dict[Literal['driving','pickandgo','expansive','creative'], Percent]
    kick_frequency: Percent
    kick_types: dict[Literal['touch','territory','contestable'], Percent]
    defense: Literal['drift','man','rush']
    intensity: Percent
    discipline: Literal['cautious','balanced','aggressive']

    @model_validator(mode='after')
    def totals(self):
        if set(self.attacks)!={'driving','pickandgo','expansive','creative'} or sum(self.attacks.values())!=100 or set(self.kick_types)!={'touch','territory','contestable'} or sum(self.kick_types.values())!=100:
            raise ValueError('Les quatre attaques et les trois types de pied doivent chacun totaliser 100 %.')
        return self


class Preview(Model):
    team_id: TeamId
    cohort: Cohort
    expected_revision: Revision
    config: Config
    manual_slots: dict[Slot, PlayerId] | None = Field(default=None, max_length=23)
    captain: PlayerId | None = None
    kicker: PlayerId | None = None
    tactics: Tactics | None = None


class Confirm(Model):
    team_id: TeamId
    cohort: Cohort
    preview_id: Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
    apply_local: bool = Field(strict=True, default=False)


def read(db, key, fallback):
    row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
    return json.loads(row['value']) if row else fallback


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def register_coach_lab(app, store, auth, require_team, state):
    def authorize(team_id, cohort):
        require_team(team_id)
        kind=team_id.split(':')[0] if ':' in team_id else 'club'
        if cohort not in (('club','youth') if kind=='club' else (kind,)):
            raise HTTPException(422,'Contexte incompatible avec le type d’équipe.')

    def key(team_id,cohort):return f'coach_lab:{team_id}:{cohort}'

    def document(db,team_id,cohort):
        return read(db,key(team_id,cohort),{'revision':0,'config':defaults(),'sheet':None,'updated_at':None})

    def sources(db,team_id,cohort,session):
        snapshot=state(team_id,session)
        roster_key='academy' if cohort=='youth' else 'squad'
        roster=snapshot.get(roster_key,[])
        source=snapshot.get(roster_key+'_source')
        lineup_key=f'coach_lineup:{team_id}:youth' if cohort=='youth' else 'lineup:'+team_id
        slots=read(db,lineup_key,{})
        ledger=read_ledger(db)
        fingerprint={'roster':digest({'players':roster,'source':source}), 'lineup':digest(slots),'performance_revision':ledger['revision']}
        return roster,source,lineup_key,ledger,fingerprint

    @app.get('/api/coach-lab')
    def get_document(team_id:TeamId=Query(),cohort:Cohort=Query(),session=Depends(auth)):
        authorize(team_id,cohort)
        with store.db() as db:
            doc=document(db,team_id,cohort)
            ledger=read_ledger(db)
        rows=[r for r in ledger['observations'] if r['team_id']==team_id and r['context']==cohort]
        scales={r['rating_scale']:{'name':r['rating_scale'],'min':r['scale_min'],'max':r['scale_max']} for r in rows}
        return {**doc,'scales':list(scales.values()),'performance_revision':ledger['revision']}

    @app.post('/api/coach-lab/preview')
    def prepare(body:Preview,session=Depends(auth)):
        authorize(body.team_id,body.cohort)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            doc=document(db,body.team_id,body.cohort)
            if doc['revision']!=body.expected_revision:
                raise HTTPException(409,'La feuille a changé. Rechargez avant de préparer un nouvel aperçu.')
            roster,source,_,ledger,fingerprint=sources(db,body.team_id,body.cohort,session)
            config=body.config.model_dump()
            try:
                result=calculate(roster,ledger['observations'],config,body.team_id,body.cohort,now(),manual=body.manual_slots,captain=body.captain,kicker=body.kicker,tactics=body.tactics.model_dump() if body.tactics else None)
            except ValueError as error:
                raise HTTPException(422,str(error)) from error
            result['source']=source
            result['performance_revision']=ledger['revision']
            result['team_id']=body.team_id;result['cohort']=body.cohort
            token=uuid.uuid4().hex
            # Bounded transient store, isolated by the request's PrivateStore.
            previews=db.execute("SELECT key,value FROM kv WHERE key LIKE 'coach_preview:%' ORDER BY rowid DESC").fetchall()
            for index,row in enumerate(previews):
                if index>=19 or json.loads(row['value']).get('expires',0)<time.time():db.execute('DELETE FROM kv WHERE key=?',(row['key'],))
            stored={'team_id':body.team_id,'cohort':body.cohort,'session':digest(session['csrf']),
                    'revision':doc['revision'],'fingerprint':fingerprint,'expires':time.time()+900,'config':config,'sheet':result}
            db.execute('INSERT INTO kv VALUES(?,?)',('coach_preview:'+token,pack(stored)))
        return {'preview_id':token,'revision':doc['revision'],'sheet':result,'expires_in':900}

    @app.post('/api/coach-lab/confirm')
    def confirm(body:Confirm,session=Depends(auth)):
        authorize(body.team_id,body.cohort)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            preview=read(db,'coach_preview:'+body.preview_id,None)
            if not preview or preview['team_id']!=body.team_id or preview['cohort']!=body.cohort or preview['session']!=digest(session['csrf']) or preview['expires']<time.time():
                raise HTTPException(409,'Aperçu expiré ou incompatible. Préparez un nouvel aperçu.')
            doc=document(db,body.team_id,body.cohort)
            _,_,lineup_key,_,fingerprint=sources(db,body.team_id,body.cohort,session)
            if doc['revision']!=preview['revision'] or fingerprint!=preview['fingerprint']:
                raise HTTPException(409,'Les données ont changé : feuille, effectif, XV local ou performances. Préparez un nouvel aperçu.')
            if body.apply_local and not preview['sheet']['slots']:
                raise HTTPException(422,'Aucun joueur à appliquer. Enregistrez seulement les critères ou corrigez la feuille.')
            saved={'revision':doc['revision']+1,'config':preview['config'],'sheet':preview['sheet'],'updated_at':now()}
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key(body.team_id,body.cohort),pack(saved)))
            if body.apply_local:
                db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(lineup_key,pack(preview['sheet']['slots'])))
            db.execute('DELETE FROM kv WHERE key=?',('coach_preview:'+body.preview_id,))
        return saved
