import datetime as dt

from api.repositories.projection_repository import ProjectionRepository
from fpl_engine.domain import Projection, ProjectionComponentBreakdown


class _FakeSession:
    def __init__(self) -> None:
        self.execute_calls = 0

    def execute(self, statement: object) -> None:
        self.execute_calls += 1


def _projection_for_index(index: int) -> Projection:
    return Projection(
        player_id=index,
        fixture_id=index,
        gameweek_id=index,
        projected_points=5.0,
        expected_minutes=80.0,
        generated_at=dt.datetime(2026, 8, 11, tzinfo=dt.UTC),
        model_version="baseline_v1",
        components=ProjectionComponentBreakdown(
            appearance_points=2.0,
            goal_points=1.0,
            assist_points=0.5,
            clean_sheet_points=0.5,
            bonus_points=0.5,
            defensive_contribution_points=0.5,
            other_points=0.0,
        ),
    )


def test_projection_repository_batches_large_upserts() -> None:
    session = _FakeSession()
    repository = ProjectionRepository(session)  # type: ignore[arg-type]

    repository.upsert_many([_projection_for_index(index) for index in range(1200)])

    assert session.execute_calls == 3
