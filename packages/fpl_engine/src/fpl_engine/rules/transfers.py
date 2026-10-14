from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fpl_engine.rules.chips import FIRST_GAMEWEEK, UNLIMITED_TRANSFER_CHIPS, Chip

MAX_BANKED_FREE_TRANSFERS = 5
FREE_TRANSFERS_PER_GAMEWEEK = 1
TRANSFER_POINTS_COST = 4


@dataclass(frozen=True)
class SquadDiff:
    players_out: tuple[int, ...]
    players_in: tuple[int, ...]

    @property
    def transfer_count(self) -> int:
        return len(self.players_in)


def diff_squads(previous: Iterable[int], current: Iterable[int]) -> SquadDiff:
    previous_ids = set(previous)
    current_ids = set(current)
    return SquadDiff(
        players_out=tuple(sorted(previous_ids - current_ids)),
        players_in=tuple(sorted(current_ids - previous_ids)),
    )


def has_unlimited_transfers(*, gameweek_number: int, chip: Chip | None) -> bool:
    """Gameweek 1 is squad selection, so transfers are free and uncapped."""
    return gameweek_number == FIRST_GAMEWEEK or chip in UNLIMITED_TRANSFER_CHIPS


def points_hit(
    *, transfers_made: int, free_transfers_available: int, chip: Chip | None, gameweek_number: int
) -> int:
    if has_unlimited_transfers(gameweek_number=gameweek_number, chip=chip):
        return 0
    return max(0, transfers_made - free_transfers_available) * TRANSFER_POINTS_COST


def free_transfers_after(
    *, available: int, transfers_made: int, chip: Chip | None, gameweek_number: int
) -> int:
    """Free transfers carried into the next gameweek, capped at five.

    Accumulation only begins after gameweek 1, so gameweek 2 always starts with
    exactly one. Wildcard/free hit consume the transfer arising for their GW.
    """
    if gameweek_number == FIRST_GAMEWEEK:
        return FREE_TRANSFERS_PER_GAMEWEEK

    remaining = (
        max(0, available - 1)
        if chip in UNLIMITED_TRANSFER_CHIPS
        else max(0, available - transfers_made)
    )
    return min(MAX_BANKED_FREE_TRANSFERS, remaining + FREE_TRANSFERS_PER_GAMEWEEK)
