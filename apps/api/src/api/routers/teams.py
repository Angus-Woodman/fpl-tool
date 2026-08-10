from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.team_read_repository import TeamReadRepository
from api.schemas.team import TeamListResponse, TeamResponse
from api.services.list_teams import ListTeamsService
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/teams", tags=["teams"])


def get_list_teams_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ListTeamsService:
    return ListTeamsService(TeamReadRepository(db_session))


@router.get("", response_model=TeamListResponse)
def list_teams(
    service: Annotated[ListTeamsService, Depends(get_list_teams_service)],
) -> TeamListResponse:
    result = service.execute()

    return TeamListResponse(
        items=[TeamResponse.model_validate(item) for item in result.items],
        total=result.total,
    )
