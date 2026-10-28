"""Resolve the planned context of one plan gameweek from storage into plain values.

This is the only Explorer-path code that reads plan storage. Everything downstream
(`PlanTransferAnalysisService`) takes the resulting immutable `PlanningContext`, so it
needs no repository, session or write capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.models import EvaluatedGameweek, Plan, PlanEvaluation, PlayerRuleData
from fpl_engine.rules import RuleViolationError

from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem


@dataclass(frozen=True)
class ContextRef:
    """What an Explorer response was computed for; echoed as `planning_context`."""

    plan_id: int
    gameweek: int
    revision: int


@dataclass(frozen=True)
class PlanningContext:
    ref: ContextRef
    plan: Plan
    metadata: Mapping[int, PlayerRuleData]
    baseline: PlanEvaluation

    @property
    def selected_week(self) -> EvaluatedGameweek:
        return next(
            week for week in self.baseline.gameweeks if week.gameweek_number == self.ref.gameweek
        )


class PlanReaderPort(Protocol):
    def load_canonical(self, plan_id: int) -> Plan: ...


class PlayerLookupPort(Protocol):
    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]: ...


class TransactionPort(Protocol):
    def rollback(self) -> None: ...


def resolve_planning_context(
    *,
    plans: PlanReaderPort,
    players: PlayerLookupPort,
    transaction: TransactionPort,
    plan_id: int,
    gameweek: int,
) -> PlanningContext:
    """Load the plan once, release its read lock, then derive metadata and the baseline.

    Raises the repository's not-found and not-ready errors unchanged, and
    `RuleViolationError` with `gameweek_not_in_plan` or `evaluation_blocked`.
    """
    plan = plans.load_canonical(plan_id)
    # `load_canonical` takes a shared plan lock; ending the transaction here keeps
    # autosave writers from waiting while candidates are analysed.
    transaction.rollback()
    if not any(week.gameweek_number == gameweek for week in plan.gameweeks):
        raise RuleViolationError(
            "gameweek_not_in_plan", f"Gameweek {gameweek} is not part of this plan"
        )
    identifiers = {player.player_id for player in plan.boundary.players}
    for week in plan.gameweeks:
        for decision in week.transfers:
            identifiers.update((decision.outgoing_player_id, decision.incoming_player_id))
    metadata = {
        item.player_id: PlayerRuleData(item.player_id, PlayerPosition(item.position), item.team_id)
        for item in players.get_by_ids(sorted(identifiers))
    }
    baseline = evaluate_plan(plan, metadata)
    context = PlanningContext(
        ContextRef(plan_id, gameweek, plan.revision), plan, metadata, baseline
    )
    if context.selected_week.players is None:
        raise RuleViolationError(
            "evaluation_blocked",
            f"Gameweek {gameweek} cannot be evaluated until the plan's earlier problems are fixed",
        )
    return context
