from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fpl_engine.domain import PlayerPosition
from fpl_engine.eligibility import is_established_at_club
from fpl_engine.projections.baseline_v2 import BaselineV2PositionPriors

if TYPE_CHECKING:
    # Deferred: fpl_engine.minutes imports fpl_engine.projections.shrinkage, so a
    # runtime import here would be circular. Only used as a type annotation.
    from fpl_engine.minutes import PreSeasonRolePriors, RoleLabel

SEASON_GAMES = 38


@dataclass(frozen=True)
class PlayerHistoryForPriors:
    """One player's prior-season aggregate, as needed to compute cohort priors.

    Built by the caller by joining a player's position onto their latest
    player_snapshots row; fpl_engine has no database access.
    """

    position: PlayerPosition
    total_minutes: float
    expected_goals: float
    expected_assists: float
    starts: int
    team_join_date: dt.date | None


@dataclass(frozen=True)
class ConfiguredPositionAssumptions:
    """Assumptions the aggregate data cannot identify -- supplied, not computed.

    `start_rate_fallback` is used when a position's established-player cohort is
    too small to trust the data-derived start rate (see PriorComputationParameters).
    """

    minutes_if_start: float
    sub_appearance_probability: float
    minutes_if_sub: float
    start_rate_fallback: float


@dataclass(frozen=True)
class PriorComputationParameters:
    minimum_minutes_for_cohort_inclusion: float = 450.0
    minimum_cohort_size: int = 5
    established_cutoff_months: int = 12


DEFAULT_PRIOR_COMPUTATION_PARAMETERS = PriorComputationParameters()


@dataclass(frozen=True)
class BaselineV2PositionPriorsResolved:
    """The full resolved prior set for one position, with provenance of how each
    field was derived."""

    expected_goals_per_90: float
    expected_assists_per_90: float
    start_rate: float
    start_rate_is_fallback: bool
    minutes_if_start: float
    sub_appearance_probability: float
    minutes_if_sub: float


@dataclass(frozen=True)
class BaselineV2Priors:
    """Resolved once per snapshot generation and consumed by every player/fixture
    in a projection run, rather than recomputed ad hoc while looping through
    players."""

    by_position: Mapping[PlayerPosition, BaselineV2PositionPriorsResolved]
    probability_60_plus_by_role: Mapping[RoleLabel, float]
    probability_60_plus_default: float
    parameters: PriorComputationParameters

    def to_pre_season_role_priors(self, position: PlayerPosition) -> PreSeasonRolePriors:
        from fpl_engine.minutes import PreSeasonRolePriors

        resolved = self.by_position[position]
        return PreSeasonRolePriors(
            minutes_if_start=resolved.minutes_if_start,
            start_rate=resolved.start_rate,
            sub_appearance_probability=resolved.sub_appearance_probability,
            minutes_if_sub=resolved.minutes_if_sub,
            probability_60_plus=dict(self.probability_60_plus_by_role),
            probability_60_plus_default=self.probability_60_plus_default,
        )

    def to_baseline_v2_position_priors(self, position: PlayerPosition) -> BaselineV2PositionPriors:
        resolved = self.by_position[position]
        return BaselineV2PositionPriors(
            expected_goals_per_90=resolved.expected_goals_per_90,
            expected_assists_per_90=resolved.expected_assists_per_90,
        )


def _exposure_weighted_rate(
    histories: Sequence[PlayerHistoryForPriors],
    *,
    rate_total: str,
    parameters: PriorComputationParameters,
) -> float:
    eligible = [
        history
        for history in histories
        if history.total_minutes >= parameters.minimum_minutes_for_cohort_inclusion
    ]
    total_minutes = sum(history.total_minutes for history in eligible)
    if total_minutes <= 0:
        raise ValueError(
            "No player has enough minutes to compute a cohort productivity prior "
            f"(minimum_minutes_for_cohort_inclusion={parameters.minimum_minutes_for_cohort_inclusion})"
        )

    total_rate_numerator = sum(float(getattr(history, rate_total)) for history in eligible)
    return 90 * total_rate_numerator / total_minutes


def _start_rate(
    histories: Sequence[PlayerHistoryForPriors],
    *,
    as_of: dt.date,
    fallback: float,
    parameters: PriorComputationParameters,
) -> tuple[float, bool]:
    established = [
        history
        for history in histories
        if is_established_at_club(
            history.team_join_date, as_of=as_of, cutoff_months=parameters.established_cutoff_months
        )
    ]

    if len(established) < parameters.minimum_cohort_size:
        return fallback, True

    total_starts = sum(history.starts for history in established)
    total_opportunities = SEASON_GAMES * len(established)
    return total_starts / total_opportunities, False


def compute_baseline_v2_priors(
    histories: Sequence[PlayerHistoryForPriors],
    *,
    as_of: dt.date,
    configured_assumptions: Mapping[PlayerPosition, ConfiguredPositionAssumptions],
    probability_60_plus_by_role: Mapping[RoleLabel, float],
    probability_60_plus_default: float,
    parameters: PriorComputationParameters = DEFAULT_PRIOR_COMPUTATION_PARAMETERS,
) -> BaselineV2Priors:
    by_position: dict[PlayerPosition, BaselineV2PositionPriorsResolved] = {}
    positions_present = {history.position for history in histories}

    for position in positions_present:
        position_histories = [history for history in histories if history.position == position]
        assumptions = configured_assumptions[position]

        expected_goals_per_90 = _exposure_weighted_rate(
            position_histories, rate_total="expected_goals", parameters=parameters
        )
        expected_assists_per_90 = _exposure_weighted_rate(
            position_histories, rate_total="expected_assists", parameters=parameters
        )
        start_rate, start_rate_is_fallback = _start_rate(
            position_histories,
            as_of=as_of,
            fallback=assumptions.start_rate_fallback,
            parameters=parameters,
        )

        by_position[position] = BaselineV2PositionPriorsResolved(
            expected_goals_per_90=expected_goals_per_90,
            expected_assists_per_90=expected_assists_per_90,
            start_rate=start_rate,
            start_rate_is_fallback=start_rate_is_fallback,
            minutes_if_start=assumptions.minutes_if_start,
            sub_appearance_probability=assumptions.sub_appearance_probability,
            minutes_if_sub=assumptions.minutes_if_sub,
        )

    return BaselineV2Priors(
        by_position=by_position,
        probability_60_plus_by_role=dict(probability_60_plus_by_role),
        probability_60_plus_default=probability_60_plus_default,
        parameters=parameters,
    )
