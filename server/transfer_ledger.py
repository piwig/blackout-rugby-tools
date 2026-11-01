"""Private completed virtual transfers. Never changes budgets or issues game orders."""
import csv
import hashlib
import io
import json
import secrets
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .storage import now, pack
from .team_identity import TeamId, require_club_id

MAX_ROWS = 1000
MAX_CONTENT = 4_000_000
MAX_REQUEST_BYTES = 8_200_000
MAX_VERSIONS = 100
TTL_SECONDS = 900
SCHEMA = 'brt-transfer-ledger-v1'
PORTABLE_LIMIT_MESSAGE = 'Ce changement dépasse la capacité d’export réimportable du registre (4 Mo). Réduisez les textes ou le nombre d’opérations ; aucune donnée n’a été modifiée.'
Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')]
Revision = Annotated[int, Field(ge=0, le=2_147_483_647)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)) or len(str(value)) > 48:
        raise ValueError('Montant requis, positif ou nul, avec deux décimales au maximum.')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('1000000000000'):
            raise ValueError()
        if amount != amount.quantize(Decimal('.01')):
            raise ValueError()
        return format(amount.quantize(Decimal('.01')), '.2f')
    except (InvalidOperation, ValueError):
        raise ValueError('Montant requis, positif ou nul, avec deux décimales au maximum.') from None


def instant(value):
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('Date ISO avec fuseau requise.')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.year < 1900 or stamp > datetime.now(timezone.utc):
            raise ValueError()
        return stamp.astimezone(timezone.utc).isoformat(timespec='seconds')
    except (ValueError, OverflowError):
        raise ValueError('Date invalide ou future : seules les opérations réalisées sont admises.') from None


class TransferEntry(Strict):
    id: Identifier
    player_id: Annotated[str, Field(pattern=r'^[1-9][0-9]{0,14}$')]
    player_name: str = Field(min_length=1, max_length=100)
    kind: Literal['buy', 'sell']
    occurred_at: str = Field(max_length=80)
    season: str = Field(min_length=1, max_length=30)
    amount: str
    fees: str
    counterparty: str = Field(default='', max_length=160)
    source: str = Field(min_length=1, max_length=500)
    notes: str = Field(default='', max_length=1000)
    status: Literal['active', 'cancelled'] = 'active'
    cancellation_reason: str = Field(default='', max_length=500)

    @field_validator('amount', 'fees', mode='before')
    @classmethod
    def valid_money(cls, value):
        return money(value)

    @field_validator('occurred_at')
    @classmethod
    def valid_date(cls, value):
        return instant(value)

    @field_validator('player_name', 'season', 'counterparty', 'source')
    @classmethod
    def printable(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('Texte invalide.')
        return value

    @model_validator(mode='after')
    def cancellation(self):
        if (self.status == 'cancelled') != bool(self.cancellation_reason):
            raise ValueError('Une annulation exige son motif ; une opération active ne porte pas de motif d’annulation.')
        return self


FIELDS = list(TransferEntry.model_fields)


class BaseWrite(Strict):
    team_id: TeamId
    expected_revision: Revision


class Save(BaseWrite):
    entry: TransferEntry
    action: Literal['create', 'correct'] = 'create'
    reason: str = Field(default='', max_length=500)


class ChangeStatus(BaseWrite):
    id: Identifier
    reason: str = Field(min_length=1, max_length=500)


class Preview(BaseWrite):
    format: Literal['csv', 'json']
    content: str = Field(min_length=1, max_length=MAX_CONTENT)
    mode: Literal['append', 'correct'] = 'append'
    reason: str = Field(default='', max_length=500)


class Confirm(BaseWrite):
    preview_id: Annotated[str, Field(pattern=r'^[0-9a-f]{48}$')]


def read_document(db, team_id):
    row = db.execute('SELECT value FROM kv WHERE key=?', ('transfer_ledger:'+team_id,)).fetchone()
    return json.loads(row['value']) if row else {'revision':0, 'updated_at':None, 'entries':[]}


def checked_revision(document, revision):
    if document['revision'] != revision:
        raise HTTPException(409, 'Le registre a changé. Votre brouillon est conservé ; rechargez avant de réessayer.')


def portable(row):
    return {field:row[field] for field in FIELDS}


def versioned(row, previous, operation, reason):
    versions = previous['versions'] if previous else []
    if len(versions) >= MAX_VERSIONS:
        raise HTTPException(422, 'Limite de versions atteinte pour cette opération.')
    version = len(versions)+1
    return {**row, 'version':version, 'versions':[*versions, {
        'version':version, 'at':now(), 'operation':operation, 'reason':reason, 'entry':dict(row)}]}


def merge(existing, incoming, mode, reason):
    # First validate collisions inside the file; order must never choose a winner.
    unique = {}
    duplicates = 0
    for row in incoming:
        previous = unique.get(row['id'])
        if previous is not None:
            if previous != row:
                raise HTTPException(409, 'Un identifiant désigne plusieurs opérations différentes dans le fichier.')
            duplicates += 1
        else:
            unique[row['id']] = row
    result = {row['id']:row for row in existing}
    added = corrected = 0
    for ident, row in unique.items():
        previous = result.get(ident)
        if previous and portable(previous) == row:
            duplicates += 1
        elif previous:
            if mode != 'correct':
                raise HTTPException(409, 'Identifiant existant avec un contenu différent. Choisissez une correction explicite.')
            if not reason.strip():
                raise HTTPException(422, 'Renseignez le motif de correction.')
            result[ident] = versioned(row, previous, 'correct', reason)
            corrected += 1
        else:
            result[ident] = versioned(row, None, 'import', reason)
            added += 1
    if len(result) > MAX_ROWS:
        raise HTTPException(422, 'Maximum 1 000 opérations par club.')
    return list(result.values()), {'added':added, 'corrected':corrected, 'duplicates':duplicates}


def parse_content(body):
    try:
        if len(body.content.encode('utf-8')) > MAX_CONTENT:
            raise ValueError()
        if body.format == 'json':
            rows = json.loads(body.content.lstrip('\ufeff'))
            if isinstance(rows, dict):
                if rows.get('schema') != SCHEMA or set(rows) != {'schema','entries'}:
                    raise ValueError()
                rows = rows['entries']
        else:
            reader = csv.DictReader(io.StringIO(body.content.lstrip('\ufeff'), newline=''))
            required = {key for key, field in TransferEntry.model_fields.items() if field.is_required()}
            if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
                    or not required <= set(reader.fieldnames) or not set(reader.fieldnames) <= set(FIELDS)):
                raise ValueError()
            rows = []
            for row in reader:
                rows.append(row)
                if len(rows) > MAX_ROWS:
                    raise ValueError()
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise ValueError()
        return [TransferEntry.model_validate(row).model_dump() for row in rows]
    except (ValueError, TypeError, csv.Error, RecursionError, ValidationError):
        raise HTTPException(422, 'Fichier invalide : vérifiez les colonnes, dates, montants et la limite de 1 000 opérations.') from None


