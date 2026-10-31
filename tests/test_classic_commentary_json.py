import asyncio
import json

import pytest

from server.classic import ClassicClient, ClassicError


def test_commentary_requests_json_and_preserves_document(monkeypatch):
    doc = {'status': 'Ok', 'fixtureid': '123', 'events': {'7': {'index': 0, 'commentary': 'Unknown action.'}}}
    async def send(self, method, query, **kwargs):
        assert method == 'GET' and query['json'] == '1'
        return json.dumps(doc).encode()
    monkeypatch.setattr(ClassicClient, '_send', send)
    client = ClassicClient({'d': '1', 'dk': 'synthetic-key'})
    assert asyncio.run(client.request('me', fixtureid='123')) == doc


def test_commentary_xml_remains_supported(monkeypatch):
    async def send(*args, **kwargs):
        return b'<root><event><commentary>Unknown action.</commentary><field>2</field><possession>0</possession></event></root>'
    monkeypatch.setattr(ClassicClient, '_send', send)
    result = asyncio.run(ClassicClient({'d': '1', 'dk': 'synthetic-key'}).request('me', fixtureid='123'))
    assert len(result['events']) == 1


@pytest.mark.parametrize('data', [b'{"status":"Failed","error":"sensitive"}', b'{"status":"Ok"}', b'{broken'])
def test_invalid_commentary_document_is_refused_without_echo(data, monkeypatch):
    async def send(*args, **kwargs):
        return data
    monkeypatch.setattr(ClassicClient, '_send', send)
    with pytest.raises(ClassicError) as exc:
        asyncio.run(ClassicClient({'d': '1', 'dk': 'synthetic-key'}).request('me', fixtureid='123'))
    assert 'sensitive' not in str(exc.value)
