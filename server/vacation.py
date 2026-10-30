"""Private Classic preparation with durable, fail-closed write claims.

No credentials, raw API responses or exception bodies enter the journal.
Automatic execution is opt-in per club and bounded by explicit UTC dates.
"""
import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .classic import ClassicClient, ClassicError, lineup_fingerprint, lineup_schema, validate_lineup_payload
from .domain import player_metrics
from .imports import parse_import
from .optimization import ROLES, energy_of, injury_status, make_lineup
from .storage import pack


Identifier = Annotated[str, Field(pattern=r'^[1-9][0-9]{0,14}$')]
_PROCESS_ID = uuid.uuid4().hex
_LOCKS = {}
_SLOTS = tuple(str(i) for i in range(1, 16))+tuple('b'+str(i) for i in range(1, 8))
_UNCERTAIN = 'Résultat incertain : contrôlez la composition dans Classic. Les envois de ce club sont suspendus, sans nouvelle tentative automatique.'


class VacationError(ValueError):
    def __init__(self, message, code='invalid', status_code=422):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class VacationOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    objective: Literal['balanced', 'recovery', 'development'] = 'balanced'
    energy_floor: float = Field(default=60, ge=0, le=110, allow_inf_nan=False)
    energy_scale: Literal['auto', 'percent', 'level'] = 'auto'
    excluded_ids: list[Identifier] = Field(default_factory=list, max_length=500)
    captain_id: Identifier | None = None
    kicker_id: Identifier | None = None


class VacationRule(VacationOptions):
    team_id: Identifier
    enabled: bool = False
    mode: Literal['prepare', 'automatic'] = 'prepare'
    start_at: AwareDatetime
    end_at: AwareDatetime
    lead_hours: int = Field(default=24, ge=2, le=168)
    manage_existing: bool = False

    @model_validator(mode='after')
    def bounded_dates(self):
        self.start_at = self.start_at.astimezone(timezone.utc)
        self.end_at = self.end_at.astimezone(timezone.utc)
        if not timedelta(0) < self.end_at-self.start_at <= timedelta(days=56):
            raise ValueError('La période doit durer plus de zéro et au maximum 56 jours.')
        return self


