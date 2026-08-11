import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.projections import BaselineProjectionModel, ProjectionInput


def test_baseline_projection_returns_versioned_result_with_components() -> None:
    model = BaselineProjectionModel()
    result = model.project(
        ProjectionInput(
            player_id=1,
            fixture_id=10,
            gameweek_id=3,
            player_position=PlayerPosition.MIDFIELDER,
            points_per_minute=0.06,
            recent_minutes=(70, 80, 90),
            fixture_difficulty_multiplier=1.1,
        )
    )

    assert result.player_id == 1
    assert result.fixture_id == 10
    assert result.gameweek_id == 3
    assert result.expected_minutes == pytest.approx(80.0)
    assert result.projected_points == pytest.approx(5.28)
    assert result.components.total_points == pytest.approx(result.projected_points)
    assert result.components.goal_points > result.components.clean_sheet_points


def test_baseline_model_version_is_present() -> None:
    model = BaselineProjectionModel()

    assert model.model_version == "baseline_v1"


def test_baseline_projection_zeroes_expected_minutes_for_unavailable_player() -> None:
    model = BaselineProjectionModel()

    result = model.project(
        ProjectionInput(
            player_id=7,
            fixture_id=None,
            gameweek_id=4,
            player_position=PlayerPosition.DEFENDER,
            points_per_minute=0.05,
            recent_minutes=(90, 90, 90),
            fixture_difficulty_multiplier=1.0,
            availability_status="i",
        )
    )

    assert result.expected_minutes == 0.0
    assert result.projected_points == 0.0


def test_project_points_compatibility_method_matches_projection_result() -> None:
    model = BaselineProjectionModel()
    data = ProjectionInput(
        player_id=11,
        fixture_id=22,
        gameweek_id=5,
        player_position=PlayerPosition.FORWARD,
        points_per_minute=0.07,
        recent_minutes=(60, 75, 80),
        fixture_difficulty_multiplier=0.95,
        chance_of_playing_next_round=80,
    )

    assert model.project_points(data) == pytest.approx(model.project(data).projected_points)
