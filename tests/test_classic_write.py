"""Classic boundary tests: synthetic fixtures and MockTransport, never game writes."""
import asyncio
import base64
import time
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from server import classic


CREDENTIALS = {'d': '99', 'dk': '0123456789abcdef', 'iv': 'abcdef0123456789', 'm': '42', 'mk': 'synthetic-manager'}


def lineup():
    raw = {f'p{i}': str(100 + i) for i in range(1, 16)}
    raw.update({f'b{i}': str(200 + i) for i in range(1, 8)})
    raw.update({f'r{rank}p{i}': str(200 + rank) for rank in (1, 2) for i in range(1, 16)})
    raw.update(captain='101', kicker='110', captain1='102', captain2='103', kicker1='109', kicker2='111',
               mode='zone', defense='rush', intensity='2', dropgoals='1')
    tactics = dict(pickandgo='25', driving='35', expansive='40', creative='0', kicking='55',
                   kickfortouch='50', upandunder='10', discipline='2')
    raw.update(tactics)
    for i in range(1, 5):
        raw[f'zone{i}'] = {**tactics, 'kickforterritory': '40'}
    raw['subs'] = {'1': {'replace': '101', 'with': '201', 'minute': '40+', 'scenario': 'any', 'margin': 10, 'enabled': 1}}
    raw.update(teamid='7', fixtureid='90', id='123', deadline='2026-11-01T13:00:00+12:00',
               tacticsdeadline='2026-11-01T14:00:00+12:00', deadline_local='2026-11-01T14:00:00+12:00')
    return raw


def payload():
    raw = lineup()
    value = {str(i): raw[f'p{i}'] for i in range(1, 16)}
    value.update({key: item for key, item in raw.items() if key.startswith(('b', 'r1p', 'r2p', 'captain', 'kicker'))})
    for key in ('mode', 'defense', 'intensity', 'dropgoals', 'pickandgo', 'driving', 'expansive', 'creative', 'kicking', 'kickfortouch', 'upandunder', 'discipline'):
        value[key] = raw[key]
    for i in range(1, 5):
        value.update({f'{key}{i}': item for key, item in raw[f'zone{i}'].items() if key != 'kickforterritory'})
    value.update(subreplace1='101', subwith1='201', subminute1='40+', subscenario1='any', submargin1='10', subenabled1='1')
    return value


@pytest.fixture
def transport(monkeypatch):
    real_client = httpx.AsyncClient
    captured = []
    def install(handler):
        async def wrapped(request):
            captured.append(request)
            result = handler(request)
            return await result if hasattr(result, '__await__') else result
        monkeypatch.setattr(classic.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(wrapped), **kwargs))
        # Exercise serialization without the external service's three-second interval.
        if hasattr(classic, '_RequestGate'):
            monkeypatch.setattr(classic, '_REQUEST_GATE', classic._RequestGate(interval=0))
        return captured
    return install


def decrypt_request(request):
    form = parse_qs(request.content.decode()) if request.method == 'POST' else dict(request.url.params.multi_items())
    encrypted = form['er'][0] if request.method == 'POST' else form['er']
    cipher = Cipher(algorithms.AES(CREDENTIALS['dk'].encode()), modes.CBC(CREDENTIALS['iv'].encode())).decryptor()
    plain = (cipher.update(base64.b64decode(encrypted)) + cipher.finalize()).rstrip(b'\0')
    return parse_qs(plain.decode())


def test_read_lineup_preserves_tactics_roles_and_subs_and_utc_deadline(transport):
    calls = transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [lineup()]}))
    result = asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))
    assert result['payload'] == payload()
    assert result['deadline'] == '2026-11-01T01:00:00+00:00'
    assert result['tactics_deadline'] == '2026-11-01T02:00:00+00:00'
    assert result['team_id'] == '7' and result['fixture_id'] == '90'
    assert decrypt_request(calls[0])['fixtureid'] == ['90']
    assert set(calls[0].url.params) == {'d', 'er'}


