from __future__ import annotations

import datetime as dt

import pytest
from fpl_engine.minutes.expected_minutes import (
    ExpectedMinutesResult,
    PreSeasonMinutesParameters,
    PreSeasonRolePriors,
    RoleConfidence,
    RoleLabel,
    estimate_pre_season_expected_minutes,
    is_established_at_club,
)

AS_OF = dt.date(2026, 8, 13)

FORWARD_PRIORS = PreSeasonRolePriors(
    minutes_if_start=72.0,
    start_rate=0.4,
    sub_appearance_probability=0.15,
    minutes_if_sub=20.0,
    probability_60_plus={
        RoleLabel.NAILED: 0.6,
        RoleLabel.REGULAR: 0.35,
        RoleLabel.ROTATION_RISK: 0.1,
    },
    probability_60_plus_default=0.05,
)

PARAMETERS = PreSeasonMinutesParameters()


def _estimate(
    *,
    starts: int,
    team_join_date: dt.date | None,
    status: str = "a",
    chance_of_playing_next_round: int | None = None,
) -> ExpectedMinutesResult:
    return estimate_pre_season_expected_minutes(
        starts=starts,
        team_join_date=team_join_date,
        as_of=AS_OF,
        status=status,
        chance_of_playing_next_round=chance_of_playing_next_round,
        priors=FORWARD_PRIORS,
        parameters=PARAMETERS,
    )


class TestIsEstablishedAtClub:
    def test_a_long_tenured_player_is_established(self) -> None:
        assert is_established_at_club(dt.date(2022, 7, 1), as_of=AS_OF, cutoff_months=12) is True

    def test_a_signing_from_this_summer_is_not_established(self) -> None:
        assert is_established_at_club(dt.date(2026, 7, 1), as_of=AS_OF, cutoff_months=12) is False

    def test_no_join_date_is_not_established(self) -> None:
        assert is_established_at_club(None, as_of=AS_OF, cutoff_months=12) is False

    def test_exactly_at_the_cutoff_boundary_is_established(self) -> None:
        cutoff = dt.date(2025, 8, 13)
        assert is_established_at_club(cutoff, as_of=AS_OF, cutoff_months=12) is True

    def test_one_day_inside_the_cutoff_is_not_established(self) -> None:
        assert is_established_at_club(dt.date(2025, 8, 14), as_of=AS_OF, cutoff_months=12) is False


class TestPreSeasonMinutesNeverUsesPlayerSpecificDuration:
    """The redesign's core requirement: minutes_if_start is a cohort prior, never derived
    from this player's own total_minutes/starts, because that ratio cannot separate
    start-minutes from substitute-appearance minutes."""

    def test_minutes_if_start_always_equals_the_supplied_prior(self) -> None:
        nailed = _estimate(starts=34, team_join_date=dt.date(2020, 1, 1))
        fringe = _estimate(starts=2, team_join_date=dt.date(2020, 1, 1))

        assert nailed.minutes_if_start == FORWARD_PRIORS.minutes_if_start
        assert fringe.minutes_if_start == FORWARD_PRIORS.minutes_if_start

    def test_the_function_signature_has_no_total_minutes_parameter(self) -> None:
        # A structural guarantee, not just a convention: total_minutes cannot be
        # passed in, so it cannot leak into a player-specific duration estimate.
        import inspect

        parameters = inspect.signature(estimate_pre_season_expected_minutes).parameters
        assert "total_minutes" not in parameters
        assert "minutes" not in parameters


