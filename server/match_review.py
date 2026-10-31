"""Private, revisioned human annotations over immutable imported match events.

Suggestions use exact, explainable templates from opted-in human examples. They
never classify an event or choose its side/zone without an explicit annotation.
"""
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import attack_label, attack_summary
from .storage import now, pack


PREFIX = 'match_review:'
TEMPLATE_VERSION = '1'
Attack = Literal['percu', 'png', 'large', 'crea', 'kick']
Classification = Literal['attack', 'non_attack', 'unclassified']
StrictSide = Annotated[int, Field(strict=True, ge=0, le=1)]
StrictZone = Annotated[int, Field(strict=True, ge=0, le=5)]


class AnnotationChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    event_key: str = Field(min_length=1, max_length=240)
    reset: bool = False
    classification: Classification | None = None
    att: Attack | None = None
    possession: StrictSide | None = None
    field: StrictZone | None = None
    learn: bool = False

    @model_validator(mode='after')
    def consistent_choice(self):
        if self.reset:
            if self.model_fields_set - {'event_key', 'reset'}:
                raise ValueError('La restauration ne doit contenir aucune nouvelle annotation.')
        elif (self.classification is None or
              not {'possession', 'field'}.issubset(self.model_fields_set) or
              (self.classification == 'attack') != (self.att is not None) or
              (self.classification == 'unclassified' and self.learn)):
            raise ValueError('Vérifiez la catégorie, le type d’attaque, le côté et la zone.')
        return self


