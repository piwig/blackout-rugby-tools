"""Read and retain a manager's national squads. Never writes to Classic."""
import json
import re
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .classic import ClassicClient, ClassicError
from .imports import parse_import
from .storage import now, pack
from .team_identity import TeamId, is_selection, team_identity


MAX_SELECTIONS = 6


def selection_game_date(value):
    """Keep only an explicit, integral Classic season/week/day observation."""
    if not isinstance(value, dict):
        return None
    result = {}
    for key, maximum in (('season', 999), ('round', 16), ('day', 7)):
        number = value.get(key)
        if (isinstance(number, bool) or not isinstance(number, (str, int))
                or not re.fullmatch(r'[0-9]{1,3}', str(number)) or not 1 <= int(number) <= maximum):
            return None
        result[key] = int(number)
    return result


class SelectionImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['u20', 'nt']
    country: str = Field(pattern=r'^[A-Z]{2}$')


class SelectionSync(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: TeamId


class SelectionPause(SelectionSync):
    expected_revision: int = Field(strict=True, ge=0, le=2147483647)


async def authenticated_member(client, manager_id):
    doc = await client.request('m', memberid=manager_id)
    members = doc.get('members')
    member = members.get(manager_id) if isinstance(members, dict) else None
    # Only the authenticated member response exposes this field. Do not retain it.
    if not isinstance(member, dict) or 'email' not in member or str(member.get('id', manager_id)) != manager_id:
        raise ClassicError('Clé manager non validée. Reconnectez votre compte Classic.')
    return member, doc


def selection_ids(account):
    ids = account.get('selection_ids', [])
    if (not isinstance(ids, list) or len(ids) > MAX_SELECTIONS
            or any(not isinstance(tid, str) for tid in ids) or len(set(ids)) != len(ids)):
        raise ClassicError('Liste des sélections non reconnue. Reconnectez votre compte Classic.')
    for tid in ids:
        if not is_selection(tid):
            raise ClassicError('Référence de sélection non reconnue.')
        try:
            team_identity(tid)
        except ValueError:
            raise ClassicError('Référence de sélection non reconnue.') from None
    return ids


def manager_credentials(store, shared):
    account = store.get('classic_account')
    encrypted = store.get('api_manager')
    if not isinstance(account, dict) or not encrypted:
        raise ClassicError('Importez d’abord votre compte Classic pour rattacher une sélection.')
    try:
        keys = json.loads(store.cipher.decrypt(encrypted.encode()))
    except Exception:
        raise ClassicError('Reconnectez votre compte Classic pour relire les sélections.') from None
    if (not isinstance(keys, dict) or str(keys.get('m', '')) != str(account.get('id'))
            or not re.fullmatch(r'[0-9]{1,15}', str(keys.get('m', ''))) or not keys.get('mk')):
        raise ClassicError('Le compte Classic ne correspond pas aux clés enregistrées.')
    # Selection credentials are inherited from the authenticated manager, never a
    # club with the same numeric ID, and never copied into api_member:<team_id>.
    credentials = {k: v for k, v in shared.items() if k in ('d', 'dk', 'iv')}
    credentials.update({k: keys[k] for k in ('m', 'mk')})
    return account, credentials


async def prepare_selection(client, manager_id, kind, *, country=None, classic_id=None):
    if kind not in ('u20', 'nt'):
        raise ClassicError('Type de sélection non reconnu.')
    flags = {'u20' if kind == 'u20' else 'nat': '1'}
    selector = {'teamid': classic_id} if classic_id else {'country_iso': country}
    doc = await client.request('t', **selector, **flags)
    teams = doc.get('teams')
    if not isinstance(teams, dict) or len(teams) != 1:
        raise ClassicError('Sélection absente ou format Classic non reconnu. Aucune donnée modifiée.')
    tid, team = next(iter(teams.items()))
    if (not isinstance(tid, str) or not re.fullmatch(r'[0-9]{1,15}', tid)
            or not isinstance(team, dict) or str(team.get('id', '')) != tid
            or (classic_id is not None and tid != classic_id)):
        raise ClassicError('L’identifiant retourné ne correspond pas à la sélection demandée.')
    actual_country = team.get('country_iso')
    if (not isinstance(actual_country, str) or not re.fullmatch(r'[A-Z]{2}', actual_country)
            or (country is not None and actual_country != country)):
        raise ClassicError('Le pays retourné ne correspond pas à la sélection demandée.')
    # Documentation uses `manager`; the U20 JSON observed on 2026-10-31 uses
    # `owner` with an explicit integer u20=1. No NT owner format is verified.
    if 'manager' in team and 'owner' in team and str(team['manager']) != str(team['owner']):
        raise ClassicError('Classic fournit des identités de sélectionneur contradictoires. Aucune donnée modifiée.')
    manager = team.get('manager')
    if 'manager' not in team and kind == 'u20' and type(team.get('u20')) is int and team['u20'] == 1:
        manager = team.get('owner')
    if not isinstance(manager, (str, int)) or isinstance(manager, bool) or not re.fullmatch(r'[0-9]{1,15}', str(manager)):
        raise ClassicError('Classic ne fournit pas le sélectionneur dans un format reconnu. Aucune donnée modifiée.')
    if str(manager) != manager_id:
        raise ClassicError('Ce compte Classic n’est pas le sélectionneur actuel. Les observations précédentes sont conservées.')
    players = await client.request('p', teamid=tid, **flags)
    if players.get('players') in ({}, []):
        result = {'players': [], 'game_date': players.get('gameDate')}
    else:
        try:
            result = parse_import(pack(players).encode(), 'players.json')
        except (ValueError, TypeError):
            raise ClassicError('Effectif de sélection non reconnu. Les observations précédentes sont conservées.') from None
    name = team.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ClassicError('Nom de sélection absent de la réponse Classic.')
    suffix = ' · U20' if kind == 'u20' else ' · Sélection nationale'
    return {'id': kind + ':' + tid, 'kind': kind, 'classic_id': tid,
            'name': name[:100-len(suffix)] + suffix,
            'country': actual_country, 'players': result['players'], 'game_date': selection_game_date(players.get('gameDate'))}


async def prepare_linked_selections(store, client, account):
    prepared = []
    for tid in selection_ids(account):
        with store.db() as db:
            row = db.execute('SELECT country FROM teams WHERE id=?', (tid,)).fetchone()
        if not row:
            raise ClassicError('Sélection rattachée introuvable dans votre espace.')
        identity = team_identity(tid)
        prepared.append(await prepare_selection(client, str(account['id']), **identity, country=row['country']))
    return prepared


def persist_selections(store, db, prepared, observed):
    result = []
    for team in prepared:
        meta = {'kind': team['kind'], 'classic_id': team['classic_id'], 'date_maj': observed,
                'game_date': selection_game_date(team.get('game_date'))}
        db.execute('INSERT INTO teams(id,name,country,meta) VALUES(?,?,?,?) '
                   'ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,meta=excluded.meta',
                   (team['id'], team['name'], team['country'], pack(meta)))
        store.save_snapshot(team['id'], False, team['players'], 'API Classic · sélection ' + team['kind'].upper(),
                            observed, team.get('game_date'), db)
        result.append({k: team[k] for k in ('id', 'kind', 'classic_id', 'name', 'country')} | {'squad': len(team['players'])})
    return result


def save_selection(store, expected_account, prepared):
    observed = now()
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT value FROM kv WHERE key='classic_account'").fetchone()
        account = json.loads(row['value']) if row else None
        if account != expected_account:
            raise ClassicError('Le compte Classic a changé pendant la lecture. Relancez la synchronisation.')
        ids = selection_ids(account)
        revision = account.get('selection_revision', 0)
        if prepared['id'] not in ids:
            if len(ids) >= MAX_SELECTIONS:
                raise ClassicError('La limite de six sélections rattachées est atteinte.')
            ids = [*ids, prepared['id']]
            revision += 1
        public = persist_selections(store, db, [prepared], observed)[0]
        updated = {**account, 'selection_ids': ids, 'selection_revision': revision, 'selections_imported_at': observed}
        db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('classic_account', pack(updated)))
    return {'ok': True, 'team': public, 'account': updated}


