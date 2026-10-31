"""Manager-owned selection coefficients. No official game formula or game action."""
import json
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .storage import now, pack
from .team_identity import TeamId

SKILL_KEYS = ('stamina', 'handling', 'attack', 'defense', 'technique', 'strength', 'jumping', 'speed', 'agility', 'kicking')
_DEFAULT = {
    'Pilier': {'strength': 3, 'technique': 2, 'stamina': 1},
    'Talonneur': {'handling': 2, 'strength': 2, 'technique': 2},
    'Deuxième ligne': {'jumping': 3, 'strength': 2, 'technique': 1},
    'Troisième ligne': {'defense': 2, 'technique': 2, 'stamina': 1, 'strength': 1},
    'Demi de mêlée': {'handling': 3, 'agility': 2, 'kicking': 1},
    'Demi d’ouverture': {'handling': 2, 'kicking': 2, 'attack': 2},
    'Centre': {'attack': 2, 'defense': 2, 'strength': 1, 'speed': 1},
    'Ailier': {'speed': 3, 'agility': 2, 'attack': 1},
    'Arrière': {'kicking': 2, 'speed': 2, 'handling': 2},
}
METHOD = 'weighted-average-v1'
DEFAULT_NAME = 'Profil par défaut'


def default_weights():
    # Preserve the historical summation order even for fractional observations.
    return {role: {skill: weights.get(skill, 0) for skill in (*weights, *(key for key in SKILL_KEYS if key not in weights))}
            for role, weights in _DEFAULT.items()}


def validate_weights(value):
    if not isinstance(value, dict) or set(value) != set(_DEFAULT):
        raise ValueError('Les coefficients doivent décrire les neuf rôles, sans clé supplémentaire.')
    for weights in value.values():
        if (not isinstance(weights, dict) or set(weights) != set(SKILL_KEYS)
                or any(type(weight) is not int or not 0 <= weight <= 10 for weight in weights.values())
                or sum(weights.values()) == 0):
            raise ValueError('Chaque rôle doit avoir dix poids entiers de 0 à 10 et un total strictement positif.')
    # Canonical order, fresh nested dictionaries: inputs cannot mutate a snapshot.
    return {role: {skill: value[role][skill] for skill in weights} for role, weights in default_weights().items()}


def clean_profile_name(value):
    value = value.strip()
    if not value or any(ord(character) < 32 for character in value):
        raise ValueError('Nom de profil invalide.')
    return value


class WeightSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: TeamId
    expected_revision: Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
    id: Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{32}$')] | None = None
    name: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    role_weights: dict

    _weights = field_validator('role_weights', mode='before')(validate_weights)
    _name = field_validator('name')(clean_profile_name)


class WeightDelete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: TeamId
    expected_revision: Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
    id: Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{32}$')]


def register_role_weights(app, store, auth, require_team):
    def document(team_id, db=None):
        key = 'lineup_lab:weights:'+team_id
        if db is None:
            return store.get(key, {'revision': 0, 'profiles': []})
        row = db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else {'revision': 0, 'profiles': []}

    def response(doc):
        return {**doc, 'default': {'name': DEFAULT_NAME, 'method': METHOD, 'role_weights': default_weights()}}

    def write(body, operation):
        require_team(body.team_id)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            doc = document(body.team_id, db)
            if doc['revision'] != body.expected_revision:
                raise HTTPException(409, 'Les profils ont changé dans un autre onglet. Rechargez les profils avant de réessayer.')
            operation(doc)
            doc['revision'] += 1
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('lineup_lab:weights:'+body.team_id, pack(doc)))
        return response(doc)

    @app.get('/api/lineup-lab/weights')
    def profiles(team_id: TeamId = Query(), session=Depends(auth)):
        require_team(team_id)
        return response(document(team_id))

    @app.post('/api/lineup-lab/weights')
    def save(body: WeightSave, session=Depends(auth)):
        def operation(doc):
            existing = next((p for p in doc['profiles'] if p['id'] == body.id), None)
            if body.id and existing is None:
                raise HTTPException(404, 'Profil introuvable dans ce club.')
            if existing is None and len(doc['profiles']) >= 10:
                raise HTTPException(422, 'Dix profils maximum par club ; supprimez un ancien profil.')
            item = {'id': body.id or uuid.uuid4().hex, 'name': body.name, 'method': METHOD,
                    'role_weights': body.role_weights, 'updated_at': now()}
            if existing is None:
                doc['profiles'].append(item)
            else:
                doc['profiles'][doc['profiles'].index(existing)] = item
        return write(body, operation)

    @app.post('/api/lineup-lab/weights/delete')
    def delete(body: WeightDelete, session=Depends(auth)):
        def operation(doc):
            existing = next((p for p in doc['profiles'] if p['id'] == body.id), None)
            if existing is None:
                raise HTTPException(404, 'Profil introuvable dans ce club.')
            doc['profiles'].remove(existing)
        return write(body, operation)
