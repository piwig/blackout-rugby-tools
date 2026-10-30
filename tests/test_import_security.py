"""Small synthetic files exercise expansion limits without large allocations."""
import io
import json
import tracemalloc
import zipfile
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import pytest

from server import imports, insights
from server.storage import Store, pack


def ods(tables):
    xml = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">' + tables + '</office:document-content>')
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('content.xml', xml)
    return data.getvalue()


def row(values, repeat=1):
    return '<table:table-row table:number-rows-repeated="'+str(repeat)+'">'+''.join(
        '<table:table-cell><text:p>'+escape(str(value))+'</text:p></table:table-cell>' for value in values)+'</table:table-row>'


def sheet(name, body):
    return '<table:table table:name="'+name+'">'+body+'</table:table>'


def test_nested_ods_table_is_rejected_instead_of_recursively_reusing_text():
    nested = sheet('players', row(['id', 'name']) + '<table:table-row><table:table-cell>' +
                   sheet('latouff_players', row(['42', 'Nested'])) + '</table:table-cell></table:table-row>')
    with pytest.raises(ValueError, match='ODS|imbriqu'):
        imports.parse_import(ods(nested), 'nested.ods')


def test_unneeded_sheets_are_ignored_before_building_their_rows():
    useful = sheet('players', row(['id', 'name']) + row(['42', 'A']))
    derived = sheet('calculated', ''.join(row(['summary']) for _ in range(4002)))
    parsed = imports.parse_import(ods(derived+useful), 'derived.ods')
    assert [player['id'] for player in parsed['players']] == ['42']


@pytest.mark.parametrize('marker', ['pops', 'reveals'])
def test_repeated_large_marker_strings_are_rejected_before_json_decode(monkeypatch, marker):
    marker_text = json.dumps(['strength']*200)
    original = json.loads
    def limited_load(value, *args, **kwargs):
        if value == marker_text:
            pytest.fail('Oversized marker string reached JSON decoding')
        return original(value, *args, **kwargs)
    monkeypatch.setattr(imports.json, 'loads', limited_load)
    with pytest.raises(ValueError):
        imports.parse_import(ods(sheet('players', row(['id','name',marker])+row(['42','A',marker_text],100))), 'markers.ods')


def test_marker_lists_are_deduplicated_and_bounded():
    player = imports.normalize_player({'id':'42','name':'A','pops':['strength','strength','speed'],'reveals':'["attack","attack"]'})
    assert player['pops'] == ['strength','speed']
    assert player['reveals'] == ['attack']
    with pytest.raises(ValueError):
        imports.normalize_player({'id':'42','name':'A','pops':['strength']*101})


def test_supported_franck_tables_keep_cached_players_training_and_plans():
    players=sheet('moeskroen_ya',row(['player_id','player_name','pops'])+row(['42','Loïc','["strength"]']))
    training=sheet('youth_training',row(['id','teamid','s1','s2','s3','s4'])+row(['1','72450','strength','speed','attack','defense']))
    team=sheet('team',row(['date_maj','name'])+row(['2026-10-27','Synthetic club']))
    academy=sheet('Academy',row(['64','S1'])+''.join(row(['',*(['FOR']*16)]) for _ in range(4)))
    parsed=imports.parse_import(ods(players+training+team+academy),'Moeskroen.ods')
    assert parsed['players'][0]['pops']==['strength']
    assert parsed['players'][0]['name']=='Loïc'
    assert parsed['team']=={'date_maj':'2026-10-27','name':'Synthetic club'}
    assert parsed['training'][0]['s4']=='defense'
    assert parsed['plans']['64']==[['strength']*16 for _ in range(4)]


def test_expanded_text_budget_precedes_row_repeat_allocation(monkeypatch):
    monkeypatch.setattr(imports, 'MAX_EXPANDED_TEXT', 120, raising=False)
    with pytest.raises(ValueError, match='volumin|budget|dépli'):
        imports.parse_import(ods(sheet('players',row(['id','name'])+row(['42','A'*80],100))), 'repeat.ods')


def test_player_limit_is_aggregate_across_ods_sheets(monkeypatch):
    monkeypatch.setattr(imports, 'MAX_PLAYERS', 3, raising=False)
    body = row(['id','name']) + row(['42','A'],2)
    with pytest.raises(ValueError, match='joueur'):
        imports.parse_import(ods(sheet('players',body)+sheet('latouff_players',body)), 'combined.ods')


@pytest.mark.parametrize('name,body', [('MAX_XML_DEPTH','<text:span>'*8+'A'+'</text:span>'*8),
                                      ('MAX_XML_NODES','<text:span>A</text:span>'*40)])