class TestEstablishedPlayerStartRate:
    def test_high_starts_pulls_start_rate_toward_its_own_high_observed_rate(self) -> None:
        result = _estimate(starts=34, team_join_date=dt.date(2020, 1, 1))

        assert result.start_probability > 0.7
        assert result.role_label == RoleLabel.NAILED
        assert result.role_confidence == RoleConfidence.HIGH
        assert result.observed_history_weight > 0.7

    def test_few_starts_stays_close_to_the_cohort_prior(self) -> None:
        result = _estimate(starts=1, team_join_date=dt.date(2020, 1, 1))

        assert result.start_probability == pytest.approx(FORWARD_PRIORS.start_rate, abs=0.05)
        assert result.role_confidence == RoleConfidence.MEDIUM

    def test_zero_starts_returns_exactly_the_cohort_prior(self) -> None:
        result = _estimate(starts=0, team_join_date=dt.date(2020, 1, 1))

        assert result.start_probability == FORWARD_PRIORS.start_rate
        assert result.observed_history_weight == 0.0

    def test_role_labels_follow_the_shrunk_start_rate(self) -> None:
        nailed = _estimate(starts=34, team_join_date=dt.date(2018, 1, 1))
        rotation = _estimate(starts=8, team_join_date=dt.date(2018, 1, 1))
        fringe = _estimate(starts=1, team_join_date=dt.date(2018, 1, 1))

        assert nailed.role_label == RoleLabel.NAILED
        assert rotation.role_label in {RoleLabel.ROTATION_RISK, RoleLabel.REGULAR}
        assert fringe.role_label in {RoleLabel.FRINGE, RoleLabel.ROTATION_RISK}


class TestNewToClubPlayers:
    def test_a_new_signing_gets_the_cohort_prior_regardless_of_past_starts(self) -> None:
        # Even a proven starter elsewhere: role at the NEW club is not assumed.
        result = _estimate(starts=30, team_join_date=dt.date(2026, 7, 1))

        assert result.start_probability == FORWARD_PRIORS.start_rate
        assert result.observed_history_weight == 0.0
        assert result.role_confidence == RoleConfidence.LOW
        assert result.role_label == RoleLabel.NEW_TO_CLUB

    def test_a_player_with_no_join_date_at_all_is_treated_as_unknown(self) -> None:
        result = _estimate(starts=0, team_join_date=None)

        assert result.role_label == RoleLabel.UNKNOWN
        assert result.role_confidence == RoleConfidence.LOW


class TestAvailabilitySeparateFromRole:
    def test_a_doubtful_nailed_starter_keeps_its_role_label(self) -> None:
        result = _estimate(
            starts=34,
            team_join_date=dt.date(2018, 1, 1),
            status="d",
            chance_of_playing_next_round=75,
        )

        assert result.role_label == RoleLabel.NAILED
        assert result.availability_multiplier == 0.75
        # Availability scales the final number without altering the role inputs.
        full_health = _estimate(starts=34, team_join_date=dt.date(2018, 1, 1))
        assert result.expected_minutes == pytest.approx(full_health.expected_minutes * 0.75)
        assert result.start_probability == full_health.start_probability
        assert result.minutes_if_start == full_health.minutes_if_start


class TestProbability60Plus:
    def test_uses_the_prior_for_the_players_role_label(self) -> None:
        result = _estimate(starts=34, team_join_date=dt.date(2018, 1, 1))

        assert result.probability_60_plus == FORWARD_PRIORS.probability_60_plus[RoleLabel.NAILED]

    def test_falls_back_to_the_default_when_the_role_has_no_specific_prior(self) -> None:
        result = _estimate(starts=30, team_join_date=dt.date(2026, 7, 1))

        assert result.probability_60_plus == FORWARD_PRIORS.probability_60_plus_default


class TestValidation:
    def test_negative_starts_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            _estimate(starts=-1, team_join_date=dt.date(2020, 1, 1))


