from __future__ import annotations

import datetime as dt

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.minutes import ExpectedMinutesResult, RoleConfidence, RoleLabel
from fpl_engine.projections.component_v3 import (
    DEFAULT_COMPONENT_V3_PARAMETERS,
    ComponentV3Input,
    ComponentV3Parameters,
    ComponentV3PositionPriors,
    ComponentV3ProjectionModel,
)

GENERATED_AT = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC)

PRIORS = {
    PlayerPosition.GOALKEEPER: ComponentV3PositionPriors(
        expected_goals_per_90=0.0, expected_assists_per_90=0.0, saves_per_90=2.5
    ),
    PlayerPosition.DEFENDER: ComponentV3PositionPriors(
        expected_goals_per_90=0.06, expected_assists_per_90=0.05
    ),
    PlayerPosition.MIDFIELDER: ComponentV3PositionPriors(
        expected_goals_per_90=0.16, expected_assists_per_90=0.13
    ),
    PlayerPosition.FORWARD: ComponentV3PositionPriors(
        expected_goals_per_90=0.44, expected_assists_per_90=0.06
    ),
}


def _expected_minutes(
    *,
    expected_minutes: float = 81.0,
    probability_of_playing: float = 0.9,
    probability_60_plus: float = 0.75,
) -> ExpectedMinutesResult:
    return ExpectedMinutesResult(
        expected_minutes=expected_minutes,
        role_label=RoleLabel.NAILED,
        role_confidence=RoleConfidence.HIGH,
        start_probability=0.85,
        minutes_if_start=85.0,
        probability_of_playing=probability_of_playing,
        probability_60_plus=probability_60_plus,
        availability_multiplier=1.0,
        observed_history_weight=0.9,
    )


def _input(
    *,
    position: PlayerPosition = PlayerPosition.FORWARD,
    expected_goals_per_90: float = 0.5,
    expected_assists_per_90: float = 0.1,
    total_minutes: float = 2500.0,
    saves_per_90: float = 0.0,
    own_team_clean_sheet_rate: float = 0.3,
    opponent_source_difficulty: int = 3,
    is_home: bool = True,
    expected_minutes: ExpectedMinutesResult | None = None,
) -> ComponentV3Input:
    return ComponentV3Input(
        player_id=1,
        fixture_id=101,
        gameweek_id=5,
        position=position,
        expected_minutes=expected_minutes or _expected_minutes(),
        expected_goals_per_90=expected_goals_per_90,
        expected_assists_per_90=expected_assists_per_90,
        total_minutes=total_minutes,
        saves_per_90=saves_per_90,
        own_team_clean_sheet_rate=own_team_clean_sheet_rate,
        opponent_source_difficulty=opponent_source_difficulty,
        is_home=is_home,
        generated_at=GENERATED_AT,
    )


def _model(
    parameters: ComponentV3Parameters = DEFAULT_COMPONENT_V3_PARAMETERS,
) -> ComponentV3ProjectionModel:
    return ComponentV3ProjectionModel(priors=PRIORS, parameters=parameters)


class TestAppearanceGoalAssistPointsMatchTheCarriedOverFormula:
    def test_appearance_points_is_p_play_plus_p60(self) -> None:
        model = _model()
        explanation = model.explain(_input())

        assert explanation.appearance_points == pytest.approx(0.9 + 0.75)

    def test_goal_points_uses_shrunk_rate_minutes_fraction_and_fixture_multiplier(self) -> None:
        model = _model()
        data = _input(
            position=PlayerPosition.FORWARD, expected_goals_per_90=0.5, total_minutes=2500.0
        )
        explanation = model.explain(data)

        prior = PRIORS[PlayerPosition.FORWARD].expected_goals_per_90
        shrunk = (0.5 * 2500.0 + prior * DEFAULT_COMPONENT_V3_PARAMETERS.xg90_m0) / (
            2500.0 + DEFAULT_COMPONENT_V3_PARAMETERS.xg90_m0
        )
        minutes_fraction = data.expected_minutes.expected_minutes / 90
        fixture_multiplier = (
            DEFAULT_COMPONENT_V3_PARAMETERS.home_venue_multiplier
            * DEFAULT_COMPONENT_V3_PARAMETERS.difficulty_multipliers[3]
        )
        expected = (
            shrunk
            * minutes_fraction
            * DEFAULT_COMPONENT_V3_PARAMETERS.goal_points[PlayerPosition.FORWARD]
            * fixture_multiplier
        )
        assert explanation.goal_points == pytest.approx(expected)
        assert explanation.shrunk_expected_goals_per_90 == pytest.approx(shrunk)

    def test_uses_opponent_source_difficulty_not_effective_difficulty(self) -> None:
        """component_v3 must key off source strength -- there is no
        `opponent_effective_difficulty` field on ComponentV3Input at all."""
        assert "opponent_effective_difficulty" not in ComponentV3Input.__dataclass_fields__
        assert "opponent_source_difficulty" in ComponentV3Input.__dataclass_fields__

    def test_unrecognised_attacking_difficulty_raises(self) -> None:
        model = _model()
        with pytest.raises(ValueError, match="difficulty"):
            model.explain(_input(opponent_source_difficulty=99))


