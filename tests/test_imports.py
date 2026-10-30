import io,zipfile,pytest
from server import imports

def test_csv_preserves_hidden_skills_and_unicode():
    result=imports.parse_import('player_id;player_name;age;strength\n42;Loïc;16;Unknown'.encode(),'academy.csv')
    assert result['players'][0]['name']=='Loïc'
    assert result['players'][0]['strength']=='Unknown'
    assert result['players'][0]['id']=='42'

def test_json_supports_classic_player_dictionary():
    r=imports.parse_import(b'{"gameDate":{"season":62,"round":9,"day":6},"players":{"42":{"name":"A","age":16}}}', 'players.json')
    assert r['players'][0]['id']=='42'
    assert r['game_date']['season']==62

def test_malformed_and_oversized_input_fail_cleanly():
    for data,name in [(b'not json','players.json'),(b'a,b\nc,d','players.csv'),(b'abc','file.exe'),(b'X'*8_000_001,'a.csv')]:
      with pytest.raises(ValueError): imports.parse_import(data,name)

def test_ods_repeated_cells_and_formulas_read_cached_values_only():
    xml='''<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><table:table table:name="moeskroen_ya"><table:table-row><table:table-cell><text:p>player_id</text:p></table:table-cell><table:table-cell><text:p>player_name</text:p></table:table-cell><table:table-cell><text:p>strength</text:p></table:table-cell><table:table-cell><text:p>speed</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell><text:p>42</text:p></table:table-cell><table:table-cell table:formula="unsafe"><text:p>A</text:p></table:table-cell><table:table-cell table:number-columns-repeated="2"><text:p>Unknown</text:p></table:table-cell></table:table-row></table:table></office:document-content>'''
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('content.xml',xml)
    r=imports.parse_import(b.getvalue(),'Moeskroen.ods')
    assert r['datasets'][0]['players'][0]['speed']=='Unknown'
    assert r['datasets'][0]['youth'] is True
