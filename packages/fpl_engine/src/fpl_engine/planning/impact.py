"""Plan impact of a hypothetical transfer: replay-based per-gameweek scoring.

Pure functions over frozen plan evaluations and projected points. Impact excludes the
points hit, which is reported separately. Gameweeks beyond the validity limit are never
estimated, and the assumed continuation after the plan's end is never summed with the
saved-plan total.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from fpl_engine.planning.evaluate import squad_slots
from fpl_engine.planning.models import (
    EvaluatedGameweek,
    LineupRole,
    Ownership,
    Plan,
    PlanEvaluation,
    PlayerRuleData,
)
from fpl_engine.rules import Chip, RuleViolationError, score_gameweek, validate_squad

HORIZONS = (1, 3, 5)
LAST_GAMEWEEK = 38

ImpactBasis = Literal["saved_plan", "assumed_continuation"]
ImpactReason = Literal["no_projection", "beyond_valid_range", "continuation_lineup_illegal"]
LimitedReason = Literal["free_hit_gameweek"]


@dataclass(frozen=True)
class HorizonWindow:
    requested: tuple[int, ...]
    evaluated: tuple[int, ...]
    saved_plan: tuple[int, ...]
    assumed: tuple[int, ...]
    partial: bool
    limited_reason: LimitedReason | None


@dataclass(frozen=True)
class GameweekImpact:
    gameweek: int
    basis: ImpactBasis
    available: bool
    reason: ImpactReason | None
    points_before: float | None
    points_after: float | None
    delta: float | None
    hit_before: int
    hit_after: int


@dataclass(frozen=True)
class HorizonTotals:
    horizon: int
    requested_gameweeks: tuple[int, ...]
    evaluated_gameweeks: tuple[int, ...]
    saved_plan_gameweeks: tuple[int, ...]
    assumed_gameweeks: tuple[int, ...]
    partial: bool
    limited_reason: LimitedReason | None
    saved_plan: float | None
    assumed_continuation: float | None
    hit_change: int
    net_saved_plan: float | None
    valid_through_gameweek: int | None


@dataclass(frozen=True)
class PlanImpact:
    by_gameweek: tuple[GameweekImpact, ...]
    totals: Mapping[int, HorizonTotals]


def horizon_window(
    plan: Plan, gameweek: int, horizon: int, covered: Collection[int]
) -> HorizonWindow:
    """Gameweeks a horizon asks for, those with projections, and their basis.

    Coverage is the contiguous run of covered gameweeks starting at `gameweek`; the first
    gap ends it. A Free Hit selected gameweek limits every horizon to that gameweek.
    """
    if horizon not in HORIZONS:
        raise ValueError(f"Horizon must be one of {HORIZONS}")
    chip = next((week.chip for week in plan.gameweeks if week.gameweek_number == gameweek), None)
    limited: LimitedReason | None = "free_hit_gameweek" if chip == Chip.FREE_HIT else None
    last = gameweek if limited else min(gameweek + horizon - 1, LAST_GAMEWEEK)
    requested = tuple(range(gameweek, last + 1))
    evaluated: list[int] = []
    for number in requested:
        if number not in covered:
            break
        evaluated.append(number)
    return HorizonWindow(
        requested,
        tuple(evaluated),
        tuple(number for number in evaluated if number <= plan.end_gameweek),
        tuple(number for number in evaluated if number > plan.end_gameweek),
        len(evaluated) < len(requested),
        limited,
    )


def _week(evaluation: PlanEvaluation, gameweek: int) -> EvaluatedGameweek | None:
    return next((item for item in evaluation.gameweeks if item.gameweek_number == gameweek), None)


def _score(
    players: tuple[Ownership, ...],
    lineup: tuple[LineupRole, ...],
    chip: Chip | None,
    metadata: Mapping[int, PlayerRuleData],
    projected: Mapping[int, float],
    *,
    legal_check: bool = False,
) -> float:
    slots = squad_slots(players, lineup, metadata)
    if legal_check:
        validate_squad(slots)
    return score_gameweek(slots=slots, projected_points=projected, chip=chip).total_points


def _unavailable(
    gameweek: int,
    basis: ImpactBasis,
    reason: ImpactReason,
    hit_before: int = 0,
    hit_after: int = 0,
) -> GameweekImpact:
    return GameweekImpact(gameweek, basis, False, reason, None, None, None, hit_before, hit_after)


def _gameweek_impact(
    plan: Plan,
    baseline: PlanEvaluation,
    candidate: PlanEvaluation,
    metadata: Mapping[int, PlayerRuleData],
    projected: Mapping[int, float],
    gameweek: int,
    valid_through: int | None,
) -> GameweekImpact:
    continuation = gameweek > plan.end_gameweek
    basis: ImpactBasis = "assumed_continuation" if continuation else "saved_plan"
    if valid_through is not None and gameweek > valid_through:
        return _unavailable(gameweek, basis, "beyond_valid_range")
    if not continuation:
        before, after = _week(baseline, gameweek), _week(candidate, gameweek)
        decided = next(week for week in plan.gameweeks if week.gameweek_number == gameweek)
        if before is None or after is None or before.players is None or after.players is None:
            return _unavailable(gameweek, basis, "beyond_valid_range")
        hit_before, hit_after = before.points_hit or 0, after.points_hit or 0
        points_before = _score(before.players, before.lineup, decided.chip, metadata, projected)
        points_after = _score(after.players, after.lineup, decided.chip, metadata, projected)
        return GameweekImpact(
            gameweek,
            basis,
            True,
            None,
            points_before,
            points_after,
            points_after - points_before,
            hit_before,
            hit_after,
        )
    final_before, final_after = baseline.gameweeks[-1], candidate.gameweeks[-1]
    permanent_before, permanent_after = (
        final_before.permanent_players,
        final_after.permanent_players,
    )
    if permanent_before is None or permanent_after is None:
        return _unavailable(gameweek, basis, "beyond_valid_range")
    roles = plan.gameweeks[-1].lineup
    try:
        points_before = _score(permanent_before, roles, None, metadata, projected, legal_check=True)
        points_after = _score(permanent_after, roles, None, metadata, projected, legal_check=True)
    except RuleViolationError:
        return _unavailable(gameweek, basis, "continuation_lineup_illegal")
    return GameweekImpact(
        gameweek, basis, True, None, points_before, points_after, points_after - points_before, 0, 0
    )


def compute_plan_impact(
    *,
    plan: Plan,
    baseline: PlanEvaluation,
    candidate: PlanEvaluation,
    metadata: Mapping[int, PlayerRuleData],
    projections: Mapping[int, Mapping[int, float]],
    gameweek: int,
    valid_through: int | None,
) -> PlanImpact:
    """Per-gameweek and per-horizon impact of `candidate` versus `baseline`.

    `projections` maps gameweek to player points; its keys are the covered gameweeks.
    `valid_through` is the last gameweek whose values may be shown (None for no limit).
    """
    covered = set(projections)
    widest = horizon_window(plan, gameweek, max(HORIZONS), covered)
    weeks = tuple(
        _gameweek_impact(
            plan, baseline, candidate, metadata, projections[number], number, valid_through
        )
        for number in widest.evaluated
    )
    by_number = {item.gameweek: item for item in weeks}
    totals: dict[int, HorizonTotals] = {}
    for horizon in HORIZONS:
        window = horizon_window(plan, gameweek, horizon, covered)
        saved = [by_number[n] for n in window.saved_plan if by_number[n].available]
        assumed = [by_number[n] for n in window.assumed if by_number[n].available]
        saved_total = sum(item.delta or 0.0 for item in saved) if saved else None
        hit_change = sum(item.hit_after - item.hit_before for item in saved)
        totals[horizon] = HorizonTotals(
            horizon,
            window.requested,
            window.evaluated,
            window.saved_plan,
            window.assumed,
            window.partial,
            window.limited_reason,
            saved_total,
            sum(item.delta or 0.0 for item in assumed) if assumed else None,
            hit_change,
            None if saved_total is None else saved_total - hit_change,
            valid_through,
        )
    return PlanImpact(weeks, totals)
