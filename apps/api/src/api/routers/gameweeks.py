from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.gameweek_read_repository import GameweekReadRepository
from api.schemas.gameweek import GameweekListResponse, GameweekResponse
from api.services.list_gameweeks import ListGameweeksService
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/gameweeks", tags=["gameweeks"])


def get_list_gameweeks_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ListGameweeksService:
    return ListGameweeksService(GameweekReadRepository(db_session))


@router.get("", response_model=GameweekListResponse)
def list_gameweeks(
    service: Annotated[ListGameweeksService, Depends(get_list_gameweeks_service)],
) -> GameweekListResponse:
    result = service.execute()

    return GameweekListResponse(
        items=[GameweekResponse.model_validate(item) for item in result.items],
        total=result.total,
    )
