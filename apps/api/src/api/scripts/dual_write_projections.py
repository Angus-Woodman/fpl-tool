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
            "v3_run_id": summary.v3_run_id,
            "v3_projections_generated": summary.v3_projections_generated,
        },
    )

    if summary.v2_missing_snapshot_warning is not None:
        logger.warning(summary.v2_missing_snapshot_warning)

    # extra={} fields above aren't rendered by the default log format, so the
    # pre-deadline workflow's required fields are also printed directly here.
    gameweeks = summary.gameweeks_covered
    gameweeks_range = (
        f"{gameweeks[0]}-{gameweeks[-1]} ({len(gameweeks)} gameweeks)" if gameweeks else "none"
    )
    print(
        "\n".join(
            [
                "=== Dual-write projection refresh summary ===",
                "Snapshot generation:  "
                + (
                    summary.snapshot_generation.isoformat()
                    if summary.snapshot_generation
                    else "none"
                ),
                f"Run generated at:     {summary.generated_at.isoformat()}",
                f"Gameweeks covered:    {gameweeks_range}",
                f"Model versions:       baseline_v1 (run {summary.v1_run_id}), "
                f"baseline_v2 (run {summary.v2_run_id}), "
                f"component_v3 (run {summary.v3_run_id})",
                f"Players projected:    v1={summary.v1.projections_generated}, "
                f"v2={summary.v2_projections_generated}, v3={summary.v3_projections_generated}",
                f"Missing players (v2/v3): {summary.v2_players_skipped_missing_snapshot} "
                f"({summary.v2_missing_snapshot_fraction:.2%})"
                + (
                    f" -- ids={list(summary.v2_missing_snapshot_player_ids)}"
                    if summary.v2_missing_snapshot_player_ids
                    else ""
                ),
            ]
        )
    )


if __name__ == "__main__":
    main()