class TestTeamCleanSheetProbability:
    def test_combines_baseline_opponent_multiplier_and_venue_multiplier(self) -> None:
        parameters = ComponentV3Parameters(
            opponent_attack_multipliers_for_clean_sheets={1: 1.2, 2: 1.1, 3: 1.0, 4: 0.9, 5: 0.75},
            home_clean_sheet_multiplier=1.1,
            away_clean_sheet_multiplier=0.9,
        )
        model = _model(parameters)
        data = _input(own_team_clean_sheet_rate=0.3, opponent_source_difficulty=2, is_home=True)

        explanation = model.explain(data)

        expected_raw = 0.3 * 1.1 * 1.1
        assert explanation.team_clean_sheet_probability_raw == pytest.approx(expected_raw)
        assert explanation.team_clean_sheet_probability == pytest.approx(expected_raw)
        assert explanation.team_clean_sheet_probability_was_clamped is False

    def test_clean_sheet_points_multiplies_by_p60_and_position_points(self) -> None:
        parameters = ComponentV3Parameters(
            clean_sheet_points={
                PlayerPosition.GOALKEEPER: 4.0,
                PlayerPosition.DEFENDER: 4.0,
                PlayerPosition.MIDFIELDER: 1.0,
                PlayerPosition.FORWARD: 0.0,
            }
        )
        model = _model(parameters)
        data = _input(
            position=PlayerPosition.DEFENDER,
            own_team_clean_sheet_rate=0.4,
            expected_minutes=_expected_minutes(probability_60_plus=0.8),
        )

        explanation = model.explain(data)

        assert explanation.clean_sheet_points == pytest.approx(
            explanation.team_clean_sheet_probability * 0.8 * 4.0
        )

    def test_forwards_get_zero_clean_sheet_points_by_default(self) -> None:
        model = _model()
        explanation = model.explain(
            _input(position=PlayerPosition.FORWARD, own_team_clean_sheet_rate=0.9)
        )

        assert explanation.clean_sheet_points == 0.0

    def test_unrecognised_opponent_attack_difficulty_raises(self) -> None:
        model = _model()
        with pytest.raises(ValueError, match="difficulty"):
            model.explain(_input(opponent_source_difficulty=42))


class TestCleanSheetProbabilityIsClampedToUnitInterval:
    def test_a_product_above_one_is_clamped_to_one(self) -> None:
        parameters = ComponentV3Parameters(
            opponent_attack_multipliers_for_clean_sheets={3: 2.0},
            difficulty_multipliers={3: 1.0},
            home_clean_sheet_multiplier=2.0,
            away_clean_sheet_multiplier=2.0,
        )
        model = _model(parameters)
        data = _input(own_team_clean_sheet_rate=0.9, opponent_source_difficulty=3)

        explanation = model.explain(data)

        assert explanation.team_clean_sheet_probability_raw == pytest.approx(0.9 * 2.0 * 2.0)
        assert explanation.team_clean_sheet_probability == 1.0
        assert explanation.team_clean_sheet_probability_was_clamped is True

    def test_a_negative_product_is_clamped_to_zero(self) -> None:
        parameters = ComponentV3Parameters(
            opponent_attack_multipliers_for_clean_sheets={3: -1.5},
            difficulty_multipliers={3: 1.0},
        )
        model = _model(parameters)
        data = _input(own_team_clean_sheet_rate=0.5, opponent_source_difficulty=3)

        explanation = model.explain(data)

        assert explanation.team_clean_sheet_probability_raw < 0.0
        assert explanation.team_clean_sheet_probability == 0.0
        assert explanation.team_clean_sheet_probability_was_clamped is True

    def test_a_probability_already_within_bounds_is_not_flagged_as_clamped(self) -> None:
        model = _model()
        explanation = model.explain(_input(own_team_clean_sheet_rate=0.3))

        assert 0.0 <= explanation.team_clean_sheet_probability <= 1.0
        assert explanation.team_clean_sheet_probability_was_clamped is False


class TestGoalkeeperSaves:
    def test_expected_saves_and_points_use_shrunk_rate_and_minutes_fraction(self) -> None:
        model = _model()
        data = _input(position=PlayerPosition.GOALKEEPER, saves_per_90=3.5, total_minutes=3000.0)

        explanation = model.explain(data)

        prior = PRIORS[PlayerPosition.GOALKEEPER].saves_per_90
        shrunk = (3.5 * 3000.0 + prior * DEFAULT_COMPONENT_V3_PARAMETERS.saves_m0) / (
            3000.0 + DEFAULT_COMPONENT_V3_PARAMETERS.saves_m0
        )
        minutes_fraction = data.expected_minutes.expected_minutes / 90
        expected_saves = shrunk * minutes_fraction

        assert explanation.raw_saves_per_90 == 3.5
        assert explanation.shrunk_saves_per_90 == pytest.approx(shrunk)
        assert explanation.expected_saves == pytest.approx(expected_saves)
        assert explanation.expected_save_points == pytest.approx(expected_saves / 3)

    def test_non_goalkeepers_get_zero_saves_points_regardless_of_input(self) -> None:
        model = _model()
        data = _input(position=PlayerPosition.DEFENDER, saves_per_90=5.0)

        explanation = model.explain(data)

        assert explanation.raw_saves_per_90 == 0.0
        assert explanation.shrunk_saves_per_90 == 0.0
        assert explanation.expected_saves == 0.0
        assert explanation.expected_save_points == 0.0


class TestProjectReturnsAComponentBreakdown:
    def test_components_sum_to_total_points(self) -> None:
        model = _model()
        data = _input(
            position=PlayerPosition.GOALKEEPER, saves_per_90=3.0, own_team_clean_sheet_rate=0.4
        )

        projection = model.project(data)

        assert projection.components.total_points == pytest.approx(projection.projected_points)
        assert projection.components.save_points > 0.0
        assert projection.components.clean_sheet_points > 0.0
        assert projection.model_version == "component_v3"
        assert projection.run_id is None

    def test_project_points_matches_project(self) -> None:
        model = _model()
        data = _input()

        assert model.project_points(data) == pytest.approx(model.project(data).projected_points)
