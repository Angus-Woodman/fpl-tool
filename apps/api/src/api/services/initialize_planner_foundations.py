from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID, uuid4

from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.models import (
    Boundary,
    GameweekDecision,
    LineupRole,
    Ownership,
    Plan,
    PlayerRuleData,
    PurchaseProvenance,
    TransferDecision,
)
from fpl_engine.planning.prices import selling_price_tenths
from fpl_engine.rules import Chip, RuleViolationError
from sqlalchemy.orm import Session

from api.repositories.plan_repository import PlanRepository
from api.services.plan_accounting import pair_transfers
from api.services.plans import PlayerLookupRepositoryPort, checked_tenths


@dataclass(frozen=True)
class InitializationReport:
    plan_id: int
    status: str
    diagnostics: tuple[str, ...] = ()


class InitializePlannerFoundationsService:
    def __init__(self, session: Session, players: PlayerLookupRepositoryPort) -> None:
        self._session, self._players = session, players
        self._repository = PlanRepository(session)

    def execute(self, plan_id: int, *, apply: bool) -> InitializationReport:
        try:
            row = self._repository.lock_plan(plan_id, shared=not apply)
            if row.foundation_state == "ready":
                self._session.rollback()
                return InitializationReport(plan_id, "already_ready")
            legacy = self._repository.get(plan_id)
            if legacy is None or not legacy.gameweeks:
                raise ValueError("No saved gameweeks; initialization can be retried after repair")
            if [week.gameweek_number for week in legacy.gameweeks] != list(
                range(legacy.start_gameweek, legacy.end_gameweek + 1)
            ):
                raise ValueError("Legacy plan is missing saved gameweeks")
            identifiers = {player.player_id for week in legacy.gameweeks for player in week.players}
            lookup = {
                player.player_id: player for player in self._players.get_by_ids(sorted(identifiers))
            }
            if identifiers - lookup.keys():
                raise ValueError("Stored players/observations are missing; retry after data repair")
            prices = {
                identifier: checked_tenths(player.current_price)
                for identifier, player in lookup.items()
            }
            first = legacy.gameweeks[0]
            starting = tuple(
                Ownership(
                    uuid4(),
                    uuid4(),
                    player.player_id,
                    prices[player.player_id],
                    PurchaseProvenance(
                        "legacy_first_gameweek_stored_market", prices[player.player_id]
                    ),
                )
                for player in sorted(first.players, key=lambda player: player.player_id)
            )
            by_player = {player.player_id: player for player in starting}
            seed = tuple(
                LineupRole(
                    by_player[player.player_id].slot_id,
                    player.is_starting,
                    player.bench_order,
                    player.is_captain,
                    player.is_vice_captain,
                )
                for player in sorted(first.players, key=lambda player: player.player_id)
            )
            boundary = Boundary(
                starting,
                seed,
                checked_tenths(legacy.initial_bank, positive=False),
                None if legacy.start_gameweek == 1 else legacy.initial_free_transfers,
                origin="legacy_first_gameweek_assumed",
            )
            permanent = by_player
            weeks: list[GameweekDecision] = []
            sales: dict[UUID, int] = {}
            observed_at = dt.datetime.now(dt.UTC).isoformat()
            for week in legacy.gameweeks:
                target = {player.player_id for player in week.players}
                entering = set(permanent)
                pairs = pair_transfers(
                    sorted(entering - target),
                    sorted(target - entering),
                    {identifier: player.position for identifier, player in lookup.items()},
                )
                current = dict(permanent)
                decisions: list[TransferDecision] = []
                for outgoing, incoming in pairs.items():
                    owned = permanent[outgoing]
                    decision = TransferDecision(
                        uuid4(),
                        outgoing,
                        owned.ownership_id,
                        incoming,
                        uuid4(),
                        prices[outgoing],
                        prices[incoming],
                        "stored_player_observation",
                        observed_at,
                        "legacy_initialized_estimate",
                    )
                    decisions.append(decision)
                    sales[decision.decision_id] = selling_price_tenths(
                        owned.purchase_price_tenths, decision.outgoing_market_tenths
                    )
                    del current[outgoing]
                    current[incoming] = Ownership(
                        owned.slot_id,
                        decision.incoming_ownership_id,
                        incoming,
                        prices[incoming],
                        PurchaseProvenance(
                            f"decision:{decision.decision_id}",
                            prices[incoming],
                            "planned_acquisition",
                            None,
                        ),
                    )
                if set(current) != target:
                    raise ValueError(f"Gameweek {week.gameweek_number} membership cannot be paired")
                roles = {
                    current[player.player_id].slot_id: LineupRole(
                        current[player.player_id].slot_id,
                        player.is_starting,
                        player.bench_order,
                        player.is_captain,
                        player.is_vice_captain,
                    )
                    for player in week.players
                }
                chip = Chip(week.chip) if week.chip is not None else None
                weeks.append(
                    GameweekDecision(
                        week.gameweek_number,
                        tuple(roles[player.slot_id] for player in starting),
                        tuple(sorted(decisions, key=lambda decision: str(decision.decision_id))),
                        chip,
                    )
                )
                if chip != Chip.FREE_HIT:
                    permanent = current
            plan = Plan(
                legacy.name, legacy.start_gameweek, legacy.end_gameweek, boundary, tuple(weeks)
            )
            metadata = {
                identifier: PlayerRuleData(
                    identifier, PlayerPosition(player.position), player.team_id
                )
                for identifier, player in lookup.items()
            }
            evaluation = evaluate_plan(plan, metadata)
            diagnostics = tuple(error.message for error in evaluation.diagnostics)
            if apply:
                self._repository.save_canonical(plan_id, plan, evaluation, initial_sales=sales)
                self._session.commit()
            else:
                self._session.rollback()
            return InitializationReport(
                plan_id, "initialized" if apply else "ready_to_initialize", diagnostics
            )
        except (ValueError, RuleViolationError) as error:
            self._session.rollback()
            return InitializationReport(plan_id, "legacy_pending", (str(error),))
        except Exception:
            self._session.rollback()
            raise
