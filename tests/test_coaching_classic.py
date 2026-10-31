import asyncio
import json

import pytest

from server.classic import ClassicClient, ClassicError


def client():
    return ClassicClient({'d': '1', 'dk': 'synthetic', 'm': '2', 'mk': 'synthetic-manager'})


@pytest.mark.parametrize('resource,params', [
    ('ti', {'teamid': '123'}), ('tr', {'teamid': '123'}),
    ('tr', {'teamid': '123', 'season': '62', 'round': '8'}),
    ('ps', {'playerids': '101,102', 'league': '1', 'season': '61'}),
    ('ps', {'playerid': '101'}),
])
def test_new_coaching_resources_are_explicit_get_reads(monkeypatch, resource, params):
    sent = []
    async def send(self, method, query, data=None, before_send=None):
        sent.append((method, query, data))
        return json.dumps({'status': 'Ok'}).encode()
    monkeypatch.setattr(ClassicClient, '_send', send)
    assert asyncio.run(client().request(resource, **params)) == {'status': 'Ok'}
    assert sent[0][0] == 'GET' and sent[0][2] is None
    assert sent[0][1]['r'] == resource
    assert all(sent[0][1][key] == value for key, value in params.items())


@pytest.mark.parametrize('resource,params', [
    ('ti', {}), ('ti', {'teamid': '123', 'update': '1'}), ('ti', {'teamid': '123', 'nat': '1'}),
    ('tr', {'teamid': '123', 'season': '62'}), ('tr', {'teamid': '123', 'season': '62', 'round': '17'}),
    ('tr', {'teamid': '123', 'season': '0', 'round': '8'}), ('tr', {'teamid': True}),
    ('ps', {'playerids': '101,101'}), ('ps', {'playerids': ',101'}),
    ('ps', {'playerids': '101,102', 'fixtureid': '5'}), ('ps', {'playerid': '101', 'playerids': '101'}),
    ('ps', {'playerid': '101', 'season': '62'}), ('ps', {'playerid': '101', 'league': '1'}),
    ('ps', {'playerid': '101', 'league': '0', 'season': '62'}),
    ('ps', {'playerids': ','.join(map(str, range(1, 52)))}),
])
def test_coaching_adapter_rejects_unbounded_or_mutating_parameters_before_network(monkeypatch, resource, params):
    async def send(*args, **kwargs):
        pytest.fail('Invalid coaching parameters must not reach the network')
    monkeypatch.setattr(ClassicClient, '_send', send)
    with pytest.raises(ClassicError):
        asyncio.run(client().request(resource, **params))


def test_training_reads_require_manager_credentials(monkeypatch):
    async def send(*args, **kwargs):
        pytest.fail('Unauthenticated private training request reached the network')
    monkeypatch.setattr(ClassicClient, '_send', send)
    with pytest.raises(ClassicError):
        asyncio.run(ClassicClient({'d': '1', 'dk': 'synthetic'}).request('ti', teamid='123'))
