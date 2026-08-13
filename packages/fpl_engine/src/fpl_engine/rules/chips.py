from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from enum import IntEnum, StrEnum

from fpl_engine.rules.errors import RuleViolationError

FIRST_GAMEWEEK = 1
FIRST_HALF_FINAL_GAMEWEEK = 19
FINAL_GAMEWEEK = 38


class Chip(StrEnum):
    WILDCARD = "WILDCARD"
    FREE_HIT = "FREE_HIT"
    BENCH_BOOST = "BENCH_BOOST"
    TRIPLE_CAPTAIN = "TRIPLE_CAPTAIN"


class SeasonHalf(IntEnum):
    FIRST = 1
    SECOND = 2


UNLIMITED_TRANSFER_CHIPS = frozenset({Chip.WILDCARD, Chip.FREE_HIT})
ALL_CHIPS: frozenset[Chip] = frozenset(
    {Chip.WILDCARD, Chip.FREE_HIT, Chip.BENCH_BOOST, Chip.TRIPLE_CAPTAIN}
)


def season_half(gameweek: int) -> SeasonHalf:
    if gameweek < FIRST_GAMEWEEK or gameweek > FINAL_GAMEWEEK:
        raise RuleViolationError(
            "gameweek_out_of_range",
            f"Gameweek must be between {FIRST_GAMEWEEK} and {FINAL_GAMEWEEK}",
        )
    if gameweek <= FIRST_HALF_FINAL_GAMEWEEK:
        return SeasonHalf.FIRST
    return SeasonHalf.SECOND


def validate_chip_usage(chips_by_gameweek: Mapping[int, Chip | None]) -> None:
    """Each chip may be played once per half of the season."""
    used: Counter[tuple[Chip, SeasonHalf]] = Counter()
    for gameweek, chip in chips_by_gameweek.items():
        if chip is None:
            continue
        used[(chip, season_half(gameweek))] += 1

    for (chip, half), count in used.items():
        if count > 1:
            raise RuleViolationError(
                "chip_already_used",
                f"{chip.value} can only be played once in the "
                f"{_half_label(half)} half of the season",
            )


def available_chips(gameweek: int, chips_by_gameweek: Mapping[int, Chip | None]) -> frozenset[Chip]:
    """Chips still playable in `gameweek`, ignoring any chip already set for it."""
    half = season_half(gameweek)
    used = {
        chip
        for other_gameweek, chip in chips_by_gameweek.items()
        if chip is not None and other_gameweek != gameweek and season_half(other_gameweek) is half
    }
    return ALL_CHIPS - used


def _half_label(half: SeasonHalf) -> str:
    return "first" if half is SeasonHalf.FIRST else "second"
