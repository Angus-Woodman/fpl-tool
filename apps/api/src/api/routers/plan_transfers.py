"""Read-only Planner Transfer Explorer endpoints.

Each request resolves a planning context (the only plan-storage access) and then
analyses it with read-only dependencies. No endpoint here writes data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from api.db.session import get_db_session
from api.repositories.my_team_projection_repository import MyTeamProjectionRepository
from api.repositories.plan_repository import PlanNotFoundError, PlanNotReadyError, PlanRepository
from api.repositories.player_read_repository import PlayerReadRepository
from api.repositories.projection_run_repository import ProjectionRunRepository
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.repositories.team_read_repository import TeamReadRepository
from api.schemas.plan_transfers import (
    PlanTransferErrorDetail,
    PlanTransferExplorerResponse,
    PlanTransferPreviewResponse,
)
from api.services.plan_context import PlanningContext, resolve_planning_context
from api.services.plan_transfer_analysis import (
    PlanTransferAnalysisService,
    PlanTransferFailure,
    PlanTransferList,
    PlanTransferPreview,
)
from fastapi import APIRouter, Depends, HTTPException, status
from fpl_engine.rules import RuleViolationError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/plans", tags=["plan-transfers"])

ContextResolver = Callable[[int, int], PlanningContext]
VALID_HORIZONS = (1, 3, 5)


def get_planning_context_resolver(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ContextResolver:
    def resolve(plan_id: int, gameweek: int) -> PlanningContext:
        return resolve_planning_context(
            plans=PlanRepository(db_session),
            players=SquadPlayerLookupRepository(db_session),
            transaction=db_session,
            plan_id=plan_id,
            gameweek=gameweek,
        )

    return resolve


def get_plan_transfer_analysis_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> PlanTransferAnalysisService:
    return PlanTransferAnalysisService(
        players=PlayerReadRepository(db_session),
        lookup=SquadPlayerLookupRepository(db_session),
        runs=ProjectionRunRepository(db_session),
        projections=MyTeamProjectionRepository(db_session),
        teams=TeamReadRepository(db_session),
    )


def _error(
    status_code: int, code: str, message: str, missing: list[int] | None = None
) -> HTTPException:
    detail = PlanTransferErrorDetail(code=code, message=message, missing_player_ids=missing or [])
    return HTTPException(status_code, detail=detail.model_dump(exclude_none=True))


def _resolve(resolver: ContextResolver, plan_id: int, gameweek: int) -> PlanningContext:
    try:
        return resolver(plan_id, gameweek)
    except PlanNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "plan_not_found", "Plan not found") from error
    except PlanNotReadyError as error:
        raise _error(status.HTTP_409_CONFLICT, "plan_not_ready", str(error)) from error
    except RuleViolationError as error:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.code, error.message) from error


def _failure(failure: PlanTransferFailure) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if failure.code == "player_not_found"
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return _error(code, failure.code, failure.message, list(failure.missing_player_ids))


@router.get(
    "/{plan_id}/gameweeks/{gameweek}/transfers/{player_out_id}",
    response_model=PlanTransferExplorerResponse,
    responses={404: {"model": PlanTransferErrorDetail}, 422: {"model": PlanTransferErrorDetail}},
)
def get_plan_transfers(
    plan_id: int,
    gameweek: int,
    player_out_id: int,
    resolver: Annotated[ContextResolver, Depends(get_planning_context_resolver)],
    service: Annotated[PlanTransferAnalysisService, Depends(get_plan_transfer_analysis_service)],
    primary_horizon: int = 5,
    projection_run_id: int | None = None,
) -> PlanTransferExplorerResponse:
    if primary_horizon not in VALID_HORIZONS:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_horizon",
            "primary_horizon must be one of 1, 3, or 5",
        )
    context = _resolve(resolver, plan_id, gameweek)
    try:
        result = service.list_candidates(
            context,
            player_out_id,
            primary_horizon=primary_horizon,
            projection_run_id=projection_run_id,
        )
    except RuleViolationError as error:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.code, error.message) from error
    if isinstance(result, PlanTransferFailure):
        raise _failure(result)
    assert isinstance(result, PlanTransferList)
    return PlanTransferExplorerResponse.model_validate(result)


@router.get(
    "/{plan_id}/gameweeks/{gameweek}/transfers/{player_out_id}/preview",
    response_model=PlanTransferPreviewResponse,
    responses={404: {"model": PlanTransferErrorDetail}, 422: {"model": PlanTransferErrorDetail}},
)
def get_plan_transfer_preview(
    plan_id: int,
    gameweek: int,
    player_out_id: int,
    player_in_id: int,
    resolver: Annotated[ContextResolver, Depends(get_planning_context_resolver)],
    service: Annotated[PlanTransferAnalysisService, Depends(get_plan_transfer_analysis_service)],
    projection_run_id: int | None = None,
) -> PlanTransferPreviewResponse:
    context = _resolve(resolver, plan_id, gameweek)
    try:
        result = service.preview(
            context, player_out_id, player_in_id, projection_run_id=projection_run_id
        )
    except RuleViolationError as error:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.code, error.message) from error
    if isinstance(result, PlanTransferFailure):
        raise _failure(result)
    assert isinstance(result, PlanTransferPreview)
    return PlanTransferPreviewResponse.model_validate(result)
