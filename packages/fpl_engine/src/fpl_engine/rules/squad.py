from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules.errors import RuleViolationError

SQUAD_SIZE = 15
STARTING_SIZE = 11
BENCH_SIZE = 4
MAX_PLAYERS_PER_TEAM = 3

SQUAD_POSITION_COUNTS: dict[PlayerPosition, int] = {
    PlayerPosition.GOALKEEPER: 2,
    PlayerPosition.DEFENDER: 5,
    PlayerPosition.MIDFIELDER: 5,
    PlayerPosition.FORWARD: 3,
}

STARTING_POSITION_LIMITS: dict[PlayerPosition, tuple[int, int]] = {
    PlayerPosition.GOALKEEPER: (1, 1),
    PlayerPosition.DEFENDER: (3, 5),
    PlayerPosition.MIDFIELDER: (2, 5),
    PlayerPosition.FORWARD: (1, 3),
}


@dataclass(frozen=True)
class SquadSlot:
    player_id: int
    position: PlayerPosition
    team_id: int
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


def validate_squad_composition(slots: Sequence[SquadSlot]) -> None:
    """Validate the 15-player squad shape, captaincy, and club limits."""
    if len(slots) != SQUAD_SIZE:
        raise RuleViolationError("squad_size", f"Squad must contain exactly {SQUAD_SIZE} players")

    player_ids = [slot.player_id for slot in slots]
    if len(set(player_ids)) != len(player_ids):
        raise RuleViolationError("duplicate_player", "Squad cannot contain duplicate players")

    starters = [slot for slot in slots if slot.is_starting]
    bench = [slot for slot in slots if not slot.is_starting]

    if len(starters) != STARTING_SIZE:
        raise RuleViolationError(
            "starting_size", f"Squad must contain exactly {STARTING_SIZE} starting players"
        )
    if len(bench) != BENCH_SIZE:
        raise RuleViolationError(
            "bench_size", f"Squad must contain exactly {BENCH_SIZE} bench players"
        )

    if {slot.bench_order for slot in bench} != set(range(1, BENCH_SIZE + 1)):
        raise RuleViolationError("bench_order", "Bench players must use bench order 1, 2, 3, and 4")
    if any(slot.bench_order is not None for slot in starters):
        raise RuleViolationError("bench_order", "Starting players cannot have a bench order")

    captains = [slot for slot in slots if slot.is_captain]
    vice_captains = [slot for slot in slots if slot.is_vice_captain]

    if len(captains) != 1:
        raise RuleViolationError("captain", "Squad must contain exactly one captain")
    if len(vice_captains) != 1:
        raise RuleViolationError("vice_captain", "Squad must contain exactly one vice-captain")
    if captains[0].player_id == vice_captains[0].player_id:
        raise RuleViolationError("captain", "Captain and vice-captain must be different players")

    positions = Counter(slot.position for slot in slots)
    if positions != Counter(SQUAD_POSITION_COUNTS):
        raise RuleViolationError(
            "squad_positions", "Squad must contain 2 GK, 5 DEF, 5 MID, and 3 FWD"
        )

    teams = Counter(slot.team_id for slot in slots)
    if any(count > MAX_PLAYERS_PER_TEAM for count in teams.values()):
        raise RuleViolationError(
            "club_limit",
            f"Squad cannot contain more than {MAX_PLAYERS_PER_TEAM} players from one team",
        )


def validate_starting_formation(slots: Iterable[SquadSlot]) -> None:
    """Validate that the starting XI uses a legal FPL formation."""
    positions = Counter(slot.position for slot in slots if slot.is_starting)
    for position, (minimum, maximum) in STARTING_POSITION_LIMITS.items():
        count = positions[position]
        if count < minimum or count > maximum:
            raise RuleViolationError(
                "formation",
                f"Starting XI must contain between {minimum} and {maximum} {position.value}",
            )


def validate_squad(slots: Sequence[SquadSlot]) -> None:
    validate_squad_composition(slots)
    validate_starting_formation(slots)
