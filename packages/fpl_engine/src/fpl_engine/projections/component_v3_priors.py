from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from fpl_engine.domain import PlayerPosition
from fpl_engine.projections.shrinkage import WeightedComponent, shrink_rate, weighted_mean


@dataclass(frozen=True)
class PlayerHistoryForTeamDefense:
    """One player's prior-season clean-sheet record, as needed to reconstruct a
    team-level defensive baseline without double-counting.

    A clean sheet is a team event: summing raw clean-sheet counts across
    several of a team's players would count the same match's clean sheet once
    per player who featured in it. Exposure-weighted averaging (see
    compute_team_defense_priors) avoids this because clean_sheets_per_90 is
    already a per-appearance rate, not a count.
    """

    team_id: int
    position: PlayerPosition
    clean_sheets_per_90: float
    total_minutes: float


@dataclass(frozen=True)
class GoalkeeperSavesHistory:
    saves_per_90: float
    total_minutes: float


@dataclass(frozen=True)
class TeamDefensePriorParameters:
    team_cs_m0: float = 900.0
    # Goalkeeper-only by default: a team's own goalkeeper(s) give a cleaner,
    # lower-noise read on the team's true clean-sheet rate than including
    # outfield players, whose per-90 rate is diluted by substitution timing.
    # Kept configurable so GK+DEF (or other combinations) can be compared
    # later if backtesting suggests they perform better.
    defense_history_positions: frozenset[PlayerPosition] = field(
        default_factory=lambda: frozenset({PlayerPosition.GOALKEEPER})
    )


DEFAULT_TEAM_DEFENSE_PRIOR_PARAMETERS = TeamDefensePriorParameters()


@dataclass(frozen=True)
class ResolvedTeamDefense:
    team_id: int
    clean_sheet_rate: float
    observed_history_weight: float
    # Provenance: confirms this was derived from the team's SOURCE strength,
    # never a manual difficulty override (see api.services.component_v3_projections).
    source_difficulty_used: int


def compute_team_defense_priors(
    histories: Sequence[PlayerHistoryForTeamDefense],
    *,
    team_source_difficulty: Mapping[int, int],
    cs_prior_by_strength: Mapping[int, float],
    parameters: TeamDefensePriorParameters = DEFAULT_TEAM_DEFENSE_PRIOR_PARAMETERS,
) -> dict[int, ResolvedTeamDefense]:
    """Resolve one shrunk clean-sheet rate per team in `team_source_difficulty`.

    A team with no eligible history (e.g. newly promoted) naturally resolves
    to exactly its strength-derived prior: shrink_rate's sample_weight is 0,
    so the observed term drops out entirely. No separate fallback branch is
    needed -- this is the fallback hierarchy.
    """
    by_team: dict[int, list[PlayerHistoryForTeamDefense]] = defaultdict(list)
    for history in histories:
        if history.position in parameters.defense_history_positions and history.total_minutes > 0:
            by_team[history.team_id].append(history)

    resolved: dict[int, ResolvedTeamDefense] = {}
    for team_id, source_difficulty in team_source_difficulty.items():
        team_histories = by_team.get(team_id, [])
        prior_rate = cs_prior_by_strength[source_difficulty]

        if team_histories:
            observed_rate = weighted_mean(
                [
                    WeightedComponent(
                        value=history.clean_sheets_per_90, weight=history.total_minutes
                    )
                    for history in team_histories
                ]
            )
            sample_weight = sum(history.total_minutes for history in team_histories)
        else:
            observed_rate = 0.0
            sample_weight = 0.0

        shrunk = shrink_rate(
            observed_rate=observed_rate,
            sample_weight=sample_weight,
            prior_rate=prior_rate,
            prior_weight=parameters.team_cs_m0,
        )
        resolved[team_id] = ResolvedTeamDefense(
            team_id=team_id,
            clean_sheet_rate=shrunk.value,
            observed_history_weight=shrunk.observed_share,
            source_difficulty_used=source_difficulty,
        )

    return resolved


def compute_saves_prior(histories: Sequence[GoalkeeperSavesHistory]) -> float:
    eligible = [history for history in histories if history.total_minutes > 0]
    if not eligible:
        raise ValueError("No goalkeeper has any minutes to compute a saves prior")

    return weighted_mean(
        [
            WeightedComponent(value=history.saves_per_90, weight=history.total_minutes)
            for history in eligible
        ]
    )