def test_absent_lineup_is_not_invented(transport):
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': []}))
    assert asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90')) is None


def test_lineup_identity_and_private_tactics_required(transport):
    raw = lineup()
    raw['teamid'] = '8'
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [raw]}))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))
    raw['teamid'] = '7'
    del raw['zone1']
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))


def test_fixtures_use_future_filter_and_keep_offset_dates(transport):
    calls = transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'fixtures': {'90': {
        'id': '90', 'hometeamid': '7', 'guestteamid': '8', 'competition': 'League',
        'matchstart': '2026-11-01T14:00:00+12:00'}}}))
    result = asyncio.run(classic.ClassicClient(CREDENTIALS).list_fixtures('7'))
    assert result == [{'id': '90', 'team_id': '7', 'home_team_id': '7', 'away_team_id': '8',
                       'competition': 'League', 'match_start': '2026-11-01T02:00:00+00:00'}]
    assert decrypt_request(calls[0])['future'] == ['7']


def test_write_encrypts_developer_key_in_post_body_and_returns_unverified_submission(transport):
    calls = transport(lambda request: httpx.Response(200, json={'status': 'Ok'}))
    result = asyncio.run(classic.ClassicClient(CREDENTIALS).write_lineup('7', '0', payload()))
    assert calls[0].method == 'POST'
    assert dict(calls[0].url.params) == {'d': '99'}
    assert set(parse_qs(calls[0].content.decode())) == {'er'}
    body = decrypt_request(calls[0])
    assert body.get('dk') == [CREDENTIALS['dk']]
    assert body['r'] == ['lu'] and body['update'] == ['1']
    assert body['teamid'] == ['7'] and body['fixtureid'] == ['0']
    assert body['1'] == ['101'] and body['subminute1'] == ['40+']
    assert body['mk'] == ['synthetic-manager']
    assert 'p1' not in body and 'iv' not in body
    assert result == {'status': 'submitted', 'requires_verification': True}
    assert b'synthetic-manager' not in calls[0].content
    assert CREDENTIALS['dk'].encode() not in calls[0].content


@pytest.mark.parametrize('missing', ['iv', 'm', 'mk', 'd', 'dk'])
def test_write_missing_credentials_never_reaches_network(transport, missing):
    calls = transport(lambda request: pytest.fail('must validate before sending'))
    credentials = {key: value for key, value in CREDENTIALS.items() if key != missing}
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(credentials).write_lineup('7', '90', payload()))
    assert not calls


@pytest.mark.parametrize('key,value', [('default', '1'), ('b9', '209'), ('r', 'lgn'), ('1', '102'),
    ('captain', '999'), ('r1p1', '999'), ('subwith1', '999'), ('subminute1', '41'),
    ('subscenario1', 'unknown'), ('creative', '100'), ('upandunder', '99'), ('intensity', '4')])
def test_write_invalid_payload_never_reaches_network(transport, key, value):
    calls = transport(lambda request: pytest.fail('must validate before sending'))
    invalid = {**payload(), key: value}
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).write_lineup('7', '90', invalid))
    assert not calls


def test_fingerprint_normalizes_integer_values_and_ignores_dict_order():
    original = payload()
    other = {key: int(value) if value.isdigit() else value for key, value in reversed(list(original.items()))}
    assert classic.lineup_fingerprint(original) == classic.lineup_fingerprint(other)
    other['subminute1'] = '45+'
    assert classic.lineup_fingerprint(original) != classic.lineup_fingerprint(other)


@pytest.mark.parametrize('response', [httpx.Response(302, headers={'location': 'https://example.com'}),
    httpx.Response(200, text='not JSON'), httpx.Response(200, json={}), httpx.Response(503)])
def test_ambiguous_write_response_is_not_retried_or_reported_success(transport, response):
    calls = transport(lambda request: response)
    with pytest.raises(classic.ClassicWriteUncertain):
        asyncio.run(classic.ClassicClient(CREDENTIALS).write_lineup('7', '90', payload()))
    assert len(calls) == 1


