"""Owner-bound, expiring, explicit roster imports. Never sends writes to Classic."""
import io
import hashlib
import json
import secrets
import threading
import time
import zipfile
from datetime import date, datetime, timezone
from typing import Literal

from defusedxml import ElementTree as ET
from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .classic import ClassicClient, ClassicError
from .imports import parse_import
from .national import authenticated_member, manager_credentials, prepare_selection, selection_game_date, selection_ids
from .team_identity import TeamId, is_selection, team_identity
from .storage import pack

TTL_SECONDS = 15 * 60
MAX_PREVIEWS = 128
MAX_CACHE_BYTES = 32_000_000
MAX_CONCURRENT_ANALYSES = 4


class Mapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = Field(min_length=1, max_length=10)
    team_id: TeamId | None = None
    cohort: Literal['seniors', 'academy', 'selection'] | None = None
    skip: bool = Field(default=False, strict=True)
    observed_at: str | None = Field(default=None, max_length=80)


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=20, max_length=100)
    mappings: list[Mapping] = Field(max_length=4)


def observation_date(value):
    """An explicit instant, never upload time or an ambiguous date-only value."""
    if not isinstance(value, str) or 'T' not in value:
        raise HTTPException(422, 'Renseignez la date et l’heure du relevé, avec son fuseau horaire.')
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None or date.year < 1900 or date > datetime.now(timezone.utc):
            raise ValueError()
    except (ValueError, OverflowError):
        raise HTTPException(422, 'Date du relevé invalide ou future.') from None
    return date.astimezone(timezone.utc).isoformat(timespec='seconds')


def context(db):
    return {row['key']: row['value'] for row in db.execute("SELECT key,value FROM kv WHERE key IN ('classic_account','api_manager','api_developer')")}


def roster_revision(db, tid, youth):
    row = db.execute('SELECT id,digest,observed_at,last_observed_at,source,last_source,game_date,last_game_date FROM snapshots WHERE team_id=? AND youth=? ORDER BY id DESC LIMIT 1', (tid, int(youth))).fetchone()
    return dict(row) if row else None


def is_older(dataset, observed, current):
    if not current or hashlib.sha256(pack(dataset['players']).encode()).hexdigest() == current['digest']:
        return False
    try:
        previous = datetime.fromisoformat((current['last_observed_at'] or current['observed_at']).replace('Z', '+00:00'))
        incoming = datetime.fromisoformat(observed)
        if ((previous.tzinfo is not None and incoming < previous)
                or (previous.tzinfo is None and incoming.date() < previous.date())):
            return True
    except (ValueError, TypeError):
        pass
    try:
        old_game = selection_game_date(json.loads(current['last_game_date'] or current['game_date'] or 'null'))
    except (ValueError, TypeError):
        old_game = None
    new_game = dataset['game_date']
    return bool(old_game and new_game and tuple(new_game[k] for k in ('season', 'round', 'day')) < tuple(old_game[k] for k in ('season', 'round', 'day')))


