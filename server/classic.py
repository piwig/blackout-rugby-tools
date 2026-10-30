"""Restricted Classic adapter. Never log URLs, response errors or credentials."""
import asyncio
import base64
import hashlib
import json
import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlencode
import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from defusedxml import ElementTree as ET

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
BASE='https://classic-api.blackoutrugby.com/'

class ClassicError(ValueError):pass

class ClassicWriteUncertain(ClassicError):
    """A POST may have reached Classic. Read back; never automatically retry."""


class _RequestGate:
    """One process-wide gate, including separate event loops and manager spaces."""
    def __init__(self, interval=3):
        self.interval = interval
        self.lock = threading.Lock()
        self.finished = None

    @asynccontextmanager
    async def hold(self):
        while not self.lock.acquire(blocking=False):
            await asyncio.sleep(.05)
        try:
            if self.finished is not None:
                delay = self.interval - (time.monotonic() - self.finished)
                while delay > 0:
                    await asyncio.sleep(delay)
                    delay = self.interval - (time.monotonic() - self.finished)
            yield
        finally:
            self.finished = time.monotonic()
            self.lock.release()


_REQUEST_GATE = _RequestGate()
_UNCERTAIN = 'Résultat Classic incertain. Relisez la composition dans le jeu avant toute nouvelle tentative.'
_REFUSED = 'Classic refuse cette requête : vérifiez les clés et les droits du manager.'
_TACTICS = ('pickandgo', 'driving', 'expansive', 'creative', 'kicking', 'kickfortouch', 'upandunder', 'discipline')
_SLOTS = tuple(str(i) for i in range(1, 16)) + tuple(f'b{i}' for i in range(1, 8))
_ROLES = ('captain', 'kicker', 'captain1', 'captain2', 'kicker1', 'kicker2')
_REPLACEMENTS = tuple(f'r{rank}p{i}' for rank in (1, 2) for i in range(1, 16))
_SUB_FIELDS = ('replace', 'with', 'minute', 'scenario', 'margin', 'enabled')
_REQUIRED = set(_SLOTS + _ROLES + _REPLACEMENTS + _TACTICS + ('mode', 'defense', 'intensity', 'dropgoals'))
_ZONE_FIELDS = {f'{key}{zone}' for zone in range(1, 5) for key in _TACTICS}
_REQUIRED.update(_ZONE_FIELDS)


def _integer(value, minimum=0, maximum=2**63-1):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'[0-9]{1,19}', str(value)):
        raise ClassicError('Composition Classic invalide : une valeur entière est requise.')
    number = int(value)
    if not minimum <= number <= maximum:
        raise ClassicError('Composition Classic invalide : valeur hors limites.')
    return str(number)


def _utc(value):
    """Only offset-aware JSON dates; legacy BRT integer timestamps are ambiguous."""
    if value in (None, '', 0, '0'):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec='seconds')
    except (ValueError, OverflowError):
        raise ClassicError('Date Classic non reconnue ou sans fuseau horaire.') from None