class AnnotationSave(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: int = Field(ge=0, le=2147483647)
    expected_source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    changes: list[AnnotationChange] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def unique_changes(self):
        if len({change.event_key for change in self.changes}) != len(self.changes):
            raise ValueError('Un événement ne peut être modifié deux fois dans la même demande.')
        return self


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_digest(doc):
    """Digest of the persisted source, never a decorated response or a timestamp."""
    return _hash(doc)


def _key(doc):
    return f'{PREFIX}{doc["type"]}:{doc["id"]}'


def _identities(doc):
    events = doc.get('events', [])
    fingerprints = [_hash(event) for event in events]
    counts = Counter(fingerprints)
    ids = Counter(str(event['id']) for event in events if event.get('id') not in (None, ''))
    indexes = Counter(str(event['index']) for event in events if event.get('index') not in (None, ''))
    duplicate_scope = source_digest(doc) if any(count > 1 for count in counts.values()) else None
    identities = []
    for position, (event, fingerprint) in enumerate(zip(events, fingerprints)):
        if event.get('id') not in (None, '') and ids[str(event['id'])] == 1:
            key = f'id:{_hash(str(event["id"]))[:16]}:{fingerprint}'
        elif event.get('index') not in (None, '') and indexes[str(event['index'])] == 1:
            key = f'index:{_hash(str(event["index"]))[:16]}:{fingerprint}'
        elif counts[fingerprint] == 1:
            key = 'event:' + fingerprint
        else:
            # With identical rows and no unique identity there is no defensible
            # cross-import alignment. Only the exact same source may reuse it.
            key = f'duplicate:{duplicate_scope}:{position}:{fingerprint}'
        identities.append((key, fingerprint))
    return identities


def _read_review(db, doc):
    row = db.execute('SELECT value FROM kv WHERE key=?', (_key(doc),)).fetchone()
    return json.loads(row['value']) if row else {'revision': 0, 'annotations': {}}


def commentary_template(event):
    text = next((event.get(key) for key in ('commentary', 'text', 'comment') if event.get(key)), '')
    if not isinstance(text, str):
        return None
    text = re.sub(r'\[player id=[0-9]{1,15} p=[0-9]{1,2}\][^\[\]]{1,150}\[/player\]', '{player}', text, flags=re.I)
    text = re.sub(r'\[team id=[0-9]{1,15}\][^\[\]]{1,150}\[/team\]', '{team}', text, flags=re.I)
    # Formatting alone is dispensable. Unknown markup and literal names remain
    # significant; removing arbitrary bracket contents could erase the action.
    text = re.sub(r'\[/?(?:b|i|u)\]', '', text, flags=re.I)
    text = re.sub(r'\b\d+(?:[.,]\d+)?\b', '{number}', text.casefold())
    text = re.sub(r'\s+', ' ', text).strip()
    words = re.findall(r'[^\W\d_]+', re.sub(r'\{(?:number|player|team)\}', '', text), flags=re.UNICODE)
    if len(words) < 4 or sum(map(len, words)) < 16 or len(text) > 2000:
        return None
    return text


def _learning_examples(db):
    examples = defaultdict(list)
    rows = db.execute("SELECT m.payload,k.value FROM matches m JOIN kv k ON k.key=? || m.type || ':' || m.id",
                      (PREFIX,))
    for row in rows:
        doc, review = json.loads(row['payload']), json.loads(row['value'])
        for event, (key, fingerprint) in zip(doc.get('events', []), _identities(doc)):
            annotation = review['annotations'].get(key)
            if not annotation or not annotation.get('learn') or annotation.get('source_fingerprint') != fingerprint:
                continue
            template = commentary_template(event)
            if not template or annotation['classification'] not in ('attack', 'non_attack'):
                continue
            examples[template].append({'id': str(doc['id']), 'type': doc['type'], 'event_key': key,
                'time': event.get('time', event.get('minute')), 'classification': annotation['classification'],
                'att': annotation['att']})
    return examples


def effective_match(store, doc, *, include_review=False):
    """Project active annotations without modifying the source or saving guesses."""
    with store.db() as db:
        db.execute('BEGIN')
        review = _read_review(db, doc)
        examples = _learning_examples(db) if include_review else {}
    result = copy.deepcopy(doc)
    if not include_review and not review['annotations']:
        # Historical summaries need no event identity unless an overlay exists.
        # Preserve a detached display copy without hashing an entire archive.
        result['summary'] = attack_summary(result.get('events', []))
        return result
    active_keys, conflict_templates = set(), set()
    for event, source, (key, fingerprint) in zip(result.get('events', []), doc.get('events', []), _identities(doc)):
        annotation = review['annotations'].get(key)
        if annotation and annotation.get('source_fingerprint') == fingerprint:
            active_keys.add(key)
            event.update({name: annotation[name] for name in ('classification', 'att', 'possession', 'field')})
            event['att_origin'] = 'manual'
        else:
            annotation = None
        if not include_review:
            continue
        suggestion = None
        template = commentary_template(source)
        candidates = examples.get(template, [])
        labels = {(example['classification'], example['att']) for example in candidates}
        if len(labels) > 1:
            conflict_templates.add(template)
        elif len(labels) == 1 and annotation is None and attack_label(event.get('att')) is None:
            classification, attack = next(iter(labels))
            suggestion = {'classification': classification, 'att': attack, 'template': template,
                'template_version': TEMPLATE_VERSION, 'example_count': len(candidates),
                'examples': candidates[:10], 'reason': 'Même commentaire normalisé que des exemples validés dans votre espace privé.',
                'conflict': False}
        event.update(event_key=key, source_event=copy.deepcopy(source),
                     annotation=copy.deepcopy(annotation), suggestion=suggestion)
    result['summary'] = attack_summary(result.get('events', []))
    if include_review:
        result['review'] = {'revision': review['revision'], 'source_digest': source_digest(doc),
            'annotation_count': len(active_keys), 'orphaned_count': len(review['annotations']) - len(active_keys),
            'suggestion_count': result['summary']['suggested'], 'learning_conflicts': len(conflict_templates)}
    return result


def register_match_review(app, store, auth):
    @app.post('/api/matches/{kind}/{mid}/annotations')
    def annotate_match(body: AnnotationSave, kind: int = Path(ge=0, le=2),
                       mid: str = Path(pattern=r'^\d{1,15}$'), session=Depends(auth)):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM matches WHERE type=? AND id=?', (kind, mid)).fetchone()
            if not row:
                raise HTTPException(404, 'Match introuvable.')
            doc = json.loads(row['payload'])
            review = _read_review(db, doc)
            if source_digest(doc) != body.expected_source_digest or review['revision'] != body.expected_revision:
                raise HTTPException(409, 'Le match ou ses annotations ont changé. Votre brouillon est conservé ; rechargez pour comparer.')
            identities = dict(_identities(doc))
            if any(change.event_key not in identities for change in body.changes):
                raise HTTPException(404, 'Événement introuvable dans cette version du match.')
            for change in body.changes:
                if change.reset:
                    review['annotations'].pop(change.event_key, None)
                else:
                    review['annotations'][change.event_key] = {
                        name: getattr(change, name) for name in ('classification', 'att', 'possession', 'field', 'learn')}
                    review['annotations'][change.event_key].update(
                        source_fingerprint=identities[change.event_key], updated_at=now())
            review.update(revision=review['revision'] + 1, updated_at=now())
            db.execute('INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)', (_key(doc), pack(review)))
        return effective_match(store, doc, include_review=True)
