"""Private, revisioned planning documents and a read-only daily workbench.

Only explicitly addressed feedback crosses the manager boundary. No route here
contacts Classic, schedules a write there, or reads stored API credentials.
"""
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .storage import now, pack

TeamId = Annotated[str, Field(pattern=r'^[1-9][0-9]{0,14}$')]
PlayerId = Annotated[str, Field(pattern=r'^[1-9][0-9]{0,14}$')]
Revision = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
FeedbackStatus = Literal['new', 'reviewing', 'planned', 'resolved']
KINDS = ('calendar', 'freshness', 'fatigue', 'followup', 'notes', 'vacation')
EVENT_LABELS = {'confirmed': 'Envoi Classic vérifié', 'uncertain': 'Résultat à vérifier',
                'blocked': 'Envoi bloqué', 'error': 'Erreur signalée', 'conflict': 'Données modifiées',
                'ready': 'Proposition prête', 'prepared': 'Proposition préparée', 'preview': 'Aperçu préparé',
                'sending': 'Envoi démarré, confirmation à vérifier', 'reconciled': 'État Classic contrôlé',
                'stopped': 'Arrêt demandé', 'rule_saved': 'Règle enregistrée', 'skipped': 'Action non traitée'}


class StrictDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class CalendarEvent(StrictDocument):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    kind: Literal['match', 'training', 'reminder']
    title: str = Field(min_length=1, max_length=160)
    starts_at: str = Field(max_length=40)
    ends_at: str | None = Field(default=None, max_length=40)
    timezone: str = Field(default='UTC', max_length=80)
    importance: Literal['low', 'normal', 'high'] = 'normal'
    notes: str = Field(default='', max_length=2000)
    player_ids: list[PlayerId] = Field(default_factory=list, max_length=80)
    status: Literal['planned', 'done', 'cancelled'] = 'planned'
    source: Literal['manual', 'classic'] = 'manual'
    fixture_id: PlayerId | None = None

    @field_validator('starts_at', 'ends_at')
    @classmethod
    def real_date(cls, value):
        if value is None:
            return value
        parsed = parse_date(value)
        if parsed is None or 'T' not in value or not 2000 <= parsed.year <= 2100:
            raise ValueError('Date ISO avec fuseau requise, entre 2000 et 2100.')
        return parsed.isoformat()

    @field_validator('timezone')
    @classmethod
    def known_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Fuseau horaire inconnu.') from None
        return value

    @model_validator(mode='after')
    def consistent_event(self):
        if len(set(self.player_ids)) != len(self.player_ids):
            raise ValueError('Un joueur ne peut figurer qu’une fois dans la rotation.')
        if self.ends_at:
            duration = parse_date(self.ends_at) - parse_date(self.starts_at)
            if not timedelta(0) < duration <= timedelta(days=31):
                raise ValueError('La fin doit suivre le début, dans les 31 jours.')
        if self.source == 'classic' and (self.kind != 'match' or not self.fixture_id):
            raise ValueError('Une rencontre Classic doit conserver son identifiant.')
        return self


class CalendarSave(StrictDocument):
    team_id: TeamId
    expected_revision: Revision
    events: list[CalendarEvent] = Field(max_length=500)

    @field_validator('events')
    @classmethod
    def unique_events(cls, events):
        if len({event.id for event in events}) != len(events):
            raise ValueError('Identifiants d’événements en double.')
        fixtures = [event.fixture_id for event in events if event.fixture_id]
        if len(set(fixtures)) != len(fixtures):
            raise ValueError('Cette rencontre figure déjà au calendrier.')
        return events


