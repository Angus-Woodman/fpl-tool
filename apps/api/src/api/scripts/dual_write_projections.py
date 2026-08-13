from __future__ import annotations

import logging

from api.core.logging import configure_logging
from api.db.session import SessionLocal
from api.repositories.projection_generation_repository import ProjectionGenerationRepository
from api.repositories.projection_repository import ProjectionRepository
from api.repositories.projection_run_repository import ProjectionRunRepository
from api.repositories.team_read_repository import TeamReadRepository
from api.services.dual_write_projections import DualWriteProjectionsService
from api.services.generate_projections import GenerateProjectionsService


def main() -> None:
    configure_logging()
    logger = logging.getLogger("api.dual_write_projections")

    with SessionLocal() as session:
        source_repository = ProjectionGenerationRepository(session)
        projection_repository = ProjectionRepository(session)
        team_repository = TeamReadRepository(session)
        run_repository = ProjectionRunRepository(session)

        v1_service = GenerateProjectionsService(
            source_repository=source_repository,
            projection_repository=projection_repository,
            team_repository=team_repository,
            run_repository=run_repository,
        )
        service = DualWriteProjectionsService(
            source_repository=source_repository,
            projection_repository=projection_repository,
            team_repository=team_repository,
            run_repository=run_repository,
            v1_service=v1_service,
        )
        summary = service.execute()
        session.commit()

    logger.info(
        "Dual-write projection refresh completed",
        extra={
            "generated_at": summary.generated_at.isoformat(),
            "snapshot_generation": (
                summary.snapshot_generation.isoformat() if summary.snapshot_generation else None
            ),
            "v1_run_id": summary.v1_run_id,
            "v1_projections_generated": summary.v1.projections_generated,
            "v2_run_id": summary.v2_run_id,
            "v2_projections_generated": summary.v2_projections_generated,
            "v2_players_considered": summary.v2_players_considered,
            "v2_players_skipped_missing_snapshot": summary.v2_players_skipped_missing_snapshot,
            "v2_missing_snapshot_fraction": summary.v2_missing_snapshot_fraction,
        },
    )

    if summary.v2_missing_snapshot_warning is not None:
        logger.warning(summary.v2_missing_snapshot_warning)


if __name__ == "__main__":
    main()
