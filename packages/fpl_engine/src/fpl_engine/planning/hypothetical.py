"""Assess a hypothetical transfer against a Planner plan without writing anything.

Every function takes frozen `Plan` and evaluation values and returns new values. The
acceptance verdict is the one the commit path uses (`candidate_verdict`), so what is
reported as `available` is exactly what `apply_intents` would accept.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID, uuid5

from fpl_engine.planning.models import (
    DecisionSale,
    Diagnostic,
    GameweekDecision,
    Plan,
    PlanEvaluation,
    PlayerRuleData,
    TransferDecision,
)
from fpl_engine.planning.mutations import candidate_verdict
from fpl_engine.rules import RuleViolationError

TransferKind = Literal["add_transfer", "edit_transfer"]
AssessmentState = Literal["available", "unavailable", "blocked_by_later_decision"]
ConflictKind = Literal["structural", "financial"]

_NAMESPACE = UUID("5e3f1c0e-0f6d-4d6c-9a43-2f58c5e6f7a1")
_OBSERVATION_SOURCE = "stored_player_observation"
_OBSERVED_AT = "hypothetical"


@dataclass(frozen=True)
class CandidateQuote:
    """Latest stored prices for one candidate, in whole tenths (50 = 5.0m)."""

    player_id: int
    outgoing_market_tenths: int
    incoming_price_tenths: int


@dataclass(frozen=True)
class TransferOperation:
    """The Planner operation a confirmation would submit (single source of the add/edit rule)."""

    kind: TransferKind
    gameweek: int
    selected_player_id: int
    sold_player_id: int
    sold_ownership_id: UUID
    replaces_decision_id: UUID | None


@dataclass(frozen=True)
class Conflict:
    kind: ConflictKind
    gameweek: int
    code: str
    decision_id: UUID | None
    message: str
    shortfall_tenths: int | None = None


@dataclass(frozen=True)
class CandidateAssessment:
    player_id: int
    state: AssessmentState
    reasons: tuple[str, ...]
    conflicts: tuple[Conflict, ...]
    valid_through_gameweek: int | None
    operation: TransferOperation
    decision: TransferDecision | None
    plan: Plan | None
    evaluation: PlanEvaluation | None
    selling_price_tenths: int | None
    selling_provisional: bool
    resulting_bank_tenths: int | None
    points_hit_after: int | None

    @property
    def confirmable(self) -> bool:
        return self.state == "available"

    @property
    def conflict(self) -> Conflict | None:
        return self.conflicts[0] if self.conflicts else None


def resolve_transfer_operation(
    plan: Plan, baseline: PlanEvaluation, gameweek: int, selected_player_id: int
) -> TransferOperation:
    """Add, or replace a transfer that acquired the selected player in this same gameweek."""
    decided = next((week for week in plan.gameweeks if week.gameweek_number == gameweek), None)
    evaluated = next(
        (week for week in baseline.gameweeks if week.gameweek_number == gameweek), None
    )
    if decided is None or evaluated is None:
        raise RuleViolationError("gameweek_not_in_plan", f"Gameweek {gameweek} is not in the plan")
    if evaluated.players is None:
        raise RuleViolationError(
            "evaluation_blocked", f"Gameweek {gameweek} cannot be evaluated for this plan"
        )
    ownership = next(
        (player for player in evaluated.players if player.player_id == selected_player_id), None
    )
    if ownership is None:
        raise RuleViolationError(
            "player_not_in_squad",
            f"Player {selected_player_id} is not in the plan's gameweek {gameweek} squad",
        )
    for decision in decided.transfers:
        if decision.incoming_ownership_id == ownership.ownership_id:
            return TransferOperation(
                "edit_transfer",
                gameweek,
                selected_player_id,
                decision.outgoing_player_id,
                decision.outgoing_ownership_id,
                decision.decision_id,
            )
    return TransferOperation(
        "add_transfer",
        gameweek,
        selected_player_id,
        selected_player_id,
        ownership.ownership_id,
        None,
    )


def _build_decision(
    plan: Plan, operation: TransferOperation, quote: CandidateQuote
) -> TransferDecision:
    key = f"{operation.gameweek}:{operation.sold_ownership_id}:{quote.player_id}"
    return TransferDecision(
        operation.replaces_decision_id or uuid5(_NAMESPACE, f"decision:{key}"),
        operation.sold_player_id,
        operation.sold_ownership_id,
        quote.player_id,
        uuid5(_NAMESPACE, f"ownership:{key}"),
        quote.outgoing_market_tenths,
        quote.incoming_price_tenths,
        _OBSERVATION_SOURCE,
        _OBSERVED_AT,
        "captured",
    )


def _unavailable(
    operation: TransferOperation,
    player_id: int,
    decision: TransferDecision | None,
    reasons: tuple[str, ...],
) -> CandidateAssessment:
    return CandidateAssessment(
        player_id,
        "unavailable",
        reasons,
        (),
        operation.gameweek - 1,
        operation,
        decision,
        None,
        None,
        None,
        False,
        None,
        None,
    )


def _sorted(decisions: list[TransferDecision]) -> tuple[TransferDecision, ...]:
    return tuple(sorted(decisions, key=lambda decision: str(decision.decision_id)))


def _with_decision(plan: Plan, operation: TransferOperation, decision: TransferDecision) -> Plan:
    weeks: list[GameweekDecision] = []
    for week in plan.gameweeks:
        if week.gameweek_number == operation.gameweek:
            kept = [
                existing
                for existing in week.transfers
                if existing.decision_id != operation.replaces_decision_id
            ]
            week = replace(week, transfers=_sorted([*kept, decision]))
        weeks.append(week)
    return replace(plan, gameweeks=tuple(weeks))


def _conflicts(
    verdict_diagnostics: tuple[Diagnostic, ...],
    verdict_shortfalls: tuple[Diagnostic, ...],
    plan: Plan,
    evaluation: PlanEvaluation,
) -> tuple[Conflict, ...]:
    decisions = {week.gameweek_number: week.transfers for week in plan.gameweeks}
    shortfalls = {week.gameweek_number: week.shortfall_tenths for week in evaluation.gameweeks}
    found = [
        Conflict("structural", item.gameweek_number, item.code, item.decision_id, item.message)
        for item in verdict_diagnostics
    ]
    for item in verdict_shortfalls:
        transfers = decisions.get(item.gameweek_number, ())
        found.append(
            Conflict(
                "financial",
                item.gameweek_number,
                item.code,
                transfers[0].decision_id if transfers else None,
                item.message,
                shortfalls.get(item.gameweek_number),
            )
        )
    return tuple(sorted(found, key=lambda item: (item.gameweek, item.kind == "financial")))


def _first_sale(
    evaluation: PlanEvaluation, gameweek: int, decision_id: UUID
) -> DecisionSale | None:
    week = next(item for item in evaluation.gameweeks if item.gameweek_number == gameweek)
    return next((sale for sale in week.sales if sale.decision_id == decision_id), None)


def assess_candidate(
    plan: Plan,
    baseline: PlanEvaluation,
    metadata: Mapping[int, PlayerRuleData],
    operation: TransferOperation,
    quote: CandidateQuote,
) -> CandidateAssessment:
    """Assess one candidate on an in-memory copy of `plan`; no input is modified."""
    decided = next(week for week in plan.gameweeks if week.gameweek_number == operation.gameweek)
    sold_here = {
        existing.outgoing_player_id
        for existing in decided.transfers
        if existing.decision_id != operation.replaces_decision_id
    } | {operation.sold_player_id}
    if quote.player_id in sold_here:
        # A same-gameweek round trip cannot be expressed as a Planner decision.
        return _unavailable(operation, quote.player_id, None, ("sold_this_gameweek",))
    decision = _build_decision(plan, operation, quote)
    try:
        candidate_plan = _with_decision(plan, operation, decision)
    except RuleViolationError as error:
        return _unavailable(operation, quote.player_id, decision, (error.code,))

    verdict = candidate_verdict(plan, candidate_plan, metadata, baseline=baseline)
    evaluation = verdict.evaluation
    conflicts = _conflicts(verdict.diagnostics, verdict.shortfalls, candidate_plan, evaluation)

    selected = [item for item in conflicts if item.gameweek <= operation.gameweek]
    if selected:
        state: AssessmentState = "unavailable"
        reasons = tuple(dict.fromkeys(item.code for item in selected))
    elif conflicts:
        state, reasons = "blocked_by_later_decision", ()
    else:
        state, reasons = "available", ()
    first = conflicts[0] if conflicts else None
    valid_through = (
        None
        if first is None
        else first.gameweek - 1
        if first.kind == "structural"
        else first.gameweek
    )

    week = next(item for item in evaluation.gameweeks if item.gameweek_number == operation.gameweek)
    sale = (
        _first_sale(evaluation, operation.gameweek, decision.decision_id)
        if operation.kind == "add_transfer"
        else None
    )
    return CandidateAssessment(
        quote.player_id,
        state,
        reasons,
        conflicts,
        valid_through,
        operation,
        decision,
        candidate_plan,
        evaluation,
        sale.selling_price_tenths if sale else None,
        sale is not None and sale.basis_confirmation == "assumed",
        week.closing_bank_tenths,
        week.points_hit,
    )