def decimal_text(value):
    return format(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f')


def summarize(rows):
    active = [row for row in rows if row['status'] == 'active']
    buys = [row for row in active if row['kind'] == 'buy']
    sales = [row for row in active if row['kind'] == 'sell']
    purchases = sum((Decimal(row['amount']) for row in buys), Decimal(0))
    revenue = sum((Decimal(row['amount']) for row in sales), Decimal(0))
    fees = sum((Decimal(row['fees']) for row in active), Decimal(0))

    def record(items, net=False):
        if not items:
            return None
        best = max(items, key=lambda r:(Decimal(r['amount'])-(Decimal(r['fees']) if net else 0), r['id']))
        return {'id':best['id'], 'player_id':best['player_id'], 'player_name':best['player_name'],
                'amount':decimal_text(Decimal(best['amount'])-(Decimal(best['fees']) if net else 0))}

    return {'count':len(active), 'cancelled_count':len(rows)-len(active), 'buy_count':len(buys), 'sell_count':len(sales),
            'purchases':decimal_text(purchases), 'sales':decimal_text(revenue), 'fees':decimal_text(fees),
            'balance':decimal_text(revenue-purchases-fees),
            'average_buy_gross':decimal_text(purchases/len(buys)) if buys else None,
            'average_sell_gross':decimal_text(revenue/len(sales)) if sales else None,
            'largest_purchase_gross':record(buys), 'largest_sale_gross':record(sales), 'largest_sale_net':record(sales, True)}


def grouped(rows, field):
    groups = {}
    for row in rows:
        groups.setdefault(row[field], []).append(row)
    return [{field:key, **({'player_name':max(items, key=lambda row:(row['occurred_at'], row['id']))['player_name']} if field == 'player_id' else {}), **summarize(items)}
            for key, items in sorted(groups.items())]


def transfer_export(rows, format):
    values = [portable(row) for row in rows]
    if format == 'json':
        return json.dumps({'schema':SCHEMA, 'entries':values}, ensure_ascii=False, indent=2)
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(values)
    return buffer.getvalue()


def checked_portable_budget(entries):
    """Every allowed current state fits both file import and its HTTP envelope."""
    for format in ('csv', 'json'):
        content = transfer_export(entries, format)
        # Reserve the largest permitted team/revision and a maximally escaped
        # correction reason. JSON.stringify uses the same UTF-8/escape boundary.
        envelope = pack({'team_id':'9'*15, 'expected_revision':2_147_483_647,
                         'format':format, 'content':content, 'mode':'correct', 'reason':'\x00'*500})
        if len(content.encode('utf-8')) > MAX_CONTENT or len(envelope.encode('utf-8')) >= MAX_REQUEST_BYTES:
            raise HTTPException(422, PORTABLE_LIMIT_MESSAGE)


def register_transfer_ledger(app, store, auth, require_team):
    def club(team_id):
        require_club_id(team_id)
        require_team(team_id)

    def team_binding(db, team_id):
        row = db.execute('SELECT name,country,meta FROM teams WHERE id=?', (team_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Club introuvable.')
        return hashlib.sha256(pack(dict(row)).encode()).hexdigest()

    def owner(session):
        return hashlib.sha256(pack([session.get('user_id'), session.get('token'), session.get('csrf')]).encode()).hexdigest()

    def persist(db, team_id, document, entries):
        checked_portable_budget(entries)
        next_document = {'revision':document['revision']+1, 'updated_at':now(), 'entries':entries}
        content = pack(next_document)
        if len(content.encode()) > 16_000_000:
            raise HTTPException(422, 'Le registre a atteint sa limite de taille.')
        db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('transfer_ledger:'+team_id, content))
        return next_document

    def response(document):
        return {**document, 'statistics':summarize(document['entries'])}

    @app.get('/api/transfer-ledger')
    def get_ledger(team_id: TeamId = Query(), season: str = Query('', max_length=30),
                   player_id: str = Query('', max_length=15), search: str = Query('', max_length=100),
                   start: date | None = None, end: date | None = None,
                   offset: int = Query(0, ge=0, le=MAX_ROWS), limit: int = Query(50, ge=1, le=100), session=Depends(auth)):
        club(team_id)
        if start and end and start > end:
            raise HTTPException(422, 'La fin doit suivre le début de la période.')
        with store.db() as db:
            document = read_document(db, team_id)
        rows = [row for row in document['entries'] if (not season or row['season'] == season)
                and (not player_id or row['player_id'] == player_id)
                and (not search or search.casefold() in row['player_name'].casefold() or search == row['player_id'])
                and (start is None or row['occurred_at'][:10] >= start.isoformat())
                and (end is None or row['occurred_at'][:10] <= end.isoformat())]
        rows.sort(key=lambda row:(row['occurred_at'], row['id']), reverse=True)
        return {'revision':document['revision'], 'updated_at':document['updated_at'], 'entries':rows[offset:offset+limit],
                'total':len(rows), 'total_stored':len(document['entries']), 'offset':offset, 'limit':limit,
                'statistics':summarize(rows), 'by_season':grouped(rows, 'season'), 'by_player':grouped(rows, 'player_id'),
                'seasons':sorted({row['season'] for row in document['entries']})}

    @app.post('/api/transfer-ledger')
    def save_entry(body: Save, session=Depends(auth)):
        club(body.team_id)
        incoming = body.entry.model_dump()
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            team_binding(db, body.team_id)
            document = read_document(db, body.team_id)
            checked_revision(document, body.expected_revision)
            previous = next((r for r in document['entries'] if r['id'] == incoming['id']), None)
            if body.action == 'correct':
                if not previous:
                    raise HTTPException(404, 'Opération introuvable.')
                if not body.reason:
                    raise HTTPException(422, 'Renseignez le motif de correction.')
                if incoming['status'] != previous['status'] or incoming['cancellation_reason'] != previous['cancellation_reason']:
                    raise HTTPException(422, 'Utilisez les commandes d’annulation ou de restauration pour changer le statut.')
            elif incoming['status'] != 'active':
                raise HTTPException(422, 'Une nouvelle saisie doit être active.')
            entries, counts = merge(document['entries'], [incoming], 'correct' if body.action == 'correct' else 'append', body.reason)
            if counts['added'] or counts['corrected']:
                if counts['added']:
                    fresh = next(r for r in entries if r['id'] == incoming['id'])
                    fresh['versions'][0]['operation'] = 'create'
                document = persist(db, body.team_id, document, entries)
        return response(document)

    def change_status(body, cancelled):
        club(body.team_id)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            team_binding(db, body.team_id)
            document = read_document(db, body.team_id)
            checked_revision(document, body.expected_revision)
            previous = next((r for r in document['entries'] if r['id'] == body.id), None)
            if previous is None:
                raise HTTPException(404, 'Opération introuvable.')
            status = 'cancelled' if cancelled else 'active'
            if previous['status'] == status:
                raise HTTPException(409, 'Le statut de cette opération a déjà changé.')
            row = {**portable(previous), 'status':status, 'cancellation_reason':body.reason if cancelled else ''}
            updated = versioned(row, previous, 'cancel' if cancelled else 'restore', body.reason)
            document = persist(db, body.team_id, document, [updated if r['id'] == body.id else r for r in document['entries']])
        return response(document)

    @app.post('/api/transfer-ledger/cancel')
    def cancel(body: ChangeStatus, session=Depends(auth)):
        return change_status(body, True)

    @app.post('/api/transfer-ledger/restore')
    def restore(body: ChangeStatus, session=Depends(auth)):
        return change_status(body, False)

    @app.get('/api/transfer-ledger/export')
    def export(team_id: TeamId = Query(), format: Literal['csv','json'] = 'json', session=Depends(auth)):
        club(team_id)
        with store.db() as db:
            document = read_document(db, team_id)
        return {'filename':'transfer-ledger.'+format, 'format':format, 'content':transfer_export(document['entries'], format), 'revision':document['revision']}

    @app.get('/api/transfer-ledger/template')
    def template(team_id: TeamId = Query(), format: Literal['csv','json'] = 'csv', session=Depends(auth)):
        club(team_id)
        sample = TransferEntry(id='replace-with-unique-id', player_id='42', player_name='Example player', kind='buy',
            occurred_at='2020-01-01T12:00:00Z', season='Example season', amount='100.00', fees='0.00',
            source='Example only: replace every value with a completed transaction').model_dump()
        return {'filename':'transfer-ledger-template.'+format, 'format':format, 'content':transfer_export([sample], format), 'sample_only':True}

    @app.post('/api/transfer-ledger/preview')
    def preview(body: Preview, session=Depends(auth)):
        club(body.team_id)
        if body.mode == 'correct' and not body.reason:
            raise HTTPException(422, 'Renseignez le motif de correction.')
        incoming = parse_content(body)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            binding = team_binding(db, body.team_id)
            document = read_document(db, body.team_id)
            checked_revision(document, body.expected_revision)
            projected, counts = merge(document['entries'], incoming, body.mode, body.reason)
            checked_portable_budget(projected)
            previews = db.execute("SELECT key,value FROM kv WHERE key GLOB 'transfer_preview:*'").fetchall()
            valid = []
            for row in previews:
                if json.loads(row['value'])['expires_at'] <= time.time():
                    db.execute('DELETE FROM kv WHERE key=?', (row['key'],))
                else:
                    valid.append(row['key'])
            # Bound temporary content per private store (at most five previews).
            for key in valid[:-4]:
                db.execute('DELETE FROM kv WHERE key=?', (key,))
            token = secrets.token_hex(24)
            expires = time.time()+TTL_SECONDS
            db.execute('INSERT INTO kv VALUES(?,?)', ('transfer_preview:'+token, pack({
                'owner':owner(session), 'team_id':body.team_id, 'team_binding':binding, 'revision':document['revision'],
                'entries':incoming, 'mode':body.mode, 'reason':body.reason, 'expires_at':expires})))
        return {'preview_id':token, 'revision':document['revision'], 'expires_at':expires, 'entries':incoming,
                'statistics':summarize(projected), **counts}

    @app.post('/api/transfer-ledger/confirm')
    def confirm(body: Confirm, session=Depends(auth)):
        club(body.team_id)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            key = 'transfer_preview:'+body.preview_id
            raw = db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
            if not raw:
                raise HTTPException(409, 'Aperçu expiré ou déjà confirmé. Préparez un nouvel aperçu.')
            preview = json.loads(raw['value'])
            if (not secrets.compare_digest(preview['owner'], owner(session)) or preview['team_id'] != body.team_id
                    or preview['expires_at'] <= time.time()):
                raise HTTPException(409, 'Aperçu expiré ou lié à une autre session ou équipe.')
            if preview['team_binding'] != team_binding(db, body.team_id):
                raise HTTPException(409, 'Le club a changé depuis l’aperçu. Préparez un nouvel aperçu.')
            document = read_document(db, body.team_id)
            checked_revision(document, body.expected_revision)
            checked_revision(preview, body.expected_revision)
            entries, counts = merge(document['entries'], preview['entries'], preview['mode'], preview['reason'])
            if counts['added'] or counts['corrected']:
                document = persist(db, body.team_id, document, entries)
            # The consumed token and the write commit atomically.
            db.execute('DELETE FROM kv WHERE key=?', (key,))
        return {'revision':document['revision'], 'total':len(document['entries']), **counts}