def test_xml_structure_budget_is_checked_during_parse(monkeypatch,name,body):
    monkeypatch.setattr(imports,name,6 if name=='MAX_XML_DEPTH' else 20,raising=False)
    with pytest.raises(ValueError):
        imports.read_ods(ods(sheet('players','<table:table-row><table:table-cell>'+body+'</table:table-cell></table:table-row>')))


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path,'Testing-password-1234',seed=False)


def snapshot(store, at, players):
    store.save_snapshot('42', True, players, 'synthetic', at)


def report(store):
    return insights.academy_report(store, '42', {'academy':[]}, {'goals':[],'sessions':[]})


def player(strength, pid='42'):
    return {'id':pid,'name':'Synthetic','strength':strength}


def test_academy_budget_chooses_recent_complete_dates_and_keeps_conflicts(store,monkeypatch):
    monkeypatch.setattr(insights,'ACADEMY_PLAYER_BUDGET',3,raising=False)
    for date, value in [('2026-10-01',1),('2026-10-02',2),('2026-10-03',3),('2026-10-03',4),('2026-10-04',5)]:
        snapshot(store,date,[player(value)])
    result=report(store)
    assert result['snapshot_count']==3
    assert result['history_truncated'] is True
    assert [(event['kind'],event['values']) for event in result['timeline']]==[('conflicting_observation',[3,4])]


def test_academy_oversized_payload_is_never_decoded_or_bridged(store,monkeypatch):
    snapshot(store,'2026-10-01',[player(1)])
    oversized=[{**player(2),'legacy':'X'*300}]
    snapshot(store,'2026-10-02',oversized)
    snapshot(store,'2026-10-03',[player(5)])
    snapshot(store,'2026-10-04',[player(6)])
    monkeypatch.setattr(insights,'ACADEMY_PAYLOAD_LIMIT',150,raising=False)
    original=json.loads
    def limited_load(value,*args,**kwargs):
        if isinstance(value,str) and 'X'*300 in value:
            pytest.fail('Oversized snapshot reached Python JSON decoding')
        return original(value,*args,**kwargs)
    monkeypatch.setattr(insights.json,'loads',limited_load)
    result=report(store)
    assert result['history_truncated'] is True
    assert [(event['observed_at'],event['delta']) for event in result['timeline']]==[('2026-10-04',1)]


def test_academy_row_boundary_discards_whole_equivalent_timestamp(store,monkeypatch):
    monkeypatch.setattr(insights,'ACADEMY_SNAPSHOT_LIMIT',2,raising=False)
    snapshot(store,'2026-10-02T00:00:00+00:00',[player(2)])
    snapshot(store,'2026-10-02T02:00:00+02:00',[player(3)])
    snapshot(store,'2026-10-03',[player(4)])
    result=report(store)
    assert result['snapshot_count']==1
    assert result['history_truncated'] is True
    assert result['timeline']==[]


def test_academy_total_byte_budget_keeps_latest_batches(store,monkeypatch):
    one_size=len(pack([player(1)]).encode())
    monkeypatch.setattr(insights,'ACADEMY_TOTAL_BYTES',one_size*2,raising=False)
    for value in range(1,5):
        snapshot(store,'2026-10-0'+str(value),[player(value)])
    original=json.loads
    decoded_bytes=0
    def count_loads(value,*args,**kwargs):
        nonlocal decoded_bytes
        decoded_bytes+=len(value.encode())
        assert decoded_bytes<=one_size*2, 'Excluded history was decoded before applying the byte budget'
        return original(value,*args,**kwargs)
    monkeypatch.setattr(insights.json,'loads',count_loads)
    result=report(store)
    assert result['snapshot_count']==2
    assert result['history_truncated'] is True
    assert [(event['before'],event['after']) for event in result['timeline']]==[(3,4)]


def test_academy_retains_only_tail_of_many_variations(store):
    for value in range(60):
        at=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=value)).isoformat()
        snapshot(store,at,[{**player(value%21), **{skill:value%21 for skill in imports.SKILLS}}])
    result=report(store)
    assert len(result['timeline'])==500
    assert result['history_truncated'] is True
    assert result['timeline'][0]['observed_at']=='2026-01-11T00:00:00+00:00'


def test_academy_timeline_does_not_materialize_all_discarded_changes(store):
    for value in range(60):
        at=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=value)).isoformat()
        snapshot(store,at,[{'id':str(pid),'name':'Synthetic',**{skill:value%21 for skill in imports.SKILLS}}
                           for pid in range(1,41)])
    tracemalloc.start()
    try:
        result=report(store)
        _,peak=tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(result['timeline'])==500
    assert peak<2_000_000, 'Discarded variations must not accumulate before slicing the response'
