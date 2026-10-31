"""Private starter declarations, without inferring or sending Classic actions."""
import secrets
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import Field, field_validator

from .workbench import Revision, StrictDocument, TeamId, read_document, replace_document
from .team_identity import require_club_id


StarterStage = Literal['mentor', 'treasury', 'transfers', 'staff', 'stadium', 'economy', 'lineup']


class StarterSave(StrictDocument):
    expected_revision: Revision
    completed: list[StarterStage] = Field(max_length=7)
    collapsed: bool = Field(strict=True)

    @field_validator('completed')
    @classmethod
    def unique_stages(cls, stages):
        if len(set(stages)) != len(stages):
            raise ValueError('Une étape ne peut être déclarée qu’une fois.')
        return stages


def register_starter(app, store, auth, require_team):
    @app.get('/api/workbench/starter/{team_id}')
    def get_starter(team_id: TeamId, request: Request, session=Depends(auth)):
        # Bind this read to the tab's session when another tab replaces its cookie.
        supplied = request.headers.get('x-csrf-token', '').encode('utf-8')
        if not secrets.compare_digest(supplied, session['csrf'].encode('utf-8')):
            raise HTTPException(403, 'Session à actualiser (protection CSRF).')
        require_team(team_id)
        require_club_id(team_id)
        return read_document(store, 'starter:' + team_id, {
            'team_id': team_id, 'updated_at': None, 'completed': [], 'collapsed': False,
        })

    @app.post('/api/workbench/starter/{team_id}')
    def save_starter(team_id: TeamId, body: StarterSave, session=Depends(auth)):
        require_team(team_id)
        require_club_id(team_id)
        return replace_document(store, 'starter:' + team_id, body.expected_revision, {
            'team_id': team_id, 'completed': body.completed, 'collapsed': body.collapsed,
        })
