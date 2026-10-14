from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Literal

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


@dataclass(frozen=True)
class ChipAvailability:
    state: Literal[
        "available", "planned_here", "planned_elsewhere", "used_before", "rule_unavailable"
    ]
    reason: str | None = None
    conflicting_gameweek: int | None = None


def chip_states(
    gameweek: int,
    chips_by_gameweek: Mapping[int, Chip | None],
    *,
    start_gameweek: int,
    used_chips: frozenset[Chip] = frozenset(),
    free_hit_gameweek_19: bool = False,
) -> dict[Chip, ChipAvailability]:
    half = season_half(gameweek)
    states: dict[Chip, ChipAvailability] = {}
    for chip in Chip:
        if gameweek == 1 and chip in UNLIMITED_TRANSFER_CHIPS:
            state = ChipAvailability(
                "rule_unavailable", f"{chip.value} is unavailable in gameweek 1"
            )
        elif chip == Chip.FREE_HIT and (
            (gameweek == 20 and (free_hit_gameweek_19 or chips_by_gameweek.get(19) == chip))
            or (gameweek == 19 and chips_by_gameweek.get(20) == chip)
        ):
            conflict = 19 if gameweek == 20 else 20
            state = ChipAvailability(
                "rule_unavailable", f"Free Hit conflicts with gameweek {conflict}", conflict
            )
        elif half == season_half(start_gameweek) and chip in used_chips:
            state = ChipAvailability("used_before", "Used before this plan")
        else:
            elsewhere = next(
                (
                    number
                    for number, planned in sorted(chips_by_gameweek.items())
                    if number != gameweek and planned == chip and season_half(number) == half
                ),
                None,
            )
            if elsewhere is not None:
                state = ChipAvailability(
                    "planned_elsewhere", f"Planned for gameweek {elsewhere}", elsewhere
                )
            elif chips_by_gameweek.get(gameweek) == chip:
                state = ChipAvailability("planned_here")
            elif chips_by_gameweek.get(gameweek) is not None:
                state = ChipAvailability(
                    "rule_unavailable", f"Another chip is planned for gameweek {gameweek}", gameweek
                )
            else:
                state = ChipAvailability("available")
        states[chip] = state
    return states


def validate_starting_declarations(
    start_gameweek: int, used_chips: frozenset[Chip], free_hit_gameweek_19: bool
) -> None:
    season_half(start_gameweek)
    if start_gameweek in {1, 20} and used_chips:
        raise RuleViolationError("starting_chips", "No used chips may be declared at GW1 or GW20")
    if start_gameweek != 20 and free_hit_gameweek_19:
        raise RuleViolationError("starting_chips", "FH19 is only applicable to a gameweek 20 start")


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
