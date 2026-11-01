"""Private match observations; Classic coaching aggregates are not player ratings.

CSV columns are the Observation fields below. Blank rating/minutes are unknown.
Identity = team namespace + context + match + player + observed position + scale.
A scale name declares a method and bounds, never an implicit conversion.
"""
import asyncio
import csv
import hashlib
import io
import json
import time
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .classic import ClassicClient, ClassicError
from .performance_classic import read_match_observations
from .storage import now, pack
from .team_identity import TeamId

PREFIX = 'player_performance:'
LEDGER = PREFIX + 'observations'
MAX_ROWS = 5000
Revision = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=160)]
Identifier = Annotated[str, Field(strict=True, pattern=r'^[1-9][0-9]{0,14}$')]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Observation(Model):
    team_id: TeamId
    context: Literal['club', 'youth', 'u20', 'nt']
    match_id: Annotated[str, Field(strict=True, pattern=r'^[a-zA-Z0-9_.:-]{1,80}$')]
    match_date: Annotated[str, Field(strict=True, pattern=r'^\d{4}-\d{2}-\d{2}$')]
    competition: Text
    opponent: Text
    venue: Literal['home', 'away', 'neutral', 'unknown']
    player_id: Identifier
    player_name: Text
    position: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    position_basis: Literal['observed', 'report_start', 'report_bench_unknown'] = 'observed'
    rating: Annotated[float, Field(strict=True, ge=-1000, le=1000)] | None = None
    rating_scale: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    scale_min: Annotated[float, Field(strict=True, ge=-1000, le=1000)] | None
    scale_max: Annotated[float, Field(strict=True, ge=-1000, le=1000)] | None
    minutes: Annotated[float, Field(strict=True, ge=0, le=240)] | None = None
    source: Annotated[str, Field(strict=True, min_length=1, max_length=500)]

    @field_validator('match_date')
    @classmethod
    def calendar_date(cls, value):
        parsed = date.fromisoformat(value)
        if not 2000 <= parsed.year <= 2100:
            raise ValueError('Date hors limites.')
        return value

    @model_validator(mode='after')
    def consistent(self):
        kind = self.team_id.split(':')[0] if ':' in self.team_id else 'club'
        if self.context not in (('club', 'youth') if kind == 'club' else (kind,)):
            raise ValueError('Contexte incompatible avec le type d’équipe.')
        if (self.scale_min is None) != (self.scale_max is None):
            raise ValueError('Les deux bornes doivent être connues ou inconnues ensemble.')
        if self.scale_min is not None and (self.scale_min >= self.scale_max or (self.rating is not None and not self.scale_min <= self.rating <= self.scale_max)):
            raise ValueError('Note ou bornes incompatibles avec l’échelle déclarée.')
        return self


class Preview(Model):
    format: Literal['csv', 'json']
    content: str = Field(min_length=1, max_length=1_000_000)
    mode: Literal['append', 'replace'] = 'append'
    expected_revision: Revision


class ClassicPreview(Model):
    team_id: TeamId
    context: Literal['club', 'youth', 'u20', 'nt']
    fixture_id: Identifier
    expected_revision: Revision
    mode: Literal['append', 'replace'] = 'append'


class Confirm(Model):
    preview_id: Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
    expected_revision: Revision


class Delete(Model):
    ids: list[Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]] = Field(min_length=1, max_length=500)
    expected_revision: Revision


def read_ledger(db):
    row = db.execute('SELECT value FROM kv WHERE key=?', (LEDGER,)).fetchone()
    return json.loads(row['value']) if row else {'revision': 0, 'observations': [], 'updated_at': None}


def identity(row):
    return tuple(row[k] for k in ('team_id', 'context', 'match_id', 'player_id', 'position', 'rating_scale', 'position_basis'))


def observation_id(row):
    return hashlib.sha256(pack(identity(row)).encode()).hexdigest()


def clean_row(row):
    return {key: row.get(key, 'observed') if key == 'position_basis' else row[key] for key in Observation.model_fields}