def test_timeout_after_post_is_uncertain_and_secrets_not_exposed(transport):
    def timeout(request):
        raise httpx.ReadTimeout('secret synthetic-manager', request=request)
    calls = transport(timeout)
    with pytest.raises(classic.ClassicWriteUncertain) as failure:
        asyncio.run(classic.ClassicClient(CREDENTIALS).write_lineup('7', '90', payload()))
    assert len(calls) == 1 and 'synthetic-manager' not in str(failure.value)


def test_explicit_api_failure_is_sanitized(transport):
    transport(lambda request: httpx.Response(200, json={'status': 'Failed', 'error': 'synthetic-manager'}))
    with pytest.raises(classic.ClassicError) as failure:
        asyncio.run(classic.ClassicClient(CREDENTIALS).write_lineup('7', '90', payload()))
    assert not isinstance(failure.value, classic.ClassicWriteUncertain)
    assert 'synthetic-manager' not in str(failure.value)


def test_get_and_post_across_clients_share_serial_gate(transport):
    active = 0
    peak = 0
    async def handle(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.01)
        active -= 1
        return httpx.Response(200, json={'status': 'Ok'})
    transport(handle)
    async def run():
        first, second = classic.ClassicClient(CREDENTIALS), classic.ClassicClient(CREDENTIALS)
        await asyncio.gather(first.request('p', playerid='1'), second.write_lineup('7', '90', payload()))
    asyncio.run(run())
    assert peak == 1


def test_legacy_get_without_iv_keeps_import_compatible(transport):
    calls = transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'players': {}}))
    credentials = {key: value for key, value in CREDENTIALS.items() if key != 'iv'}
    assert asyncio.run(classic.ClassicClient(credentials).request('p', teamid='7'))['players'] == {}
    assert calls[0].url.params['mk'] == 'synthetic-manager'


def test_read_rejects_failed_status_even_without_error_field(transport):
    transport(lambda request: httpx.Response(200, json={'status': 'Failed'}))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).request('p', teamid='7'))


@pytest.mark.parametrize('date', ['2026-11-01T13:00:00', '1793538000', 'broken'])
def test_lineup_deadline_without_unambiguous_timezone_is_rejected(transport, date):
    raw = lineup()
    raw['deadline'] = date
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [raw]}))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))


@pytest.mark.parametrize('key', ['iv', 'dk'])
def test_invalid_aes_credentials_do_not_fall_back_to_plaintext(transport, key):
    calls = transport(lambda request: pytest.fail('invalid encryption must not send'))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient({**CREDENTIALS, key: 'bad'}).write_lineup('7', '90', payload()))
    assert not calls


@pytest.mark.parametrize('write', [False, True])
def test_oversized_response_is_rejected_without_retry(transport, write):
    calls = transport(lambda request: httpx.Response(200, content=b' ' * 8_000_001))
    client = classic.ClassicClient(CREDENTIALS)
    with pytest.raises(classic.ClassicWriteUncertain if write else classic.ClassicError):
        asyncio.run(client.write_lineup('7', '90', payload()) if write else client.request('p', playerid='1'))
    assert len(calls) == 1


def test_gate_waits_between_requests_and_releases_after_cancellation(transport, monkeypatch):
    starts = []
    def handle(request):
        starts.append(time.monotonic())
        return httpx.Response(200, json={'status': 'Ok'})
    transport(handle)
    monkeypatch.setattr(classic, '_REQUEST_GATE', classic._RequestGate(interval=.04))
    async def run():
        client = classic.ClassicClient(CREDENTIALS)
        await client.request('p', playerid='1')
        waiting = asyncio.create_task(client.request('p', playerid='2'))
        await asyncio.sleep(.005)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        await asyncio.wait_for(client.request('p', playerid='3'), timeout=1)
    asyncio.run(run())
    assert len(starts) == 2 and starts[1] - starts[0] >= .035