def validate_lineup_payload(payload):
    """Validate a complete, flat senior lineup; return canonical string values.

    Never repair or remove player references silently. The caller must preserve
    all existing tactics and substitution rules when changing the players.
    """
    if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
        raise ClassicError('Composition Classic invalide.')
    # Current live Classic basic lineups can omit all zones. A partial zone
    # configuration is never guessed or completed from global tactics.
    with_zones = payload.get('mode') == 'zone' or bool(payload.keys() & _ZONE_FIELDS)
    required = _REQUIRED if with_zones else _REQUIRED - _ZONE_FIELDS
    if not required.issubset(payload):
        raise ClassicError('Composition Classic incomplète : joueurs, rôles et tactiques sont requis.')
    sub_indices = set()
    for key in payload.keys() - _REQUIRED - {'b8'}:
        match = re.fullmatch(r'sub(replace|with|minute|scenario|margin|enabled)([1-9][0-9]?)', key)
        if not match:
            raise ClassicError('Champ de composition Classic non autorisé.')
        sub_indices.add(int(match[2]))
    if sub_indices and sub_indices != set(range(1, max(sub_indices) + 1)):
        raise ClassicError('Les règles de remplacement doivent être numérotées sans interruption.')
    slots = _SLOTS + ('b8',) if 'b8' in payload else _SLOTS
    result = {key: _integer(payload[key], 1) for key in slots}
    selected = set(result.values())
    if len(selected) != len(slots):
        raise ClassicError('La composition Classic doit contenir des joueurs distincts.')
    starters = {result[str(i)] for i in range(1, 16)}
    for key in _ROLES + _REPLACEMENTS:
        value = _integer(payload[key])
        if key in ('captain', 'kicker') and value not in starters:
            raise ClassicError('Le capitaine et le buteur doivent être titulaires.')
        if value != '0' and value not in selected:
            raise ClassicError('Un rôle ou un remplacement référence un joueur absent de la composition.')
        result[key] = value
    for suffix in ('', '1', '2', '3', '4') if with_zones else ('',):
        for key in _TACTICS:
            result[key + suffix] = _integer(payload[key + suffix], 1 if key == 'discipline' else 0, 3 if key == 'discipline' else 100)
        if sum(int(result[key + suffix]) for key in _TACTICS[:4]) != 100:
            raise ClassicError('Les quatre tactiques d’attaque doivent totaliser 100 %.')
        # The read examples leave a remainder for territory. Do not redistribute it.
        if int(result['kickfortouch' + suffix]) + int(result['upandunder' + suffix]) > 100:
            raise ClassicError('Les tactiques de jeu au pied dépassent 100 %.')
    for key, allowed in (('mode', ('basic', 'zone')), ('defense', ('drift', 'rush', 'manonman'))):
        if payload[key] not in allowed:
            raise ClassicError('Tactique Classic non reconnue.')
        result[key] = payload[key]
    result['intensity'] = _integer(payload['intensity'], 1, 3)
    result['dropgoals'] = _integer(payload['dropgoals'], 0, 1)
    for index in sorted(sub_indices):
        if any(f'sub{field}{index}' not in payload for field in _SUB_FIELDS):
            raise ClassicError('Règle de remplacement Classic incomplète.')
        for field in ('replace', 'with'):
            key = f'sub{field}{index}'
            result[key] = _integer(payload[key], 1)
            if result[key] not in selected:
                raise ClassicError('Une substitution référence un joueur absent de la composition.')
        if result[f'subreplace{index}'] == result[f'subwith{index}']:
            raise ClassicError('Une substitution doit concerner deux joueurs différents.')
        minute = str(payload[f'subminute{index}'])
        if not re.fullmatch(r'(?:[5-9]|[1-7][0-9])\+?', minute) or int(minute.rstrip('+')) not in range(5, 76, 5):
            raise ClassicError('Minute de remplacement Classic invalide.')
        result[f'subminute{index}'] = minute
        scenario = payload[f'subscenario{index}']
        if scenario not in ('any', 'wal', 'wlt', 'lal', 'llt', 'mal', 'mlt'):
            raise ClassicError('Scénario de remplacement Classic invalide.')
        result[f'subscenario{index}'] = scenario
        result[f'submargin{index}'] = _integer(payload[f'submargin{index}'])
        result[f'subenabled{index}'] = _integer(payload[f'subenabled{index}'], 0, 1)
    return result


def lineup_fingerprint(payload):
    canonical = validate_lineup_payload(payload)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def lineup_schema(payload):
    canonical = validate_lineup_payload(payload)
    size = '23' if 'b8' in canonical else '22'
    tactics = 'zones' if canonical.keys() & _ZONE_FIELDS else 'basic'
    return f'classic-{size}-{tactics}'


