from __future__ import annotations

import datetime as dt

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.minutes import RoleLabel, estimate_pre_season_expected_minutes
from fpl_engine.projections.baseline_v2 import BaselineV2ProjectionModel
from fpl_engine.projections.baseline_v2_priors import (
    ConfiguredPositionAssumptions,
    PlayerHistoryForPriors,
    PriorComputationParameters,
    compute_baseline_v2_priors,
)

AS_OF = dt.date(2026, 8, 13)
OLD_JOIN_DATE = dt.date(2018, 7, 1)
RECENT_JOIN_DATE = dt.date(2026, 7, 1)

FORWARD_ASSUMPTIONS = ConfiguredPositionAssumptions(
    minutes_if_start=68.0,
    sub_appearance_probability=0.15,
    minutes_if_sub=18.0,
    start_rate_fallback=0.3,
)
MIDFIELDER_ASSUMPTIONS = ConfiguredPositionAssumptions(
    minutes_if_start=72.0,
    sub_appearance_probability=0.15,
    minutes_if_sub=18.0,
    start_rate_fallback=0.3,
)
ASSUMPTIONS_BY_POSITION = {
    PlayerPosition.FORWARD: FORWARD_ASSUMPTIONS,
    PlayerPosition.MIDFIELDER: MIDFIELDER_ASSUMPTIONS,
    PlayerPosition.DEFENDER: MIDFIELDER_ASSUMPTIONS,
    PlayerPosition.GOALKEEPER: MIDFIELDER_ASSUMPTIONS,
}

P60_BY_ROLE = {RoleLabel.NAILED: 0.6, RoleLabel.REGULAR: 0.35, RoleLabel.ROTATION_RISK: 0.1}
P60_DEFAULT = 0.05


def _history(
    *,
    position: PlayerPosition = PlayerPosition.FORWARD,
    total_minutes: float,
    expected_goals: float,
    expected_assists: float = 0.0,
    starts: int = 0,
    team_join_date: dt.date | None = OLD_JOIN_DATE,
) -> PlayerHistoryForPriors:
    return PlayerHistoryForPriors(
        position=position,
        total_minutes=total_minutes,
        expected_goals=expected_goals,
        expected_assists=expected_assists,
        starts=starts,
        team_join_date=team_join_date,
    )


def _compute(
    histories: list[PlayerHistoryForPriors], parameters: PriorComputationParameters | None = None
):
    return compute_baseline_v2_priors(
        histories,
        as_of=AS_OF,
        configured_assumptions=ASSUMPTIONS_BY_POSITION,
        probability_60_plus_by_role=P60_BY_ROLE,
        probability_60_plus_default=P60_DEFAULT,
        parameters=parameters or PriorComputationParameters(),
    )


class TestExposureWeightedProductivityPriors:
    def test_xg90_is_the_ratio_of_summed_goals_to_summed_minutes(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=25.0),
            _history(total_minutes=1500.0, expected_goals=5.0),
        ]
        priors = _compute(histories)

        expected = 90 * (25.0 + 5.0) / (3000.0 + 1500.0)
        assert priors.by_position[PlayerPosition.FORWARD].expected_goals_per_90 == pytest.approx(
            expected
        )

    def test_a_low_minute_extreme_rate_player_cannot_disproportionately_move_the_prior(
        self,
    ) -> None:
        established_cohort = [
            _history(total_minutes=3000.0, expected_goals=25.0),
            _history(total_minutes=2800.0, expected_goals=20.0),
        ]
        cohort_prior_without_outlier = (
            _compute(established_cohort).by_position[PlayerPosition.FORWARD].expected_goals_per_90
        )

        # A 10-minute cameo with an absurd extrapolated rate (45 xG/90) must not
        # move the prior at all, because it falls below the minutes threshold.
        outlier = _history(total_minutes=10.0, expected_goals=5.0)
        cohort_prior_with_outlier = (
            _compute([*established_cohort, outlier])
            .by_position[PlayerPosition.FORWARD]
            .expected_goals_per_90
        )

        assert cohort_prior_with_outlier == cohort_prior_without_outlier

    def test_xa90_uses_the_same_exposure_weighting(self) -> None:
        histories = [
            _history(total_minutes=2000.0, expected_goals=10.0, expected_assists=8.0),
            _history(total_minutes=1000.0, expected_goals=5.0, expected_assists=2.0),
        ]
        priors = _compute(histories)

        expected = 90 * (8.0 + 2.0) / (2000.0 + 1000.0)
        assert priors.by_position[PlayerPosition.FORWARD].expected_assists_per_90 == pytest.approx(
            expected
        )

    def test_minimum_minutes_threshold_is_configurable(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=25.0),
            _history(total_minutes=500.0, expected_goals=10.0),
        ]
        strict = _compute(
            histories, PriorComputationParameters(minimum_minutes_for_cohort_inclusion=600.0)
        )
        lenient = _compute(
            histories, PriorComputationParameters(minimum_minutes_for_cohort_inclusion=400.0)
        )

        assert strict.by_position[PlayerPosition.FORWARD].expected_goals_per_90 == pytest.approx(
            90 * 25.0 / 3000.0
        )
        assert lenient.by_position[PlayerPosition.FORWARD].expected_goals_per_90 == pytest.approx(
            90 * 35.0 / 3500.0
        )

    def test_raises_when_no_player_in_a_position_has_enough_minutes(self) -> None:
        histories = [_history(total_minutes=10.0, expected_goals=1.0)]

        with pytest.raises(ValueError, match="minutes"):
            _compute(histories)