class TestSubstituteContributionToExpectedMinutes:
    """The fix for the P(play)/expected-minutes inconsistency: a player who does not
    start can still contribute expected minutes (and hence attacking productivity)
    via a coarse, explicit, cohort-level substitute-appearance assumption."""

    def test_role_expected_minutes_includes_the_substitute_term(self) -> None:
        # Zero starts on an established player: start_probability is exactly the
        # cohort prior (0.4), so the formula is fully hand-verifiable.
        result = _estimate(starts=0, team_join_date=dt.date(2020, 1, 1))

        expected = 0.4 * 72.0 + 0.6 * 0.15 * 20.0
        assert result.expected_minutes == pytest.approx(expected)

    def test_a_higher_minutes_if_sub_prior_increases_expected_minutes(self) -> None:
        low_sub_minutes = PreSeasonRolePriors(
            minutes_if_start=72.0,
            start_rate=0.2,
            sub_appearance_probability=0.3,
            minutes_if_sub=0.0,
            probability_60_plus={},
            probability_60_plus_default=0.05,
        )
        high_sub_minutes = PreSeasonRolePriors(
            minutes_if_start=72.0,
            start_rate=0.2,
            sub_appearance_probability=0.3,
            minutes_if_sub=40.0,
            probability_60_plus={},
            probability_60_plus_default=0.05,
        )

        low = estimate_pre_season_expected_minutes(
            starts=30,
            team_join_date=dt.date(2026, 7, 1),
            as_of=AS_OF,
            status="a",
            chance_of_playing_next_round=None,
            priors=low_sub_minutes,
        )
        high = estimate_pre_season_expected_minutes(
            starts=30,
            team_join_date=dt.date(2026, 7, 1),
            as_of=AS_OF,
            status="a",
            chance_of_playing_next_round=None,
            priors=high_sub_minutes,
        )

        assert high.expected_minutes > low.expected_minutes

    def test_availability_scales_the_full_role_based_minutes_including_the_sub_term(
        self,
    ) -> None:
        full_health = _estimate(starts=0, team_join_date=dt.date(2020, 1, 1))
        doubtful = _estimate(
            starts=0,
            team_join_date=dt.date(2020, 1, 1),
            status="d",
            chance_of_playing_next_round=50,
        )

        assert doubtful.expected_minutes == pytest.approx(full_health.expected_minutes * 0.5)


class TestProbabilityOfPlayingConsistency:
    """P(play) and expected_minutes must come from the same start/substitute
    assumptions -- there must not be two different models of getting onto the
    pitch."""

    def test_probability_of_playing_matches_the_documented_formula(self) -> None:
        result = _estimate(starts=0, team_join_date=dt.date(2020, 1, 1))

        expected = 0.4 + 0.6 * 0.15
        assert result.probability_of_playing == pytest.approx(expected)

    def test_probability_of_playing_uses_the_same_start_probability_as_expected_minutes(
        self,
    ) -> None:
        result = _estimate(starts=34, team_join_date=dt.date(2018, 1, 1))

        expected = result.start_probability + (1 - result.start_probability) * 0.15
        assert result.probability_of_playing == pytest.approx(expected)

    def test_rejects_priors_where_p60_exceeds_probability_of_playing(self) -> None:
        inconsistent_priors = PreSeasonRolePriors(
            minutes_if_start=72.0,
            start_rate=0.1,
            sub_appearance_probability=0.0,
            minutes_if_sub=0.0,
            probability_60_plus={},
            probability_60_plus_default=0.99,
        )

        with pytest.raises(ValueError, match="P.60"):
            estimate_pre_season_expected_minutes(
                starts=0,
                team_join_date=dt.date(2026, 7, 1),
                as_of=AS_OF,
                status="a",
                chance_of_playing_next_round=None,
                priors=inconsistent_priors,
            )


class TestDeterminism:
    def test_identical_inputs_produce_identical_results(self) -> None:
        first = _estimate(starts=20, team_join_date=dt.date(2021, 1, 1))
        second = _estimate(starts=20, team_join_date=dt.date(2021, 1, 1))

        assert first == second


class TestAvailabilityScalesProbabilityOfPlaying:
    """A discovered-and-fixed bug: a player ruled out this gameweek must not keep
    full role-based appearance-points credit while simultaneously showing
    near-zero expected_minutes -- probability_of_playing/probability_60_plus must
    reflect current availability too, not just expected_minutes."""

    def test_a_ruled_out_player_has_zero_probability_of_playing_and_p60(self) -> None:
        result = _estimate(
            starts=34,
            team_join_date=dt.date(2018, 1, 1),
            status="i",
            chance_of_playing_next_round=0,
        )

        assert result.probability_of_playing == 0.0
        assert result.probability_60_plus == 0.0
        assert result.expected_minutes == 0.0

    def test_a_doubtful_player_scales_probability_of_playing_by_availability(self) -> None:
        full_health = _estimate(starts=34, team_join_date=dt.date(2018, 1, 1))
        doubtful = _estimate(
            starts=34,
            team_join_date=dt.date(2018, 1, 1),
            status="d",
            chance_of_playing_next_round=75,
        )

        assert doubtful.probability_of_playing == pytest.approx(
            full_health.probability_of_playing * 0.75
        )
        assert doubtful.probability_60_plus == pytest.approx(full_health.probability_60_plus * 0.75)