def _lineup_payload(raw):
    known_slots = {f'p{i}' for i in range(1, 16)} | {f'b{i}' for i in range(1, 9)}
    known_zones = {f'zone{i}' for i in range(1, 5)}
    if any((re.fullmatch(r'[pb][0-9]+', key) and key not in known_slots) or
           (re.fullmatch(r'zone[0-9]+', key) and key not in known_zones) for key in raw):
        raise ClassicError('Le format de composition Classic a changé : actualisation de l’outil nécessaire.')
    payload = {key: raw[key] for key in _REQUIRED if key in raw and not key.isdigit()}
    payload.update({str(i): raw[f'p{i}'] for i in range(1, 16) if f'p{i}' in raw})
    if 'b8' in raw:
        payload['b8'] = raw['b8']
    if payload.get('mode') == 'zoned':
        payload['mode'] = 'zone'
    zone_numbers = range(1, 5) if payload.get('mode') == 'zone' or any(f'zone{i}' in raw for i in range(1, 5)) else ()
    for i in zone_numbers:
        zone = raw.get(f'zone{i}')
        if not isinstance(zone, dict):
            raise ClassicError('Tactiques privées Classic manquantes.')
        for key in _TACTICS:
            if key in zone:
                payload[f'{key}{i}'] = zone[key]
        if 'kickforterritory' in zone:
            territory = int(_integer(zone['kickforterritory'], 0, 100))
            if territory + int(_integer(zone.get('kickfortouch'), 0, 100)) + int(_integer(zone.get('upandunder'), 0, 100)) != 100:
                raise ClassicError('Tactiques de zone Classic incohérentes.')
    # Absence is not treated as an empty set: doing so could erase unseen rules.
    subs = raw.get('subs')
    if isinstance(subs, dict):
        try:
            items = sorted(subs.items(), key=lambda item: int(item[0]))
        except (ValueError, TypeError):
            raise ClassicError('Règles de remplacement Classic non reconnues.') from None
        rules = [item[1] for item in items]
    elif isinstance(subs, list):
        rules = subs
    else:
        raise ClassicError('Règles de remplacement Classic manquantes.')
    for index, rule in enumerate(rules, 1):
        if not isinstance(rule, dict) or any(field not in rule for field in _SUB_FIELDS):
            raise ClassicError('Règle de remplacement Classic incomplète.')
        if rule.keys() - set(_SUB_FIELDS) - {'index'}:
            raise ClassicError('Condition de remplacement Classic non reconnue.')
        payload.update({f'sub{field}{index}': rule[field] for field in _SUB_FIELDS})
    return validate_lineup_payload(payload)


