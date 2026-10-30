"""One-time move of Franck's supplied data into his private application account.

Run with the service stopped, after backup. Credentials are read from stdin.
No plaintext credentials are written or printed by this script.
"""
import argparse,asyncio,json,shutil,sqlite3,sys
from pathlib import Path
from server.storage import Store
from server.accounts import Accounts
from server.manager import import_manager

def migrate(root,credentials):
    primary=Store(root);accounts=Accounts(root,primary)
    if primary.get('private_managers_migrated'):
        print('Private manager migration already complete.');return
    user=accounts.user('franck')
    if user:raise RuntimeError('Existing franck account requires a manual migration review.')
    old_keys=primary.secrets('72450')
    created=accounts.create('franck',credentials['franck']['password']);private=accounts.store(created['id'])
    with sqlite3.connect(primary.path) as source,sqlite3.connect(private.path) as target:source.backup(target)
    shutil.copy2(root/'encryption.key',private.path.parent/'encryption.key')
    accounts.stores.pop(created['id']);private=accounts.store(created['id'])
    private.set('password',json.loads(accounts.user('franck')['password']))
    with private.db() as db:db.execute('DELETE FROM sessions')
    # Preserve all source data, including followed clubs, then clear the admin workspace.
    with primary.db() as db:
        for table in ('teams','snapshots','notes','plans','matches','sessions'):db.execute('DELETE FROM '+table)
        db.execute("DELETE FROM kv WHERE key NOT IN ('password','initial_seed_done','api_developer')")
    primary.set('private_managers_migrated',True)
    print('Franck private account created; supplied data transferred; admin workspace separated.')
    if old_keys.get('m') and old_keys.get('mk'):
        try:
            result=asyncio.run(import_manager(private,old_keys,'m='+old_keys['m']+'&mk='+old_keys['mk']))
            print('Franck Classic account imported:',len(result['teams']),'owned clubs.')
        except ValueError:print('Supplied data preserved. Live Classic account import needs a retry.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',default='/var/lib/brt')
    args=parser.parse_args();migrate(Path(args.data),json.load(sys.stdin))
