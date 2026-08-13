from __future__ import annotations

import pytest
from fpl_engine.minutes.availability import availability_multiplier


class TestAvailabilityMultiplier:
    def test_chance_of_playing_takes_precedence_over_status(self) -> None:
        # A double penalty would give 0.75 * 0.75 = 0.5625; the correct rule uses
        # chance_of_playing_next_round alone once it is present.
        result = availability_multiplier(status="d", chance_of_playing_next_round=75)

        assert result == 0.75

    def test_zero_chance_means_fully_unavailable_regardless_of_status(self) -> None:
        assert availability_multiplier(status="i", chance_of_playing_next_round=0) == 0.0

    def test_full_chance_means_fully_available(self) -> None:
        assert availability_multiplier(status="a", chance_of_playing_next_round=100) == 1.0

    def test_falls_back_to_status_when_chance_is_absent(self) -> None:
        assert availability_multiplier(status="d", chance_of_playing_next_round=None) == 0.75

    def test_available_status_with_no_chance_is_fully_available(self) -> None:
        assert availability_multiplier(status="a", chance_of_playing_next_round=None) == 1.0

    @pytest.mark.parametrize("status", ["i", "u", "s"])
    def test_unavailable_statuses_default_to_zero_without_a_chance_value(self, status: str) -> None:
        assert availability_multiplier(status=status, chance_of_playing_next_round=None) == 0.0

    def test_unrecognised_status_without_a_chance_value_is_treated_cautiously(self) -> None:
        assert availability_multiplier(status="zz", chance_of_playing_next_round=None) == 0.85

    def test_is_deterministic(self) -> None:
        first = availability_multiplier(status="d", chance_of_playing_next_round=50)
        second = availability_multiplier(status="d", chance_of_playing_next_round=50)

        assert first == second
