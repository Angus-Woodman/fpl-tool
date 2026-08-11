from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.current_squad_repository import CurrentSquadRepository
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.schemas.my_team import (
    CurrentSquadPlayerResponse,
    CurrentSquadResponse,
    UpsertCurrentSquadRequestBody,
)
from api.services.current_squad import (
    CurrentSquadPlayerSelection,
    GetCurrentSquadService,
    UpsertCurrentSquadRequest,
    UpsertCurrentSquadService,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/my-team", tags=["my-team"])


def get_current_squad_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GetCurrentSquadService:
    return GetCurrentSquadService(CurrentSquadRepository(db_session))


def get_upsert_current_squad_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> UpsertCurrentSquadService:
    return UpsertCurrentSquadService(
        CurrentSquadRepository(db_session),
        SquadPlayerLookupRepository(db_session),
    )


@router.get("", response_model=CurrentSquadResponse)
def get_my_team(
    service: Annotated[GetCurrentSquadService, Depends(get_current_squad_service)],
) -> CurrentSquadResponse:
    result = service.execute()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    return CurrentSquadResponse(
        squad_id=result.squad_id,
        name=result.name,
        bank=result.bank,
        free_transfers=result.free_transfers,
        players=[CurrentSquadPlayerResponse.model_validate(player) for player in result.players],
    )


@router.put("", response_model=CurrentSquadResponse)
def put_my_team(
    body: UpsertCurrentSquadRequestBody,
    service: Annotated[UpsertCurrentSquadService, Depends(get_upsert_current_squad_service)],
) -> CurrentSquadResponse:
    try:
        result = service.execute(
            UpsertCurrentSquadRequest(
                bank=body.bank,
                free_transfers=body.free_transfers,
                players=[
                    CurrentSquadPlayerSelection(
                        player_id=player.player_id,
                        is_starting=player.is_starting,
                        bench_order=player.bench_order,
                        is_captain=player.is_captain,
                        is_vice_captain=player.is_vice_captain,
                    )
                    for player in body.players
                ],
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return CurrentSquadResponse(
        squad_id=result.squad_id,
        name=result.name,
        bank=result.bank,
        free_transfers=result.free_transfers,
        players=[CurrentSquadPlayerResponse.model_validate(player) for player in result.players],
    )