def _date(value):
    if value is None:
        return None
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='seconds')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class VacationService:
    def __init__(self, store, shared_credentials=None, client_factory=ClassicClient, clock=None):
        self.store = store
        self.shared_credentials = dict(shared_credentials or {})
        self.client_factory = client_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = _LOCKS.setdefault(str(store.path.resolve()), asyncio.Lock())
        with store.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS vacation_rules(
                    team_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,rule TEXT,
                    paused_reason TEXT);
                CREATE TABLE IF NOT EXISTS vacation_previews(
                    id TEXT PRIMARY KEY,team_id TEXT NOT NULL,fixture_id TEXT NOT NULL,
                    status TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,
                    revision INTEGER NOT NULL,document TEXT NOT NULL,process_id TEXT);
                CREATE INDEX IF NOT EXISTS vacation_previews_team ON vacation_previews(team_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS vacation_attempts(
                    team_id TEXT NOT NULL,fixture_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
                    preview_id TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,
                    PRIMARY KEY(team_id,fixture_id,fingerprint));
                CREATE TABLE IF NOT EXISTS vacation_events(
                    id INTEGER PRIMARY KEY,team_id TEXT NOT NULL,preview_id TEXT,
                    kind TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vacation_schema_verifications(
                    team_id TEXT NOT NULL,manager_id TEXT NOT NULL,schema_id TEXT NOT NULL,
                    preview_id TEXT NOT NULL,verified_at TEXT NOT NULL,
                    PRIMARY KEY(team_id,manager_id,schema_id));
            ''')
        self.recover_inflight()

    def _now(self):
        value = _date(self.clock())
        if value is None:
            raise ValueError('Vacation clock must return an offset-aware datetime.')
        return value

    def _require_team(self, team_id):
        if not isinstance(team_id, str) or not re.fullmatch(r'[1-9][0-9]{0,14}', team_id):
            raise VacationError('Identifiant de club invalide.')
        with self.store.db() as db:
            found = db.execute('SELECT 1 FROM teams WHERE id=?', (team_id,)).fetchone()
        if not found:
            raise VacationError('Club introuvable dans cet espace.', 'not_found', 404)

    def _state(self, team_id, db=None):
        if db is None:
            with self.store.db() as conn:
                return self._state(team_id, conn)
        row = db.execute('SELECT * FROM vacation_rules WHERE team_id=?', (team_id,)).fetchone()
        return dict(row) if row else {'team_id': team_id, 'revision': 0, 'rule': None, 'paused_reason': None}

    def _rule_view(self, state):
        rule = json.loads(state['rule']) if state['rule'] else {
            **VacationOptions().model_dump(), 'team_id': state['team_id'], 'enabled': False,
            'mode': 'prepare', 'start_at': None, 'end_at': None, 'lead_hours': 24, 'manage_existing': False}
        return {**rule, 'revision': state['revision'], 'paused_reason': state['paused_reason']}

    def _event(self, team_id, kind, message, preview_id=None, db=None):
        if db is None:
            with self.store.db() as conn:
                self._event(team_id, kind, message, preview_id, conn)
            return
        db.execute('INSERT INTO vacation_events(team_id,preview_id,kind,message,created_at) VALUES(?,?,?,?,?)',
                   (team_id, preview_id, kind, message, _iso(self._now())))
        db.execute('DELETE FROM vacation_events WHERE id NOT IN (SELECT id FROM vacation_events ORDER BY id DESC LIMIT 300)')

    def recover_inflight(self):
        """A new process never retries an old process's pending POST.

        A second instance in the same process leaves live requests alone.
        """
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT * FROM vacation_previews WHERE status='sending' AND (process_id IS NULL OR process_id<>?)", (_PROCESS_ID,)).fetchall()
            for row in rows:
                self._uncertain(dict(row), db=db)

    def status(self, team_id=None):
        if team_id is not None:
            self._require_team(team_id)
        with self.store.db() as db:
            tids = [team_id] if team_id else [r['id'] for r in db.execute('SELECT id FROM teams ORDER BY id')]
            # Expiration only changes unclaimed previews, never a live POST.
            db.execute("UPDATE vacation_previews SET status='expired' WHERE status='ready' AND expires_at<=?", (_iso(self._now()),))
            condition, args = ('WHERE team_id=?', (team_id,)) if team_id else ('', ())
            combine = condition+' AND ' if condition else 'WHERE '
            # Unresolved results must stay reachable even after many later previews.
            pending = db.execute('SELECT * FROM vacation_previews '+combine+"status IN ('sending','uncertain') ORDER BY created_at DESC,rowid DESC", args).fetchall()
            recent = db.execute('SELECT * FROM vacation_previews '+combine+"status NOT IN ('sending','uncertain') ORDER BY created_at DESC,rowid DESC LIMIT 20", args).fetchall()
            previews = [*pending, *recent]
            events = db.execute('SELECT * FROM vacation_events '+condition+' ORDER BY id DESC LIMIT 100', args).fetchall()
            rules = [self._rule_view(self._state(tid, db)) for tid in tids]
        return {'rules': rules, 'previews': [self._public_preview(dict(p)) for p in previews],
                'events': [dict(e) for e in events], 'worker_interval_seconds': 900}

    def save_rule(self, rule, expected_revision=0):
        rule = rule if isinstance(rule, VacationRule) else VacationRule.model_validate(rule)
        self._require_team(rule.team_id)
        account = self.store.get('classic_account', {}) or {}
        if rule.team_id not in [str(x) for x in account.get('team_ids', [])]:
            raise VacationError('Ce club doit appartenir au compte Classic importé.', 'ownership', 403)
        if rule.enabled and rule.end_at <= self._now():
            raise VacationError('La période choisie est déjà terminée.', 'period')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._state(rule.team_id, db)
            if state['revision'] != expected_revision:
                raise VacationError('Règles modifiées : rechargez la page.', 'revision', 409)
            if rule.enabled and state['paused_reason']:
                raise VacationError('Relisez et réconciliez le résultat incertain avant de réactiver ce club.', 'paused', 409)
            db.execute('INSERT OR REPLACE INTO vacation_rules VALUES(?,?,?,?)',
                       (rule.team_id, state['revision']+1, rule.model_dump_json(), state['paused_reason']))
            db.execute("UPDATE vacation_previews SET status='cancelled' WHERE team_id=? AND status='ready'", (rule.team_id,))
            self._event(rule.team_id, 'rule_saved', 'Règles enregistrées ; les anciens aperçus sont invalidés.', db=db)
            return self._rule_view(self._state(rule.team_id, db))

    def stop(self, team_id=None):
        if team_id is not None:
            self._require_team(team_id)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            tids = [team_id] if team_id else [r['id'] for r in db.execute('SELECT id FROM teams')]
            for tid in tids:
                state = self._state(tid, db)
                rule = json.loads(state['rule']) if state['rule'] else None
                if rule:
                    rule['enabled'] = False
                db.execute('INSERT OR REPLACE INTO vacation_rules VALUES(?,?,?,?)',
                           (tid, state['revision']+1, pack(rule) if rule else None, state['paused_reason']))
                db.execute("UPDATE vacation_previews SET status='cancelled' WHERE team_id=? AND status='ready'", (tid,))
                self._event(tid, 'stopped', 'Arrêt demandé. Une requête déjà transmise à Classic ne peut pas être annulée.', db=db)
        return self.status(team_id)

    def _credentials(self, team_id):
        values = {k: str(v) for k, v in self.shared_credentials.items() if k in ('d', 'dk', 'iv') and v}
        private = {k: str(v) for k, v in self.store.secrets(team_id).items() if k in ('d', 'dk', 'iv', 'm', 'mk') and v}
        if any(private.get(k, values.get(k)) != values.get(k) for k in ('d', 'dk')) and not private.get('iv'):
            values.pop('iv', None)
        values.update(private)
        return values

    async def _owned(self, team_id):
        self._require_team(team_id)
        credentials = self._credentials(team_id)
        account = self.store.get('classic_account', {}) or {}
        mid = credentials.get('m')
        if not mid or not credentials.get('mk') or str(account.get('id')) != mid or team_id not in [str(x) for x in account.get('team_ids', [])]:
            raise VacationError('Le compte Classic importé ne prouve pas la propriété de ce club.', 'ownership', 403)
        client = self.client_factory(credentials)
        doc = await client.request('m', memberid=mid)
        member = doc.get('members', {}).get(mid)
        if not isinstance(member, dict) or 'email' not in member:
            raise VacationError('La clé manager n’a pas été authentifiée par Classic.', 'ownership', 403)
        teams = member.get('teams', [])
        if not teams and member.get('teamid'):
            teams = [member['teamid']]
        if team_id not in [str(x) for x in teams]:
            raise VacationError('Classic ne rattache pas ce club à ce manager.', 'ownership', 403)
        doc = await client.request('t', teamid=team_id)
        team = doc.get('teams', {}).get(team_id)
        if not isinstance(team, dict) or str(team.get('owner')) != mid:
            raise VacationError('Le propriétaire actuel du club ne correspond pas au manager.', 'ownership', 403)
        return client, credentials

    async def fixtures(self, team_id):
        async with self.lock:
            client, _ = await self._owned(team_id)
            return {'fixtures': await client.list_fixtures(team_id)}

    async def _fresh(self, team_id, fixture_id):
        client, credentials = await self._owned(team_id)
        fixture = None
        if fixture_id != '0':
            fixture = next((f for f in await client.list_fixtures(team_id) if str(f['id']) == fixture_id), None)
            if fixture is None or team_id not in (str(fixture.get('home_team_id')), str(fixture.get('away_team_id'))):
                raise VacationError('Ce match futur ne figure pas dans le calendrier du club.', 'fixture')
        doc = await client.request('p', teamid=team_id)
        try:
            squad = parse_import(pack(doc).encode(), 'players.json')['players']
        except (ValueError, TypeError):
            raise VacationError('L’effectif Classic actuel est absent ou incomplet.', 'squad') from None
        squad = sorted(squad, key=lambda p: p['id'])
        if len({p['id'] for p in squad}) != len(squad):
            raise VacationError('L’effectif Classic contient des identifiants en double.', 'squad')
        remote = await client.read_lineup(team_id, fixture_id)
        return client, credentials, squad, remote, fixture

    def _deadline(self, remote, fixture_id, fixture):
        if fixture_id == '0':
            return None, []
        blockers = []
        lineup_deadline = _date(remote.get('deadline')) if remote else None
        tactics_deadline = _date(remote.get('tactics_deadline')) if remote else None
        deadline = min(d for d in (lineup_deadline, tactics_deadline) if d) if lineup_deadline or tactics_deadline else None
        # The lineup deadline itself is required, even if a tactics deadline exists.
        if not lineup_deadline:
            blockers.append('Échéance officielle de composition inconnue. Enregistrez d’abord une composition pour ce match dans Classic puis relisez-la.')
        elif deadline <= self._now():
            blockers.append('L’échéance officielle Classic est dépassée.')
        start = _date(fixture.get('match_start')) if fixture else None
        if not start or start <= self._now():
            blockers.append('La date de ce match futur n’est plus valide.')
        return _iso(deadline) if deadline else None, blockers

    def _write_configuration(self, credentials):
        if len(credentials.get('dk', '').encode()) not in (16, 24, 32) or len(credentials.get('iv', '').encode()) != 16:
            return ['L’envoi nécessite une clé développeur AES valide et son IV de 16 caractères dans Connexion & données.']
        return []

    async def preview(self, team_id, fixture_id='0', source='optimized', options=None):
        async with self.lock:
            return await self._preview(team_id, fixture_id, source, options, automatic=False)

    async def _preview(self, team_id, fixture_id, source, options, automatic):
        if source not in ('optimized', 'saved') or not re.fullmatch(r'(?:0|[1-9][0-9]{0,14})', fixture_id):
            raise VacationError('Source ou match invalide.')
        self._require_team(team_id)
        state = self._state(team_id)
        rule = self._rule_view(state)
        values = {key: rule[key] for key in VacationOptions.model_fields}
        values.update(options or {})
        config = VacationOptions.model_validate(values)
        _, credentials, squad, remote, fixture = await self._fresh(team_id, fixture_id)
        template = remote
        if template is None and fixture_id != '0':
            client, _ = await self._owned(team_id)
            template = await client.read_lineup(team_id, '0')
        deadline, blockers = self._deadline(remote, fixture_id, fixture)
        blockers.extend(self._write_configuration(credentials))
        warnings = ['Les tactiques et références de remplacement de Classic sont conservées.']
        schema = lineup_schema(template['payload']) if template else 'unknown'
        bench_size = 8 if template and 'b8' in template['payload'] else 7
        total_slots = 15+bench_size
        with self.store.db() as db:
            proven = db.execute('SELECT 1 FROM vacation_schema_verifications WHERE team_id=? AND manager_id=? AND schema_id=?',
                                (team_id, credentials.get('m'), schema)).fetchone()
        verification_required = schema != 'classic-22-zones' and not proven
        if verification_required:
            warnings.append('Ce format Classic diffère de la documentation historique. Un envoi manuel explicitement confirmé par relecture est nécessaire avant sa gestion automatique pour ce club.')
            if automatic and rule['mode'] == 'automatic':
                blockers.append('Ce format de composition nécessite d’abord un envoi manuel confirmé pour ce club avant d’activer les envois automatiques.')
        if state['paused_reason']:
            blockers.append(state['paused_reason'])
        if config.energy_scale == 'auto':
            blockers.append('Choisissez explicitement le format d’énergie : pourcentage premium ou niveau 1–11. Le format du compte ne peut pas être confirmé automatiquement.')
        if config.energy_scale == 'level':
            warnings.append('Le niveau d’énergie 1–11 est converti approximativement en pourcentage (niveau × 10).')
        if not template:
            blockers.append('Composition de référence introuvable dans Classic. Enregistrez une composition complète dans le jeu avant de préparer un envoi.')
        if automatic and rule['mode'] == 'automatic' and remote:
            with self.store.db() as db:
                previous = db.execute("SELECT fingerprint FROM vacation_attempts WHERE team_id=? AND fixture_id=? AND status='confirmed' ORDER BY created_at DESC,rowid DESC LIMIT 1", (team_id, fixture_id)).fetchone()
            if previous and previous['fingerprint'] != remote['fingerprint']:
                blockers.append('La composition a été modifiée dans Classic depuis le dernier envoi : intervention manuelle préservée.')
            elif not previous and not rule['manage_existing']:
                blockers.append('Composition Classic existante préservée : la règle n’autorise pas sa gestion automatique.')
        now = _iso(self._now())
        saved = self.store.get('lineup:'+team_id, {})
        excluded = set(config.excluded_ids)
        eligible = [p for p in squad if p['id'] not in excluded and injury_status(p.get('injured'), now) is False
                    and energy_of(p, config.energy_scale) is not None and energy_of(p, config.energy_scale) >= config.energy_floor]
        players, slots = [], {}
        if source == 'optimized':
            lineup, _, _ = make_lineup(eligible, saved, config.objective, config.energy_floor, config.energy_scale, now)
            slots = {k: v for k, v in lineup['slots'].items() if int(k) <= total_slots}
            players = [p for p in lineup['players'] if p['slot'] <= total_slots]
            if bench_size == 7 and any(p['slot'] == 23 for p in lineup['players']):
                omitted = next(p for p in lineup['players'] if p['slot'] == 23)
                warnings.append(f'Ce format Classic accepte 7 remplaçants. La huitième réserve, {omitted["name"]} (#{omitted["id"]}), reste hors de cet envoi.')
            if len(eligible) < len(squad):
                warnings.append(f'{len(squad)-len(eligible)} joueur(s) écarté(s) : exclusion, énergie ou disponibilité non confirmée.')
        else:
            slots = {str(i): str(saved[str(i)]) for i in range(1, total_slots+1) if saved.get(str(i))}
            if bench_size == 7 and saved.get('23'):
                omitted = next((p for p in squad if p['id'] == str(saved['23'])), None)
                label = f'{omitted["name"]} (#{omitted["id"]})' if omitted else '#'+str(saved['23'])
                warnings.append(f'La place locale 23, {label}, est explicitement exclue : ce format Classic reçoit 15 titulaires et 7 remplaçants.')
            by_id = {p['id']: p for p in squad}
            for position, ident in slots.items():
                p = by_id.get(ident)
                if p:
                    players.append({'slot': int(position), 'id': ident, 'name': p['name'],
                                    'energy': energy_of(p, config.energy_scale),
                                    'role': ROLES[int(position)-1] if int(position) <= 15 else 'Réserve'})
        eligible_ids = {p['id'] for p in eligible}
        by_id = {p['id']: p for p in squad}
        if len(slots) != total_slots or len(set(slots.values())) != total_slots:
            blockers.append(f'Il faut 15 titulaires et {bench_size} remplaçants distincts et disponibles pour ce format Classic.')
        if any(ident not in eligible_ids for ident in slots.values()):
            blockers.append('Un joueur retenu est exclu, blessé, sous le seuil, ou son énergie/disponibilité est inconnue.')
        for position, ident in slots.items():
            scores = {r['name'] for r in player_metrics(by_id.get(ident, {}))['roles']}
            if (int(position) <= 15 and ROLES[int(position)-1] not in scores) or not scores:
                blockers.append('Compétences insuffisantes pour vérifier les affinités de tous les joueurs retenus.')
                break
        payload = dict(template['payload']) if template else {}
        for position, ident in slots.items():
            payload[position if int(position) <= 15 else 'b'+str(int(position)-15)] = ident
        if config.captain_id:
            payload['captain'] = config.captain_id
        if config.kicker_id:
            payload['kicker'] = config.kicker_id
        if template and len(slots) == total_slots:
            try:
                payload = validate_lineup_payload(payload)
            except ClassicError:
                blockers.append('La composition proposée rend un rôle ou remplacement Classic incohérent. Ajustez le capitaine/buteur ou les références de remplacement dans le jeu ; aucune référence n’a été supprimée.')
        before = template['payload'] if template else {}
        changes = [{'field': k, 'before': before.get(k), 'after': v} for k, v in payload.items() if before.get(k) != v]
        current = self._state(team_id)
        cancelled = current['revision'] != state['revision']
        document = {'id': uuid.uuid4().hex, 'team_id': team_id, 'fixture_id': fixture_id,
                    'source': source, 'status': 'cancelled' if cancelled else 'blocked' if blockers else 'ready',
                    'created_at': now, 'expires_at': _iso(self._now()+timedelta(minutes=10)),
                    'revision': state['revision'], 'automatic': automatic and rule['mode'] == 'automatic',
                    'payload': payload, 'players': players, 'changes': changes, 'warnings': warnings,
                    'schema': schema, 'bench_size': bench_size, 'verification_required': bool(verification_required),
                    'reconciliation_required': False,
                    'blocking_reasons': list(dict.fromkeys(blockers)), 'deadline': deadline,
                    'rule': config.model_dump(), '_remote_fingerprint': remote['fingerprint'] if remote else None,
                    '_squad_fingerprint': _digest(squad), '_scheduled': automatic}
        with self.store.db() as db:
            db.execute('INSERT INTO vacation_previews VALUES(?,?,?,?,?,?,?,?,?)',
                       (document['id'], team_id, fixture_id, document['status'], now, document['expires_at'],
                        state['revision'], pack(document), _PROCESS_ID))
            self._event(team_id, document['status'], 'Aperçu préparé.' if document['status'] == 'ready' else 'Aperçu bloqué ou invalidé : consultez les contrôles.', document['id'], db)
            db.execute("DELETE FROM vacation_previews WHERE status NOT IN ('sending','uncertain') AND id NOT IN (SELECT id FROM vacation_previews ORDER BY created_at DESC,rowid DESC LIMIT 100)")
        return self._public_preview({'document': pack(document), 'status': document['status']})

    def _public_preview(self, row):
        doc = json.loads(row['document'])
        result = {k: v for k, v in doc.items() if not k.startswith('_')}
        result['status'] = row['status']
        result['can_send'] = row['status'] == 'ready' and _date(doc['expires_at']) > self._now()
        return result

    def _get_preview(self, preview_id):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM vacation_previews WHERE id=?', (preview_id,)).fetchone()
        if row is None:
            raise VacationError('Aperçu introuvable dans cet espace.', 'not_found', 404)
        return dict(row)

    def _fail_preview(self, row, status, message, code='conflict'):
        with self.store.db() as db:
            db.execute('UPDATE vacation_previews SET status=? WHERE id=?', (status, row['id']))
            self._event(row['team_id'], status, message, row['id'], db)
        raise VacationError(message, code, 409)

    def _guard(self, document, db=None):
        state = self._state(document['team_id'], db)
        if state['revision'] != document['revision']:
            raise VacationError('Arrêt ou modification de règles : cet aperçu est invalidé.', 'revision', 409)
        if state['paused_reason']:
            raise VacationError(state['paused_reason'], 'paused', 409)
        if _date(document['expires_at']) <= self._now():
            raise VacationError('Aperçu périmé : préparez une nouvelle proposition.', 'expired', 409)
        if document.get('deadline') and _date(document['deadline']) <= self._now():
            raise VacationError('L’échéance officielle Classic est dépassée.', 'deadline', 409)
        if document.get('_scheduled'):
            rule = self._rule_view(state)
            if not rule['enabled'] or (document['automatic'] and rule['mode'] != 'automatic') or not _date(rule['start_at']) <= self._now() < _date(rule['end_at']):
                raise VacationError('L’envoi automatique est arrêté ou hors de sa période autorisée.', 'period', 409)

    async def send(self, preview_id):
        async with self.lock:
            return await self._send(preview_id)

    async def _send(self, preview_id):
        row = self._get_preview(preview_id)
        if row['status'] == 'confirmed':
            return self._public_preview(row)
        if row['status'] != 'ready':
            raise VacationError('Cet aperçu n’est pas envoyable. Un résultat incertain ne sera jamais répété automatiquement.', 'preview_state', 409)
        document = json.loads(row['document'])
        try:
            self._guard(document)
            client, credentials, squad, remote, fixture = await self._fresh(row['team_id'], row['fixture_id'])
            self._guard(document)
            fresh_deadline, blockers = self._deadline(remote, row['fixture_id'], fixture)
            if fresh_deadline:
                document['deadline'] = min(document['deadline'], fresh_deadline) if document['deadline'] else fresh_deadline
            blockers.extend(self._write_configuration(credentials))
            if blockers:
                raise VacationError(blockers[0], 'deadline', 409)
            if _digest(squad) != document['_squad_fingerprint']:
                raise VacationError('L’effectif a changé depuis cet aperçu. Recalculez la proposition.', 'squad_changed', 409)
            if (remote['fingerprint'] if remote else None) != document['_remote_fingerprint']:
                raise VacationError('La composition Classic a changé depuis cet aperçu. La modification distante est conservée.', 'remote_changed', 409)
            canonical = validate_lineup_payload(document['payload'])
        except VacationError as error:
            self._fail_preview(row, 'expired' if error.code == 'expired' else 'cancelled' if error.code == 'revision' else 'conflict', str(error), error.code)
        fingerprint = lineup_fingerprint(canonical)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._guard(document, db)
            # Atomic claims protect against concurrent workers and separate service instances.
            blocked = db.execute("SELECT 1 FROM vacation_attempts WHERE team_id=? AND status IN ('sending','uncertain') LIMIT 1", (row['team_id'],)).fetchone()
            if blocked:
                raise VacationError(_UNCERTAIN, 'paused', 409)
            previous = db.execute('SELECT status FROM vacation_attempts WHERE team_id=? AND fixture_id=? AND fingerprint=?',
                                  (row['team_id'], row['fixture_id'], fingerprint)).fetchone()
            if previous:
                if previous['status'] == 'confirmed' and remote and remote['fingerprint'] == fingerprint:
                    db.execute("UPDATE vacation_previews SET status='confirmed' WHERE id=?", (preview_id,))
                    return self._public_preview({**row, 'status': 'confirmed'})
                if previous['status'] not in ('confirmed', 'abandoned'):
                    raise VacationError('Cette proposition a déjà fait l’objet d’un envoi. Relecture manuelle requise.', 'duplicate', 409)
                # A new, freshly revalidated preview may restore A after B.
                # The old confirmed preview remains immutable and cannot replay.
            db.execute('INSERT OR REPLACE INTO vacation_attempts VALUES(?,?,?,?,?,?)',
                       (row['team_id'], row['fixture_id'], fingerprint, preview_id, 'sending', _iso(self._now())))
            db.execute("UPDATE vacation_previews SET status='sending',process_id=? WHERE id=? AND status='ready'", (_PROCESS_ID, preview_id))
            self._event(row['team_id'], 'sending', 'Envoi enregistré avant transmission à Classic.', preview_id, db)
        transmitted = False
        def before_send():
            nonlocal transmitted
            self._guard(document)
            transmitted = True
        try:
            await client.write_lineup(row['team_id'], row['fixture_id'], canonical, before_send=before_send)
            verified = await client.read_lineup(row['team_id'], row['fixture_id'])
            if not verified or verified['fingerprint'] != fingerprint:
                raise VacationError('La relecture ne confirme pas la composition.', 'verification')
        except BaseException as error:
            if isinstance(error, VacationError) and not transmitted:
                with self.store.db() as db:
                    db.execute("UPDATE vacation_previews SET status='cancelled' WHERE id=?", (preview_id,))
                    db.execute("DELETE FROM vacation_attempts WHERE preview_id=? AND status='sending'", (preview_id,))
                    self._event(row['team_id'], 'cancelled', 'Envoi annulé avant transmission : arrêt, règle ou échéance modifiée.', preview_id, db)
                return self._public_preview({**row, 'status': 'cancelled'})
            self._uncertain(row)
            if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            return self._public_preview({**row, 'status': 'uncertain'})
        with self.store.db() as db:
            db.execute("UPDATE vacation_previews SET status='confirmed' WHERE id=?", (preview_id,))
            db.execute("UPDATE vacation_attempts SET status='confirmed' WHERE preview_id=?", (preview_id,))
            if not document['automatic']:
                db.execute('INSERT OR REPLACE INTO vacation_schema_verifications VALUES(?,?,?,?,?)',
                           (row['team_id'], credentials['m'], lineup_schema(canonical), preview_id, _iso(self._now())))
            self._event(row['team_id'], 'confirmed', 'Composition confirmée par une nouvelle lecture de Classic.', preview_id, db)
        return self._public_preview({**row, 'status': 'confirmed'})

    async def reconcile(self, preview_id, accept_current=False):
        """Read only: resolve a previous uncertain POST without resending it.

        Accepting a different lineup requires a prior observed fingerprint. If
        it changes before acceptance, another explicit review is required.
        """
        async with self.lock:
            row = self._get_preview(preview_id)
            if row['status'] in ('confirmed', 'reconciled'):
                return self._public_preview(row)
            if row['status'] != 'uncertain':
                raise VacationError('Seul un résultat incertain nécessite cette vérification.', 'preview_state', 409)
            document = json.loads(row['document'])
            client, credentials = await self._owned(row['team_id'])
            remote = await client.read_lineup(row['team_id'], row['fixture_id'])
            fingerprint = remote['fingerprint'] if remote else None
            matches = fingerprint == lineup_fingerprint(document['payload'])
            accepted = bool(accept_current and fingerprint and document.get('_reviewed_fingerprint') == fingerprint)
            document['reconciliation_required'] = not matches
            document['current_payload'] = dict(remote['payload']) if remote else None
            document['_reviewed_fingerprint'] = fingerprint
            if not matches and not accepted:
                document['blocking_reasons'] = ['La composition actuellement relue dans Classic diffère de l’envoi. Contrôlez-la puis acceptez explicitement cet état pour lever la suspension. Aucun nouvel envoi n’a été effectué.']
                if not remote:
                    document['blocking_reasons'] = ['La composition actuelle reste indisponible dans Classic. La suspension est conservée ; aucun envoi n’a été effectué.']
                with self.store.db() as db:
                    db.execute('UPDATE vacation_previews SET document=? WHERE id=?', (pack(document), preview_id))
                    self._event(row['team_id'], 'uncertain', document['blocking_reasons'][0], preview_id, db)
                return self._public_preview({**row, 'document': pack(document)})
            status = 'confirmed' if matches else 'reconciled'
            document['reconciliation_required'] = False
            document['blocking_reasons'] = []
            with self.store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE vacation_previews SET status=?,document=? WHERE id=?', (status, pack(document), preview_id))
                db.execute('UPDATE vacation_attempts SET status=? WHERE preview_id=?', ('confirmed' if matches else 'abandoned', preview_id))
                if matches and not document['automatic']:
                    db.execute('INSERT OR REPLACE INTO vacation_schema_verifications VALUES(?,?,?,?,?)',
                               (row['team_id'], credentials['m'], lineup_schema(document['payload']), preview_id, _iso(self._now())))
                pending = db.execute("SELECT 1 FROM vacation_previews WHERE team_id=? AND status IN ('sending','uncertain') LIMIT 1", (row['team_id'],)).fetchone()
                if not pending:
                    state = self._state(row['team_id'], db)
                    rule = json.loads(state['rule']) if state['rule'] else None
                    if rule:
                        rule['enabled'] = False
                    db.execute('INSERT OR REPLACE INTO vacation_rules VALUES(?,?,?,NULL)',
                               (row['team_id'], state['revision']+1, pack(rule) if rule else None))
                message = 'Envoi confirmé par relecture. Le mode vacances reste désactivé.' if matches else 'Composition actuelle acceptée après relecture. Ancien envoi abandonné ; le mode vacances reste désactivé.'
                self._event(row['team_id'], status, message, preview_id, db)
            return self._public_preview({**row, 'status': status, 'document': pack(document)})

    def _uncertain(self, row, db=None):
        if db is None:
            with self.store.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                self._uncertain(row, conn)
            return
        state = self._state(row['team_id'], db)
        rule = json.loads(state['rule']) if state['rule'] else None
        if rule:
            rule['enabled'] = False
        db.execute('INSERT OR REPLACE INTO vacation_rules VALUES(?,?,?,?)',
                   (row['team_id'], state['revision']+1, pack(rule) if rule else None, _UNCERTAIN))
        db.execute("UPDATE vacation_previews SET status='cancelled' WHERE team_id=? AND status='ready'", (row['team_id'],))
        db.execute("UPDATE vacation_previews SET status='uncertain' WHERE id=?", (row['id'],))
        db.execute("UPDATE vacation_attempts SET status='uncertain' WHERE preview_id=?", (row['id'],))
        self._event(row['team_id'], 'uncertain', _UNCERTAIN, row['id'], db)

    async def tick(self):
        results = []
        async with self.lock:
            with self.store.db() as db:
                states = [dict(r) for r in db.execute('SELECT * FROM vacation_rules WHERE rule IS NOT NULL')]
            for state in states:
                rule = self._rule_view(state)
                if not rule['enabled'] or rule['paused_reason']:
                    continue
                if _date(rule['end_at']) <= self._now():
                    self.stop(rule['team_id'])
                    continue
                if _date(rule['start_at']) > self._now():
                    continue
                try:
                    client, _ = await self._owned(rule['team_id'])
                    fixtures = await client.list_fixtures(rule['team_id'])
                    for fixture in fixtures[:100]:
                        start = _date(fixture.get('match_start'))
                        if not start or not self._now() < start <= self._now()+timedelta(hours=rule['lead_hours']):
                            continue
                        # Stop and rules may change during any external read.
                        current = self._state(rule['team_id'])
                        if current['revision'] != state['revision']:
                            break
                        with self.store.db() as db:
                            existing = db.execute("SELECT * FROM vacation_previews WHERE team_id=? AND fixture_id=? AND revision=? AND status IN ('ready','confirmed','uncertain') ORDER BY created_at DESC,rowid DESC LIMIT 1",
                                                  (rule['team_id'], fixture['id'], state['revision'])).fetchone()
                        if existing and (existing['status'] != 'ready' or _date(existing['expires_at']) > self._now()):
                            continue
                        preview = await self._preview(rule['team_id'], fixture['id'], 'optimized', None, automatic=True)
                        if rule['mode'] == 'automatic' and preview['can_send']:
                            preview = await self._send(preview['id'])
                        results.append(preview)
                except (VacationError, ClassicError):
                    self._event(rule['team_id'], 'blocked', 'Exécution suspendue pour ce passage : vérifiez les droits Classic, les échéances et les contrôles de l’aperçu.')
                except Exception:
                    # Opaque external failures must never copy response bodies or secrets.
                    self._event(rule['team_id'], 'error', 'Lecture Classic interrompue. Aucun nouvel envoi prévu pour ce passage.')
        return results
