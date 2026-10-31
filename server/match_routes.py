"""Private Classic match previews: fixed upstream, bounded cache, atomic confirmation."""
import json
import secrets
import threading
import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .classic import ClassicClient
from .match_direct import fetch_match, parse_fixture_reference, recent_matches
from .match_review import effective_match, source_digest
from .storage import now, pack
from .team_identity import TeamId


class DirectPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reference: str = Field(min_length=1, max_length=2048)
    type: Literal[0, 1, 2] = 0


class DirectConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_token: str = Field(min_length=20, max_length=100)
    expected_revision: int = Field(ge=0)
    expected_source_digest: str | None = Field(pattern=r'^[a-f0-9]{64}$')


class RecentMatches(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: TeamId


class LegacySync(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[0-9]{1,15}$')
    type: Literal[0, 1, 2] = 0


def _baseline(db, kind, mid):
    row=db.execute('SELECT payload FROM matches WHERE type=? AND id=?',(kind,mid)).fetchone()
    review=db.execute('SELECT value FROM kv WHERE key=?',(f'match_review:{kind}:{mid}',)).fetchone()
    return ((json.loads(review['value']).get('revision',0) if review else 0),
            source_digest(json.loads(row['payload'])) if row else None)


def register_match_direct(app, store, auth, credentials, throttle, require_team, match_model):
    previews={}
    guard=threading.Lock()

    def save(doc, baseline):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if _baseline(db,doc['type'],doc['id']) != baseline:
                raise HTTPException(409,'Ce match ou ses corrections ont changé. Relisez un nouvel aperçu avant de confirmer.')
            db.execute('INSERT OR REPLACE INTO matches VALUES(?,?,?,?)',
                       (doc['id'],doc['type'],pack(doc),now()))
        return {'ok':True,'id':doc['id'],'type':doc['type'],
                'match':effective_match(store,doc,include_review=True)}

    @app.post('/api/matches/recent',dependencies=[Depends(auth)])
    async def recent(body:RecentMatches):
        require_team(body.team_id)
        throttle('recent-matches:'+body.team_id)
        result=await recent_matches(ClassicClient(credentials(body.team_id)),body.team_id)
        with store.db() as db:
            for fixture in result['fixtures']:
                fixture['already_imported']=bool(db.execute('SELECT 1 FROM matches WHERE id=? AND type=?',
                                                (fixture['id'],fixture['type'])).fetchone())
        return result

    @app.post('/api/matches/direct/preview',dependencies=[Depends(auth)])
    async def preview(body:DirectPreview):
        mid=parse_fixture_reference(body.reference,body.type)
        throttle('match-preview:'+str(body.type)+':'+mid)
        with store.db() as db: baseline=_baseline(db,body.type,mid)
        doc=match_model.model_validate(await fetch_match(ClassicClient(credentials()),mid,body.type)).model_dump()
        with store.db() as db:
            if _baseline(db,body.type,mid)!=baseline:
                raise HTTPException(409,'Ce match a changé pendant la lecture. Relancez l’aperçu.')
        token=secrets.token_urlsafe(32)
        payload=pack(doc)
        size=len(payload.encode())
        if size>16_000_000:
            raise HTTPException(413,'Aperçu trop volumineux. Choisissez un autre match.')
        with guard:
            for key in list(previews):
                if previews[key]['expires']<time.monotonic():previews.pop(key)
            own=[key for key,value in previews.items() if value['owner']==str(store.path)]
            while len(own)>=3:previews.pop(own.pop(0))
            # Cache serialized payloads rather than many decoded event graphs.
            # Bound both record count and total UTF-8 bytes for the 512 MB VPS.
            while previews and (len(previews)>=16 or sum(value['size'] for value in previews.values())+size>16_000_000):
                previews.pop(next(iter(previews)))
            previews[token]={'owner':str(store.path),'expires':time.monotonic()+600,'payload':payload,'size':size,'baseline':baseline}
        display=effective_match(store,doc,include_review=True)
        display['event_count']=len(display.pop('events',[]))
        return {'match':display,'source_token':token,'expected_revision':baseline[0],
                'expected_source_digest':baseline[1]}

    @app.post('/api/matches/direct/confirm',dependencies=[Depends(auth)])
    def confirm(body:DirectConfirm):
        with guard:
            entry=previews.get(body.source_token)
            if not entry or entry['owner']!=str(store.path) or entry['expires']<time.monotonic():
                raise HTTPException(409,'Cet aperçu a expiré ou a déjà été utilisé. Relisez le match.')
            if entry['baseline']!=(body.expected_revision,body.expected_source_digest):
                raise HTTPException(409,'L’aperçu ne correspond plus à cette confirmation. Relisez le match.')
            previews.pop(body.source_token)
        return save(json.loads(entry['payload']),entry['baseline'])

    @app.post('/api/matches/sync',dependencies=[Depends(auth)])
    async def sync(body:LegacySync):
        mid=parse_fixture_reference(body.id,body.type)
        throttle('match-sync:'+str(body.type)+':'+mid)
        with store.db() as db:baseline=_baseline(db,body.type,mid)
        doc=match_model.model_validate(await fetch_match(ClassicClient(credentials()),mid,body.type)).model_dump()
        saved=save(doc,baseline)
        return {**saved,'summary':saved['match']['summary']}