def test_incomplete_or_noncontiguous_substitutions_are_rejected():
    incomplete = payload()
    del incomplete['subwith1']
    with pytest.raises(classic.ClassicError):
        classic.validate_lineup_payload(incomplete)
    gap = {key.replace('1', '2') if key.startswith('sub') else key: value for key, value in payload().items()}
    with pytest.raises(classic.ClassicError):
        classic.validate_lineup_payload(gap)


def test_missing_substitutions_are_not_silently_erased_on_read(transport):
    raw = lineup()
    del raw['subs']
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [raw]}))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))


def test_unknown_substitution_properties_are_not_silently_erased(transport):
    raw = lineup()
    raw['subs']['1']['new_condition'] = 'keep-me'
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [raw]}))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))


def test_stop_while_waiting_for_transport_gate_prevents_post(transport, monkeypatch):
    calls = transport(lambda request: pytest.fail('the stop must prevent the POST'))
    gate = classic._RequestGate(interval=.04)
    gate.finished = time.monotonic()
    monkeypatch.setattr(classic, '_REQUEST_GATE', gate)
    stopped = False
    class Stopped(Exception):
        pass
    def before_send():
        if stopped:
            raise Stopped()
    async def run():
        nonlocal stopped
        pending = asyncio.create_task(classic.ClassicClient(CREDENTIALS).write_lineup('7', '90', payload(), before_send=before_send))
        await asyncio.sleep(.005)
        stopped = True
        with pytest.raises(Stopped):
            await pending
    asyncio.run(run())
    assert not calls


def modern_payload():
    return {**{key: value for key, value in payload().items()
               if not any(key == f'{field}{zone}' for field in ('pickandgo', 'driving', 'expansive', 'creative', 'kicking', 'kickfortouch', 'upandunder', 'discipline') for zone in range(1, 5))},
            'b8': '208', 'mode': 'basic'}


def test_live_basic_schema_preserves_eighth_bench_without_inventing_zones(transport):
    raw = lineup()
    raw.update(b8='208', mode='basic')
    for i in range(1, 5):
        del raw[f'zone{i}']
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [raw]}))
    result = asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))
    assert result['payload'] == modern_payload()
    assert result['schema'] == 'classic-23-basic'
    changed = {**result['payload'], 'b8': '209'}
    assert classic.lineup_fingerprint(changed) != result['fingerprint']


def test_modern_write_sends_eighth_bench_and_no_invented_zones(transport):
    calls = transport(lambda request: httpx.Response(200, json={'status': 'Ok'}))
    result = asyncio.run(classic.ClassicClient(CREDENTIALS).write_lineup('7', '90', modern_payload()))
    sent = decrypt_request(calls[0])
    assert sent['b8'] == ['208'] and sent['mode'] == ['basic']
    assert 'pickandgo1' not in sent
    assert result['requires_verification'] is True


def test_modern_schema_still_requires_distinct_bench_and_zones_when_zoned():
    assert classic.lineup_schema(modern_payload()) == 'classic-23-basic'
    for invalid in ({**modern_payload(), 'b8': '101'}, {**modern_payload(), 'mode': 'zone'},
                    {**modern_payload(), 'pickandgo1': '25'}):
        with pytest.raises(classic.ClassicError):
            classic.validate_lineup_payload(invalid)


@pytest.mark.parametrize('key,value', [('b9', '209'), ('p16', '116'), ('zone5', {})])
def test_unrecognized_remote_slots_or_zones_are_not_silently_dropped(transport, key, value):
    raw = {**lineup(), key: value}
    transport(lambda request: httpx.Response(200, json={'status': 'Ok', 'lineups': [raw]}))
    with pytest.raises(classic.ClassicError):
        asyncio.run(classic.ClassicClient(CREDENTIALS).read_lineup('7', '90'))
