from __future__ import annotations

from fpl_engine.domain import Projection
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import ProjectionModel

UPSERT_BATCH_SIZE = 500


class ProjectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, projections: list[Projection]) -> None:
        if not projections:
            return

        for start_index in range(0, len(projections), UPSERT_BATCH_SIZE):
            batch = projections[start_index : start_index + UPSERT_BATCH_SIZE]
            values = [
                {
                    "player_id": projection.player_id,
                    "fixture_id": projection.fixture_id,
                    "gameweek_id": projection.gameweek_id,
                    "projected_points": projection.projected_points,
                    "expected_minutes": projection.expected_minutes,
                    "appearance_points": projection.components.appearance_points,
                    "goal_points": projection.components.goal_points,
                    "assist_points": projection.components.assist_points,
                    "clean_sheet_points": projection.components.clean_sheet_points,
                    "bonus_points": projection.components.bonus_points,
                    "defensive_contribution_points": (
                        projection.components.defensive_contribution_points
                    ),
                    "other_points": projection.components.other_points,
                    "generated_at": projection.generated_at,
                    "model_version": projection.model_version,
                }
                for projection in batch
            ]

            statement = insert(ProjectionModel).values(values)
            statement = statement.on_conflict_do_update(
                constraint="uq_projection_versioned",
                set_={
                    "fixture_id": statement.excluded.fixture_id,
                    "projected_points": statement.excluded.projected_points,
                    "expected_minutes": statement.excluded.expected_minutes,
                    "appearance_points": statement.excluded.appearance_points,
                    "goal_points": statement.excluded.goal_points,
                    "assist_points": statement.excluded.assist_points,
                    "clean_sheet_points": statement.excluded.clean_sheet_points,
                    "bonus_points": statement.excluded.bonus_points,
                    "defensive_contribution_points": (
                        statement.excluded.defensive_contribution_points
                    ),
                    "other_points": statement.excluded.other_points,
                },
            )
            self._session.execute(statement)
