from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.team_read_repository import TeamReadRepository
from api.repositories.team_repository import TeamRepository
from api.schemas.team import TeamListResponse, TeamResponse, UpdateTeamDifficultyPayload
from api.services.list_teams import ListTeamsService
from api.services.update_team_difficulty import (
    UpdateTeamDifficultyRequest,
    UpdateTeamDifficultyService,
)
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/teams", tags=["teams"])


def get_list_teams_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ListTeamsService:
    return ListTeamsService(TeamReadRepository(db_session))


def get_update_team_difficulty_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> UpdateTeamDifficultyService:
    return UpdateTeamDifficultyService(TeamRepository(db_session))


@router.get("", response_model=TeamListResponse)
def list_teams(
    service: Annotated[ListTeamsService, Depends(get_list_teams_service)],
) -> TeamListResponse:
    result = service.execute()

    return TeamListResponse(
        items=[TeamResponse.model_validate(item) for item in result.items],
        total=result.total,
    )


@router.patch("/{team_id}", response_model=TeamResponse)
def update_team_difficulty(
    team_id: Annotated[int, Path(ge=1)],
    payload: UpdateTeamDifficultyPayload,
    db_session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[UpdateTeamDifficultyService, Depends(get_update_team_difficulty_service)],
) -> TeamResponse:
    result = service.execute(
        UpdateTeamDifficultyRequest(team_id=team_id, difficulty=payload.difficulty)
    )
    if result is None:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    db_session.commit()
    return TeamResponse.model_validate(result)
