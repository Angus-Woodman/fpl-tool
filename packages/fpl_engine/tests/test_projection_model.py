import pytest
from fpl_engine.projections import BaselineProjectionModel, ProjectionInput


def test_baseline_projection_formula() -> None:
    model = BaselineProjectionModel()
    result = model.project_points(
        ProjectionInput(
            points_per_minute=0.06,
            expected_minutes=80.0,
            fixture_difficulty_multiplier=1.1,
        )
    )

    assert result == pytest.approx(5.28)


def test_baseline_model_version_is_present() -> None:
    model = BaselineProjectionModel()

    assert model.model_version == "baseline_v1"