class AlertPreferences(StrictDocument):
    in_app: bool = True
    browser: bool = False
    energy_scale: Literal['unknown', 'percent', 'level'] = 'unknown'
    energy_floor: float = Field(default=60, strict=True, ge=0, le=110)
    stale_days: int = Field(default=7, strict=True, ge=1, le=60)
    horizon_days: int = Field(default=7, strict=True, ge=1, le=60)
    categories: list[Literal['calendar', 'freshness', 'fatigue', 'followup', 'notes', 'vacation']] = Field(default_factory=lambda: list(KINDS), max_length=6)

    @model_validator(mode='after')
    def scale_bounds(self):
        if self.energy_scale == 'level' and not 1 <= self.energy_floor <= 11:
            raise ValueError('Le seuil de niveau doit être compris entre 1 et 11.')
        if len(set(self.categories)) != len(self.categories):
            raise ValueError('Catégories d’alertes en double.')
        return self


class PreferencesSave(StrictDocument):
    expected_revision: Revision
    preferences: AlertPreferences


class Identity(StrictDocument):
    palette: Literal['forest', 'ocean', 'burgundy', 'gold'] = 'forest'
    initials: str = Field(default='RFC', pattern=r'^[A-Z0-9À-ÖØ-Þ]{1,4}$')
    symbol: Literal['ball', 'shield', 'star', 'leaf'] = 'ball'


class IdentitySave(StrictDocument):
    team_id: TeamId
    expected_revision: Revision
    identity: Identity


class FeedbackSave(StrictDocument):
    team_id: TeamId
    expected_revision: Revision
    page: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')
    text: str = Field(min_length=1, max_length=2000)
    rating: int = Field(strict=True, ge=1, le=5)
    audience: Literal['private', 'admin'] = 'private'


class FeedbackUpdate(StrictDocument):
    feedback_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    status: FeedbackStatus
    expected_revision: Revision
    admin_view: bool = False


def parse_date(value):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date if date.tzinfo and date.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def read_document(store, key, content):
    return store.get('workbench:' + key, {'revision': 0, **content})


def replace_document(store, key, expected_revision, content):
    """Compare and replace in one SQLite write transaction, including across workers."""
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM kv WHERE key=?', ('workbench:' + key,)).fetchone()
        previous = json.loads(row['value']) if row else {'revision': 0}
        if previous['revision'] != expected_revision:
            raise HTTPException(409, 'Ces données ont changé dans un autre onglet. Rechargez avant de réessayer.')
        document = {'revision': expected_revision + 1, **content, 'updated_at': now()}
        db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('workbench:' + key, pack(document)))
    return document


def identity_for(store, team_id):
    return read_document(store, 'identity:' + team_id, {'identity': Identity().model_dump()})['identity']


def export_workbench(store):
    # Exact namespace: never export arbitrary kv entries (passwords/API ciphertext).
    with store.db() as db:
        return {row['key'][10:]: json.loads(row['value']) for row in db.execute(
            "SELECT key,value FROM kv WHERE key GLOB 'workbench:*' ORDER BY key")}


def fatigue_summary(squad, preferences):
    scale, floor = preferences['energy_scale'], preferences['energy_floor']
    valid, low = 0, 0
    for player in squad:
        value = player.get('energy')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        if scale == 'unknown' or not (1 <= value <= 11 if scale == 'level' else 0 <= value <= 110):
            continue
        valid += 1
        low += value < floor
    return {'scale': scale, 'floor': floor, 'low_count': low if scale != 'unknown' else None,
            'known_count': valid, 'unknown_count': len(squad)-valid, 'total': len(squad)}


