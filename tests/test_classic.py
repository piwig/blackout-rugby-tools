from defusedxml import ElementTree as ET
from server import classic
from server.domain import attack_summary
import pytest

def test_commentary_classifies_explicit_attack_and_corrects_post_action_possession():
    root=ET.fromstring('''<root><event><commentary>Scrum won.</commentary><possession>1</possession><field>2</field><gametime>86</gametime></event><event><commentary>A takes the ball up strongly on the drive. Forward pass.</commentary><possession>0</possession><field>2</field><gametime>91</gametime></event><event><commentary>Looks like something creative here.</commentary><possession>0</possession><field>2</field><gametime>110</gametime></event></root>''')
    events=classic.parse_commentary(root)
    assert len(events)==3
    assert events[1]['att']=='percu'
    assert events[1]['possession']=='1'
    assert events[1]['possession_reported']=='0'
    assert events[1]['att_origin']=='commentary-rule'
    assert events[2]['att']=='crea'
    assert events[1]['time']=='1:31'

def test_breakdown_scrum_and_ambiguous_prose_remain_unclassified():
    for text in ['The forwards drive well past the ball at this breakdown.','A scrum drives forward.','He runs fast.','Great creative support from the crowd.']:
        assert classic.classify_attack(text) is None
    assert classic.classify_attack('The famous triple scissors move!')=='crea'
    assert classic.classify_attack('They move the ball out wide.')=='large'
    assert classic.classify_attack('A pick and go from the base.')=='png'


def test_partial_xml_keeps_contextless_events_without_counting_their_text_twice():
    root = ET.fromstring('''<root><events>
        <event id="1"><commentary>The carrier is on the drive.</commentary><field>2</field><possession>0</possession></event>
        <event id="2"><text>A passage without known context.</text></event>
        <event id="3"><text>On the drive.</text></event>
        <event id="4">A plain text event.</event>
        <event id="5"><gametime>45</gametime></event>
    </events></root>''')
    events = classic.parse_commentary(root)
    assert [row['id'] for row in events] == ['1', '2', '3', '4', '5']
    assert events[1]['text'] == 'A passage without known context.'
    assert events[3]['text'] == 'A plain text event.'
    assert all('field' not in row and 'possession' not in row for row in events[1:])
    summary = attack_summary(events)
    assert (summary['total_events'], summary['classified'], summary['unclassified']) == (5, 1, 4)
    assert summary['attack_missing_context'] == 1
    assert summary['home']['zones']['40']['Percussion'] == 1


def test_contextless_xml_limit_cannot_be_bypassed_by_one_structured_event():
    root = ET.fromstring('<root><event><text>Unknown.</text><field>2</field></event>'
        + '<event><text>A passage without context.</text></event>' * 20000 + '</root>')
    with pytest.raises(classic.ClassicError):
        classic.parse_commentary(root)


def test_unmapped_xml_leaf_comments_remain_in_source_order_without_duplicates():
    root = ET.fromstring('<root><commentary>First passage.</commentary>'
        '<event><commentary>Structured passage.</commentary><field>2</field></event>'
        '<comment>Final passage.</comment></root>')
    events = classic.parse_commentary(root)
    assert [row['text'] for row in events] == ['First passage.', 'Structured passage.', 'Final passage.']
    assert attack_summary(events)['total_events'] == 3


def test_nested_commentary_text_is_retained_as_one_event_without_invented_context():
    root = ET.fromstring('''<root>
      <event id="1"><commentary><text>A plain readable passage.</text></commentary></event>
      <event id="2"><commentary>The ball goes <b>out wide</b> today.</commentary><field>2</field><possession>0</possession></event>
      <commentary>A <b>final</b> passage.</commentary>
    </root>''')
    events = classic.parse_commentary(root)
    assert [row['text'] for row in events] == ['A plain readable passage.', 'The ball goes out wide today.', 'A final passage.']
    assert 'field' not in events[0] and 'possession' not in events[0]
    assert events[1]['att'] == 'large'
    summary = attack_summary(events)
    assert (summary['total_events'], summary['classified'], summary['unclassified']) == (3, 1, 2)


def test_commentary_container_keeps_its_records_separate():
    root = ET.fromstring('<commentary><event id="1"><text>First.</text></event>'
                        '<event id="2"><text>Second.</text></event></commentary>')
    assert classic.parse_commentary(root) == [{'id': '1', 'text': 'First.'}, {'id': '2', 'text': 'Second.'}]


@pytest.mark.parametrize('tag', ['comment', 'text'])
def test_standalone_commentary_collection_does_not_merge_distinct_passages(tag):
    root = ET.fromstring(f'<commentary><{tag} id="1">First passage.</{tag}>'
                        f'<{tag} id="2">Second passage.</{tag}></commentary>')
    assert [event['text'] for event in classic.parse_commentary(root)] == ['First passage.', 'Second passage.']
