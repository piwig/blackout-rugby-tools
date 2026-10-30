"""Vacation actions use isolated stores and a simulated Classic server only."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json

import pytest

from server.domain import SKILLS
from server.storage import Store


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def engine():
    try:
        return importlib.import_module('server.vacation')
    except ModuleNotFoundError:
        pytest.fail('Vacation service has not been implemented yet.')


def squad():
    return {str(i): {'name': 'Player '+str(i), **dict.fromkeys(SKILLS, 10),
                    'energy': 85, 'injured': '0', 'age': 25} for i in range(1, 31)}


def payload():
    return {**{str(i): str(i) for i in range(1, 16)},
            **{'b'+str(i): str(i+15) for i in range(1, 8)},
            'captain': '1', 'kicker': '10', 'intensity': '2',
            'defense': 'drift', 'mode': 'basic', 'dropgoals': '0',
            **dict.fromkeys(('captain1', 'captain2', 'kicker1', 'kicker2'), '0'),
            **{f'r{rank}p{i}': '0' for rank in (1, 2) for i in range(1, 16)},
            **{key+zone: val for zone in ('', '1', '2', '3', '4')
               for key, val in {'pickandgo': '25', 'driving': '25', 'expansive': '25',
                                'creative': '25', 'kicking': '20', 'kickfortouch': '40',
                                'upandunder': '20', 'discipline': '2'}.items()}}


class FakeClassic:
    def __init__(self):
        self.players = squad()
        self.owner = '9'
        self.member_teams = ['1']
        self.lineups = {'0': payload(), '7': payload()}
        self.deadline = NOW+timedelta(hours=5)
        self.writes = []
        self.fail_after_write = False
        self.before_read = None
        self.before_post = None
        self.member = {'email': 'private@example.test', 'teams': ['1']}

    async def request(self, resource, **params):
        if resource == 'm':
            return {'members': {'9': {**self.member, 'teams': self.member_teams}}}
        if resource == 't':
            return {'teams': {'1': {'owner': self.owner}}}
        if resource == 'p':
            return {'players': deepcopy(self.players)}
        raise AssertionError(resource)

    async def list_fixtures(self, team_id):
        return [{'id': '7', 'team_id': '1', 'home_team_id': '1', 'away_team_id': '2',
                 'competition': 'league', 'match_start': (NOW+timedelta(hours=6)).isoformat()}]

    async def read_lineup(self, team_id, fixture_id='0'):
        if self.before_read:
            callback, self.before_read = self.before_read, None
            await callback()
        doc = self.lineups.get(fixture_id)
        if doc is None:
            return None
        return {'team_id': team_id, 'fixture_id': fixture_id, 'payload': deepcopy(doc),
                'fingerprint': engine().lineup_fingerprint(doc),
                'deadline': self.deadline.isoformat() if self.deadline and fixture_id != '0' else None,
                'tactics_deadline': self.deadline.isoformat() if self.deadline and fixture_id != '0' else None}

    async def write_lineup(self, team_id, fixture_id, values, *, before_send=None):
        if self.before_post:
            await self.before_post()
        if before_send:
            before_send()
        self.writes.append((team_id, fixture_id, deepcopy(values)))
        self.lineups[fixture_id] = deepcopy(values)
        if self.fail_after_write:
            raise TimeoutError('DO NOT LEAK dk=private-secret')
        return {'status': 'submitted', 'requires_verification': True}


@pytest.fixture
def setup(tmp_path):
    module = engine()
    store = Store(tmp_path, 'long-test-password', seed=False)
    with store.db() as db:
        db.execute("INSERT INTO teams VALUES('1','Club','FR','{}')")
    store.set('classic_account', {'id': '9', 'team_ids': ['1']})
    store.save_secrets('1', {'d': '123', 'dk': 'x'*16, 'm': '9', 'mk': 'test-manager'})
    server = FakeClassic()
    clock = [NOW]
    service = module.VacationService(store, {'d': '123', 'dk': 'x'*16, 'iv': 'i'*16}, client_factory=lambda c: server,
                                     clock=lambda: clock[0])
    # Saved lineups have 23 local slots. The adapter writes exactly 22.
    store.set('lineup:1', {str(i): str(i) for i in range(1, 24)})
    return module, store, server, service, clock


def rule(module, **values):
    return module.VacationRule(team_id='1', start_at=NOW-timedelta(hours=1),
                               end_at=NOW+timedelta(days=2), energy_scale='percent', **values)


def run(awaitable):
    return asyncio.run(awaitable)


def ready(service, fixture_id='0', **options):
    return run(service.preview('1', fixture_id, source='saved', options={'energy_scale': 'percent', **options}))


def test_rule_boundaries_and_revision_isolation(setup, tmp_path):
    module, store, server, service, clock = setup
    assert service.status('1')['rules'][0]['enabled'] is False
    saved = service.save_rule(rule(module), expected_revision=0)
    assert saved['revision'] == 1
    with pytest.raises(module.VacationError) as error:
        service.save_rule(rule(module), expected_revision=0)
    assert error.value.status_code == 409
    other = Store(tmp_path/'other', 'long-test-password', seed=False)
    assert module.VacationService(other).status()['rules'] == []
    with pytest.raises(ValueError):
        module.VacationRule(team_id='1', start_at='2026-10-30T12:00:00', end_at='2026-10-31T12:00:00Z')
    with pytest.raises(ValueError):
        module.VacationRule(team_id='1', start_at=NOW, end_at=NOW+timedelta(days=57))


@pytest.mark.parametrize('mismatch', ['owner', 'membership', 'saved_account'])
def test_live_ownership_required_before_preview_or_send(setup, mismatch):
    module, store, server, service, clock = setup
    if mismatch == 'owner':
        server.owner = '10'
    elif mismatch == 'membership':
        server.member_teams = ['2']
    else:
        store.set('classic_account', {'id': '10', 'team_ids': ['1']})
    with pytest.raises(module.VacationError) as error:
        ready(service)
    assert error.value.status_code == 403
    assert not server.writes


def test_default_preview_requires_no_deadline_and_preserves_tactics(setup):
    module, store, server, service, clock = setup
    preview = ready(service)
    assert preview['status'] == 'ready'
    assert preview['payload']['b7'] == '22'
    assert 'b8' not in preview['payload'] and '23' not in preview['payload']
    assert preview['payload']['defense'] == server.lineups['0']['defense']
    assert preview['warnings']
    result = run(service.send(preview['id']))
    assert result['status'] == 'confirmed'
    run(service.send(preview['id']))
    assert len(server.writes) == 1


@pytest.mark.parametrize('deadline', [None, NOW-timedelta(seconds=1)])
def test_match_without_valid_official_deadline_never_sends(setup, deadline):
    module, store, server, service, clock = setup
    server.deadline = deadline
    preview = ready(service, '7')
    assert preview['status'] == 'blocked'
    assert not preview['can_send']
    with pytest.raises(module.VacationError):
        run(service.send(preview['id']))
    assert not server.writes


@pytest.mark.parametrize('change', ['remote', 'squad', 'expired', 'rule'])
def test_preview_revalidation_rejects_conflicts(setup, change):
    module, store, server, service, clock = setup
    preview = ready(service, '7')
    if change == 'remote':
        server.lineups['7']['captain'] = '2'
    elif change == 'squad':
        server.players['1']['energy'] = 70
    elif change == 'expired':
        clock[0] += timedelta(minutes=11)
    else:
        service.save_rule(rule(module), 0)
    with pytest.raises(module.VacationError):
        run(service.send(preview['id']))
    assert not server.writes


def test_stop_during_network_revalidation_prevents_post(setup):
    module, store, server, service, clock = setup
    preview = ready(service, '7')
    async def stop():
        service.stop('1')
    server.before_read = stop
    with pytest.raises(module.VacationError):
        run(service.send(preview['id']))
    assert not server.writes
    assert service.status('1')['rules'][0]['enabled'] is False


def test_stop_while_post_waits_for_rate_gate_prevents_transmission(setup):
    module, store, server, service, clock = setup
    preview = ready(service, '7')
    async def stop():
        service.stop('1')
    server.before_post = stop
    result = run(service.send(preview['id']))
    assert result['status'] == 'cancelled'
    assert not server.writes
    assert service.status('1')['rules'][0]['paused_reason'] is None


def test_uncertain_result_pauses_team_and_never_retries_or_logs_secrets(setup):
    module, store, server, service, clock = setup
    preview = ready(service)
    server.fail_after_write = True
    result = run(service.send(preview['id']))
    assert result['status'] == 'uncertain'
    assert service.status('1')['rules'][0]['paused_reason']
    with pytest.raises(module.VacationError):
        run(service.send(preview['id']))
    with pytest.raises(module.VacationError):
        service.save_rule(rule(module, enabled=True, mode='automatic', manage_existing=True), 1)
    run(service.tick())
    assert len(server.writes) == 1
    assert 'private-secret' not in json.dumps(service.status())


@pytest.mark.parametrize('field,value', [('injured', None), ('energy', None), ('energy', 30)])
def test_incomplete_or_ineligible_saved_players_block_send(setup, field, value):
    module, store, server, service, clock = setup
    server.players['1'][field] = value
    preview = ready(service)
    assert preview['status'] == 'blocked'
    assert preview['blocking_reasons']


def test_auto_energy_requires_explicit_scale(setup):
    module, store, server, service, clock = setup
    preview = run(service.preview('1', '0', source='saved'))
    assert preview['status'] == 'blocked'


def test_automatic_rules_are_bounded_and_idempotent(setup):
    module, store, server, service, clock = setup
    # Keep current referees in the optimized selection using explicit constraints.
    service.save_rule(rule(module, enabled=True, mode='automatic', manage_existing=True,
                           captain_id='1', kicker_id='10'), 0)
    results = run(service.tick())
    assert results and results[0]['status'] == 'confirmed'
    run(service.tick())
    assert len(server.writes) == 1
    clock[0] += timedelta(days=3)
    run(service.tick())
    assert service.status('1')['rules'][0]['enabled'] is False


def test_auto_preserves_unknown_custom_lineup_by_default(setup):
    module, store, server, service, clock = setup
    service.save_rule(rule(module, enabled=True, mode='automatic'), 0)
    results = run(service.tick())
    assert results[0]['status'] == 'blocked'
    assert not server.writes


def test_restart_never_retries_sending_attempt(setup):
    module, store, server, service, clock = setup
    preview = ready(service)
    # A persisted POST claim from a different process survived a crash.
    with store.db() as db:
        db.execute("UPDATE vacation_previews SET status='sending',process_id='old-process' WHERE id=?", (preview['id'],))
    restarted = module.VacationService(store, {'iv': 'i'*16}, client_factory=lambda c: server, clock=lambda: clock[0])
    assert restarted.status('1')['previews'][0]['status'] == 'uncertain'
    with pytest.raises(module.VacationError):
        run(restarted.send(preview['id']))
    assert not server.writes


def test_prepared_scheduler_proposal_can_be_explicitly_sent(setup):
    module, store, server, service, clock = setup
    service.save_rule(rule(module, enabled=True, mode='prepare'), 0)
    results = run(service.tick())
    assert results[0]['status'] == 'ready'
    assert not server.writes
    assert run(service.send(results[0]['id']))['status'] == 'confirmed'


def test_shared_iv_is_not_reused_with_a_different_private_developer_key(setup):
    module, store, server, service, clock = setup
    service.shared_credentials = {'d': '123', 'dk': 'a'*16, 'iv': 'i'*16}
    preview = ready(service)
    assert preview['status'] == 'blocked'
    service.shared_credentials = {'d': '123', 'dk': 'x'*16, 'iv': 'i'*16}
    assert ready(service)['status'] == 'ready'


def test_unknown_orphaned_replacement_reference_is_preserved_and_blocks(setup):
    module, store, server, service, clock = setup
    server.lineups['0']['r1p1'] = '22'
    saved = store.get('lineup:1')
    saved['22'] = '25'
    store.set('lineup:1', saved)
    preview = ready(service)
    assert preview['status'] == 'blocked'
    assert preview['payload']['r1p1'] == '22'
    assert not server.writes


def test_automatic_mode_does_not_overwrite_human_change_after_rule_update(setup):
    module, store, server, service, clock = setup
    active = rule(module, enabled=True, mode='automatic', manage_existing=True)
    service.save_rule(active, 0)
    assert run(service.tick())[0]['status'] == 'confirmed'
    server.lineups['7']['defense'] = 'rush'
    service.save_rule(active, 1)
    results = run(service.tick())
    assert results[0]['status'] == 'blocked'
    assert server.lineups['7']['defense'] == 'rush'
    assert len(server.writes) == 1


def test_two_services_claim_one_post_and_do_not_recover_live_sending(setup):
    module, store, server, service, clock = setup
    preview = ready(service)
    second = module.VacationService(store, {'d': '123', 'dk': 'x'*16, 'iv': 'i'*16}, client_factory=lambda c: server, clock=lambda: clock[0])
    async def check_live_state():
        third = module.VacationService(store, {'d': '123', 'dk': 'x'*16, 'iv': 'i'*16}, client_factory=lambda c: server, clock=lambda: clock[0])
        assert third.status('1')['previews'][0]['status'] == 'sending'
    server.before_post = check_live_state
    async def race():
        return await asyncio.gather(service.send(preview['id']), second.send(preview['id']))
    results = run(race())
    assert [r['status'] for r in results] == ['confirmed', 'confirmed']
    assert len(server.writes) == 1


def test_deadline_elapsing_while_post_waits_cancels_without_uncertainty(setup):
    module, store, server, service, clock = setup
    server.deadline = NOW+timedelta(minutes=2)
    preview = ready(service, '7')
    async def elapsed():
        clock[0] += timedelta(minutes=3)
    server.before_post = elapsed
    assert run(service.send(preview['id']))['status'] == 'cancelled'
    assert not server.writes


def modern(server):
    for lineup in server.lineups.values():
        lineup['b8'] = '23'
        for key in list(lineup):
            if key[-1:] in ('1', '2', '3', '4') and key.rstrip('1234') in ('pickandgo', 'driving', 'expansive', 'creative', 'kicking', 'kickfortouch', 'upandunder', 'discipline'):
                del lineup[key]


def test_modern_23_player_schema_is_explicit_and_requires_manual_proof_for_auto(setup):
    module, store, server, service, clock = setup
    modern(server)
    preview = ready(service)
    assert preview['status'] == 'ready'
    assert preview['bench_size'] == 8
    assert preview['schema'] == 'classic-23-basic'
    assert preview['verification_required'] is True
    assert preview['payload']['b8'] == '23'
    assert len(preview['players']) == 23
    service.save_rule(rule(module, enabled=True, mode='automatic', manage_existing=True), 0)
    automatic = run(service.tick())[0]
    assert automatic['status'] == 'blocked'
    assert not server.writes
    # A fresh explicit preview is needed after the rule revision changed.
    assert run(service.send(ready(service)['id']))['status'] == 'confirmed'
    assert ready(service)['verification_required'] is False
    assert run(service.tick())[0]['status'] == 'confirmed'
    assert len(server.writes) == 2


def test_manual_readback_failure_does_not_unlock_modern_schema(setup):
    module, store, server, service, clock = setup
    modern(server)
    preview = ready(service)
    server.fail_after_write = True
    assert run(service.send(preview['id']))['status'] == 'uncertain'
    assert ready(service)['verification_required'] is True


def uncertain(setup):
    module, store, server, service, clock = setup
    preview = ready(service)
    server.fail_after_write = True
    assert run(service.send(preview['id']))['status'] == 'uncertain'
    return preview


def test_reconcile_confirms_readback_without_reposting_or_reactivating(setup):
    module, store, server, service, clock = setup
    preview = uncertain(setup)
    result = run(service.reconcile(preview['id']))
    assert result['status'] == 'confirmed'
    status = service.status('1')
    assert status['rules'][0]['paused_reason'] is None
    assert status['rules'][0]['enabled'] is False
    assert len(server.writes) == 1


def test_reconcile_keeps_ambiguous_difference_until_explicit_acceptance(setup):
    module, store, server, service, clock = setup
    preview = uncertain(setup)
    server.lineups['0']['defense'] = 'rush'
    result = run(service.reconcile(preview['id']))
    assert result['status'] == 'uncertain'
    assert result['blocking_reasons']
    assert service.status('1')['rules'][0]['paused_reason']
    result = run(service.reconcile(preview['id'], accept_current=True))
    assert result['status'] == 'reconciled'
    assert service.status('1')['rules'][0]['paused_reason'] is None
    with pytest.raises(module.VacationError):
        run(service.send(preview['id']))
    assert server.lineups['0']['defense'] == 'rush'
    assert len(server.writes) == 1


def test_reconcile_cannot_accept_another_managers_club(setup):
    module, store, server, service, clock = setup
    preview = uncertain(setup)
    server.owner = 'other-manager'
    with pytest.raises(module.VacationError) as error:
        run(service.reconcile(preview['id'], accept_current=True))
    assert error.value.status_code == 403
    assert service.status('1')['rules'][0]['paused_reason']
    assert len(server.writes) == 1


def test_reconcile_rejects_acceptance_if_current_lineup_changed_again(setup):
    module, store, server, service, clock = setup
    preview = uncertain(setup)
    server.lineups['0']['defense'] = 'rush'
    result = run(service.reconcile(preview['id']))
    assert result['current_payload']['defense'] == 'rush'
    server.lineups['0']['defense'] = 'manonman'
    result = run(service.reconcile(preview['id'], accept_current=True))
    assert result['status'] == 'uncertain'
    assert result['current_payload']['defense'] == 'manonman'
    assert service.status('1')['rules'][0]['paused_reason']
    assert len(server.writes) == 1


def test_new_earlier_deadline_is_rechecked_after_rate_gate(setup):
    module, store, server, service, clock = setup
    preview = ready(service, '7')
    server.deadline = NOW+timedelta(minutes=2)
    async def elapsed():
        clock[0] += timedelta(minutes=3)
    server.before_post = elapsed
    assert run(service.send(preview['id']))['status'] == 'cancelled'
    assert not server.writes


def test_new_explicit_preview_can_restore_a_previously_confirmed_lineup(setup):
    module, store, server, service, clock = setup
    first = ready(service, captain_id='1')
    assert run(service.send(first['id']))['status'] == 'confirmed'
    second = ready(service, captain_id='2')
    assert run(service.send(second['id']))['status'] == 'confirmed'
    third = ready(service, captain_id='1')
    assert third['status'] == 'ready'
    assert run(service.send(third['id']))['status'] == 'confirmed'
    assert server.lineups['0']['captain'] == '1'
    assert len(server.writes) == 3
    # Replaying the old accepted preview never causes another POST.
    run(service.send(first['id']))
    assert len(server.writes) == 3


def test_uncertain_preview_remains_recoverable_after_many_new_blocked_previews(setup):
    module, store, server, service, clock = setup
    preview = uncertain(setup)
    for _ in range(21):
        ready(service)
    visible = service.status('1')['previews']
    assert any(p['id'] == preview['id'] and p['status'] == 'uncertain' for p in visible)


def test_uncertainty_invalidates_other_ready_previews(setup):
    module, store, server, service, clock = setup
    first = ready(service)
    uncertain(setup)
    original = next(p for p in service.status('1')['previews'] if p['id'] == first['id'])
    assert original['status'] == 'cancelled'
    assert original['can_send'] is False