class TestStartRatePrior:
    def test_is_summed_starts_over_summed_opportunities(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=1.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=1.0, starts=30),
            _history(total_minutes=2000.0, expected_goals=1.0, starts=20),
            _history(total_minutes=1900.0, expected_goals=1.0, starts=18),
            _history(total_minutes=1500.0, expected_goals=1.0, starts=15),
        ]
        priors = _compute(histories)

        expected = (34 + 30 + 20 + 18 + 15) / (38 * 5)
        assert priors.by_position[PlayerPosition.FORWARD].start_rate == pytest.approx(expected)
        assert priors.by_position[PlayerPosition.FORWARD].start_rate_is_fallback is False

    def test_excludes_non_established_players_from_both_sums(self) -> None:
        established = [
            _history(total_minutes=3000.0, expected_goals=1.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=1.0, starts=30),
            _history(total_minutes=2000.0, expected_goals=1.0, starts=20),
            _history(total_minutes=1900.0, expected_goals=1.0, starts=18),
            _history(total_minutes=1500.0, expected_goals=1.0, starts=15),
        ]
        # A recent signing with a huge start count elsewhere: 38 is not a
        # defensible denominator for him, so he must not enter the cohort sum.
        new_signing = _history(
            total_minutes=3000.0, expected_goals=1.0, starts=36, team_join_date=RECENT_JOIN_DATE
        )

        with_new_signing = _compute([*established, new_signing])
        without_new_signing = _compute(established)

        assert (
            with_new_signing.by_position[PlayerPosition.FORWARD].start_rate
            == without_new_signing.by_position[PlayerPosition.FORWARD].start_rate
        )

    def test_falls_back_to_the_configured_prior_when_the_cohort_is_too_small(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=1.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=1.0, starts=30),
        ]
        priors = _compute(histories, PriorComputationParameters(minimum_cohort_size=5))

        resolved = priors.by_position[PlayerPosition.FORWARD]
        assert resolved.start_rate == FORWARD_ASSUMPTIONS.start_rate_fallback
        assert resolved.start_rate_is_fallback is True

    def test_minimum_cohort_size_is_configurable(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=1.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=1.0, starts=30),
        ]
        priors = _compute(histories, PriorComputationParameters(minimum_cohort_size=2))

        resolved = priors.by_position[PlayerPosition.FORWARD]
        assert resolved.start_rate_is_fallback is False
        assert resolved.start_rate == pytest.approx((34 + 30) / (38 * 2))


class TestConfigurationDerivedPriorsPassThrough:
    """minutes_if_start, sub_appearance_probability and minutes_if_sub are never
    computed from data -- they must come through unchanged from configuration."""

    def test_minutes_if_start_is_the_configured_value_unchanged(self) -> None:
        histories = [_history(total_minutes=3000.0, expected_goals=25.0, starts=34)]
        priors = _compute(histories)

        assert (
            priors.by_position[PlayerPosition.FORWARD].minutes_if_start
            == FORWARD_ASSUMPTIONS.minutes_if_start
        )

    def test_sub_appearance_and_minutes_if_sub_are_configured_values_unchanged(self) -> None:
        histories = [_history(total_minutes=3000.0, expected_goals=25.0, starts=34)]
        priors = _compute(histories)

        resolved = priors.by_position[PlayerPosition.FORWARD]
        assert resolved.sub_appearance_probability == FORWARD_ASSUMPTIONS.sub_appearance_probability
        assert resolved.minutes_if_sub == FORWARD_ASSUMPTIONS.minutes_if_sub


class TestPipelineIntegration:
    """The resolved priors must be directly usable by the existing, already-approved
    engine functions without further conversion by the caller."""

    def test_zero_history_player_resolves_to_the_position_start_rate(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=25.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=20.0, starts=30),
        ]
        priors = _compute(histories)
        role_priors = priors.to_pre_season_role_priors(PlayerPosition.FORWARD)

        result = estimate_pre_season_expected_minutes(
            starts=0,
            team_join_date=RECENT_JOIN_DATE,
            as_of=AS_OF,
            status="a",
            chance_of_playing_next_round=None,
            priors=role_priors,
        )

        assert result.start_probability == priors.by_position[PlayerPosition.FORWARD].start_rate

    def test_resolved_priors_feed_baseline_v2_directly(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=25.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=20.0, starts=30),
        ]
        priors = _compute(histories)
        model = BaselineV2ProjectionModel(
            priors={
                PlayerPosition.FORWARD: priors.to_baseline_v2_position_priors(
                    PlayerPosition.FORWARD
                )
            }
        )

        assert model.priors[PlayerPosition.FORWARD].expected_goals_per_90 == pytest.approx(
            priors.by_position[PlayerPosition.FORWARD].expected_goals_per_90
        )


class TestDeterminism:
    def test_identical_inputs_produce_identical_priors(self) -> None:
        histories = [
            _history(total_minutes=3000.0, expected_goals=25.0, starts=34),
            _history(total_minutes=2800.0, expected_goals=20.0, starts=30),
        ]

        first = _compute(histories)
        second = _compute(histories)

        assert first == second
