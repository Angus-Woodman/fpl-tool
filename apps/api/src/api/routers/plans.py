from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar

from api.db.session import get_db_session
from api.repositories.current_squad_repository import CurrentSquadRepository
from api.repositories.my_team_projection_repository import MyTeamProjectionRepository
from api.repositories.plan_repository import PlanNotFoundError, PlanRecord, PlanRepository
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.schemas.plans import (
    CreatePlanRequestBody,
    PlanListResponse,
    PlanResponse,
    PlanSummaryResponse,
    SavePlanGameweekRequestBody,
    UpdatePlanRequestBody,
)
from api.services.get_plan_view import GetPlanViewService
from api.services.plan_accounting import PlanPlayerSelection
from api.services.plans import (
    CreatePlanRequest,
    CreatePlanService,
    DeletePlanService,
    GetPlanService,
    ListPlansService,
    SavePlanGameweekRequest,
    SavePlanGameweekService,
    UpdatePlanRequest,
    UpdatePlanService,
)
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fpl_engine.rules import RuleViolationError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/plans", tags=["plans"])

T = TypeVar("T")


def get_plan_repository(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> PlanRepository:
    return PlanRepository(db_session)


def get_plan_view_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GetPlanViewService:
    return GetPlanViewService(MyTeamProjectionRepository(db_session))


def get_list_plans_service(
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
) -> ListPlansService:
    return ListPlansService(repository)


def get_get_plan_service(
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
) -> GetPlanService:
    return GetPlanService(repository)


def get_create_plan_service(
    db_session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
) -> CreatePlanService:
    return CreatePlanService(repository, CurrentSquadRepository(db_session))


def get_update_plan_service(
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
) -> UpdatePlanService:
    return UpdatePlanService(repository)


def get_delete_plan_service(
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
) -> DeletePlanService:
    return DeletePlanService(repository)


def get_save_plan_gameweek_service(
    db_session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
) -> SavePlanGameweekService:
    return SavePlanGameweekService(repository, SquadPlayerLookupRepository(db_session))


@router.get("", response_model=PlanListResponse)
def list_plans(
    service: Annotated[ListPlansService, Depends(get_list_plans_service)],
) -> PlanListResponse:
    return PlanListResponse(
        plans=[PlanSummaryResponse.model_validate(plan) for plan in service.execute()]
    )


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(
    plan_id: int,
    service: Annotated[GetPlanService, Depends(get_get_plan_service)],
    view_service: Annotated[GetPlanViewService, Depends(get_plan_view_service)],
) -> PlanResponse:
    plan = service.execute(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return _to_response(plan, view_service)


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: CreatePlanRequestBody,
    db_session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CreatePlanService, Depends(get_create_plan_service)],
    view_service: Annotated[GetPlanViewService, Depends(get_plan_view_service)],
) -> PlanResponse:
    plan = _commit(
        db_session,
        lambda: service.execute(
            CreatePlanRequest(
                name=body.name,
                start_gameweek=body.start_gameweek,
                end_gameweek=body.end_gameweek,
            )
        ),
    )
    return _to_response(plan, view_service)


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: int,
    body: UpdatePlanRequestBody,
    db_session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[UpdatePlanService, Depends(get_update_plan_service)],
    view_service: Annotated[GetPlanViewService, Depends(get_plan_view_service)],
) -> PlanResponse:
    plan = _commit(
        db_session,
        lambda: service.execute(
            plan_id,
            UpdatePlanRequest(
                name=body.name,
                start_gameweek=body.start_gameweek,
                end_gameweek=body.end_gameweek,
            ),
        ),
    )
    return _to_response(plan, view_service)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[DeletePlanService, Depends(get_delete_plan_service)],
) -> Response:
    _commit(db_session, lambda: service.execute(plan_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{plan_id}/gameweeks/{gameweek_number}", response_model=PlanResponse)
def save_plan_gameweek(
    plan_id: int,
    gameweek_number: int,
    body: SavePlanGameweekRequestBody,
    db_session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SavePlanGameweekService, Depends(get_save_plan_gameweek_service)],
    view_service: Annotated[GetPlanViewService, Depends(get_plan_view_service)],
) -> PlanResponse:
    plan = _commit(
        db_session,
        lambda: service.execute(
            SavePlanGameweekRequest(
                plan_id=plan_id,
                gameweek_number=gameweek_number,
                chip=body.chip,
                players=[
                    PlanPlayerSelection(
                        player_id=player.player_id,
                        is_starting=player.is_starting,
                        bench_order=player.bench_order,
                        is_captain=player.is_captain,
                        is_vice_captain=player.is_vice_captain,
                    )
                    for player in body.players
                ],
            )
        ),
    )
    return _to_response(plan, view_service)


def _commit(db_session: Session, action: Callable[[], T]) -> T:
    try:
        result = action()
        db_session.commit()
        return result
    except PlanNotFoundError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found"
        ) from error
    except RuleViolationError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": error.code, "message": error.message},
        ) from error
    except ValueError as error:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception:
        db_session.rollback()
        raise


def _to_response(plan: PlanRecord, view_service: GetPlanViewService) -> PlanResponse:
    return PlanResponse.model_validate(view_service.execute(plan))