def inventory(data, filename, result):
    """Inventory only after the bounded parser validated the whole input."""
    names = []
    source_date = result.get('team', {}).get('date_maj')
    if filename.lower().endswith('.ods'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive, archive.open('content.xml') as stream:
            for _, node in ET.iterparse(stream, events=('end',)):
                if node.tag == '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table':
                    names.append(node.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name', '')[:120])
                    if len(names) > 1000:
                        raise ValueError('Maximum 1 000 feuilles par classeur.')
                node.clear()
    elif filename.lower().endswith('.json'):
        doc = json.loads(data.decode('utf-8-sig'))
        if isinstance(doc, dict):
            raw_date = doc.get('gameDate', doc.get('game_date'))
            if raw_date is not None and selection_game_date(raw_date) is None:
                raise ValueError('Date de jeu invalide.')
            if len(doc) > 1000:
                raise ValueError('Maximum 1 000 jeux de données par fichier.')
            names = [str(k)[:120] for k in doc if k not in ('players', 'gameDate', 'game_date', 'observed_at', 'date_maj')]
            source_date = doc.get('observed_at', doc.get('date_maj', source_date))
    recognized = {dataset['sheet'] for dataset in result['datasets']}
    excluded = [{'name': name, 'reason': 'roster_only'} for name in names if name not in recognized]
    # A supplied timestamp is provenance, not a missing-value placeholder.
    # Only a valid calendar date can be completed later; malformed, future or
    # timezone-less instants must never become freely replaceable timestamps.
    source_hint = source_date[:80] if isinstance(source_date, str) else None
    if source_date is None or source_date == '':
        source_date = None
    elif isinstance(source_date, str) and len(source_date) == 10 and source_date[4] == '-' and source_date[7] == '-':
        try:
            day = date.fromisoformat(source_date)
            if day.year < 1900 or day > datetime.now(timezone.utc).date():
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'Date du relevé invalide ou future.') from None
        source_date = None
    else:
        source_date = observation_date(source_date)
    return excluded, source_date, source_hint


def analyze(data, filename):
    result = parse_import(data, filename)
    excluded, source_date, source_hint = inventory(data, filename, result)
    game_date = selection_game_date(result.get('game_date'))
    if result.get('game_date') is not None and game_date is None:
        raise ValueError('Date de jeu invalide.')
    return result, excluded, source_date, source_hint, game_date


def register_import_preview(app, store, auth, require_team, credentials, throttle):
    previews = {}
    lock = threading.RLock()
    active_analyses = 0

    def owner(session):
        return (session['user_id'], str(store.path))

    def lookup(token, session):
        entry = previews.get(token)
        if not entry or entry['owner'] != owner(session) or time.monotonic() >= entry['deadline']:
            if entry and entry['owner'] == owner(session):
                previews.pop(token, None)
            raise HTTPException(404, 'Aperçu absent ou expiré. Analysez de nouveau le fichier.')
        return entry

    async def create_preview(file, session):
        data = await file.read(8_000_001)
        filename = (file.filename or 'import')[:180]
        await file.close()
        try:
            result, excluded, source_date, source_hint, game_date = await run_in_threadpool(analyze, data, filename)
        except (ValueError, TypeError, zipfile.BadZipFile):
            raise HTTPException(422, 'Fichier invalide, vide ou hors limites. Formats : ODS, CSV, JSON ; 8 Mo et 4 000 joueurs maximum.') from None
        datasets = [{
            'id': str(index), 'sheet': item.get('sheet', filename), 'players': item['players'],
            'count': len(item['players']), 'observed_at': source_date, 'source_date_hint': source_hint, 'game_date': game_date,
        } for index, item in enumerate(result['datasets'] or [{'players': result['players']}])]
        with store.db() as db:
            db.execute('BEGIN')
            baseline_context = context(db)
            account = json.loads(baseline_context.get('classic_account', 'null'))
            active = selection_ids(account) if isinstance(account, dict) else []
            teams = [dict(row) for row in db.execute('SELECT * FROM teams ORDER BY name,id')]
            destinations = []
            revisions = {}
            for team in teams:
                identity = team_identity(team['id'])
                selection = identity['kind'] != 'club'
                if selection and team['id'] not in active:
                    continue
                destination = {'team_id': team['id'], 'name': team['name'], 'cohorts': ['selection'] if selection else ['seniors', 'academy'], 'current': {}}
                destinations.append(destination)
                for youth in ([False] if selection else [False, True]):
                    revision = roster_revision(db, team['id'], youth)
                    revisions[(team['id'], youth)] = revision
                    count = db.execute('SELECT json_array_length(payload) FROM snapshots WHERE id=?', (revision['id'],)).fetchone()[0] if revision else 0
                    destination['current']['selection' if selection else 'academy' if youth else 'seniors'] = {
                        'count': count, 'observed_at': (revision['last_observed_at'] or revision['observed_at']) if revision else None,
                        'game_date': json.loads(revision['last_game_date'] or revision['game_date'] or 'null') if revision else None}
        stamp = time.monotonic()
        token = secrets.token_urlsafe(32)
        cached = {'owner': owner(session), 'deadline': stamp + TTL_SECONDS, 'datasets': datasets,
                  'destinations': destinations, 'context': baseline_context,
                  'teams': {team['id']: team for team in teams}, 'revisions': revisions, 'filename': filename}
        # Bound retained data by bytes as well as entry count. Compact revisions
        # deliberately never copy existing roster payloads into the cache.
        cached['bytes'] = sum(len(json.dumps(value, ensure_ascii=False).encode()) for value in
                              [datasets, destinations, baseline_context, teams, list(revisions.values()), filename])
        if cached['bytes'] > MAX_CACHE_BYTES:
            raise HTTPException(413, 'Aperçu trop volumineux. Séparez les effectifs en plusieurs fichiers.')
        with lock:
            for previous in list(previews):
                if previews[previous]['deadline'] <= stamp:
                    del previews[previous]
            own_tokens = [key for key, value in previews.items() if value['owner'] == owner(session)]
            while len(own_tokens) >= 4:
                previews.pop(own_tokens.pop(0), None)
            while len(previews) >= MAX_PREVIEWS:
                previews.pop(next(iter(previews)))
            while previews and sum(value['bytes'] for value in previews.values()) + cached['bytes'] > MAX_CACHE_BYTES:
                previews.pop(next(iter(previews)))
            previews[token] = cached
        return {'token': token, 'expires_at': datetime.fromtimestamp(time.time() + TTL_SECONDS, timezone.utc).isoformat(),
                'datasets': datasets, 'destinations': destinations, 'excluded': excluded,
                'limitations': ['roster_only', 'recognized_player_sheets_only', 'source_date_required']}

    @app.post('/api/import/preview')
    async def preview(file: UploadFile = File(...), session=Depends(auth)):
        nonlocal active_analyses
        # UploadFile is spooled by Starlette. Reserve a slot before expanding its
        # contents into bytes/XML/player objects, and never queue bytes in RAM.
        with lock:
            available = active_analyses < MAX_CONCURRENT_ANALYSES
            if available:
                active_analyses += 1
        if not available:
            await file.close()
            raise HTTPException(429, 'Trop d’analyses simultanées. Réessayez dans quelques instants.')
        try:
            return await create_preview(file, session)
        finally:
            with lock:
                active_analyses -= 1

    @app.post('/api/import/confirm')
    async def confirm(body: Confirmation, session=Depends(auth)):
        with lock:
            entry = lookup(body.token, session)
        if len(body.mappings) != len(entry['datasets']) or {row.dataset_id for row in body.mappings} != {row['id'] for row in entry['datasets']}:
            raise HTTPException(422, 'Choisissez une destination ou une exclusion pour chaque jeu de données.')
        destinations = {(row['team_id'], cohort) for row in entry['destinations'] for cohort in row['cohorts']}
        prepared = []
        skipped = []
        used = set()
        for mapping in body.mappings:
            dataset = next(row for row in entry['datasets'] if row['id'] == mapping.dataset_id)
            if mapping.skip:
                if mapping.team_id is not None or mapping.cohort is not None:
                    raise HTTPException(422, 'Une exclusion ne peut pas avoir de destination.')
                skipped.append({'dataset_id': dataset['id'], 'sheet': dataset['sheet'], 'count': dataset['count']})
                continue
            destination = (mapping.team_id, mapping.cohort)
            if destination not in destinations:
                raise HTTPException(422, 'Destination inconnue, en pause ou non autorisée.')
            if destination in used:
                raise HTTPException(422, 'Plusieurs feuilles visent le même effectif. Choisissez des destinations distinctes ou excluez une feuille.')
            used.add(destination)
            observed = observation_date(mapping.observed_at or dataset['observed_at'])
            if dataset['observed_at'] and observed != dataset['observed_at']:
                raise HTTPException(422, 'La date fournie par le fichier doit être conservée ; elle ne peut pas être rendue plus récente.')
            hint = dataset.get('source_date_hint')
            try:
                date_only = date.fromisoformat(hint) if hint and len(hint) == 10 else None
            except ValueError:
                date_only = None
            if date_only and (mapping.observed_at or '')[:10] != hint:
                raise HTTPException(422, 'Complétez la date du fichier avec une heure et un fuseau, sans changer son jour.')
            if is_older(dataset, observed, entry['revisions'][(mapping.team_id, mapping.cohort == 'academy')]):
                raise HTTPException(422, 'Ce relevé ancien diffère de l’effectif actuel. Son remplacement est refusé pour préserver la chronologie ; conservez ce fichier comme archive.')
            prepared.append((mapping, dataset, observed))
        if not prepared:
            raise HTTPException(422, 'Sélectionnez au moins un effectif à importer.')
        with store.db() as db:
            if context(db) != entry['context']:
                with lock:
                    previews.pop(body.token, None)
                raise HTTPException(409, 'Le compte Classic a changé. Analysez de nouveau le fichier.')
        selections = [mapping.team_id for mapping, _, _ in prepared if is_selection(mapping.team_id)]
        if selections:
            throttle('import-selection-confirm')
            try:
                account, keys = manager_credentials(store, credentials())
                client = ClassicClient(keys)
                await authenticated_member(client, str(account['id']))
                for tid in selections:
                    if tid not in selection_ids(account):
                        raise ClassicError('Le rattachement de la sélection a changé.')
                    await prepare_selection(client, str(account['id']), **team_identity(tid), country=entry['teams'][tid]['country'])
            except (ClassicError, ValueError):
                with lock:
                    previews.pop(body.token, None)
                raise HTTPException(422, 'Mandat non confirmé. Vérifiez votre compte Classic puis analysez de nouveau le fichier.') from None
        with lock:
            lookup(body.token, session)
            with store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                if context(db) != entry['context']:
                    previews.pop(body.token, None)
                    raise HTTPException(409, 'Le compte Classic a changé. Analysez de nouveau le fichier.')
                # Validate every baseline before the first write, under the same
                # write lock used for the entire batch and observation history.
                for mapping, _, _ in prepared:
                    tid = mapping.team_id
                    row = db.execute('SELECT * FROM teams WHERE id=?', (tid,)).fetchone()
                    if not row or dict(row) != entry['teams'][tid] or roster_revision(db, tid, mapping.cohort == 'academy') != entry['revisions'][(tid, mapping.cohort == 'academy')]:
                        previews.pop(body.token, None)
                        raise HTTPException(409, 'Les données ont changé depuis l’aperçu. Analysez de nouveau le fichier.')
                for mapping, dataset, observed in prepared:
                    store.save_snapshot(mapping.team_id, mapping.cohort == 'academy', dataset['players'],
                                        entry['filename'] + ' · ' + dataset['sheet'], observed, dataset['game_date'], db)
            previews.pop(body.token, None)
        return {'ok': True, 'imported': [{'dataset_id': dataset['id'], 'sheet': dataset['sheet'], 'team_id': mapping.team_id, 'cohort': mapping.cohort, 'count': dataset['count']} for mapping, dataset, _ in prepared], 'skipped': skipped}