def build_daily(states, calendars, preferences, vacation, generated_at=None):
    clock = parse_date(generated_at or now())
    clubs, actions = [], []
    for data in states:
        tid, name = data['current_team']['id'], data['current_team']['name']
        fatigue = fatigue_summary(data['squad'], preferences)
        sources = []
        for kind, field in [('squad', 'squad_source'), ('academy', 'academy_source')]:
            source = data.get(field)
            date = parse_date(source.get('observed_at')) if source else None
            # Legacy imports sometimes have date-only observations: keep them unknown.
            days = max(0, (clock-date).days) if date and date <= clock else None
            sources.append({'kind': kind, 'observed_at': source.get('observed_at') if source else None,
                            'age_days': days, 'stale': days is None or days >= preferences['stale_days']})
        notes = data.get('notes', {})
        cohorts = {kind: {str(player['id']) for player in data.get(kind, [])} for kind in ('squad', 'academy')}
        present_ids = cohorts['squad'] | cohorts['academy']
        watch_count = sum(bool(note.get('watch')) for pid, note in notes.items() if pid in present_ids)
        note_count = sum(bool(note.get('text', '').strip()) for pid, note in notes.items() if pid in present_ids)
        stale_watch_count = sum(bool(note.get('watch')) for pid, note in notes.items() if pid not in present_ids)
        stale_note_count = sum(bool(note.get('text', '').strip()) for pid, note in notes.items() if pid not in present_ids)
        clubs.append({'team_id': tid, 'name': name, 'sources': sources, 'fatigue': fatigue,
                      'watch_count': watch_count, 'note_count': note_count,
                      'stale_watch_count': stale_watch_count, 'stale_note_count': stale_note_count})

        def action(kind, title, priority, page, **fields):
            actions.append({'id': f'{tid}:{kind}:{fields.get("event_id", fields.get("cohort", ""))}', 'kind': kind,
                            'team_id': tid, 'team_name': name, 'title': title, 'priority': priority,
                            'page': page, **fields})

        if any(source['stale'] for source in sources):
            action('freshness', 'Actualiser les observations anciennes ou non datées', 4, 'settings')
        if fatigue['low_count']:
            unit = 'niveau / 11' if fatigue['scale'] == 'level' else '% (maximum 110)'
            action('fatigue', f'{fatigue["low_count"]} joueur(s) sous le seuil {fatigue["floor"]:g} {unit}', 3, 'optimization')
        for cohort, ids in cohorts.items():
            cohort_watch = sum(bool(notes.get(pid, {}).get('watch')) for pid in ids)
            cohort_notes = sum(bool(notes.get(pid, {}).get('text', '').strip()) for pid in ids)
            label = 'de l’effectif senior' if cohort == 'squad' else 'de l’académie'
            if cohort_watch:
                action('followup', f'Revoir les {cohort_watch} joueur(s) suivis {label}', 5, cohort,
                       cohort=cohort, count=cohort_watch)
            if cohort_notes:
                action('notes', f'Relire {cohort_notes} note(s) {label}', 6, cohort,
                       cohort=cohort, count=cohort_notes)
        for event in calendars.get(tid, []):
            date = parse_date(event['starts_at'])
            if event['status'] != 'planned' or date is None or date > clock + timedelta(days=preferences['horizon_days']):
                continue
            # A past match is historical, while an uncompleted reminder remains actionable.
            if date < clock - timedelta(days=1) and event['kind'] == 'match':
                continue
            overdue = date < clock
            action('calendar', event['title'], 1 if overdue else (2 if date < clock + timedelta(days=2) else 5),
                   'season', event_id=event['id'], starts_at=event['starts_at'], overdue=overdue,
                   importance=event['importance'])
        paused = any(r.get('paused_reason') for r in vacation.get('rules', []) if r['team_id'] == tid)
        unresolved = sum(p.get('status') in ('uncertain', 'sending') for p in vacation.get('previews', []) if p['team_id'] == tid)
        recent_incidents = sum(e.get('kind') in ('blocked', 'error', 'conflict') and bool(parse_date(e.get('created_at')) and parse_date(e['created_at']) >= clock-timedelta(days=2))
                               for e in vacation.get('events', []) if e['team_id'] == tid)
        if paused or unresolved or recent_incidents:
            action('vacation', 'Contrôler les incidents du mode vacances', 0, 'vacation',
                   unresolved=unresolved, paused=paused, recent_incidents=recent_incidents)
    actions.sort(key=lambda a: (a['priority'], 0 if a.get('importance') == 'high' else 1, a.get('starts_at', ''), a['team_name']))
    return {'clubs': clubs, 'actions': actions, 'generated_at': clock.isoformat()}