def parse_content(body):
    try:
        if len(body.content.encode('utf-8')) > 1_000_000:
            raise ValueError('Texte UTF-8 limité à 1 Mo.')
        if body.format == 'json':
            rows = json.loads(body.content)
            if not isinstance(rows, list):
                raise ValueError('Le JSON doit être une liste d’observations.')
        else:
            reader = csv.DictReader(io.StringIO(body.content.lstrip('\ufeff')))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or (set(reader.fieldnames) - set(Observation.model_fields) or set(Observation.model_fields) - {'position_basis'} - set(reader.fieldnames)):
                raise ValueError('Colonnes CSV incorrectes. Utilisez le modèle proposé.')
            rows = []
            for row in reader:
                if len(rows) >= 500:
                    raise ValueError('Import limité à 500 observations.')
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('Ligne CSV incomplète.')
                for key in ('rating', 'scale_min', 'scale_max', 'minutes'):
                    row[key] = float(row[key]) if row[key].strip() else None
                rows.append(row)
        if not 1 <= len(rows) <= 500:
            raise ValueError('Import limité à 1–500 observations.')
        return [Observation.model_validate(row).model_dump() for row in rows]
    except (ValueError, TypeError, UnicodeError, RecursionError, csv.Error, ValidationError):
        raise HTTPException(422, 'Observations invalides : vérifiez le modèle, les dates, les identifiants, les notes et les bornes ; 500 lignes maximum.') from None


def merge(existing, incoming, mode):
    rows = {identity(row): row for row in existing}
    added = replaced = duplicates = 0
    seen = {}
    for row in incoming:
        key = identity(row)
        if key in seen and seen[key] != row:
            raise HTTPException(422, 'Deux lignes contradictoires visent la même observation.')
        seen[key] = row
        previous = rows.get(key)
        if previous and clean_row(previous) == row:
            duplicates += 1
            continue
        if previous:
            if mode != 'replace':
                raise HTTPException(409, 'Une observation existe déjà avec des valeurs différentes. Choisissez le remplacement explicite.')
            replaced += 1
        else:
            added += 1
        rows[key] = {**row, 'id': observation_id(row), 'imported_at': previous['imported_at'] if previous else now(), 'updated_at': now()}
    if len(rows) > MAX_ROWS:
        raise HTTPException(422, 'Bibliothèque limitée à 5 000 observations. Exportez puis supprimez des observations avant de poursuivre.')
    matches, scales = {}, {}
    for row in rows.values():
        match_key = tuple(row[k] for k in ('team_id', 'context', 'match_id'))
        match_value = tuple(row[k] for k in ('match_date', 'competition', 'opponent', 'venue'))
        if match_key in matches and matches[match_key] != match_value:
            raise HTTPException(422, 'Le même match possède des dates ou contextes contradictoires. Corrigez toutes ses observations ensemble.')
        matches[match_key] = match_value
        bounds = (row['scale_min'], row['scale_max'])
        if row['rating_scale'] in scales and scales[row['rating_scale']] != bounds:
            raise HTTPException(422, 'Une échelle de notes possède des bornes contradictoires. Donnez un nom distinct à chaque méthode.')
        scales[row['rating_scale']] = bounds
    return list(rows.values()), {'added': added, 'replaced': replaced, 'duplicates': duplicates}


def summarize(rows):
    buckets = {}
    for row in rows:
        key = tuple(row[k] for k in ('team_id', 'context', 'player_id', 'position', 'rating_scale', 'position_basis'))
        buckets.setdefault(key, []).append(row)
    groups = []
    for key, values in buckets.items():
        rated = [r['rating'] for r in values if r['rating'] is not None]
        minutes = [r['minutes'] for r in values if r['minutes'] is not None]
        matches = len({r['match_id'] for r in values})
        groups.append({**dict(zip(('team_id', 'context', 'player_id', 'position', 'rating_scale', 'position_basis'), key)),
                       'player_name': values[-1]['player_name'], 'scale_min': values[0]['scale_min'], 'scale_max': values[0]['scale_max'],
                       'matches': matches, 'observations': len(values), 'rated': len(rated), 'missing_ratings': len(values)-len(rated),
                       'mean': round(sum(rated)/len(rated), 4) if rated else None,
                       'min': min(rated) if rated else None, 'max': max(rated) if rated else None,
                       'known_minutes': sum(minutes) if minutes else None, 'minutes_observations': len(minutes),
                       'missing_minutes': len(values)-len(minutes), 'small_sample': len(rated) < 5,
                       'first_match': min(r['match_date'] for r in values), 'last_match': max(r['match_date'] for r in values)})
    return sorted(groups, key=lambda g: (g['team_id'], g['context'], g['position'], g['rating_scale'], g['player_name'], g['player_id']))


def checked_revision(document, expected):
    if document['revision'] != expected:
        raise HTTPException(409, 'Ces observations ont changé. Rechargez et préparez un nouvel aperçu.')


