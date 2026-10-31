"""Private human corrections and cautious suggestions, using synthetic matches."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED', '0')
    with TestClient(create_app(tmp_path, 'Testing-password-1234', secure=False)) as client:
        client.headers['X-CSRF-Token'] = client.post('/api/login', json={
            'username': 'piwig', 'password': 'Testing-password-1234'}).json()['csrf']
        yield client


def document(mid='123', events=None):
    return {'id': mid, 'type': 0, 'home': 'Home', 'away': 'Away', 'events': events or [
        {'id': '11', 'index': '0', 'text': 'A runner carries the ball into contact.', 'field': '2', 'possession': '0', 'time': '0:31'},
        {'id': '12', 'index': '1', 'text': 'The referee stops play for the interval.', 'field': '2', 'possession': '0', 'time': '0:32'}]}


def imported(client, doc=None):
    doc = doc or document()
    response = client.post('/api/matches/import', json=doc)
    assert response.status_code == 200, response.text
    return client.get('/api/matches/0/' + doc['id']).json()


def change(match, index=0, **values):
    return {'event_key': match['events'][index]['event_key'], 'classification': 'attack',
            'att': 'percu', 'possession': 0, 'field': 2, **values}


def save(client, match, changes):
    return client.post('/api/matches/0/' + match['id'] + '/annotations', json={
        'expected_revision': match['review']['revision'],
        'expected_source_digest': match['review']['source_digest'], 'changes': changes})


def raw(client, mid='123'):
    with client.app.state.store.db() as db:
        return json.loads(db.execute('SELECT payload FROM matches WHERE id=? AND type=0', (mid,)).fetchone()[0])


def test_manual_classification_preserves_source_and_updates_every_summary(client):
    match = imported(client)
    assert 'review' in match, 'Match detail must provide a review baseline before editing.'
    original = raw(client)
    response = save(client, match, [change(match)])
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['events'][0]['att'] == 'percu'
    assert saved['events'][0]['att_origin'] == 'manual'
    assert saved['events'][0]['source_event'] == original['events'][0]
    assert saved['summary']['classified'] == saved['summary']['manual'] == 1
    assert saved['summary']['home']['zones']['40']['Percussion'] == 1
    assert raw(client) == original
    assert client.get('/api/state').json()['matches'][0]['summary']['manual'] == 1


def test_revision_and_source_digest_prevent_stale_writes_and_batch_is_atomic(client):
    match = imported(client)
    first = save(client, match, [change(match)])
    assert first.status_code == 200
    assert save(client, match, [change(match, att='large')]).status_code == 409
    current = first.json()
    assert save(client, current, [change(current, att='large'), change(current, event_key='missing')]).status_code == 404
    assert client.get('/api/matches/0/123').json()['events'][0]['att'] == 'percu'
    altered = document()
    altered['events'][1]['text'] += ' Changed source.'
    imported(client, altered)
    assert save(client, current, [change(current, att='large')]).status_code == 409


def test_identical_reimport_keeps_corrections_changed_source_orphans_them_and_reset_restores(client):
    match = imported(client)
    saved = save(client, match, [change(match, learn=True)]).json()
    again = imported(client)
    assert again['events'][0]['att'] == 'percu' and again['review']['annotation_count'] == 1
    altered = document()
    altered['events'][0]['text'] += ' Changed source.'
    changed = imported(client, altered)
    assert not changed['events'][0].get('att')
    assert changed['review']['orphaned_count'] == 1
    restored = imported(client)
    reset = save(client, restored, [{'event_key': saved['events'][0]['event_key'], 'reset': True}])
    assert reset.status_code == 200
    assert reset.json()['events'][0]['annotation'] is None
    assert reset.json()['events'][0]['source_event'] == raw(client)['events'][0]
    assert reset.json()['summary']['manual'] == 0


def test_non_attack_unknown_and_missing_context_have_separate_counts(client):
    doc = document()
    doc['events'].append({'id': '13', 'text': 'An event with no known context.'})
    match = imported(client, doc)
    response = save(client, match, [change(match, 1, classification='non_attack', att=None),
                                    change(match, 2, field=None, possession=None)])
    assert response.status_code == 200
    result = response.json()['summary']
    assert result['classified'] == 0
    assert result['non_attack'] == 1 and result['unclassified'] == 2
    assert result['attack_missing_context'] == 1
    assert result['classified'] + result['non_attack'] + result['unclassified'] == result['total_events'] == 3


def test_learning_is_opt_in_private_and_never_applies_a_suggestion(client):
    match = imported(client)
    assert save(client, match, [change(match)]).status_code == 200
    target = imported(client, document('124'))
    assert target['events'][0]['suggestion'] is None
    source = client.get('/api/matches/0/123').json()
    assert save(client, source, [change(source, learn=True)]).status_code == 200
    target = client.get('/api/matches/0/124').json()
    suggestion = target['events'][0]['suggestion']
    assert suggestion['att'] == 'percu' and suggestion['example_count'] == 1
    assert suggestion['examples'][0]['id'] == '123'
    assert target['summary']['classified'] == 0 and target['summary']['suggested'] == 1
    assert not target['events'][0].get('att')
    client.app.state.accounts.create('other', 'Another-password-1234')
    with TestClient(client.app) as other:
        other.headers['X-CSRF-Token'] = other.post('/api/login', json={'username': 'other', 'password': 'Another-password-1234'}).json()['csrf']
        separate = imported(other, document('124'))
        assert separate['events'][0]['suggestion'] is None
        assert other.get('/api/matches/0/123').status_code == 404


def test_contradictory_examples_remove_suggestion_and_reset_retracts_example(client):
    first = imported(client)
    first = save(client, first, [change(first, learn=True)]).json()
    second = imported(client, document('124'))
    second = save(client, second, [change(second, att='large', learn=True)]).json()
    target = imported(client, document('125'))
    assert target['events'][0]['suggestion'] is None
    assert target['review']['learning_conflicts'] == 1
    save(client, second, [{'event_key': second['events'][0]['event_key'], 'reset': True}])
    assert client.get('/api/matches/0/125').json()['events'][0]['suggestion']['att'] == 'percu'
    save(client, first, [{'event_key': first['events'][0]['event_key'], 'reset': True}])
    assert client.get('/api/matches/0/125').json()['events'][0]['suggestion'] is None


def test_duplicate_source_rows_never_transfer_annotation_after_reordering(client):
    event = {'text': 'A runner carries the ball into contact.', 'field': '2', 'possession': '0'}
    match = imported(client, document(events=[event, copy.deepcopy(event)]))
    assert match['events'][0]['event_key'] != match['events'][1]['event_key']
    assert save(client, match, [change(match)]).status_code == 200
    identical = imported(client, document(events=[event, copy.deepcopy(event)]))
    assert identical['events'][0]['att'] == 'percu'
    altered = imported(client, document(events=[{'text': 'New event'}, event, copy.deepcopy(event)]))
    assert all(not row.get('att') for row in altered['events'])
    assert altered['review']['orphaned_count'] == 1


def test_export_contains_private_annotations_without_mutating_source(client):
    match = imported(client)
    save(client, match, [change(match, learn=True)])
    exported = client.get('/api/export').json()
    assert exported['manager_documents']['match_review:0:123']['annotations']
    exported_source = json.loads(exported['matches'][0]['payload'])
    assert 'att' not in exported_source['events'][0]


@pytest.mark.parametrize('values', [
    {'classification': 'non_attack'}, {'att': None}, {'possession': True},
    {'field': 6}, {'classification': 'invented'}, {'learn': 'yes'},
])
def test_invalid_annotations_do_not_change_anything(client, values):
    match = imported(client)
    response = save(client, match, [change(match, **values)])
    assert response.status_code == 422
    assert client.get('/api/matches/0/123').json()['review']['revision'] == 0


def test_xml_keeps_unknown_possession_for_an_inferred_attack():
    from server.classic import parse_commentary
    from xml.etree.ElementTree import fromstring
    events = parse_commentary(fromstring('<root><event><text>Restart</text><field>2</field><possession>1</possession></event>'
        '<event><text>On the drive.</text><field>2</field><possession>Unknown</possession></event></root>'))
    assert events[1]['possession'] == 'Unknown'


def test_learning_matches_only_controlled_classic_name_tags_and_preserves_negation(client):
    event = {'id': '1', 'commentary': '[player id=123 p=7]Example Player[/player] carries the ball 4 metres for [team id=321]Example Club[/team].',
             'possession': '0', 'field': '2'}
    first = imported(client, document(events=[event]))
    assert save(client, first, [change(first, learn=True)]).status_code == 200
    target_event = {**event, 'commentary': '[player id=456 p=8]Other Player[/player] carries the ball 12 metres for [team id=654]Other Club[/team].'}
    target = imported(client, document('124', [target_event]))
    assert target['events'][0]['suggestion']['att'] == 'percu'
    negated = {**target_event, 'commentary': target_event['commentary'].replace('carries', 'does not carry')}
    assert imported(client, document('125', [negated]))['events'][0]['suggestion'] is None
    plain = {**target_event, 'commentary': 'Other Player carries the ball 12 metres for Other Club.'}
    assert imported(client, document('126', [plain]))['events'][0]['suggestion'] is None


def test_short_comments_and_automatic_rules_are_not_learning_examples(client):
    match = imported(client, document(events=[{'id': '1', 'text': 'Good play!', 'field': '2', 'possession': '0'}]))
    assert save(client, match, [change(match, learn=True)]).status_code == 200
    target = imported(client, document('124', [{'id': '2', 'text': 'Good play!', 'field': '2', 'possession': '0'}]))
    assert target['events'][0]['suggestion'] is None
    imported(client, document('125', [{'text': 'The ball carrier is on the drive.'}]))
    from server.match_review import _learning_examples
    with client.app.state.store.db() as db:
        assert _learning_examples(db) == {}


def test_write_requires_csrf_and_private_match_even_with_a_valid_foreign_key(client):
    match = imported(client)
    payload = {'expected_revision': 0, 'expected_source_digest': match['review']['source_digest'], 'changes': [change(match)]}
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/matches/0/123/annotations', json=payload).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    client.app.state.accounts.create('other', 'Another-password-1234')
    with TestClient(client.app) as other:
        other.headers['X-CSRF-Token'] = other.post('/api/login', json={'username': 'other', 'password': 'Another-password-1234'}).json()['csrf']
        assert other.post('/api/matches/0/123/annotations', json=payload).status_code == 404


def test_stats_ignore_unaccepted_suggestions_and_separate_inference_context():
    from server.domain import attack_summary
    result = attack_summary([
        {'att': 'percu', 'att_origin': 'commentary-rule', 'possession': 'Unknown', 'field': '2'},
        {'att': 'large', 'att_origin': 'commentary-rule', 'possession': '1', 'field': '0'},
        {'att': 'kick', 'att_origin': 'manual', 'classification': 'attack', 'possession': 0, 'field': 2},
        {'att': None, 'classification': 'non_attack'},
        {'suggestion': {'att': 'png'}, 'possession': '0', 'field': '2'},
    ])
    assert result['classified'] == 2 and result['unclassified'] == 2 and result['non_attack'] == 1
    assert result['inferred'] == 1 and result['inferred_events'] == 2
    assert result['manual'] == result['suggested'] == result['attack_missing_context'] == 1
    assert result['provenance'] == {'source': 0, 'commentary_rule': 1, 'manual': 1}


def test_template_normalization_preserves_action_words():
    from server.match_review import commentary_template
    tagged = {'commentary': '[player id=123 p=7]Example Player[/player] carries the ball 4 metres for [team id=321]Example Club[/team].'}
    template = commentary_template(tagged)
    assert template == '{player} carries the ball {number} metres for {team}.'
    assert commentary_template({'text': '[b]Good play![/b]'}) is None
    assert commentary_template({'text': 'This [unknown]meaningful action[/unknown] stays in the commentary.'}) == 'this [unknown]meaningful action[/unknown] stays in the commentary.'


def test_explicit_unclassified_suppresses_rule_until_source_is_restored(client):
    match = imported(client, document(events=[{'text': 'The carrier is on the drive.', 'possession': '0', 'field': '2'}]))
    assert match['summary']['inferred'] == 1
    saved = save(client, match, [change(match, classification='unclassified', att=None)]).json()
    assert saved['summary']['classified'] == 0 and saved['summary']['inferred'] == 0
    assert saved['events'][0]['source_event']['att'] == 'percu'
    reset = save(client, saved, [{'event_key': saved['events'][0]['event_key'], 'reset': True}]).json()
    assert reset['summary']['inferred'] == 1 and reset['events'][0]['att_origin'] == 'commentary-rule'


def test_unique_event_identity_survives_reorder_and_changed_examples_stop_learning(client):
    match = imported(client)
    save(client, match, [change(match, learn=True)])
    source = document()
    source['events'].reverse()
    reordered = imported(client, source)
    assert reordered['events'][1]['att'] == 'percu'
    assert reordered['review']['orphaned_count'] == 0
    source['events'][1]['text'] += ' Different action.'
    imported(client, source)
    target = imported(client, document('124'))
    assert target['events'][0]['suggestion'] is None


def test_opponent_report_uses_manual_overlays_and_reports_provenance(client):
    match = imported(client)
    assert save(client, match, [change(match, possession=1), change(match, 1, classification='non_attack', att=None)]).status_code == 200
    data = client.get('/api/insights/72450').json()['document']
    revision = data.pop('revision')
    data.pop('updated_at', None)
    data['match_links'] = [{'match_id': '123', 'match_type': 0, 'club_side': 'home', 'opponent': 'Away', 'season': 62}]
    assert client.post('/api/insights/72450', json={'expected_revision': revision, 'document': data}).status_code == 200
    report = client.get('/api/insights/72450/opponents').json()
    assert report['opponent_actions'] == report['classified'] == 1
    assert report['zone_attacks']['40A']['Percussion'] == 1
    assert report['manual'] == 1 and report['non_attack'] == 1 and report['unclassified'] == 0
    assert report['provenance'] == {'source': 0, 'commentary_rule': 0, 'manual': 1}


def test_unknown_source_attack_can_receive_suggestion_but_known_attack_cannot(client):
    match = imported(client)
    assert save(client, match, [change(match, learn=True)]).status_code == 200
    unknown = document('124')
    unknown['events'][0]['att'] = 'Unknown'
    target = imported(client, unknown)
    assert target['events'][0]['suggestion']['att'] == 'percu'
    assert target['events'][0]['att'] == 'Unknown'
    known = document('125')
    known['events'][0].update(att='wide', possession='Unknown')
    target = imported(client, known)
    assert target['events'][0]['suggestion'] is None
    assert target['summary']['attack_missing_context'] == 1


def test_oversized_xml_commentary_is_rejected_instead_of_truncated():
    from server.classic import ClassicError, parse_commentary
    from xml.etree.ElementTree import fromstring
    root = fromstring('<root>' + '<event><text>Unknown action.</text><field>2</field></event>' * 20001 + '</root>')
    with pytest.raises(ClassicError):
        parse_commentary(root)


@pytest.mark.parametrize('envelope', [
    '<root status="Failed">{event}</root>',
    '<root><status>Failed</status>{event}</root>',
    '<root fixtureid="123"><fixtureid>999</fixtureid>{event}</root>',
])
def test_xml_failure_and_conflicting_identity_are_not_discarded(envelope, monkeypatch):
    import asyncio
    from server.classic import ClassicClient, ClassicError
    data = envelope.format(event='<event><text>Unknown action.</text><field>2</field></event>').encode()
    async def send(*args, **kwargs):
        return data
    monkeypatch.setattr(ClassicClient, '_send', send)
    with pytest.raises(ClassicError):
        asyncio.run(ClassicClient({'d': '1', 'dk': 'synthetic'}).request('me', fixtureid='123'))


def test_xml_commentary_preserves_reported_identity_for_downstream_check(monkeypatch):
    import asyncio
    from server.classic import ClassicClient
    async def send(*args, **kwargs):
        return b'<root status="Ok" fixtureid="999"><u20>1</u20><nat>0</nat><event><text>Unknown action.</text><field>2</field></event></root>'
    monkeypatch.setattr(ClassicClient, '_send', send)
    doc = asyncio.run(ClassicClient({'d': '1', 'dk': 'synthetic'}).request('me', fixtureid='123'))
    assert doc['fixtureid'] == '999' and doc['u20'] == '1' and doc['nat'] == '0'
    assert len(doc['events']) == 1


def test_unannotated_history_summary_avoids_event_hashes_and_keeps_source_immutable(client, monkeypatch):
    from server import match_review
    imported(client)
    source = raw(client)
    original = copy.deepcopy(source)
    def unnecessary_hash(value):
        pytest.fail('A summary without annotations should not fingerprint every source event.')
    monkeypatch.setattr(match_review, '_hash', unnecessary_hash)
    projected = match_review.effective_match(client.app.state.store, source)
    assert projected['summary']['total_events'] == 2
    projected['events'][0]['text'] = 'A changed display copy.'
    assert source == original and raw(client) == original