def pause_selection(store, team_id, expected_revision):
    """Unlink future reads while retaining every private observation and note."""
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT value FROM kv WHERE key='classic_account'").fetchone()
        account = json.loads(row['value']) if row else None
        if not isinstance(account, dict):
            raise HTTPException(422, 'Aucun compte Classic importé.')
        ids = selection_ids(account)
        revision = account.get('selection_revision', 0)
        if revision != expected_revision or team_id not in ids:
            raise HTTPException(409, 'Le rattachement des sélections a changé. Rechargez les données avant de réessayer.')
        updated = {**account, 'selection_ids': [tid for tid in ids if tid != team_id], 'selection_revision': revision + 1}
        db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('classic_account', pack(updated)))
    return {'ok': True, 'account': updated}


async def sync_selection(store, shared, team_id):
    account, credentials = manager_credentials(store, shared)
    if team_id not in selection_ids(account):
        raise ClassicError('Cette sélection n’est pas rattachée au compte Classic importé.')
    with store.db() as db:
        team = db.execute('SELECT country FROM teams WHERE id=?', (team_id,)).fetchone()
    if not team:
        raise ClassicError('Sélection introuvable dans votre espace.')
    client = ClassicClient(credentials)
    await authenticated_member(client, str(account['id']))
    prepared = await prepare_selection(client, str(account['id']), **team_identity(team_id), country=team['country'])
    return save_selection(store, account, prepared)


def register_national(app, store, auth, credentials, throttle, require_team):
    @app.post('/api/classic/selections', dependencies=[Depends(auth)])
    async def attach_selection(body: SelectionImport):
        throttle('selection-add:' + body.kind + ':' + body.country)
        account, keys = manager_credentials(store, credentials())
        client = ClassicClient(keys)
        await authenticated_member(client, str(account['id']))
        prepared = await prepare_selection(client, str(account['id']), body.kind, country=body.country)
        return save_selection(store, account, prepared)

    @app.post('/api/classic/selections/sync', dependencies=[Depends(auth)])
    async def refresh_selection(body: SelectionSync):
        require_team(body.team_id)
        if not is_selection(body.team_id):
            raise HTTPException(422, 'Choisissez une sélection U20 ou nationale.')
        throttle('selection-sync:' + body.team_id)
        return await sync_selection(store, credentials(), body.team_id)

    @app.post('/api/classic/selections/pause', dependencies=[Depends(auth)])
    def suspend_selection(body: SelectionPause):
        require_team(body.team_id)
        if not is_selection(body.team_id):
            raise HTTPException(422, 'Choisissez une sélection U20 ou nationale.')
        # Local unlinking must still work after a mandate or API key expires.
        return pause_selection(store, body.team_id, body.expected_revision)