def vacation_digest(status, team_id, days):
    clock = datetime.now(timezone.utc)
    since = clock - timedelta(days=days)
    all_events = [e for e in status.get('events', []) if not team_id or e['team_id'] == team_id]
    events = [e for e in all_events if parse_date(e.get('created_at')) and since <= parse_date(e['created_at']) <= clock]
    # Use an allowlist and trusted labels instead of raw diagnostic messages/payloads.
    public_events = [{k: e.get(k) for k in ('id', 'team_id', 'kind', 'created_at')} |
                     {'message': EVENT_LABELS.get(e.get('kind'), 'Événement enregistré')} for e in events]
    rules = [{k: r.get(k) for k in ('team_id', 'enabled', 'mode', 'start_at', 'end_at')} |
             {'paused': bool(r.get('paused_reason'))} for r in status.get('rules', []) if not team_id or r['team_id'] == team_id]
    previews = [p for p in status.get('previews', []) if not team_id or p['team_id'] == team_id]
    return {'days': days, 'from': since.isoformat(), 'to': clock.isoformat(), 'rules': rules,
            'events': public_events, 'confirmed_count': sum(e['kind'] == 'confirmed' for e in events),
            'prepared_count': sum(e['kind'] in ('prepared', 'ready') for e in events),
            'incident_count': sum(e['kind'] in ('error', 'blocked', 'uncertain', 'conflict') for e in events),
            'unresolved_count': sum(p['status'] in ('uncertain', 'sending') for p in previews),
            'coverage': 'Journal conservé : les 100 derniers événements du manager, dans la limite de la rétention. Les compteurs ne garantissent pas une période exhaustive.'}