class ClassicClient:
    def __init__(self,credentials):
        self.credentials={k:str(v) for k,v in credentials.items() if k in ['d','dk','m','mk','iv'] and v is not None}

    def _check_credentials(self, manager=False):
        if not self.credentials.get('d') or not self.credentials.get('dk'):raise ClassicError('Ajoutez vos identifiants développeur Classic dans Connexion & données.')
        if manager and (not self.credentials.get('m') or not self.credentials.get('mk')):
            raise ClassicError('Ajoutez les clés du manager propriétaire de ce club.')

    def _encrypt(self, values):
        key = self.credentials['dk'].encode()
        iv = self.credentials.get('iv', '').encode()
        if len(key) not in (16, 24, 32) or len(iv) != 16:
            raise ClassicError('Une clé développeur AES valide et son IV de 16 caractères sont requis pour envoyer une composition.')
        plain = urlencode(values).encode()
        plain += b'\0' * (16 - len(plain) % 16)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        return base64.b64encode(cipher.update(plain) + cipher.finalize()).decode()

    async def _send(self, method, query, data=None, before_send=None):
        write = method == 'POST'
        try:
            async with _REQUEST_GATE.hold():
                async with httpx.AsyncClient(timeout=25,follow_redirects=False) as client:
                    # Synchronous guard runs after queue/throttle waits, immediately
                    # before sending. Its exceptions are deliberate cancellations.
                    if before_send is not None:
                        before_send()
                    async with client.stream(method,BASE,params=query,data=data) as response:
                        if response.status_code!=200:
                            if write:raise ClassicWriteUncertain(_UNCERTAIN)
                            raise ClassicError('API Classic indisponible. Réessayez plus tard.')
                        chunks=[];size=0
                        async for chunk in response.aiter_bytes():
                            size+=len(chunk)
                            if size>8_000_000:
                                if write:raise ClassicWriteUncertain(_UNCERTAIN)
                                raise ClassicError('Réponse Classic trop volumineuse.')
                            chunks.append(chunk)
            return b''.join(chunks)
        except httpx.HTTPError:
            if write:raise ClassicWriteUncertain(_UNCERTAIN) from None
            raise ClassicError('Impossible de joindre l’API Classic. Les données précédentes sont conservées.') from None

    def _json(self, data, write=False):
        try:doc=json.loads(data)
        except ValueError:
            if write:raise ClassicWriteUncertain(_UNCERTAIN) from None
            raise ClassicError('Réponse Classic non JSON. Vérifiez les clés et les droits du manager.') from None
        if isinstance(doc,dict) and (doc.get('error') or doc.get('errors') or doc.get('status') == 'Failed'):
            raise ClassicError(_REFUSED)
        if not isinstance(doc,dict) or (write and doc.get('status') != 'Ok'):
            if write:raise ClassicWriteUncertain(_UNCERTAIN)
            raise ClassicError(_REFUSED)
        if doc.get('status') not in (None, 'Ok'):
            raise ClassicError(_REFUSED)
        return doc

    async def request(self,resource,**params):
        self._check_credentials()
        if resource not in ['p','t','f','ls','me','m','lu']:raise ClassicError('Ressource non autorisée.')
        if set(params) & {'r','d','dk','m','mk','iv','er','json','update','delete','default','saved'}:
            raise ClassicError('Paramètre Classic non autorisé.')
        query={**{k:v for k,v in self.credentials.items() if k != 'iv'},'r':resource,'json':'1',**params}
        if resource=='me':query.pop('json')
        if self.credentials.get('iv'):
            encrypted = self._encrypt({k:v for k,v in query.items() if k not in ('d','dk')})
            query = {'d':self.credentials['d'],'er':encrypted}
        data = await self._send('GET', query)
        if resource=='me':
            try:
                root=ET.fromstring(data)
                if any(e.tag.lower().endswith('error') for e in root.iter()):raise ClassicError('Classic refuse cette requête : vérifiez les clés et les droits du manager.')
                return {'events':parse_commentary(root)}
            except ClassicError:raise
            except Exception:raise ClassicError('Commentaire XML Classic non reconnu.') from None
        return self._json(data)

    async def read_lineup(self, team_id, fixture_id='0'):
        self._check_credentials(manager=True)
        team_id, fixture_id = _integer(team_id, 1), _integer(fixture_id)
        doc = await self.request('lu', teamid=team_id, fixtureid=fixture_id)
        rows = doc.get('lineups')
        if rows in ([], {}):
            return None
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ClassicError('Composition Classic non reconnue.')
        raw = rows[0]
        if str(raw.get('teamid')) != team_id or str(raw.get('fixtureid')) != fixture_id:
            raise ClassicError('La composition Classic ne correspond pas au club ou au match demandé.')
        payload = _lineup_payload(raw)
        return {'team_id':team_id, 'fixture_id':fixture_id, 'payload':payload,
                'fingerprint':lineup_fingerprint(payload), 'schema':lineup_schema(payload), 'deadline':_utc(raw.get('deadline')),
                'tactics_deadline':_utc(raw.get('tacticsdeadline'))}

    async def list_fixtures(self, team_id):
        team_id = _integer(team_id, 1)
        doc = await self.request('f', future=team_id)
        rows = doc.get('fixtures')
        if not isinstance(rows, (dict, list)):
            raise ClassicError('Calendrier Classic non reconnu.')
        fixtures = []
        for raw in rows.values() if isinstance(rows, dict) else rows:
            if not isinstance(raw, dict):raise ClassicError('Match Classic non reconnu.')
            home, away = _integer(raw.get('hometeamid'), 1), _integer(raw.get('guestteamid'), 1)
            if team_id not in (home, away):raise ClassicError('Le calendrier Classic contient un autre club.')
            start = _utc(raw.get('matchstart'))
            if not start:raise ClassicError('Date de match Classic manquante.')
            fixtures.append({'id':_integer(raw.get('id'), 1), 'team_id':team_id,
                             'home_team_id':home, 'away_team_id':away,
                             'competition':str(raw.get('competition', ''))[:80], 'match_start':start})
        return sorted(fixtures, key=lambda fixture:(fixture['match_start'], fixture['id']))

    async def write_lineup(self, team_id, fixture_id, payload, *, before_send=None):
        self._check_credentials(manager=True)
        team_id, fixture_id = _integer(team_id, 1), _integer(fixture_id)
        canonical = validate_lineup_payload(payload)
        values = {'dk':self.credentials['dk'],'m':self.credentials['m'],'mk':self.credentials['mk'],'r':'lu','json':'1',
                  'update':'1','teamid':team_id,'fixtureid':fixture_id,**canonical}
        encrypted = self._encrypt(values)
        data = await self._send('POST', {'d':self.credentials['d']}, {'er':encrypted}, before_send=before_send)
        self._json(data, write=True)
        return {'status':'submitted','requires_verification':True}

