from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

from fpl_engine.minutes.availability import availability_multiplier
from fpl_engine.projections.shrinkage import shrink_rate

SEASON_GAMES = 38


class RoleLabel(StrEnum):
    NAILED = "NAILED"
    REGULAR = "REGULAR"
    ROTATION_RISK = "ROTATION_RISK"
    FRINGE = "FRINGE"
    UNKNOWN = "UNKNOWN"
    NEW_TO_CLUB = "NEW_TO_CLUB"


class RoleConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class PreSeasonRolePriors:
    """Cohort/position-level priors, computed by the caller from real data.

    fpl_engine has no database access, so these are supplied rather than derived
    here. `minutes_if_start` is deliberately the only source of playing duration:
    prior-season total_minutes/starts cannot separate start-minutes from
    substitute-appearance minutes, so no player-specific version of it exists.
    """

    minutes_if_start: float
    start_rate: float
    probability_60_plus: dict[RoleLabel, float] = field(default_factory=dict)
    probability_60_plus_default: float = 0.2


@dataclass(frozen=True)
class PreSeasonMinutesParameters:
    established_cutoff_months: int = 12
    m0_start_rate: float = 8.0
    high_confidence_starts: int = 10
    nailed_threshold: float = 30 / SEASON_GAMES
    regular_threshold: float = 15 / SEASON_GAMES
    rotation_threshold: float = 5 / SEASON_GAMES
    fringe_threshold: float = 1 / SEASON_GAMES


DEFAULT_PRE_SEASON_PARAMETERS = PreSeasonMinutesParameters()


@dataclass(frozen=True)
class ExpectedMinutesResult:
    expected_minutes: float
    role_label: RoleLabel
    role_confidence: RoleConfidence
    start_probability: float
    minutes_if_start: float
    probability_60_plus: float
    availability_multiplier: float
    observed_history_weight: float


def is_established_at_club(
    team_join_date: dt.date | None, *, as_of: dt.date, cutoff_months: int
) -> bool:
    """Whether `starts / 38` is defensible: the player was at this club before last
    season began. This does not detect loans away or mid-season returns; that
    information isn't available, so those cases are simply not treated as
    established (an accepted limitation, not solved).
    """
    if team_join_date is None:
        return False

    return team_join_date <= _months_before(as_of, cutoff_months)


def _months_before(date: dt.date, months: int) -> dt.date:
    month_index = date.month - 1 - months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(date.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def _role_label(start_probability: float, parameters: PreSeasonMinutesParameters) -> RoleLabel:
    if start_probability >= parameters.nailed_threshold:
        return RoleLabel.NAILED
    if start_probability >= parameters.regular_threshold:
        return RoleLabel.REGULAR
    if start_probability >= parameters.rotation_threshold:
        return RoleLabel.ROTATION_RISK
    if start_probability >= parameters.fringe_threshold:
        return RoleLabel.FRINGE
    return RoleLabel.UNKNOWN


def estimate_pre_season_expected_minutes(
    *,
    starts: int,
    team_join_date: dt.date | None,
    as_of: dt.date,
    status: str,
    chance_of_playing_next_round: int | None,
    priors: PreSeasonRolePriors,
    parameters: PreSeasonMinutesParameters = DEFAULT_PRE_SEASON_PARAMETERS,
) -> ExpectedMinutesResult:
    """A deliberately coarse pre-season estimate.

    `minutes_if_start` is always the supplied cohort prior -- never derived from
    this player's own minutes, since prior-season aggregates cannot separate
    start-minutes from substitute-appearance minutes (see PreSeasonRolePriors).
    Only `start_probability` uses player-specific data, and only when a genuine
    opportunity denominator (38 games) is defensible.
    """
    if starts < 0:
        raise ValueError(f"starts cannot be negative: {starts}")

    established = is_established_at_club(
        team_join_date, as_of=as_of, cutoff_months=parameters.established_cutoff_months
    )

    if established:
        shrunk = shrink_rate(
            observed_rate=min(starts, SEASON_GAMES) / SEASON_GAMES,
            sample_weight=float(starts),
            prior_rate=priors.start_rate,
            prior_weight=parameters.m0_start_rate,
        )
        start_probability = shrunk.value
        observed_history_weight = shrunk.observed_share
        role_confidence = (
            RoleConfidence.HIGH
            if starts >= parameters.high_confidence_starts
            else RoleConfidence.MEDIUM
        )
        role_label = _role_label(start_probability, parameters)
    else:
        start_probability = priors.start_rate
        observed_history_weight = 0.0
        role_confidence = RoleConfidence.LOW
        role_label = RoleLabel.NEW_TO_CLUB if team_join_date is not None else RoleLabel.UNKNOWN

    probability_60_plus = priors.probability_60_plus.get(
        role_label, priors.probability_60_plus_default
    )
    availability = availability_multiplier(
        status=status, chance_of_playing_next_round=chance_of_playing_next_round
    )
    expected_minutes = start_probability * priors.minutes_if_start * availability

    return ExpectedMinutesResult(
        expected_minutes=expected_minutes,
        role_label=role_label,
        role_confidence=role_confidence,
        start_probability=start_probability,
        minutes_if_start=priors.minutes_if_start,
        probability_60_plus=probability_60_plus,
        availability_multiplier=availability,
        observed_history_weight=observed_history_weight,
    )