def register_workbench(app, store, auth, require_team, state, accounts, vacation_service):
    def preferences():
        return read_document(store, 'preferences', {'preferences': AlertPreferences().model_dump()})

    def calendar(tid):
        return read_document(store, 'calendar:' + tid, {'events': []})

    @app.get('/api/workbench/daily')
    def daily(session=Depends(auth)):
        with store.db() as db:
            tids = [r['id'] for r in db.execute('SELECT id FROM teams ORDER BY name,id')]
        document = preferences()
        return {**build_daily([state(tid, session) for tid in tids], {tid: calendar(tid)['events'] for tid in tids},
                              document['preferences'], vacation_service(session['user_id']).status()),
                'preferences': document}

    @app.get('/api/workbench/calendar')
    def get_calendar(team_id: TeamId, session=Depends(auth)):
        require_team(team_id)
        document = calendar(team_id)
        data = state(team_id, session)
        present = {str(p['id']) for p in data['squad'] + data['academy']}
        missing = sorted({pid for event in document['events'] for pid in event['player_ids'] if pid not in present})
        return {**document, 'missing_player_ids': missing}

    @app.post('/api/workbench/calendar')
    def save_calendar(body: CalendarSave, session=Depends(auth)):
        require_team(body.team_id)
        previous = calendar(body.team_id)
        if previous['revision'] != body.expected_revision:
            raise HTTPException(409, 'Ces données ont changé dans un autre onglet. Rechargez avant de réessayer.')
        data = state(body.team_id, session)
        present = {str(p['id']) for p in data['squad'] + data['academy']}
        retained = {event['id']: set(event['player_ids']) for event in previous['events']}
        if any(pid not in present and pid not in retained.get(event.id, set())
               for event in body.events for pid in event.player_ids):
            raise HTTPException(422, 'La rotation ajoute un joueur absent des observations actuelles. Retirez cette nouvelle référence ou actualisez les joueurs.')
        # A player may disappear after planning. Keep existing references editable
        # event by event; the atomic revision check below also protects this exact
        # previous document if another writer changes it during roster validation.
        saved = replace_document(store, 'calendar:' + body.team_id, body.expected_revision,
                                 {'events': [event.model_dump() for event in body.events]})
        return {**saved, 'missing_player_ids': sorted({pid for event in body.events
                                                     for pid in event.player_ids if pid not in present})}

    @app.get('/api/workbench/preferences')
    def get_preferences(session=Depends(auth)):
        return preferences()

    @app.post('/api/workbench/preferences')
    def save_preferences(body: PreferencesSave, session=Depends(auth)):
        return replace_document(store, 'preferences', body.expected_revision, {'preferences': body.preferences.model_dump()})

    @app.get('/api/workbench/identity')
    def get_identity(team_id: TeamId, session=Depends(auth)):
        require_team(team_id)
        return read_document(store, 'identity:' + team_id, {'identity': Identity().model_dump()})

    @app.post('/api/workbench/identity')
    def save_identity(body: IdentitySave, session=Depends(auth)):
        require_team(body.team_id)
        return replace_document(store, 'identity:' + body.team_id, body.expected_revision, {'identity': body.identity.model_dump()})

    @app.get('/api/workbench/vacation-digest')
    def get_digest(team_id: str = Query(default='', pattern=r'^(\d{1,15})?$'),
                   days: int = Query(default=7, ge=1, le=90), session=Depends(auth)):
        if team_id:
            require_team(team_id)
        return vacation_digest(vacation_service(session['user_id']).status(), team_id, days)

    def feedback(owner=store):
        return read_document(owner, 'feedback', {'items': []})

    @app.get('/api/workbench/feedback')
    def get_feedback(session=Depends(auth)):
        return feedback()

    @app.post('/api/workbench/feedback')
    def send_feedback(body: FeedbackSave, session=Depends(auth)):
        require_team(body.team_id)
        document = feedback()
        if len(document['items']) >= 500:
            raise HTTPException(422, 'Limite de 500 retours atteinte dans cet espace.')
        item = {'id': uuid.uuid4().hex, 'revision': 1, 'team_id': body.team_id, 'page': body.page,
                'text': body.text, 'rating': body.rating, 'audience': body.audience,
                'status': 'new', 'created_at': now(), 'updated_at': now()}
        return replace_document(store, 'feedback', body.expected_revision, {'items': [item, *document['items']]})

    def shared_feedback_sources():
        with accounts.db() as db:
            users = [dict(r) for r in db.execute('SELECT id,username FROM users ORDER BY username')]
        for user in users:
            owner = accounts.store(user['id'])
            # Read this one deliberately shareable document, never another manager's state.
            yield user['username'], owner, feedback(owner)

    @app.get('/api/workbench/feedback/admin')
    def admin_feedback(session=Depends(auth)):
        if not session['admin']:
            raise HTTPException(403, 'Réservé à l’administrateur.')
        fields = ('id', 'revision', 'page', 'text', 'rating', 'status', 'created_at', 'updated_at')
        items = [{'author': username, **{key: item[key] for key in fields}}
                 for username, _, document in shared_feedback_sources() for item in document['items'] if item['audience'] == 'admin']
        return {'items': sorted(items, key=lambda item: item['created_at'], reverse=True)}

    @app.post('/api/workbench/feedback/status')
    def update_feedback(body: FeedbackUpdate, session=Depends(auth)):
        if body.admin_view and not session['admin']:
            raise HTTPException(403, 'Réservé à l’administrateur.')
        owners = [(session['username'], store, feedback())] if not body.admin_view else shared_feedback_sources()
        for _, owner, document in owners:
            candidate = next((item for item in document['items'] if item['id'] == body.feedback_id and (not body.admin_view or item['audience'] == 'admin')), None)
            if not candidate:
                continue
            # Item revision is checked under the same transaction as its parent document.
            with owner.db() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT value FROM kv WHERE key='workbench:feedback'").fetchone()
                current = json.loads(row['value'])
                item = next(i for i in current['items'] if i['id'] == body.feedback_id)
                if item['revision'] != body.expected_revision:
                    raise HTTPException(409, 'Ce retour a été modifié. Rechargez la liste.')
                item.update(status=body.status, revision=item['revision']+1, updated_at=now())
                current.update(revision=current['revision']+1, updated_at=now())
                db.execute("UPDATE kv SET value=? WHERE key='workbench:feedback'", (pack(current),))
            return {'ok': True, 'id': item['id'], 'status': item['status'], 'revision': item['revision']}
        raise HTTPException(404, 'Retour introuvable.')
