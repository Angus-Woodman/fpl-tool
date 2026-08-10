from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.fixture_read_repository import FixtureReadRepository
from api.schemas.fixture import FixtureTickerItemResponse, FixtureTickerResponse
from api.services.list_fixtures import (
    ListFixtureTickerRequest,
    ListFixtureTickerService,
)
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


def get_list_fixture_ticker_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ListFixtureTickerService:
    return ListFixtureTickerService(FixtureReadRepository(db_session))


@router.get("/ticker", response_model=FixtureTickerResponse)
def get_fixture_ticker(
    service: Annotated[ListFixtureTickerService, Depends(get_list_fixture_ticker_service)],
    limit: int = Query(default=20, ge=1, le=100),
    team_id: int | None = Query(default=None, ge=1),
    gameweek: int | None = Query(default=None, ge=1, le=38),
) -> FixtureTickerResponse:
    result = service.execute(
        ListFixtureTickerRequest(limit=limit, team_id=team_id, gameweek=gameweek)
    )

    return FixtureTickerResponse(
        items=[FixtureTickerItemResponse.model_validate(item) for item in result.items],
        total=result.total,
    )
