from __future__ import annotations

import logging

from api.core.logging import configure_logging
from api.db.session import SessionLocal
from api.repositories.projection_generation_repository import ProjectionGenerationRepository
from api.repositories.projection_repository import ProjectionRepository
from api.repositories.projection_run_repository import ProjectionRunRepository
from api.repositories.team_read_repository import TeamReadRepository
from api.services.generate_projections import GenerateProjectionsService


def main() -> None:
    configure_logging()
    logger = logging.getLogger("api.generate_projections")

    with SessionLocal() as session:
        service = GenerateProjectionsService(
            source_repository=ProjectionGenerationRepository(session),
            projection_repository=ProjectionRepository(session),
            team_repository=TeamReadRepository(session),
            run_repository=ProjectionRunRepository(session),
        )
        summary = service.execute()
        session.commit()

    logger.info(
        "Projection refresh completed",
        extra={
            "projections_generated": summary.projections_generated,
            "fixtures_considered": summary.fixtures_considered,
            "players_considered": summary.players_considered,
            "model_version": summary.model_version,
            "generated_at": summary.generated_at.isoformat(),
        },
    )


if __name__ == "__main__":
    main()