def classify_attack(text):
    """Conservative, versioned EN commentary heuristics, never official tactics."""
    text=re.sub(r'\[[^\]]+\]','',text).lower()
    rules=[
      ('png',r'pick(?:s|ing)?\s*(?:and|&|n|[’\x27]n[’\x27])\s*go|picks? (?:it|the ball) up (?:and|then) (?:drives|goes)'),
      ('crea',r'something creative|creative (?:move|play|attack)|(?:triple |double )?scissors|switch move|loop move|dummy runner|decoy runner'),
      ('large',r'out wide|go(?:es|ing)? wide|expansive (?:move|play|attack)|spread(?:s|ing)? the ball|through the hands'),
      ('percu',r'on the drive|crash ball|crash-ball|takes? the ball up|hits? it up|charges? (?:straight )?at (?:the )?(?:defence|defense)'),
      ('kick',r'grubber|up.and.under|box kick|chip kick|punts? (?:the ball )?(?:downfield|upfield|into touch)|hoists? (?:the ball )?high')]
    for category,pattern in rules:
        if re.search(pattern,text):return category
    return None

def parse_commentary(root):
    """Preserve raw fields and label every inferred tactical classification."""
    events=[]
    previous=None
    for element in root.iter():
        fields=dict(element.attrib)
        fields.update({child.tag.rsplit('}',1)[-1]:(child.text or '').strip() for child in element if not list(child)})
        if ('field' in fields or 'possession' in fields) and any(k in fields for k in ['text','commentary','comment','att']):
            event={k:fields[k] for k in ['id','field','possession','att','time','minute','text','commentary','comment','gametime','half','homescore','guestscore'] if k in fields}
            raw=event.get('commentary',event.get('text',event.get('comment','')))
            event['text']=re.sub(r'\[[^\]]+\]','',raw)
            if event.get('gametime','').isdigit():
                seconds=int(event['gametime']);event['time']=f'{seconds//60}:{seconds%60:02d}'
            if not event.get('att'):
                attack=classify_attack(raw)
                if attack:
                    event['att']=attack;event['att_origin']='commentary-rule';event['rule_version']='1'
                    # Engine possession is post-action: use prior possession on a turnover.
                    if previous in ['0','1'] and previous!=event.get('possession'):
                        event['possession_reported']=event.get('possession');event['possession']=previous
            previous=fields.get('possession',previous)
            events.append(event)
    if not events:
        # Preserve readable evidence even when this engine schema has no mapped fields.
        for element in root.iter():
            if element.tag.rsplit('}',1)[-1].lower() in ['comment','commentary','event','text'] and element.text and len(element.text.strip())>5:
                events.append({'text':element.text.strip()[:2000]})
    return events[:20000]
