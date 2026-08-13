from __future__ import annotations

from typing import Annotated

from api.db.session import get_db_session
from api.repositories.projection_generation_repository import ProjectionGenerationRepository
from api.repositories.projection_repository import ProjectionRepository
from api.services.generate_projections import GenerateProjectionsService
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

router = APIRouter(prefix="/projections", tags=["projections"])


class ProjectionRefreshResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    projections_generated: int
    fixtures_considered: int
    players_considered: int
    model_version: str
    generated_at: str


def get_generate_projections_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> GenerateProjectionsService:
    return GenerateProjectionsService(
        source_repository=ProjectionGenerationRepository(db_session),
        projection_repository=ProjectionRepository(db_session),
    )


@router.post("/run", response_model=ProjectionRefreshResponse)
def run_projections_refresh(
    service: Annotated[GenerateProjectionsService, Depends(get_generate_projections_service)],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ProjectionRefreshResponse:
    try:
        summary = service.execute()
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    return ProjectionRefreshResponse(
        projections_generated=summary.projections_generated,
        fixtures_considered=summary.fixtures_considered,
        players_considered=summary.players_considered,
        model_version=summary.model_version,
        generated_at=summary.generated_at.isoformat(),
    )
