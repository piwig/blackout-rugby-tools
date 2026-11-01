"""Private, revisioned manager identity and display preferences."""
import json
import unicodedata
from typing import Annotated, Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .storage import now, pack


PROFILE_KEY = 'profile:preferences'
DashboardSection = Literal['priorities', 'metrics', 'progress', 'talents', 'actions', 'gallery']
DASHBOARD_SECTIONS = ('priorities', 'metrics', 'progress', 'talents', 'actions', 'gallery')


class StrictProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProfilePreferences(StrictProfile):
    language: Literal['fr', 'en', 'es', 'it'] = 'fr'
    display_name: str = Field(default='', max_length=60)
    initials: str = Field(default='BRT', pattern=r'^[A-Z0-9À-ÖØ-Þ]{1,3}$')
    jersey_number: int = Field(default=15, strict=True, ge=0, le=99)
    avatar_style: Literal['jersey', 'shield', 'trophy', 'rugby'] = 'jersey'
    favorite_club: Literal['none', 'toulouse', 'larochelle', 'leinster', 'racing92',
                           'toulon', 'clermont', 'munster', 'crusaders'] = 'none'
    density: Literal['comfortable', 'compact'] = 'comfortable'
    text_size: Literal['normal', 'large'] = 'normal'
    motion: Literal['system', 'reduced'] = 'system'
    start_page: Literal['home', 'progression', 'academy', 'squad', 'coaching', 'season'] = 'home'
    banner: Literal['matchday', 'clubhouse'] = 'matchday'
    dashboard_sections: list[DashboardSection] = Field(
        default_factory=lambda: list(DASHBOARD_SECTIONS), max_length=6)

    @field_validator('display_name', 'initials', mode='before')
    @classmethod
    def plain_text(cls, value):
        if isinstance(value, str):
            value = unicodedata.normalize('NFC', value)
            if any(unicodedata.category(char).startswith('C') or char in '<>' for char in value):
                raise ValueError('Utilisez du texte simple, sans balise ni caractère de contrôle.')
            return value.strip()
        return value

    @field_validator('initials', mode='before')
    @classmethod
    def uppercase_initials(cls, value):
        return value.upper() if isinstance(value, str) else value

    @field_validator('dashboard_sections')
    @classmethod
    def unique_sections(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Chaque rubrique d’accueil doit apparaître une seule fois.')
        return value


class ProfileSave(StrictProfile):
    expected_revision: Annotated[int, Field(strict=True, ge=0, le=2147483647)]
    profile: ProfilePreferences


def get_profile(store):
    """Read only this manager's profile; callers supply the authenticated store."""
    defaults = ProfilePreferences().model_dump()
    document = store.get(PROFILE_KEY, {'revision': 0, 'profile': {}, 'updated_at': None})
    # Merge new preferences into older saved documents without changing revision.
    return {**document, 'profile': {**defaults, **document.get('profile', {})}}


def register_profile(app, store, auth):
    @app.get('/api/profile')
    def read_profile(session=Depends(auth)):
        return get_profile(store)

    @app.post('/api/profile')
    def save_profile(body: ProfileSave, session=Depends(auth)):
        # The shared proxy resolves to the authenticated manager's private store.
        # A write lock makes revision comparison atomic across tabs and workers.
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM kv WHERE key=?', (PROFILE_KEY,)).fetchone()
            previous = json.loads(row['value']) if row else {'revision': 0}
            if previous['revision'] != body.expected_revision:
                raise HTTPException(409, 'Votre profil a changé dans un autre onglet. '
                                    'Votre brouillon est conservé ; rechargez la version enregistrée pour comparer.')
            document = {'revision': body.expected_revision + 1,
                        'profile': body.profile.model_dump(), 'updated_at': now()}
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', (PROFILE_KEY, pack(document)))
        return document
