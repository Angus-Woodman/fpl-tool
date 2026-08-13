from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class WeightedComponent:
    """One value contributing to a weighted average, e.g. an observed rate or a prior."""

    value: float
    weight: float


def weighted_mean(components: Sequence[WeightedComponent]) -> float:
    """A general weighted average over any number of components.

    Reused as-is for the later prior-season / current-season / cohort-prior
    blend, which is the same operation with a third component.
    """
    if not components:
        raise ValueError("weighted_mean requires at least one component")

    for component in components:
        if component.weight < 0:
            raise ValueError(f"Component weight cannot be negative: {component.weight}")

    total_weight = sum(component.weight for component in components)
    if total_weight <= 0:
        raise ValueError("Total weight must be positive")

    return sum(component.value * component.weight for component in components) / total_weight


@dataclass(frozen=True)
class ShrinkageResult:
    """A shrunk rate plus enough detail to explain where it came from."""

    value: float
    observed_weight: float
    prior_weight: float

    @property
    def total_weight(self) -> float:
        return self.observed_weight + self.prior_weight

    @property
    def observed_share(self) -> float:
        """The fraction of `value` attributable to observed data rather than the prior."""
        if self.total_weight <= 0:
            return 0.0
        return self.observed_weight / self.total_weight


def shrink_rate(
    *,
    observed_rate: float,
    sample_weight: float,
    prior_rate: float,
    prior_weight: float,
) -> ShrinkageResult:
    """Blend an observed rate toward a prior, weighted by evidence.

        shrunk = (sample_weight * observed_rate + prior_weight * prior_rate)
                 / (sample_weight + prior_weight)

    `sample_weight` is typically observed minutes and `prior_weight` a tunable
    pseudo-minutes constant (e.g. M0); both are supplied by the caller rather
    than assumed here.
    """
    result = weighted_mean(
        [
            WeightedComponent(value=observed_rate, weight=sample_weight),
            WeightedComponent(value=prior_rate, weight=prior_weight),
        ]
    )
    return ShrinkageResult(value=result, observed_weight=sample_weight, prior_weight=prior_weight)
