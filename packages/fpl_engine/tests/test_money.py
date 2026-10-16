from __future__ import annotations

import math

import pytest
from fpl_engine.rules import (
    MAX_MONEY_TENTHS,
    RuleViolationError,
    exact_tenths,
    observed_tenths,
    tenths_to_money,
)


class TestExactTenths:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.0, 0), (0.5, 5), (4.8, 48), (12.0, 120), (-2.5, -25), (7, 70), (0.1, 1)],
    )
    def test_accepts_whole_tenths(self, value: float, expected: int) -> None:
        assert exact_tenths(value) == expected

    @pytest.mark.parametrize(
        "value",
        [0.5000000000000062, 0.55, 0.05, 4.8000000000000001e-5, 1e-12],
    )
    def test_rejects_any_non_tenth_even_representation_noise(self, value: float) -> None:
        with pytest.raises(RuleViolationError) as error:
            exact_tenths(value)
        assert error.value.code == "invalid_money"
        assert "whole number of tenths" in error.value.message

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rejects_non_finite_values(self, value: float) -> None:
        with pytest.raises(RuleViolationError) as error:
            exact_tenths(value)
        assert error.value.code == "invalid_money"

    @pytest.mark.parametrize("value", [True, False, "0.5", None])
    def test_rejects_non_numeric_types(self, value: object) -> None:
        with pytest.raises(RuleViolationError):
            exact_tenths(value)  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [1e308, -1e308, MAX_MONEY_TENTHS / 10 + 0.1])
    def test_rejects_extreme_values(self, value: float) -> None:
        with pytest.raises(RuleViolationError) as error:
            exact_tenths(value)
        assert error.value.code == "invalid_money"

    def test_the_largest_supported_amount_is_accepted(self) -> None:
        assert exact_tenths(MAX_MONEY_TENTHS / 10) == MAX_MONEY_TENTHS

    def test_label_names_the_rejected_amount(self) -> None:
        with pytest.raises(RuleViolationError, match="Saved bank must be"):
            exact_tenths(0.55, label="Saved bank")


class TestObservedTenths:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.5000000000000062, 5),
            (0.5, 5),
            (0.5000000000000009, 5),
            (-2.8000000000000016, -28),
            (9.999999999999998, 100),
            (0.4999999999999938, 5),
            (0.0, 0),
            (-0.0, 0),
            (3, 30),
        ],
    )
    def test_repairs_float_representation_noise(self, value: float, expected: int) -> None:
        assert observed_tenths(value) == expected

    @pytest.mark.parametrize(
        "value",
        [0.55, 0.05, 0.51, 0.5000001, 0.50000001, 12.34, -0.55],
    )
    def test_rejects_genuine_sub_tenth_values(self, value: float) -> None:
        with pytest.raises(RuleViolationError) as error:
            observed_tenths(value)
        assert error.value.code == "invalid_money"

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rejects_non_finite_values(self, value: float) -> None:
        with pytest.raises(RuleViolationError):
            observed_tenths(value)

    @pytest.mark.parametrize("value", [True, "0.5", None])
    def test_rejects_non_numeric_types(self, value: object) -> None:
        with pytest.raises(RuleViolationError):
            observed_tenths(value)  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [1e308, -1e308, 1e12, MAX_MONEY_TENTHS])
    def test_rejects_extreme_values(self, value: float) -> None:
        with pytest.raises(RuleViolationError):
            observed_tenths(value)

    def test_the_tolerance_is_narrow_and_explicit(self) -> None:
        # The tolerance is 1e-9 tenths: 1e-10 tenths of noise repairs, 1e-8 does not.
        assert observed_tenths(0.5 + 1e-11) == 5
        with pytest.raises(RuleViolationError):
            observed_tenths(0.5 + 1e-9)


class TestTenthsToMoney:
    @pytest.mark.parametrize(("tenths", "expected"), [(5, 0.5), (-28, -2.8), (0, 0.0), (123, 12.3)])
    def test_converts_to_the_nearest_double_of_the_decimal(
        self, tenths: int, expected: float
    ) -> None:
        assert tenths_to_money(tenths) == expected
        assert repr(tenths_to_money(tenths)) == repr(expected)
