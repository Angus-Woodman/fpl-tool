from __future__ import annotations

from typing import Annotated, Literal

from api.db.session import get_db_session
from api.repositories.player_read_repository import PlayerReadRepository
from api.schemas.player import PlayerListResponse, PlayerResponse
from api.services.list_players import ListPlayersRequest, ListPlayersService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/players", tags=["players"])


def get_list_players_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ListPlayersService:
    return ListPlayersService(PlayerReadRepository(db_session))


@router.get("", response_model=PlayerListResponse)
def list_players(
    service: Annotated[ListPlayersService, Depends(get_list_players_service)],
    search: str | None = Query(default=None, min_length=1),
    position: Literal["GK", "DEF", "MID", "FWD"] | None = Query(default=None),
    team_id: int | None = Query(default=None, ge=1),
    status: str | None = Query(default=None, min_length=1, max_length=20),
    sort: Literal["web_name", "price_desc", "price_asc"] = Query(default="web_name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> PlayerListResponse:
    result = service.execute(
        ListPlayersRequest(
            search=search,
            position=position,
            team_id=team_id,
            status=status,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    )

    return PlayerListResponse(
        items=[PlayerResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )
