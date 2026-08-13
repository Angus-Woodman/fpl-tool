from __future__ import annotations

import datetime as dt

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.minutes import ExpectedMinutesResult, RoleConfidence, RoleLabel
from fpl_engine.projections.baseline_v2 import (
    BaselineV2Input,
    BaselineV2Parameters,
    BaselineV2PositionPriors,
    BaselineV2ProjectionModel,
)

GENERATED_AT = dt.datetime(2026, 8, 13, tzinfo=dt.UTC)

FORWARD_PRIORS = BaselineV2PositionPriors(
    expected_goals_per_90=0.35,
    expected_assists_per_90=0.15,
    sub_appearance_probability=0.15,
)
MIDFIELDER_PRIORS = BaselineV2PositionPriors(
    expected_goals_per_90=0.2,
    expected_assists_per_90=0.2,
    sub_appearance_probability=0.15,
)

PRIORS_BY_POSITION = {
    PlayerPosition.FORWARD: FORWARD_PRIORS,
    PlayerPosition.MIDFIELDER: MIDFIELDER_PRIORS,
}


def _expected_minutes(
    *,
    expected_minutes: float,
    start_probability: float,
    probability_60_plus: float,
    availability_multiplier: float = 1.0,
    role_label: RoleLabel = RoleLabel.REGULAR,
) -> ExpectedMinutesResult:
    return ExpectedMinutesResult(
        expected_minutes=expected_minutes,
        role_label=role_label,
        role_confidence=RoleConfidence.HIGH,
        start_probability=start_probability,
        minutes_if_start=75.0,
        probability_60_plus=probability_60_plus,
        availability_multiplier=availability_multiplier,
        observed_history_weight=0.7,
    )


def _input(
    *,
    position: PlayerPosition = PlayerPosition.FORWARD,
    expected_goals_per_90: float = 0.5,
    expected_assists_per_90: float = 0.1,
    total_minutes: float = 2500.0,
    opponent_effective_difficulty: int = 3,
    is_home: bool = True,
    expected_minutes: ExpectedMinutesResult | None = None,
) -> BaselineV2Input:
    return BaselineV2Input(
        player_id=1,
        fixture_id=10,
        gameweek_id=1,
        position=position,
        expected_minutes=expected_minutes
        or _expected_minutes(
            expected_minutes=80.0, start_probability=0.85, probability_60_plus=0.8
        ),
        expected_goals_per_90=expected_goals_per_90,
        expected_assists_per_90=expected_assists_per_90,
        total_minutes=total_minutes,
        opponent_effective_difficulty=opponent_effective_difficulty,
        is_home=is_home,
        generated_at=GENERATED_AT,
    )


def _model(parameters: BaselineV2Parameters | None = None) -> BaselineV2ProjectionModel:
    return BaselineV2ProjectionModel(
        priors=PRIORS_BY_POSITION, parameters=parameters or BaselineV2Parameters()
    )


class TestProbabilityOfPlaying:
    def test_combines_start_and_substitute_probability(self) -> None:
        expected_minutes = _expected_minutes(
            expected_minutes=80.0, start_probability=0.8, probability_60_plus=0.75
        )
        explanation = _model().explain(_input(expected_minutes=expected_minutes))

        # P(play) = 0.8 + (1-0.8)*0.15 = 0.83, using the position's sub-appearance prior.
        assert explanation.probability_of_playing == pytest.approx(0.8 + 0.2 * 0.15)

    def test_first_appearance_point_never_exceeds_probability_of_playing(self) -> None:
        explanation = _model().explain(_input())

        first_appearance_component = explanation.appearance_points - explanation.probability_60_plus
        assert first_appearance_component == pytest.approx(explanation.probability_of_playing)
        assert first_appearance_component <= explanation.probability_of_playing + 1e-9

    def test_rejects_inconsistent_priors_where_p60_exceeds_p_play(self) -> None:
        # A rotation-risk player (low start probability) with an implausibly high P60 prior.
        expected_minutes = _expected_minutes(
            expected_minutes=20.0, start_probability=0.1, probability_60_plus=0.9
        )

        with pytest.raises(ValueError, match="P.60"):
            _model().explain(_input(expected_minutes=expected_minutes))

    def test_appearance_points_cap_at_two(self) -> None:
        expected_minutes = _expected_minutes(
            expected_minutes=90.0, start_probability=1.0, probability_60_plus=1.0
        )
        explanation = _model().explain(_input(expected_minutes=expected_minutes))

        assert explanation.appearance_points == pytest.approx(2.0)


