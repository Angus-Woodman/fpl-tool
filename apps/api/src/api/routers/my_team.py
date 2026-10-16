from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.current_squad_repository import CurrentSquadRepository
from api.repositories.my_team_projection_repository import MyTeamProjectionRepository
from api.repositories.player_read_repository import PlayerReadRepository
from api.repositories.projection_run_repository import ProjectionRunRepository
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.schemas.apply_transfer import (
    ApplyTransferRequestBody,
    ApplyTransferUnavailableResponse,
)
from api.schemas.lineup import LineupRearrangementResponse
from api.schemas.my_team import (
    CurrentSquadPlayerResponse,
    CurrentSquadResponse,
    HorizonProjectionTotalsResponse,
    MyTeamRecommendationResponse,
    MyTeamRecommendationUnavailableResponse,
    PlayerFixtureProjectionResponse,
    UpsertCurrentSquadRequestBody,
)
from api.schemas.transfer_preview import (
    LineupSummaryResponse,
    TransferPreviewResponse,
    TransferPreviewUnavailableResponse,
)
from api.schemas.transfers import (
    OutgoingPlayerSummaryResponse,
    RankedTransferCandidateResponse,
    TransferExplorerResponse,
    TransferExplorerUnavailableResponse,
)
from api.services.apply_transfer import ApplyTransferFailure, ApplyTransferService
from api.services.current_squad import (
    CurrentSquadPlayerSelection,
    UpsertCurrentSquadRequest,
    UpsertCurrentSquadService,
)
from api.services.get_my_team_recommendation import (
    GetMyTeamRecommendationService,
    MyTeamRecommendationFailure,
)
from api.services.get_my_team_view import GetMyTeamViewService, MyTeamViewRecord
from api.services.get_transfer_explorer import (
    GetTransferExplorerService,
    TransferExplorerFailure,
)
from api.services.get_transfer_preview import (
    GetTransferPreviewService,
    TransferPreviewFailure,
)
from api.services.squad_rearrangements import current_squad_rearrangements
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


def get_transfer_explorer_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GetTransferExplorerService:
    return GetTransferExplorerService(
        CurrentSquadRepository(db_session),
        ProjectionRunRepository(db_session),
        MyTeamProjectionRepository(db_session),
        PlayerReadRepository(db_session),
    )


def get_transfer_preview_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GetTransferPreviewService:
    return GetTransferPreviewService(
        CurrentSquadRepository(db_session),
        ProjectionRunRepository(db_session),
        MyTeamProjectionRepository(db_session),
        PlayerReadRepository(db_session),
    )


def get_apply_transfer_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ApplyTransferService:
    return ApplyTransferService(
        CurrentSquadRepository(db_session),
        ProjectionRunRepository(db_session),
        MyTeamProjectionRepository(db_session),
        PlayerReadRepository(db_session),
        GetMyTeamViewService(
            CurrentSquadRepository(db_session),
            MyTeamProjectionRepository(db_session),
        ),
    )


def _map_my_team_view_to_response(result: MyTeamViewRecord) -> CurrentSquadResponse:
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
        legal_rearrangements=[
            LineupRearrangementResponse(
                first_player_id=choice.first_player_id,
                second_player_id=choice.second_player_id,
                kind=choice.kind,
            )
            for choice in result.legal_rearrangements
        ],
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


@router.get("", response_model=CurrentSquadResponse)
def get_my_team(
    service: Annotated[GetMyTeamViewService, Depends(get_current_squad_service)],
) -> CurrentSquadResponse:
    result = service.execute()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    return _map_my_team_view_to_response(result)


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
        legal_rearrangements=[
            LineupRearrangementResponse(
                first_player_id=choice.first_player_id,
                second_player_id=choice.second_player_id,
                kind=choice.kind,
            )
            for choice in current_squad_rearrangements(result.players)
        ],
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
        current_captain_adjusted_points=result.current_captain_adjusted_points,
    )


