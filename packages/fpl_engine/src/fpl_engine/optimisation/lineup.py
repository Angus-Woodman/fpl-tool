from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import (
    SQUAD_POSITION_COUNTS,
    SQUAD_SIZE,
    STARTING_POSITION_LIMITS,
    STARTING_SIZE,
    RuleViolationError,
    SquadSlot,
    score_gameweek,
    validate_starting_formation,
)

_POSITION_DISPLAY_ORDER = (
    PlayerPosition.GOALKEEPER,
    PlayerPosition.DEFENDER,
    PlayerPosition.MIDFIELDER,
    PlayerPosition.FORWARD,
)


@dataclass(frozen=True)
class LineupCandidate:
    """One of the 15 squad players, with the projected points to optimise
    against for a single target gameweek.

    Availability (injury, suspension, rotation risk) is expressed entirely
    through `projected_points` -- there is no separate availability flag. A
    player already expected to barely play will simply project close to zero
    and lose out to teammates who project higher, which is exactly the
    signal `fpl_engine.projections` already encodes.
    """

    player_id: int
    position: PlayerPosition
    team_id: int
    projected_points: float


@dataclass(frozen=True)
class LineupSelection:
    """The recommended lineup for one gameweek, given a 15-player squad.

    `starting_xi` is ordered goalkeeper first, then by position
    (defenders/midfielders/forwards), then by descending projected points --
    a stable "team sheet" reading order, not a ranking. `bench_outfield` is
    the three outfield substitutes in FPL auto-sub priority order (highest
    projected points first); `bench_goalkeeper` is always separate, per the
    established bench model.
    """

    starting_xi: tuple[int, ...]
    bench_goalkeeper: int
    bench_outfield: tuple[int, int, int]
    captain: int
    vice_captain: int
    starting_xi_points: float
    captain_adjusted_points: float


def _valid_formations() -> list[tuple[int, int, int]]:
    """Every (DEF, MID, FWD) outfield split that fills the 10 non-goalkeeper
    starting slots within STARTING_POSITION_LIMITS.

    Derived from fpl_engine.rules.squad's own limits rather than a
    hand-maintained list, so the two can never drift apart.
    """
    def_min, def_max = STARTING_POSITION_LIMITS[PlayerPosition.DEFENDER]
    mid_min, mid_max = STARTING_POSITION_LIMITS[PlayerPosition.MIDFIELDER]
    fwd_min, fwd_max = STARTING_POSITION_LIMITS[PlayerPosition.FORWARD]
    outfield_slots = STARTING_SIZE - 1

    return [
        (defenders, midfielders, forwards)
        for defenders in range(def_min, def_max + 1)
        for midfielders in range(mid_min, mid_max + 1)
        for forwards in range(fwd_min, fwd_max + 1)
        if defenders + midfielders + forwards == outfield_slots
    ]


def _sort_key(candidate: LineupCandidate) -> tuple[float, int]:
    # Higher projected points first; lower player_id breaks ties, so results
    # are deterministic even when projections are exactly equal.
    return (-candidate.projected_points, candidate.player_id)


def _validate_squad_shape(squad: list[LineupCandidate]) -> None:
    if len(squad) != SQUAD_SIZE:
        raise RuleViolationError(
            "squad_size", f"Lineup optimisation needs exactly {SQUAD_SIZE} players"
        )

    player_ids = [candidate.player_id for candidate in squad]
    if len(set(player_ids)) != len(player_ids):
        raise RuleViolationError("duplicate_player", "Squad cannot contain duplicate players")

    counts = Counter(candidate.position for candidate in squad)
    if counts != Counter(SQUAD_POSITION_COUNTS):
        raise RuleViolationError(
            "squad_positions", "Squad must contain 2 GK, 5 DEF, 5 MID, and 3 FWD"
        )


def optimise_lineup(squad: list[LineupCandidate]) -> LineupSelection:
    _validate_squad_shape(squad)

    by_position: dict[PlayerPosition, list[LineupCandidate]] = defaultdict(list)
    for candidate in squad:
        by_position[candidate.position].append(candidate)
    for candidates in by_position.values():
        candidates.sort(key=_sort_key)

    goalkeepers = by_position[PlayerPosition.GOALKEEPER]
    defenders = by_position[PlayerPosition.DEFENDER]
    midfielders = by_position[PlayerPosition.MIDFIELDER]
    forwards = by_position[PlayerPosition.FORWARD]

    best_formation: tuple[int, int, int] | None = None
    best_total = float("-inf")
    for def_count, mid_count, fwd_count in _valid_formations():
        starters = (
            goalkeepers[:1] + defenders[:def_count] + midfielders[:mid_count] + forwards[:fwd_count]
        )
        total = sum(candidate.projected_points for candidate in starters)
        if total > best_total:
            best_total = total
            best_formation = (def_count, mid_count, fwd_count)

    assert best_formation is not None  # squad shape already validated above
    def_count, mid_count, fwd_count = best_formation

    starters = (
        goalkeepers[:1] + defenders[:def_count] + midfielders[:mid_count] + forwards[:fwd_count]
    )
    starter_ids = {candidate.player_id for candidate in starters}

    bench_goalkeeper = goalkeepers[1]
    bench_outfield = sorted(
        defenders[def_count:] + midfielders[mid_count:] + forwards[fwd_count:],
        key=_sort_key,
    )

    squad_slots = [
        SquadSlot(
            player_id=candidate.player_id,
            position=candidate.position,
            team_id=candidate.team_id,
            is_starting=candidate.player_id in starter_ids,
            bench_order=None,
            is_captain=False,
            is_vice_captain=False,
        )
        for candidate in squad
    ]
    validate_starting_formation(squad_slots)

    ranked_starters = sorted(starters, key=_sort_key)
    captain, vice_captain = ranked_starters[0], ranked_starters[1]

    scored_slots = [
        SquadSlot(
            player_id=slot.player_id,
            position=slot.position,
            team_id=slot.team_id,
            is_starting=slot.is_starting,
            bench_order=None,
            is_captain=slot.player_id == captain.player_id,
            is_vice_captain=slot.player_id == vice_captain.player_id,
        )
        for slot in squad_slots
    ]
    score = score_gameweek(
        slots=scored_slots,
        projected_points={candidate.player_id: candidate.projected_points for candidate in squad},
    )

    display_order = sorted(
        starters,
        key=lambda candidate: (
            _POSITION_DISPLAY_ORDER.index(candidate.position),
            _sort_key(candidate),
        ),
    )

    return LineupSelection(
        starting_xi=tuple(candidate.player_id for candidate in display_order),
        bench_goalkeeper=bench_goalkeeper.player_id,
        bench_outfield=(
            bench_outfield[0].player_id,
            bench_outfield[1].player_id,
            bench_outfield[2].player_id,
        ),
        captain=captain.player_id,
        vice_captain=vice_captain.player_id,
        starting_xi_points=score.starting_points,
        captain_adjusted_points=score.starting_points + score.captain_bonus_points,
    )