class TestShrinkage:
    def test_zero_history_player_resolves_exactly_to_the_position_prior(self) -> None:
        explanation = _model().explain(
            _input(expected_goals_per_90=0.0, expected_assists_per_90=0.0, total_minutes=0.0)
        )

        assert explanation.shrunk_expected_goals_per_90 == FORWARD_PRIORS.expected_goals_per_90
        assert explanation.shrunk_expected_assists_per_90 == FORWARD_PRIORS.expected_assists_per_90

    def test_a_two_minute_extreme_rate_player_stays_close_to_the_prior(self) -> None:
        explanation = _model().explain(_input(expected_goals_per_90=3.6, total_minutes=2.0))

        assert explanation.shrunk_expected_goals_per_90 == pytest.approx(
            FORWARD_PRIORS.expected_goals_per_90, abs=0.01
        )

    def test_established_player_own_rate_dominates(self) -> None:
        explanation = _model().explain(_input(expected_goals_per_90=0.78, total_minutes=2953.0))

        assert explanation.shrunk_expected_goals_per_90 > 0.6


class TestMonotonicity:
    def test_higher_xg90_strictly_increases_the_projection(self) -> None:
        low = _model().project(_input(expected_goals_per_90=0.2))
        high = _model().project(_input(expected_goals_per_90=0.8))

        assert high.projected_points > low.projected_points

    def test_higher_xa90_strictly_increases_the_projection(self) -> None:
        low = _model().project(_input(expected_assists_per_90=0.05))
        high = _model().project(_input(expected_assists_per_90=0.4))

        assert high.projected_points > low.projected_points

    def test_a_prolific_established_forward_outprojects_a_zero_minute_player(self) -> None:
        star = _model().project(
            _input(expected_goals_per_90=0.8, expected_assists_per_90=0.2, total_minutes=3000.0)
        )
        unused = _model().project(
            _input(
                expected_goals_per_90=0.0,
                expected_assists_per_90=0.0,
                total_minutes=0.0,
                expected_minutes=_expected_minutes(
                    expected_minutes=0.0, start_probability=0.0, probability_60_plus=0.0
                ),
            )
        )

        assert star.projected_points > unused.projected_points


class TestFixtureAdjustment:
    def test_an_easier_fixture_projects_higher_than_a_harder_one(self) -> None:
        easy = _model().project(_input(opponent_effective_difficulty=1))
        hard = _model().project(_input(opponent_effective_difficulty=5))

        assert easy.projected_points > hard.projected_points

    def test_home_projects_higher_than_away_otherwise_identical(self) -> None:
        home = _model().project(_input(is_home=True))
        away = _model().project(_input(is_home=False))

        assert home.projected_points > away.projected_points

    def test_fixture_adjustment_never_changes_appearance_points(self) -> None:
        easy = _model().explain(_input(opponent_effective_difficulty=1))
        hard = _model().explain(_input(opponent_effective_difficulty=5))

        assert easy.appearance_points == hard.appearance_points

    def test_difficulty_changes_the_projection_only_through_the_documented_multiplier(
        self,
    ) -> None:
        parameters = BaselineV2Parameters()
        easy = _model(parameters).explain(_input(opponent_effective_difficulty=1))
        baseline = _model(parameters).explain(_input(opponent_effective_difficulty=3))

        expected_ratio = parameters.difficulty_multipliers[1] / parameters.difficulty_multipliers[3]
        actual_ratio = (easy.goal_points + easy.assist_points) / (
            baseline.goal_points + baseline.assist_points
        )
        assert actual_ratio == pytest.approx(expected_ratio)

    def test_rejects_an_unrecognised_difficulty(self) -> None:
        with pytest.raises(ValueError):
            _model().project(_input(opponent_effective_difficulty=9))


class TestComposition:
    def test_components_sum_exactly_to_the_total(self) -> None:
        projection = _model().project(_input())

        assert projection.projected_points == pytest.approx(projection.components.total_points)

    def test_unused_v2_components_are_exactly_zero(self) -> None:
        projection = _model().project(_input())

        assert projection.components.clean_sheet_points == 0.0
        assert projection.components.bonus_points == 0.0
        assert projection.components.defensive_contribution_points == 0.0
        assert projection.components.other_points == 0.0

    def test_projection_carries_the_v2_model_version(self) -> None:
        projection = _model().project(_input())

        assert projection.model_version == "baseline_v2"

    def test_expected_minutes_is_carried_through_unchanged(self) -> None:
        expected_minutes = _expected_minutes(
            expected_minutes=63.5, start_probability=0.7, probability_60_plus=0.6
        )
        projection = _model().project(_input(expected_minutes=expected_minutes))

        assert projection.expected_minutes == 63.5


class TestDeterminism:
    def test_identical_inputs_produce_identical_projections(self) -> None:
        first = _model().project(_input())
        second = _model().project(_input())

        assert first == second

    def test_identical_inputs_produce_identical_explanations(self) -> None:
        first = _model().explain(_input())
        second = _model().explain(_input())

        assert first == second
