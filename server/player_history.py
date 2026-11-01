"""Bounded individual observations, selected within the requested population."""
import json
import re

from fastapi import HTTPException

from .team_identity import team_identity


def player_history(store, team_id, player_id, cohort=None):
    if not re.fullmatch(r'[0-9]{1,15}', player_id):
        raise HTTPException(422, 'Identifiant du joueur invalide.')
    kind = team_identity(team_id)['kind']
    allowed = ('club', 'youth') if kind == 'club' else (kind,)
    if cohort is not None and cohort not in allowed:
        raise HTTPException(422, 'Cette population ne correspond pas à l’équipe sélectionnée.')
    youth = (None if cohort is None else int(cohort == 'youth')) if kind == 'club' else 0
    with store.db() as db:
        # The correlated lookup returns one player, not a complete roster. Both
        # population and player presence are filtered before the response limit.
        rows = db.execute('''
            SELECT id, youth, substr(observed_at,1,80) AS observed_at,
                   substr(source,1,500) AS source,
                   (SELECT value FROM json_each(
                       CASE WHEN json_valid(payload) THEN
                           CASE WHEN json_type(payload)='array' THEN payload ELSE '[]' END
                       ELSE '[]' END)
                    WHERE CASE WHEN type='object' THEN
                        CASE WHEN json_type(value,'$.id') IN ('text','integer')
                             THEN CAST(json_extract(value,'$.id') AS TEXT) END
                        END=?
                    LIMIT 1) AS player
            FROM snapshots
            WHERE team_id=? AND (? IS NULL OR youth=?) AND player IS NOT NULL
            ORDER BY id DESC LIMIT 100
        ''', (player_id, team_id, youth, youth))
        return [{'snapshot_id': row['id'], 'team_id': team_id,
                 'youth': bool(row['youth']),
                 'cohort': ('youth' if row['youth'] else 'club') if kind == 'club' else kind,
                 'observed_at': row['observed_at'], 'source': row['source'],
                 'player': json.loads(row['player'])} for row in rows]
