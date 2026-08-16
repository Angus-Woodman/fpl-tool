from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.current_squad_repository import CurrentSquadRepository
from api.repositories.my_team_projection_repository import MyTeamProjectionRepository
from api.repositories.projection_run_repository import ProjectionRunRepository
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.schemas.my_team import (
    CurrentSquadPlayerResponse,
    CurrentSquadResponse,
    HorizonProjectionTotalsResponse,
    MyTeamRecommendationResponse,
    MyTeamRecommendationUnavailableResponse,
    PlayerFixtureProjectionResponse,
    UpsertCurrentSquadRequestBody,
)
from api.services.current_squad import (
    CurrentSquadPlayerSelection,
    UpsertCurrentSquadRequest,
    UpsertCurrentSquadService,
)
from api.services.get_my_team_recommendation import (
    GetMyTeamRecommendationService,
    MyTeamRecommendationFailure,
)
from api.services.get_my_team_view import GetMyTeamViewService
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/my-team", tags=["my-team"])


def get_current_squad_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GetMyTeamViewService:
    return GetMyTeamViewService(
        CurrentSquadRepository(db_session),
        MyTeamProjectionRepository(db_session),
    )


def get_upsert_current_squad_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> UpsertCurrentSquadService:
    return UpsertCurrentSquadService(
        CurrentSquadRepository(db_session),
        SquadPlayerLookupRepository(db_session),
    )


def get_my_team_recommendation_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GetMyTeamRecommendationService:
    return GetMyTeamRecommendationService(
        CurrentSquadRepository(db_session),
        ProjectionRunRepository(db_session),
        MyTeamProjectionRepository(db_session),
    )


@router.get("", response_model=CurrentSquadResponse)
def get_my_team(
    service: Annotated[GetMyTeamViewService, Depends(get_current_squad_service)],
) -> CurrentSquadResponse:
    result = service.execute()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    return CurrentSquadResponse(
        squad_id=result.squad_id,
        name=result.name,
        bank=result.bank,
        free_transfers=result.free_transfers,
        projection_totals=(
            HorizonProjectionTotalsResponse.model_validate(result.projection_totals)
            if result.projection_totals is not None
            else None
        ),
        bench_projection_totals=(
            HorizonProjectionTotalsResponse.model_validate(result.bench_projection_totals)
            if result.bench_projection_totals is not None
            else None
        ),
        captain_adjusted_projection_totals=(
            HorizonProjectionTotalsResponse.model_validate(
                result.captain_adjusted_projection_totals
            )
            if result.captain_adjusted_projection_totals is not None
            else None
        ),
        gameweek_numbers=result.gameweek_numbers,
        players=[
            CurrentSquadPlayerResponse(
                player_id=player.player_id,
                web_name=player.web_name,
                first_name=player.first_name,
                second_name=player.second_name,
                team_name=player.team_name,
                team_short_name=player.team_short_name,
                position=player.position,
                current_price=player.current_price,
                status=player.status,
                is_starting=player.is_starting,
                bench_order=player.bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
                projection_totals=(
                    HorizonProjectionTotalsResponse.model_validate(player.projection_totals)
                    if player.projection_totals is not None
                    else None
                ),
                fixture_projections=[
                    PlayerFixtureProjectionResponse.model_validate(fixture)
                    for fixture in player.fixture_projections
                ],
            )
            for player in result.players
        ],
    )


@router.put("", response_model=CurrentSquadResponse)
def put_my_team(
    body: UpsertCurrentSquadRequestBody,
    db_session: Annotated[Session, Depends(get_db_session)],
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
        db_session.commit()
    except ValueError as error:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception:
        db_session.rollback()
        raise

    return CurrentSquadResponse(
        squad_id=result.squad_id,
        name=result.name,
        bank=result.bank,
        free_transfers=result.free_transfers,
        projection_totals=None,
        bench_projection_totals=None,
        captain_adjusted_projection_totals=None,
        gameweek_numbers=[],
        players=[CurrentSquadPlayerResponse.model_validate(player) for player in result.players],
    )


@router.get(
    "/recommendation",
    response_model=MyTeamRecommendationResponse,
    responses={422: {"model": MyTeamRecommendationUnavailableResponse}},
)
def get_my_team_recommendation(
    service: Annotated[GetMyTeamRecommendationService, Depends(get_my_team_recommendation_service)],
) -> MyTeamRecommendationResponse:
    result = service.execute()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    if isinstance(result, MyTeamRecommendationFailure):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": result.code,
                "message": result.message,
                "missing_player_ids": list(result.missing_player_ids),
            },
        )

    return MyTeamRecommendationResponse(
        model_version=result.model_version,
        projection_run_id=result.projection_run_id,
        generated_at=result.generated_at.isoformat(),
        target_gameweek_number=result.target_gameweek_number,
        starting_xi_points=result.starting_xi_points,
        captain_adjusted_points=result.captain_adjusted_points,
        starting_xi=list(result.starting_xi),
        bench_goalkeeper=result.bench_goalkeeper,
        bench_outfield=list(result.bench_outfield),
        captain=result.captain,
        vice_captain=result.vice_captain,
        player_projected_points=result.player_projected_points,
    )
