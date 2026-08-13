from __future__ import annotations

import pytest
from fpl_engine.projections.shrinkage import (
    ShrinkageResult,
    WeightedComponent,
    shrink_rate,
    weighted_mean,
)

M0 = 900.0
FORWARD_PRIOR_XG90 = 0.35


class TestWeightedMean:
    def test_single_component_returns_its_value(self) -> None:
        assert weighted_mean([WeightedComponent(value=7.0, weight=3.0)]) == 7.0

    def test_two_equal_weights_average_evenly(self) -> None:
        assert (
            weighted_mean(
                [WeightedComponent(value=4.0, weight=1.0), WeightedComponent(value=6.0, weight=1.0)]
            )
            == 5.0
        )

    def test_supports_three_components_for_the_future_blend(self) -> None:
        value = weighted_mean(
            [
                WeightedComponent(value=1.0, weight=1.0),
                WeightedComponent(value=2.0, weight=1.0),
                WeightedComponent(value=3.0, weight=1.0),
            ]
        )
        assert value == pytest.approx(2.0)

    def test_rejects_a_negative_weight(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            weighted_mean([WeightedComponent(value=1.0, weight=-1.0)])

    def test_rejects_an_empty_sequence(self) -> None:
        with pytest.raises(ValueError):
            weighted_mean([])

    def test_rejects_all_zero_weights(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            weighted_mean([WeightedComponent(value=1.0, weight=0.0)])

    def test_is_deterministic(self) -> None:
        components = [
            WeightedComponent(value=2953.0, weight=1.0),
            WeightedComponent(value=0.35, weight=900.0),
        ]
        assert weighted_mean(components) == weighted_mean(components)


class TestShrinkRate:
    def test_zero_observed_weight_returns_the_prior(self) -> None:
        result = shrink_rate(
            observed_rate=3.6, sample_weight=0.0, prior_rate=FORWARD_PRIOR_XG90, prior_weight=M0
        )

        assert result.value == FORWARD_PRIOR_XG90
        assert result.observed_share == 0.0

    def test_very_small_samples_stay_close_to_the_prior(self) -> None:
        result = shrink_rate(
            observed_rate=3.6, sample_weight=2.0, prior_rate=FORWARD_PRIOR_XG90, prior_weight=M0
        )

        assert result.value == pytest.approx(FORWARD_PRIOR_XG90, abs=0.01)
        assert result.observed_share < 0.01

    def test_large_samples_approach_the_observed_rate(self) -> None:
        result = shrink_rate(
            observed_rate=0.78, sample_weight=2953.0, prior_rate=FORWARD_PRIOR_XG90, prior_weight=M0
        )

        # With minutes far exceeding M0, the shrunk value sits closer to the
        # observed rate than to the prior, though it is not fully unshrunk.
        assert FORWARD_PRIOR_XG90 < result.value < 0.78
        assert abs(result.value - 0.78) < abs(result.value - FORWARD_PRIOR_XG90)
        assert result.observed_share > 0.75

    def test_observed_rate_equal_to_prior_is_unchanged_at_any_sample_size(self) -> None:
        result = shrink_rate(
            observed_rate=FORWARD_PRIOR_XG90,
            sample_weight=137.0,
            prior_rate=FORWARD_PRIOR_XG90,
            prior_weight=M0,
        )

        assert result.value == pytest.approx(FORWARD_PRIOR_XG90)

    def test_zero_prior_weight_returns_the_observed_rate_unshrunk(self) -> None:
        result = shrink_rate(
            observed_rate=3.6, sample_weight=2.0, prior_rate=0.35, prior_weight=0.0
        )

        assert result.value == 3.6
        assert result.observed_share == 1.0

    def test_rejects_a_negative_sample_weight(self) -> None:
        with pytest.raises(ValueError):
            shrink_rate(observed_rate=1.0, sample_weight=-1.0, prior_rate=0.5, prior_weight=M0)

    def test_rejects_a_negative_prior_weight(self) -> None:
        with pytest.raises(ValueError):
            shrink_rate(observed_rate=1.0, sample_weight=100.0, prior_rate=0.5, prior_weight=-1.0)

    def test_result_reports_its_weights_and_total(self) -> None:
        result = shrink_rate(
            observed_rate=0.78, sample_weight=2953.0, prior_rate=FORWARD_PRIOR_XG90, prior_weight=M0
        )

        assert result.observed_weight == 2953.0
        assert result.prior_weight == M0
        assert result.total_weight == 2953.0 + M0

    def test_is_deterministic(self) -> None:
        first = shrink_rate(
            observed_rate=0.78, sample_weight=2953.0, prior_rate=0.35, prior_weight=M0
        )
        second = shrink_rate(
            observed_rate=0.78, sample_weight=2953.0, prior_rate=0.35, prior_weight=M0
        )

        assert first == second

    def test_haaland_scale_minutes_versus_a_two_minute_player(self) -> None:
        """A hand-checked pair from the live pre-season data (§3 of the design)."""
        haaland = shrink_rate(
            observed_rate=0.78, sample_weight=2953.0, prior_rate=FORWARD_PRIOR_XG90, prior_weight=M0
        )
        cameo_player = shrink_rate(
            observed_rate=3.6, sample_weight=2.0, prior_rate=FORWARD_PRIOR_XG90, prior_weight=M0
        )

        expected_haaland = (2953.0 * 0.78 + M0 * FORWARD_PRIOR_XG90) / (2953.0 + M0)
        expected_cameo = (2.0 * 3.6 + M0 * FORWARD_PRIOR_XG90) / (2.0 + M0)

        assert haaland.value == pytest.approx(expected_haaland)
        assert cameo_player.value == pytest.approx(expected_cameo)

        # Established minutes dominate; two minutes barely moves the prior at all.
        assert haaland.observed_share > 0.75
        assert cameo_player.observed_share < 0.01
        assert haaland.value > cameo_player.value


class TestShrinkageResult:
    def test_observed_share_is_zero_when_there_is_no_weight_at_all(self) -> None:
        result = ShrinkageResult(value=0.0, observed_weight=0.0, prior_weight=0.0)

        assert result.observed_share == 0.0

    def test_observed_share_is_the_fraction_of_total_weight(self) -> None:
        result = ShrinkageResult(value=1.0, observed_weight=300.0, prior_weight=900.0)

        assert result.observed_share == pytest.approx(300.0 / 1200.0)