def save_ledger(db, revision, observations):
    document = {'revision': revision + 1, 'observations': observations, 'updated_at': now()}
    db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', (LEDGER, pack(document)))
    return document


def export_player_performance(store):
    with store.db() as db:
        document = read_ledger(db)
    return {**document, 'observations': [clean_row(row) for row in document['observations']]}


def register_player_performance(app, store, auth, require_team, classic_credentials=None, throttle=None):
    def binding_for(db, team_id):
        if classic_credentials is None:
            raise HTTPException(422, 'Lecture Classic indisponible dans cette installation.')
        team = db.execute('SELECT meta FROM teams WHERE id=?', (team_id,)).fetchone()
        if not team:
            raise HTTPException(404, 'Équipe détachée depuis l’aperçu.')
        account = db.execute("SELECT value FROM kv WHERE key='classic_account'").fetchone()
        # Keep a one-way digest only; keys and full account metadata never leave
        # the server and are never copied into preview/export records.
        values = {'credentials': classic_credentials(team_id), 'team': team['meta'],
                  'account': account['value'] if account else None}
        return hashlib.sha256(pack(values).encode()).hexdigest()

    @app.get('/api/player-performance', dependencies=[Depends(auth)])
    def report(team_id: str = Query('', max_length=20), context: Literal['', 'club', 'youth', 'u20', 'nt'] = '',
               position: str = Query('', max_length=80), rating_scale: str = Query('', max_length=80),
               competition: str = Query('', max_length=160), opponent: str = Query('', max_length=160),
               venue: Literal['', 'home', 'away', 'neutral', 'unknown'] = '',
               start: date | None = None, end: date | None = None,
               offset: int = Query(0, ge=0, le=5000), limit: int = Query(50, ge=1, le=100)):
        if start and end and start > end:
            raise HTTPException(422, 'La fin doit suivre le début de la période.')
        if team_id:
            require_team(team_id)
        with store.db() as db:
            document = read_ledger(db)
        rows = document['observations']
        filters = {'team_id': team_id, 'context': context, 'position': position, 'rating_scale': rating_scale,
                   'competition': competition, 'opponent': opponent, 'venue': venue}
        options = {key: sorted({r[key] for r in rows}) for key in filters}
        selected = [row for row in rows if all(not value or row[key] == value for key, value in filters.items())
                    and (start is None or row['match_date'] >= start.isoformat()) and (end is None or row['match_date'] <= end.isoformat())]
        selected.sort(key=lambda r: (r['match_date'], r['id']), reverse=True)
        return {'revision': document['revision'], 'updated_at': document['updated_at'], 'total': len(selected), 'total_stored': len(rows),
                'observations': selected[offset:offset+limit], 'groups': summarize(selected), 'options': options, 'limit': limit, 'offset': offset}

    @app.get('/api/player-performance/export', dependencies=[Depends(auth)])
    def export():
        return export_player_performance(store)

    @app.get('/api/player-performance/template', dependencies=[Depends(auth)])
    def template(team_id: TeamId):
        require_team(team_id)
        context = team_id.split(':')[0] if ':' in team_id else 'club'
        sample = Observation(team_id=team_id, context=context, match_id='example-1', match_date=date.today().isoformat(),
                             competition='Example competition', opponent='Example opponent', venue='unknown', player_id='42',
                             player_name='Example player', position='Centre', rating_scale='manual-observer-0-10-v1',
                             scale_min=0, scale_max=10, source='Example notebook: replace with your real source').model_dump()
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=Observation.model_fields)
        writer.writeheader(); writer.writerow(sample)
        return {'filename': 'player-performance-template.csv', 'content': buffer.getvalue(), 'sample_only': True}

    def create_preview(incoming, mode, revision, classic_binding=None, warnings=None):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            document = read_ledger(db)
            checked_revision(document, revision)
            if classic_binding and binding_for(db, classic_binding['team_id']) != classic_binding['fingerprint']:
                raise HTTPException(409, 'Le compte Classic ou l’équipe a changé. Préparez un nouvel aperçu.')
            _, counts = merge(document['observations'], incoming, mode)
            # Private, bounded, single-use previews. Only confirmed rows reach export.
            previews = db.execute('SELECT key,value FROM kv WHERE key GLOB ?', (PREFIX+'preview:*',)).fetchall()
            valid = []
            for row in previews:
                if json.loads(row['value'])['expires_at'] <= time.time():
                    db.execute('DELETE FROM kv WHERE key=?', (row['key'],))
                else:
                    valid.append(row['key'])
            for key in valid[:-9]:
                db.execute('DELETE FROM kv WHERE key=?', (key,))
            token = uuid.uuid4().hex
            expires = time.time()+900
            db.execute('INSERT INTO kv VALUES(?,?)', (PREFIX+'preview:'+token, pack({
                'revision': document['revision'], 'mode': mode, 'observations': incoming, 'expires_at': expires, 'consumed': False, 'classic_binding': classic_binding})))
        return {'preview_id': token, 'revision': document['revision'], 'mode': mode, 'expires_at': expires,
                'observations': incoming, 'warnings': warnings or [], **counts}

    @app.post('/api/player-performance/preview', dependencies=[Depends(auth)])
    def preview(body: Preview):
        incoming = parse_content(body)
        for tid in {r['team_id'] for r in incoming}:
            require_team(tid)
        return create_preview(incoming, body.mode, body.expected_revision)

    @app.post('/api/player-performance/classic-preview', dependencies=[Depends(auth)])
    async def classic_preview(body: ClassicPreview):
        require_team(body.team_id)
        with store.db() as db:
            checked_revision(read_ledger(db), body.expected_revision)
            fingerprint = binding_for(db, body.team_id)
            snapshot = db.execute('SELECT payload FROM snapshots WHERE team_id=? AND youth=? ORDER BY id DESC LIMIT 1',
                                  (body.team_id, int(body.context == 'youth'))).fetchone()
            names = {str(p['id']): p['name'] for p in json.loads(snapshot['payload'])
                     if isinstance(p, dict) and p.get('id') and isinstance(p.get('name'), str)} if snapshot else {}
        if throttle:
            throttle('player-performance:' + body.team_id)
        client = ClassicClient({key: value for key, value in classic_credentials(body.team_id).items() if key in ('d', 'dk', 'm', 'mk')})
        try:
            result = await asyncio.wait_for(read_match_observations(client, body.team_id, body.context, body.fixture_id, names=names), 120)
            incoming = [Observation.model_validate(row).model_dump() for row in result['observations']]
        except (ClassicError, ValidationError, ValueError, TimeoutError):
            raise HTTPException(422, 'Lecture des observations Classic indisponible ou incohérente. Les observations conservées restent inchangées.') from None
        return create_preview(incoming, body.mode, body.expected_revision,
                              {'team_id': body.team_id, 'fingerprint': fingerprint}, result['warnings'])

    @app.post('/api/player-performance/confirm', dependencies=[Depends(auth)])
    def confirm(body: Confirm):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            key = PREFIX+'preview:'+body.preview_id
            raw = db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
            if not raw:
                raise HTTPException(404, 'Aperçu introuvable dans ce compte.')
            preview = json.loads(raw['value'])
            if preview['consumed'] or preview['expires_at'] <= time.time():
                raise HTTPException(409, 'Aperçu expiré ou déjà confirmé. Préparez un nouvel aperçu.')
            document = read_ledger(db)
            checked_revision(document, body.expected_revision)
            checked_revision(preview, body.expected_revision)
            binding = preview.get('classic_binding')
            if binding and binding_for(db, binding['team_id']) != binding['fingerprint']:
                raise HTTPException(409, 'Le compte Classic ou l’équipe a changé. Préparez un nouvel aperçu.')
            # Recheck current team attachment inside the same write lock.
            for tid in {r['team_id'] for r in preview['observations']}:
                if not db.execute('SELECT 1 FROM teams WHERE id=?', (tid,)).fetchone():
                    raise HTTPException(404, 'Équipe détachée depuis l’aperçu.')
            observations, counts = merge(document['observations'], preview['observations'], preview['mode'])
            if counts['added'] or counts['replaced']:
                document = save_ledger(db, document['revision'], observations)
            preview['consumed'] = True
            db.execute('UPDATE kv SET value=? WHERE key=?', (pack(preview), key))
        return {'revision': document['revision'], 'total': len(document['observations']), **counts}

    @app.post('/api/player-performance/delete', dependencies=[Depends(auth)])
    def delete(body: Delete):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            document = read_ledger(db)
            checked_revision(document, body.expected_revision)
            ids = set(body.ids)
            known = {r['id'] for r in document['observations']}
            if len(ids) != len(body.ids) or not ids <= known:
                raise HTTPException(422, 'Observations inconnues ou dupliquées.')
            document = save_ledger(db, document['revision'], [r for r in document['observations'] if r['id'] not in ids])
        return {'revision': document['revision'], 'total': len(document['observations']), 'deleted': len(ids)}
