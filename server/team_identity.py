"""Local team identifiers keep Classic's club, U20 and national spaces apart."""
import re
from typing import Annotated

from fastapi import HTTPException
from pydantic import Field


TEAM_PATTERN = r'^(?:(?:u20|nt):)?[0-9]{1,15}$'
OPTIONAL_TEAM_PATTERN = r'^(?:(?:(?:u20|nt):)?[0-9]{1,15})?$'
TeamId = Annotated[str, Field(strict=True, pattern=r'^(?:(?:u20|nt):)?[1-9][0-9]{0,14}$')]
CLUB_ONLY = 'Cette fonction est réservée aux clubs ; elle n’est pas disponible pour une sélection U20 ou nationale.'


def team_identity(team_id):
    if not isinstance(team_id, str) or not re.fullmatch(TEAM_PATTERN, team_id):
        raise ValueError('Identifiant d’équipe invalide.')
    if ':' in team_id:
        kind, classic_id = team_id.split(':', 1)
        return {'kind': kind, 'classic_id': classic_id}
    return {'kind': 'club', 'classic_id': team_id}


def is_selection(team_id):
    return isinstance(team_id, str) and team_id.startswith(('u20:', 'nt:'))


def require_club_id(team_id):
    if is_selection(team_id):
        raise HTTPException(422, CLUB_ONLY)


def describe_team(team):
    return {**team, **team_identity(team['id'])}
