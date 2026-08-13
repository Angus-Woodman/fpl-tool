from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_engine.rules.chips import Chip
from fpl_engine.rules.squad import SquadSlot

CAPTAIN_MULTIPLIER = 2
TRIPLE_CAPTAIN_MULTIPLIER = 3


@dataclass(frozen=True)
class GameweekScore:
    starting_points: float
    bench_points: float
    captain_bonus_points: float
    points_hit: int
    bench_boost_applied: bool

    @property
    def total_points(self) -> float:
        total = self.starting_points + self.captain_bonus_points - self.points_hit
        if self.bench_boost_applied:
            total += self.bench_points
        return total


def captain_multiplier(chip: Chip | None) -> int:
    if chip is Chip.TRIPLE_CAPTAIN:
        return TRIPLE_CAPTAIN_MULTIPLIER
    return CAPTAIN_MULTIPLIER


def score_gameweek(
    *,
    slots: Sequence[SquadSlot],
    projected_points: Mapping[int, float],
    chip: Chip | None = None,
    points_hit: int = 0,
) -> GameweekScore:
    bench_boost_applied = chip is Chip.BENCH_BOOST

    starting_points = sum(
        projected_points.get(slot.player_id, 0.0) for slot in slots if slot.is_starting
    )
    bench_points = sum(
        projected_points.get(slot.player_id, 0.0) for slot in slots if not slot.is_starting
    )

    captain_bonus_points = 0.0
    for slot in slots:
        if not slot.is_captain:
            continue
        if slot.is_starting or bench_boost_applied:
            captain_points = projected_points.get(slot.player_id, 0.0)
            captain_bonus_points = captain_points * (captain_multiplier(chip) - 1)

    return GameweekScore(
        starting_points=starting_points,
        bench_points=bench_points,
        captain_bonus_points=captain_bonus_points,
        points_hit=points_hit,
        bench_boost_applied=bench_boost_applied,
    )