@router.get(
    "/transfers/{player_out_id}",
    response_model=TransferExplorerResponse,
    responses={422: {"model": TransferExplorerUnavailableResponse}},
)
def get_transfer_explorer(
    player_out_id: int,
    service: Annotated[GetTransferExplorerService, Depends(get_transfer_explorer_service)],
    primary_horizon: int = 5,
) -> TransferExplorerResponse:
    if primary_horizon not in (1, 3, 5):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="primary_horizon must be one of 1, 3, or 5",
        )

    result = service.execute(player_out_id, primary_horizon=primary_horizon)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    if isinstance(result, TransferExplorerFailure):
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.code == "player_not_found"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.code,
                "message": result.message,
                "missing_player_ids": list(result.missing_player_ids),
            },
        )

    return TransferExplorerResponse(
        model_version=result.model_version,
        projection_run_id=result.projection_run_id,
        generated_at=result.generated_at.isoformat(),
        primary_horizon=result.primary_horizon,
        bank=result.bank,
        selling_price_is_approximate=result.selling_price_is_approximate,
        outgoing=OutgoingPlayerSummaryResponse(
            player_id=result.outgoing.player_id,
            web_name=result.outgoing.web_name,
            position=result.outgoing.position,
            team_short_name=result.outgoing.team_short_name,
            current_price=result.outgoing.current_price,
            selling_price=result.outgoing.selling_price,
            projected_points_by_horizon=result.outgoing.projected_points_by_horizon,
        ),
        candidates=[
            RankedTransferCandidateResponse(
                player_id=candidate.player_id,
                web_name=candidate.web_name,
                team_short_name=candidate.team_short_name,
                price=candidate.price,
                resulting_bank=candidate.resulting_bank,
                team_gain_by_horizon=candidate.team_gain_by_horizon,
                direct_xpts_difference=candidate.direct_xpts_difference,
                gameweeks_evaluated=candidate.gameweeks_evaluated,
                is_legal=candidate.is_legal,
                unavailable_reasons=list(candidate.unavailable_reasons),
                status=candidate.status,
            )
            for candidate in result.candidates
        ],
        evaluated_gameweek_numbers=result.evaluated_gameweek_numbers,
    )


@router.get(
    "/transfers/{player_out_id}/preview",
    response_model=TransferPreviewResponse,
    responses={422: {"model": TransferPreviewUnavailableResponse}},
)
def get_transfer_preview(
    player_out_id: int,
    player_in_id: int,
    service: Annotated[GetTransferPreviewService, Depends(get_transfer_preview_service)],
) -> TransferPreviewResponse:
    result = service.execute(player_out_id, player_in_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    if isinstance(result, TransferPreviewFailure):
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.code == "player_not_found"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.code,
                "message": result.message,
                "missing_player_ids": list(result.missing_player_ids),
            },
        )

    return TransferPreviewResponse(
        model_version=result.model_version,
        projection_run_id=result.projection_run_id,
        generated_at=result.generated_at.isoformat(),
        target_gameweek_number=result.target_gameweek_number,
        bank=result.bank,
        resulting_bank=result.resulting_bank,
        selling_price_is_approximate=result.selling_price_is_approximate,
        player_out_id=result.player_out_id,
        player_in_id=result.player_in_id,
        is_legal=result.is_legal,
        errors=list(result.errors),
        projected_team_gain=result.projected_team_gain,
        direct_player_xpts_difference=result.direct_player_xpts_difference,
        lineup_before=(
            LineupSummaryResponse(
                starting_xi=list(result.lineup_before.starting_xi),
                bench_goalkeeper=result.lineup_before.bench_goalkeeper,
                bench_outfield=list(result.lineup_before.bench_outfield),
                captain=result.lineup_before.captain,
                vice_captain=result.lineup_before.vice_captain,
                starting_xi_points=result.lineup_before.starting_xi_points,
                captain_adjusted_points=result.lineup_before.captain_adjusted_points,
            )
            if result.lineup_before is not None
            else None
        ),
        lineup_after=(
            LineupSummaryResponse(
                starting_xi=list(result.lineup_after.starting_xi),
                bench_goalkeeper=result.lineup_after.bench_goalkeeper,
                bench_outfield=list(result.lineup_after.bench_outfield),
                captain=result.lineup_after.captain,
                vice_captain=result.lineup_after.vice_captain,
                starting_xi_points=result.lineup_after.starting_xi_points,
                captain_adjusted_points=result.lineup_after.captain_adjusted_points,
            )
            if result.lineup_after is not None
            else None
        ),
        captain_changed=result.captain_changed,
        vice_captain_changed=result.vice_captain_changed,
        player_in_status=result.player_in_status,
    )


@router.post(
    "/transfers/{player_out_id}/apply",
    response_model=CurrentSquadResponse,
    responses={422: {"model": ApplyTransferUnavailableResponse}},
)
def apply_transfer(
    player_out_id: int,
    body: ApplyTransferRequestBody,
    db_session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ApplyTransferService, Depends(get_apply_transfer_service)],
) -> CurrentSquadResponse:
    result = service.execute(player_out_id, body.player_in_id)

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No squad saved yet")

    if isinstance(result, ApplyTransferFailure):
        db_session.rollback()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.code == "player_not_found"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.code,
                "message": result.message,
                "missing_player_ids": list(result.missing_player_ids),
                "errors": list(result.errors),
            },
        )

    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    return _map_my_team_view_to_response(result)
