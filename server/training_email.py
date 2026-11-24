"""Read the English Classic training email format without rendering its HTML."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from email import policy
from email.errors import MessageError
from email.feedparser import BytesFeedParser
from html.parser import HTMLParser
from pathlib import PurePath
from urllib.parse import parse_qsl, urlsplit


SKILLS = frozenset(('stamina', 'handling', 'attack', 'defense', 'technique', 'strength', 'jumping', 'speed', 'agility', 'kicking'))
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 512_000
MAX_PLAYERS = 200
MAX_MIME_PARTS = 50
MAX_MIME_DEPTH = 8
_INVALID = 'Rapport d’entraînement Classic en anglais incomplet, incohérent ou non reconnu.'
_SIZE = 'Ce fichier dépasse la limite de taille du rapport d’entraînement.'
_LIMIT = 'Ce fichier dépasse les limites de structure du rapport d’entraînement.'
_AMBIGUOUS = 'Ce message contient plusieurs rapports d’entraînement. Exportez un seul rapport.'
_FORMAT = 'Choisissez un rapport d’entraînement Classic au format HTML ou EML.'
_PREFACE = re.compile(r'Your team \((.{1,120}?)\) has completed their weekly training for season ([0-9]{1,3}), round ([0-9]{1,2})\.')
_PHASES = ('Team Training', 'Individual Training')
_EMPTY_PHASES = frozenset(('No players', 'No individual training'))
_TRANSFER_ENCODINGS = frozenset(('7bit', '8bit', 'binary', 'quoted-printable', 'base64'))
_BOLD = frozenset(('b', 'strong'))
_BLOCK_ELEMENTS = frozenset(('blockquote', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'ol', 'p', 'td', 'th', 'ul'))
_VOID = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'))
_IGNORED = frozenset(('head', 'iframe', 'math', 'noscript', 'object', 'script', 'style', 'svg', 'template'))
_UNKNOWN = frozenset(('', '-', '—', '–', 'N/A'))
_CHANGE = re.compile(r'\x00([A-Za-z]+)\x00 (popped|dropped) from \x00([^\x00]{1,120})\x00 to \x00([^\x00]{1,120})\x00')


class TrainingEmailError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def _bad():
    raise TrainingEmailError(_INVALID)


def normalize_club_name(name):
    return ' '.join(unicodedata.normalize('NFC', name).split())


@dataclass(eq=False)
class _Node:
    tag: str
    parent: '_Node | None' = field(default=None, repr=False)
    href: str | None = None
    children: list = field(default_factory=list, repr=False)

    def nearest(self, tag):
        node = self.parent
        while node and node.tag != tag:
            node = node.parent
        return node

    def nodes(self, *tags):
        for child in self.children:
            if isinstance(child, _Node):
                if child.tag in tags:
                    yield child
                yield from child.nodes(*tags)

    def _render_text(self, *, mark_bold=False, include_tables=True, line_break=None):
        def render(node):
            if node.tag == 'table' and not include_tables:
                yield line_break or ' '
                return
            if node.tag in ('br', 'hr'):
                yield line_break or ' '
            block_boundary = line_break if node.tag in _BLOCK_ELEMENTS else None
            if block_boundary is not None:
                yield block_boundary
            if mark_bold and node.tag in _BOLD:
                yield '\x00'
            for child in node.children:
                if isinstance(child, str):
                    yield child
                else:
                    yield from render(child)
            if mark_bold and node.tag in _BOLD:
                yield '\x00'
            if block_boundary is not None:
                yield block_boundary

        return ''.join(render(self))

    def text(self, *, mark_bold=False):
        return normalize_club_name(self._render_text(mark_bold=mark_bold))

    def lines_outside_tables(self):
        # Source newlines are ordinary whitespace. Only the HTML structure
        # determines line breaks, and nested player cards contribute no text.
        lines = self._render_text(include_tables=False, line_break='\x00').split('\x00')
        return map(normalize_club_name, lines)


class _ReportHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('document')
        self.stack = [self.root]
        self.ignored = []

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORED or self.ignored:
            if tag not in _VOID:
                self.ignored.append(tag)
                if len(self.ignored) > 64:
                    raise TrainingEmailError(_LIMIT)
            return
        hrefs = [value for key, value in attrs if key == 'href'] if tag == 'a' else []
        if len(hrefs) > 1:
            _bad()
        node = _Node(tag, self.stack[-1], hrefs[0] if hrefs else None)
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)
            if len(self.stack) > 64:
                raise TrainingEmailError(_LIMIT)

    def handle_startendtag(self, tag, attrs):
        # HTMLParser switches to CDATA only after handle_starttag.
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.ignored:
            if tag in self.ignored:
                while self.ignored.pop() != tag:
                    pass
            return
        if tag not in _VOID:
            if self.stack[-1].tag != tag or len(self.stack) == 1:
                _bad()
            self.stack.pop()

    def handle_data(self, data):
        if not self.ignored:
            if '\x00' in data:
                _bad()
            self.stack[-1].children.append(data)


def _decode_html(raw, charset=None):
    if charset is None:
        byte_order_mark = (
            'utf-32' if raw.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')) else
            'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else None
        )
        advertised = re.search(rb'<meta\b[^>]{0,500}\bcharset\s*=\s*["\']?\s*([a-zA-Z0-9_-]{1,40})', raw[:8192], re.I)
        charset = byte_order_mark or (advertised[1].decode('ascii') if advertised else 'utf-8-sig')
    try:
        text = raw.decode(charset).removeprefix('\ufeff')
    except (UnicodeError, LookupError, ValueError):
        raise TrainingEmailError(_INVALID) from None
    return text


def _decoded_size(html):
    try:
        return len(html.encode('utf-8'))
    except UnicodeError:
        raise TrainingEmailError(_INVALID) from None


class _BoundedMailParser(BytesFeedParser):
    def __init__(self):
        super().__init__(policy=policy.default)
        self._part_count = 0

    def _new_message(self):
        # FeedParser calls this before the part is allocated and attached.
        if self._part_count >= MAX_MIME_PARTS or len(self._msgstack) >= MAX_MIME_DEPTH:
            raise TrainingEmailError(_LIMIT)
        super()._new_message()
        self._part_count += 1


def _mime_report(content):
    try:
        parser = _BoundedMailParser()
        for start in range(0, len(content), 64 * 1024):
            parser.feed(content[start:start + 64 * 1024])
        pending = [parser.close()]
        decoded_bytes = 0
        candidate = None
        while pending:
            part = pending.pop()
            if part.defects:
                _bad()
            if part.is_multipart():
                pending.extend(reversed(part.get_payload()))
                continue
            payload = part.get_payload(decode=True) or b''
            decoded_bytes += len(payload)
            if decoded_bytes > MAX_FILE_BYTES:
                raise TrainingEmailError(_SIZE, 413)
            if part.get_content_type() != 'text/html':
                continue
            if part.defects:
                _bad()
            html = _decode_html(payload, part.get_content_charset())
            # Include the Unicode representation in the decoded budget.
            decoded_bytes += max(0, _decoded_size(html) - len(payload))
            if decoded_bytes > MAX_FILE_BYTES:
                raise TrainingEmailError(_SIZE, 413)
            if any(marker in html for marker in (*_PHASES, 'has completed their weekly training', 'club.squad.php')):
                root = _html_tree(html)
                if _mime_report_candidate(root):
                    encodings = part.get_all('Content-Transfer-Encoding', ['7bit'])
                    if len(encodings) != 1 or str(encodings[0]).strip().lower() not in _TRANSFER_ENCODINGS:
                        _bad()
                    if candidate is not None:
                        raise TrainingEmailError(_AMBIGUOUS)
                    candidate = root
        if candidate is None:
            _bad()
        return candidate
    except RecursionError:
        raise TrainingEmailError(_LIMIT) from None
    except MessageError:
        raise TrainingEmailError(_INVALID) from None


def _number(value, maximum, minimum=0):
    if not re.fullmatch(r'[0-9]{1,15}', value) or not minimum <= int(value) <= maximum:
        _bad()
    return int(value)


def _csr(value):
    if value in _UNKNOWN:
        return None
    if ',' in value or ' ' in value:
        if not re.fullmatch(r'[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?: [0-9]{3})+', value):
            _bad()
    return _number(value.replace(',', '').replace(' ', ''), 10**12)


def _label(value):
    value = normalize_club_name(value)
    if not 0 < len(value) <= 120 or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value):
        _bad()
    return value


def _skill(label):
    code = label.lower()
    if code == 'defence':
        code = 'defense'
    if code not in SKILLS:
        _bad()
    return code


def _link_args(link, path):
    if not link.href or len(link.href) > 2048:
        return None
    try:
        parts = urlsplit(link.href)
        if parts.path != path or parts.scheme not in ('', 'http', 'https'):
            return None
        if parts.netloc and (parts.hostname not in ('blackoutrugby.com', 'www.blackoutrugby.com') or parts.username or parts.password):
            return None
        if parts.scheme and not parts.netloc:
            return None
        return (parse_qsl(parts.query, keep_blank_values=True, max_num_fields=24)
                + parse_qsl(parts.fragment, keep_blank_values=True, max_num_fields=24))
    except ValueError:
        _bad()


def _declared_id(params, aliases, *, required=False):
    ids = [value for key, value in params if key.lower() in aliases]
    if not ids and not required:
        return None
    if len(ids) != 1 or not re.fullmatch(r'[1-9][0-9]{0,14}', ids[0]):
        _bad()
    return ids[0]


def _links(node, path):
    for link in node.nodes('a'):
        params = _link_args(link, path)
        if params is not None:
            yield link, params


def _rows(table):
    return [row for row in table.nodes('tr') if row.nearest('table') is table]


def _cells(row):
    return [node for node in row.nodes('td', 'th') if node.nearest('tr') is row]


def _skills_trained(node, *, individual):
    # Team skill slots precede player cards. Individual sessions are in the card header.
    lists = [item for item in node.nodes('ul', 'ol') if item.nearest('table') is node.nearest('table')]
    headings = [item for item in node.nodes(*_BOLD) if item.nearest('table') is node.nearest('table') and item.text() == 'Skills Trained']
    if not lists and not headings:
        return None
    if len(headings) != 1 or len(lists) != 1:
        _bad()
    items = list(lists[0].nodes('li'))
    if len(items) > (len(SKILLS) if individual else 4):
        raise TrainingEmailError(_LIMIT)
    if not individual:
        return [_skill(item.text()) for item in items]

    skills = {}
    for item in items:
        match = re.fullmatch(r'\x00([A-Za-z]+)\x00 ?([0-9]{1,4}) sessions?(?: from (.{1,120}?)(?: \(Level ([0-9]{1,4})\))?)?', item.text(mark_bold=True))
        if not match:
            _bad()
        code = _skill(match[1])
        if code in skills:
            _bad()
        trainer = None
        if match[3] is not None:
            if '(Level ' in match[3]:
                _bad()
            trainer = {'name': _label(match[3]), 'level': _number(match[4], 1000) if match[4] else None, 'type': None}
        skills[code] = {'skill': code, 'sessions': _number(match[2], 1000, 1), 'pops': None, 'trainer': trainer}
    return skills


def _change_level(value):
    value = normalize_club_name(value)
    if value in _UNKNOWN:
        return None, None
    if value.isascii() and value.isdecimal():
        return _number(value, 1000), None
    if not value or not all(char.isalpha() or char in " -’'" for char in value):
        _bad()
    return None, _label(value)


def _changes(cell):
    raw = cell.text(mark_bold=True).replace('\x00No pops\x00', 'No pops').replace('\x00No drops\x00', 'No drops')
    pops = [] if re.search(r'(?:^| )No pops\.?(?: |$)', raw) else None
    drops = [] if re.search(r'(?:^| )No drops\.?(?: |$)', raw) else None
    remainder = re.sub(r'(?:^| )(?:No pops|No drops)\.?(?= |$)', ' ', raw).strip()
    seen = set()
    for match in _CHANGE.finditer(remainder):
        code = _skill(match[1])
        before, before_label = _change_level(match[3])
        after, after_label = _change_level(match[4])
        rise = match[2] == 'popped'
        if (code in seen or (pops if rise else drops) == []
                or (before is not None and after is not None and ((after - before) if rise else (before - after)) <= 0)
                or (before_label is not None and after_label is not None and before_label.lower() == after_label.lower())):
            _bad()
        seen.add(code)
        change = {'skill': code, 'before': before, 'after': after}
        if before_label is not None:
            change['before_label'] = before_label
        if after_label is not None:
            change['after_label'] = after_label
        if rise:
            pops = (pops or []) + [change]
        else:
            drops = (drops or []) + [change]
    if _CHANGE.sub('', remainder).strip(' .'):
        _bad()
    return (sorted(pops, key=lambda item: item['skill']) if pops else pops,
            sorted(drops, key=lambda item: item['skill']) if drops else drops)


def _before_after(text):
    if (text.count('Before:') > 1 or text.count('After:') > 1
            or not text.startswith(('Before:', 'After:'))):
        _bad()
    before, _, after = text.partition('After:')
    if 'Before:' in after:
        _bad()
    return before.removeprefix('Before:').strip(), after.strip()


def _player(card, *, individual):
    rows = _rows(card)
    if len(rows) != 2:
        _bad()
    links = list(_links(rows[0], '/game/club.squad.php'))
    if len(links) != 1:
        _bad()
    link, params = links[0]
    player_id = _declared_id(params, ('player', 'playerid'), required=True)
    player = {'player_id': player_id, 'player_name': _label(link.text()), 'csr_before': None, 'csr_after': None,
              'energy_before': None, 'energy_after': None}
    pops = drops = None
    seen = set()
    for cell in _cells(rows[1]):
        text = cell.text()
        if not text:
            continue
        heading, _, _ = cell.text(mark_bold=True).removeprefix('\x00').partition('\x00')
        values = text.removeprefix(heading).strip()
        kind = heading if heading in ('CSR', 'Energy Levels') else 'changes'
        if kind in seen:
            _bad()
        seen.add(kind)
        if kind == 'CSR':
            player['csr_before'], player['csr_after'] = map(_csr, _before_after(values.strip()))
        elif kind == 'Energy Levels':
            before, after = _before_after(values.strip())
            player['energy'] = {'kind': 'label', 'before': None if before in _UNKNOWN else _label(before),
                                'after': None if after in _UNKNOWN else _label(after)}
        else:
            pops, drops = _changes(cell)
    if not individual:
        player.update(pops=pops, drops=drops)
        return player

    skills = _skills_trained(rows[0], individual=True)
    player['skills'] = None if skills is None else list(skills.values())
    if drops is not None:
        player['drops'] = drops
    if skills is None or not skills:
        if pops is not None:
            player['pops'] = pops
    elif pops is not None:
        by_skill = {change['skill']: change for change in pops}
        for code, skill in skills.items():
            skill['pops'] = [by_skill[code]] if code in by_skill else []
        unmatched = [change for change in pops if change['skill'] not in skills]
        if unmatched:
            player['pops'] = unmatched
    if player['skills']:
        player['skills'].sort(key=lambda item: item['skill'])
    return player


def _phase_empty_markers(rows, table):
    markers = set()
    for row in rows:
        for node in (row, *row.nodes('td', 'th', 'p', 'div', 'span', 'b', 'strong')):
            if node.nearest('table') is not table:
                continue
            for line in node.lines_outside_tables():
                marker = line.removesuffix('.')
                if marker in _EMPTY_PHASES:
                    markers.add(marker)
    return markers


def _phase(rows, table, *, individual):
    cards = [card for row in rows for card in row.nodes('table') if card.nearest('table') is table]
    if len(cards) > MAX_PLAYERS:
        raise TrainingEmailError(_LIMIT)
    empty_markers = _phase_empty_markers(rows, table)
    if not individual and 'No individual training' in empty_markers:
        _bad()
    # A phase supplies player cards or explicitly reports that it is empty.
    if bool(cards) == bool(empty_markers):
        _bad()
    players = {}
    for card in cards:
        player = _player(card, individual=individual)
        if player['player_id'] in players:
            _bad()
        players[player['player_id']] = player
    phase = {'players': sorted(players.values(), key=lambda item: int(item['player_id']))}
    if not individual:
        skills = [trained for row in rows if (trained := _skills_trained(row, individual=False)) is not None]
        if len(skills) > 1:
            _bad()
        phase['skills'] = skills[0] if skills else None
    return phase


def _html_tree(html):
    parser = _ReportHTML()
    try:
        parser.feed(html)
        parser.close()
    except AssertionError:
        raise TrainingEmailError(_INVALID) from None
    if len(parser.stack) != 1 or parser.ignored:
        _bad()
    return parser.root


def _phase_markers(root):
    markers = {phase: [] for phase in _PHASES}
    for node in root.nodes(*_BOLD, 'h1', 'h2', 'h3', 'h4'):
        text = node.text()
        if text in markers and node.nearest('tr') is not None:
            markers[text].append(node.nearest('tr'))
    return markers


def _mime_report_candidate(root):
    visible = root.text()
    if _PREFACE.search(visible):
        return True
    phases = _phase_markers(root)
    if not any(phases.values()):
        return False
    # The declaration can be missing from a forwarded fragment. A phase
    # heading alone is also common in unrelated agendas.
    if any(_links(root, '/game/club.squad.php')) or any(_links(root, '/game/club.office.php')):
        return True
    return all(phases.values()) and any(marker in visible for marker in ('Skills Trained', *_EMPTY_PHASES))


def _html_report(root):
    markers = _phase_markers(root)
    if any(len(rows) != 1 for rows in markers.values()):
        _bad()
    team_marker, individual_marker = (markers[name][0] for name in _PHASES)
    table = team_marker.nearest('table')
    if table is None or individual_marker.nearest('table') is not table:
        _bad()
    rows = _rows(table)
    team_index, individual_index = rows.index(team_marker), rows.index(individual_marker)
    declarations = [(link, params, row) for row in rows[:team_index]
                    for link, params in _links(row, '/game/club.office.php')]
    if not 0 < team_index < individual_index or len(declarations) != 1:
        _bad()
    club, params, preface = declarations[0]
    periods = list(_PREFACE.finditer(preface.text()))
    if len(periods) != 1 or periods[0][1] != club.text():
        _bad()
    period = periods[0]
    team = _phase(rows[team_index + 1:individual_index], table, individual=False)
    individual = _phase(rows[individual_index + 1:], table, individual=True)
    team_names = {player['player_id']: player['player_name'] for player in team['players']}
    if any(team_names.get(player['player_id'], player['player_name']) != player['player_name'] for player in individual['players']):
        _bad()
    return {'club_name': _label(club.text()), 'club_id': _declared_id(params, ('team', 'teamid', 'club', 'clubid')),
            'season': _number(period[2], 999, 1), 'round': _number(period[3], 16, 1), 'team': team, 'individual': individual}


def parse_training_email(content: bytes, filename: str) -> dict:
    """Return normalized report fields and declared identity, with no raw source."""
    suffix = PurePath(filename).suffix.lower()
    if suffix not in ('.html', '.eml'):
        raise TrainingEmailError(_FORMAT)
    if len(content) > MAX_FILE_BYTES:
        raise TrainingEmailError(_SIZE, 413)
    if suffix == '.eml':
        root = _mime_report(content)
    else:
        html = _decode_html(content)
        if _decoded_size(html) > MAX_FILE_BYTES:
            raise TrainingEmailError(_SIZE, 413)
        root = _html_tree(html)
    document = _html_report(root)
    document.update(schema_version=2, report_id=None, observed_at=None, key=None,
                    provenance={'source': 'Classic email', 'source_format': suffix[1:],
                                'source_game_date': None, 'source_observed_at': None})
    if len(json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode()) > MAX_DOCUMENT_BYTES:
        raise TrainingEmailError(_SIZE, 413)
    return document
