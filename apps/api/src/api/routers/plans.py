from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar
from uuid import UUID

from api.db.session import get_db_session
from api.repositories.current_squad_repository import CurrentSquadRepository
from api.repositories.my_team_projection_repository import MyTeamProjectionRepository
from api.repositories.plan_repository import (
    PlanNotFoundError,
    PlanNotReadyError,
    PlanRecord,
    PlanRepository,
)
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.schemas.plans import (
    CreatePlanRequestBody,
    PlanListResponse,
    PlanMutationRequestBody,
    PlanMutationResponse,
    PlannerErrorResponse,
    PlanResponse,
    PlanSummaryResponse,
)
from api.services.get_plan_view import GetPlanViewService
from api.services.plans import (
    CreatePlanRequest,
    CreatePlanService,
    DeletePlanService,
    GetPlanService,
    ListPlansService,
    PlanMutationService,
    PlannerMutationError,
    PlannerMutationOutcome,
    SavePlanGameweekService,
    UpdatePlanService,
)
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from fpl_engine.planning.mutations import MutationRejectedError
from fpl_engine.rules import RuleViolationError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/plans", tags=["plans"])

T = TypeVar("T")


def get_plan_repository(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> PlanRepository:
    return PlanRepository(db_session)


def get_plan_mutation_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> PlanMutationService:
    return PlanMutationService(db_session, SquadPlayerLookupRepository(db_session))


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


@router.post("/{plan_id}/mutations", response_model=PlanMutationResponse)
def mutate_plan(
    plan_id: int,
    body: PlanMutationRequestBody,
    service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
    view_service: Annotated[GetPlanViewService, Depends(get_plan_view_service)],
) -> PlanMutationResponse:
    return _mutation_call(
        plan_id, body.mutation_id, lambda: service.mutate(plan_id, body), repository, view_service
    )


@router.get("/{plan_id}/mutations/{mutation_id}", response_model=PlanMutationResponse)
def get_plan_mutation(
    plan_id: int,
    mutation_id: UUID,
    service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
    repository: Annotated[PlanRepository, Depends(get_plan_repository)],
    view_service: Annotated[GetPlanViewService, Depends(get_plan_view_service)],
) -> PlanMutationResponse:
    return _mutation_call(
        plan_id, mutation_id, lambda: service.lookup(plan_id, mutation_id), repository, view_service
    )


def _mutation_call(
    plan_id: int,
    mutation_id: UUID,
    action: Callable[[], PlannerMutationOutcome],
    repository: PlanRepository,
    view_service: GetPlanViewService,
) -> PlanMutationResponse:
    def view(canonical: object) -> PlanResponse | None:
        from fpl_engine.planning.models import Plan

        if not isinstance(canonical, Plan):
            return None
        record = repository.get_for_view(plan_id, canonical=canonical)
        return _to_response(record, view_service) if record is not None else None

    try:
        outcome = action()
    except PlannerMutationError as error:
        detail = PlannerErrorResponse(
            code=error.code,
            message=error.message,
            mutation_id=mutation_id,
            plan=view(error.plan),
            candidate=view(error.candidate),
            intent_metadata=error.intent_metadata,
        )
        raise HTTPException(error.status_code, detail=jsonable_encoder(detail)) from error
    except PlanNotFoundError as error:
        raise HTTPException(
            404, detail={"code": "plan_not_found", "message": "Plan not found"}
        ) from error
    except PlanNotReadyError as error:
        raise HTTPException(
            409, detail={"code": "plan_not_ready", "message": str(error)}
        ) from error
    except MutationRejectedError as error:
        detail = PlannerErrorResponse(
            code=error.code,
            message=error.message,
            mutation_id=mutation_id,
            diagnostics=list(error.diagnostics),
        )
        raise HTTPException(422, detail=jsonable_encoder(detail)) from error
    except RuleViolationError as error:
        raise HTTPException(422, detail={"code": error.code, "message": error.message}) from error
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_input", "message": str(error)}) from error
    try:
        plan = view(outcome.plan)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return PlanMutationResponse(
            status=outcome.status,
            mutation_id=outcome.mutation_id,
            committed_revision=outcome.committed_revision,
            plan=plan,
            candidate=view(outcome.candidate),
        )
    except Exception as error:
        raise HTTPException(
            503,
            detail={
                "code": "outcome_unknown",
                "mutation_id": str(mutation_id),
                "message": "Response unavailable; reconcile the same mutation ID",
            },
        ) from error


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: int,
) -> PlanResponse:
    raise HTTPException(
        410,
        detail={
            "code": "planner_writer_retired",
            "message": "Reload the updated Planner",
            "mutation_url": f"/plans/{plan_id}/mutations",
        },
    )


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
) -> PlanResponse:
    raise HTTPException(
        410,
        detail={
            "code": "planner_writer_retired",
            "message": "Reload the updated Planner",
            "mutation_url": f"/plans/{plan_id}/mutations",
        },
    )


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
