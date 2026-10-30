from defusedxml import ElementTree as ET
from server import classic

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
