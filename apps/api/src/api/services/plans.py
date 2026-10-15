from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from fpl_engine.domain import PlayerPosition
from fpl_engine.planning import models as planning
from fpl_engine.planning.evaluate import EVALUATOR_VERSION, evaluate_plan
from fpl_engine.planning.mutations import MutationRejectedError, apply_intents
from fpl_engine.rules import (
    FINAL_GAMEWEEK,
    FIRST_GAMEWEEK,
    Chip,
    RuleViolationError,
    SquadSlot,
    validate_chip_usage,
    validate_squad,
)
from pydantic import TypeAdapter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.models.entities import PlanMutationModel
from api.repositories.current_squad_repository import CurrentSquadRecord
from api.repositories.plan_repository import (
    PlanGameweekAccounting as PlanGameweekAccountingSave,
)
from api.repositories.plan_repository import (
    PlanGameweekRecord,
    PlanNotFoundError,
    PlanPlayerSave,
    PlanRecord,
    PlanRepository,
    PlanSummaryRecord,
)
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.schemas import plans as bodies
from api.services.plan_accounting import (
    PlanGameweekState,
    PlanPlayerSelection,
    apply_transfers_forward,
    pair_transfers,
    recalculate_accounting,
)


class PlanRepositoryPort(Protocol):
    def list_plans(self) -> list[PlanSummaryRecord]: ...

    def get(self, plan_id: int) -> PlanRecord | None: ...

    def get_for_view(self, plan_id: int) -> PlanRecord | None: ...

    def save_canonical(
        self, plan_id: int, plan: planning.Plan, evaluation: planning.PlanEvaluation
    ) -> None: ...

    def create(
        self,
        *,
        name: str,
        start_gameweek: int,
        end_gameweek: int,
        initial_bank: float,
        initial_free_transfers: int,
    ) -> int: ...

    def update_details(
        self,
        plan_id: int,
        *,
        name: str | None = None,
        start_gameweek: int | None = None,
        end_gameweek: int | None = None,
    ) -> None: ...

    def delete(self, plan_id: int) -> None: ...

    def delete_gameweeks_outside(self, plan_id: int, *, start: int, end: int) -> None: ...

    def save_gameweek(
        self,
        plan_id: int,
        gameweek_number: int,
        *,
        chip: str | None,
        bank: float,
        free_transfers_available: int,
        transfers_made: int,
        points_hit: int,
        players: list[PlanPlayerSave],
    ) -> None: ...

    def update_accounting(
        self, plan_id: int, entries: list[PlanGameweekAccountingSave]
    ) -> None: ...


class CurrentSquadRepositoryPort(Protocol):
    def get_current(self) -> CurrentSquadRecord | None: ...


class PlayerLookupRepositoryPort(Protocol):
    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]: ...


@dataclass(frozen=True)
class CreatePlanRequest:
    name: str
    start_gameweek: int
    end_gameweek: int


@dataclass(frozen=True)
class UpdatePlanRequest:
    name: str | None = None
    start_gameweek: int | None = None
    end_gameweek: int | None = None


@dataclass(frozen=True)
class SavePlanGameweekRequest:
    plan_id: int
    gameweek_number: int
    chip: str | None
    players: list[PlanPlayerSelection]


class ListPlansService:
    def __init__(self, repository: PlanRepositoryPort) -> None:
        self._repository = repository

    def execute(self) -> list[PlanSummaryRecord]:
        return self._repository.list_plans()


class GetPlanService:
    def __init__(
        self,
        repository: PlanRepositoryPort,
        initialization_check: Callable[[int], str | None] | None = None,
    ) -> None:
        self._repository = repository
        self._initialization_check = initialization_check

    def execute(self, plan_id: int) -> PlanRecord | None:
        plan = self._repository.get_for_view(plan_id)
        if plan is not None and plan.canonical_plan is None and self._initialization_check:
            reason = self._initialization_check(plan_id)
            plan = self._repository.get_for_view(plan_id)
            if plan is not None:
                return replace(plan, initialization_reason=reason)
        return plan


class DeletePlanService:
    def __init__(self, repository: PlanRepositoryPort) -> None:
        self._repository = repository

    def execute(self, plan_id: int) -> None:
        if self._repository.get(plan_id) is None:
            raise PlanNotFoundError(plan_id)
        self._repository.delete(plan_id)


class CreatePlanService:
    """Capture the saved squad once as an independent canonical boundary."""

    def __init__(
        self,
        repository: PlanRepositoryPort,
        current_squad_repository: CurrentSquadRepositoryPort,
    ) -> None:
        self._repository = repository
        self._current_squad_repository = current_squad_repository

    def execute(self, request: CreatePlanRequest) -> PlanRecord:
        _validate_name(request.name)
        _validate_horizon(request.start_gameweek, request.end_gameweek)

        current_squad = self._current_squad_repository.get_current()
        if current_squad is None or not current_squad.players:
            raise RuleViolationError("no_squad", "Save your team before creating a plan from it")

        ownership = tuple(
            planning.Ownership(
                uuid4(),
                uuid4(),
                player.player_id,
                checked_tenths(player.current_price),
                planning.PurchaseProvenance(
                    "my_team_stored_market", checked_tenths(player.current_price)
                ),
            )
            for player in current_squad.players
        )
        lineup = tuple(
            planning.LineupRole(
                owned.slot_id,
                player.is_starting,
                player.bench_order,
                player.is_captain,
                player.is_vice_captain,
            )
            for owned, player in zip(ownership, current_squad.players, strict=True)
        )
        boundary = planning.Boundary(
            ownership,
            lineup,
            checked_tenths(current_squad.bank, positive=False),
            None if request.start_gameweek == 1 else 1,
            origin="my_team_capture",
        )
        canonical = planning.Plan(
            request.name,
            request.start_gameweek,
            request.end_gameweek,
            boundary,
            tuple(
                planning.GameweekDecision(number, lineup)
                for number in range(request.start_gameweek, request.end_gameweek + 1)
            ),
        )
        metadata = {
            player.player_id: planning.PlayerRuleData(
                player.player_id, PlayerPosition(player.position), player.team_id
            )
            for player in current_squad.players
        }
        evaluation = evaluate_plan(canonical, metadata)
        if evaluation.diagnostics:
            raise MutationRejectedError(evaluation.diagnostics)
        plan_id = self._repository.create(
            name=request.name,
            start_gameweek=request.start_gameweek,
            end_gameweek=request.end_gameweek,
            initial_bank=current_squad.bank,
            initial_free_transfers=boundary.free_transfers or 0,
        )
        self._repository.save_canonical(plan_id, canonical, evaluation)
        result = self._repository.get_for_view(plan_id)
        if result is None:
            raise PlanNotFoundError(plan_id)
        return result


class UpdatePlanService:
    """Rename a plan or move its horizon, extending or trimming gameweeks."""

    def __init__(self, repository: PlanRepositoryPort) -> None:
        self._repository = repository

    def execute(self, plan_id: int, request: UpdatePlanRequest) -> PlanRecord:
        plan = self._repository.get(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)

        if request.name is not None:
            _validate_name(request.name)

        start = request.start_gameweek or plan.start_gameweek
        end = request.end_gameweek or plan.end_gameweek
        _validate_horizon(start, end)

        self._repository.update_details(
            plan_id,
            name=request.name,
            start_gameweek=request.start_gameweek,
            end_gameweek=request.end_gameweek,
        )
        self._repository.delete_gameweeks_outside(plan_id, start=start, end=end)

        existing = {gameweek.gameweek_number for gameweek in plan.gameweeks}
        for gameweek_number in range(start, end + 1):
            if gameweek_number in existing:
                continue
            source = _nearest_gameweek(plan, gameweek_number)
            if source is None:
                continue
            if source.bank is None or source.free_transfers_available is None:
                raise RuleViolationError("blocked_accounting", "Gameweek accounting is unavailable")
            self._repository.save_gameweek(
                plan_id,
                gameweek_number,
                chip=None,
                bank=source.bank,
                free_transfers_available=source.free_transfers_available,
                transfers_made=0,
                points_hit=0,
                players=[
                    PlanPlayerSave(
                        player_id=player.player_id,
                        is_starting=player.is_starting,
                        bench_order=player.bench_order,
                        is_captain=player.is_captain,
                        is_vice_captain=player.is_vice_captain,
                    )
                    for player in source.players
                ],
            )

        return _require_plan(self._repository, plan_id)


class SavePlanGameweekService:
    """Save one gameweek of a plan and roll the consequences forward."""

    def __init__(
        self,
        repository: PlanRepositoryPort,
        player_lookup_repository: PlayerLookupRepositoryPort,
    ) -> None:
        self._repository = repository
        self._player_lookup_repository = player_lookup_repository

    def execute(self, request: SavePlanGameweekRequest) -> PlanRecord:
        plan = self._repository.get(request.plan_id)
        if plan is None:
            raise PlanNotFoundError(request.plan_id)

        if not plan.start_gameweek <= request.gameweek_number <= plan.end_gameweek:
            raise RuleViolationError(
                "gameweek_outside_plan",
                f"Gameweek {request.gameweek_number} is outside this plan",
            )

        target_index = next(
            (
                index
                for index, gameweek in enumerate(plan.gameweeks)
                if gameweek.gameweek_number == request.gameweek_number
            ),
            None,
        )
        if target_index is None:
            raise RuleViolationError(
                "gameweek_outside_plan",
                f"Gameweek {request.gameweek_number} is not part of this plan",
            )

        chip = _parse_chip(request.chip)
        lookup = self._lookup(plan, request.players)

        states = [
            PlanGameweekState(
                gameweek_number=gameweek.gameweek_number,
                chip=_parse_chip(gameweek.chip),
                players=tuple(
                    PlanPlayerSelection(
                        player_id=player.player_id,
                        is_starting=player.is_starting,
                        bench_order=player.bench_order,
                        is_captain=player.is_captain,
                        is_vice_captain=player.is_vice_captain,
                    )
                    for player in gameweek.players
                ),
            )
            for gameweek in plan.gameweeks
        ]

        previous_ids = states[target_index].player_ids
        states[target_index] = PlanGameweekState(
            gameweek_number=request.gameweek_number,
            chip=chip,
            players=tuple(request.players),
        )
        _validate_state(states[target_index], lookup)

        if chip is not Chip.FREE_HIT:
            new_ids = states[target_index].player_ids
            positions = {item.player_id: item.position for item in lookup.values()}
            states = apply_transfers_forward(
                states,
                from_index=target_index,
                pairs=pair_transfers(
                    sorted(previous_ids - new_ids), sorted(new_ids - previous_ids), positions
                ),
            )

        for state in states:
            _validate_state(state, lookup)

        validate_chip_usage({state.gameweek_number: state.chip for state in states})

        accounting = recalculate_accounting(
            states,
            initial_bank=plan.initial_bank,
            initial_free_transfers=plan.initial_free_transfers,
            prices={item.player_id: item.current_price for item in lookup.values()},
        )
        negative = next((entry for entry in accounting if entry.bank < 0), None)
        if negative is not None:
            raise RuleViolationError(
                "budget",
                f"Gameweek {negative.gameweek_number} goes over budget by "
                f"{abs(negative.bank):.1f}m",
            )

        for state, entry in zip(states, accounting, strict=True):
            self._repository.save_gameweek(
                request.plan_id,
                state.gameweek_number,
                chip=state.chip.value if state.chip is not None else None,
                bank=entry.bank,
                free_transfers_available=entry.free_transfers_available,
                transfers_made=entry.transfers_made,
                points_hit=entry.points_hit,
                players=[
                    PlanPlayerSave(
                        player_id=player.player_id,
                        is_starting=player.is_starting,
                        bench_order=player.bench_order,
                        is_captain=player.is_captain,
                        is_vice_captain=player.is_vice_captain,
                    )
                    for player in state.players
                ],
            )

        return _require_plan(self._repository, request.plan_id)

    def _lookup(
        self, plan: PlanRecord, players: Sequence[PlanPlayerSelection]
    ) -> dict[int, SquadPlayerLookupItem]:
        player_ids = {player.player_id for player in players}
        for gameweek in plan.gameweeks:
            player_ids.update(player.player_id for player in gameweek.players)

        items = self._player_lookup_repository.get_by_ids(sorted(player_ids))
        lookup = {item.player_id: item for item in items}
        missing = player_ids - lookup.keys()
        if missing:
            raise RuleViolationError("unknown_player", "Plan contains unknown players")
        return lookup


def _validate_state(state: PlanGameweekState, lookup: dict[int, SquadPlayerLookupItem]) -> None:
    try:
        validate_squad(
            [
                SquadSlot(
                    player_id=player.player_id,
                    position=PlayerPosition(lookup[player.player_id].position),
                    team_id=lookup[player.player_id].team_id,
                    is_starting=player.is_starting,
                    bench_order=player.bench_order,
                    is_captain=player.is_captain,
                    is_vice_captain=player.is_vice_captain,
                )
                for player in state.players
            ]
        )
    except RuleViolationError as error:
        raise RuleViolationError(
            error.code, f"Gameweek {state.gameweek_number}: {error.message}"
        ) from error


def _parse_chip(chip: str | None) -> Chip | None:
    if chip is None:
        return None
    try:
        return Chip(chip)
    except ValueError as error:
        raise RuleViolationError("unknown_chip", f"Unknown chip {chip}") from error


def _validate_name(name: str) -> None:
    if not name.strip():
        raise RuleViolationError("plan_name", "Plan name cannot be empty")
    if len(name) > 100:
        raise RuleViolationError("plan_name", "Plan name cannot exceed 100 characters")


def _validate_horizon(start: int, end: int) -> None:
    if start < FIRST_GAMEWEEK or end > FINAL_GAMEWEEK:
        raise RuleViolationError(
            "plan_horizon",
            f"Plan must sit between gameweek {FIRST_GAMEWEEK} and {FINAL_GAMEWEEK}",
        )
    if end < start:
        raise RuleViolationError("plan_horizon", "Plan must end on or after it starts")


def _nearest_gameweek(plan: PlanRecord, gameweek_number: int) -> PlanGameweekRecord | None:
    if not plan.gameweeks:
        return None
    return min(
        plan.gameweeks,
        key=lambda gameweek: abs(gameweek.gameweek_number - gameweek_number),
    )


def _require_plan(repository: PlanRepositoryPort, plan_id: int) -> PlanRecord:
    plan = repository.get(plan_id)
    if plan is None:
        raise PlanNotFoundError(plan_id)
    return plan


def checked_tenths(value: float, *, positive: bool = True) -> int:
    try:
        decimal = Decimal(str(value)) * 10
        if not decimal.is_finite() or decimal != decimal.to_integral_value():
            raise ValueError("Money must be a finite whole number of tenths")
        result = int(decimal)
    except (InvalidOperation, OverflowError) as error:
        raise ValueError("Invalid stored monetary observation") from error
    if positive and result <= 0:
        raise ValueError("Stored player price must be positive")
    return result


@dataclass(frozen=True)
class PlannerMutationOutcome:
    status: Literal["committed", "already_committed", "accepted_not_saved"]
    mutation_id: UUID
    committed_revision: int | None
    plan: planning.Plan
    candidate: planning.Plan | None = None


class PlannerMutationError(Exception):
    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        plan: planning.Plan | None = None,
        candidate: planning.Plan | None = None,
        intent_metadata: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.status_code, self.message = code, status_code, message
        self.plan, self.candidate = plan, candidate
        self.intent_metadata = intent_metadata


_INTENT_TYPES: tuple[type[planning.Intent], ...] = (
    planning.RenamePlan,
    planning.ChangeHorizon,
    planning.SetStartingTransfers,
    planning.SetStartingChips,
    planning.CorrectPurchasePrice,
    planning.ConfirmPurchasePrice,
    planning.ChangeCaptain,
    planning.ChangeViceCaptain,
    planning.SwapLineupPlayers,
    planning.SetChip,
    planning.MoveChip,
    planning.AddTransfer,
    planning.EditTransfer,
    planning.RemoveTransfer,
)


def _encode_operations(intents: tuple[planning.Intent, ...]) -> dict[str, object]:
    return {
        "operations": [
            {
                "type": type(intent).__name__,
                "payload": TypeAdapter(type(intent)).dump_python(intent, mode="json"),
            }
            for intent in intents
        ]
    }


def _decode_operations(inputs: dict[str, object]) -> tuple[planning.Intent, ...]:
    operations = cast(list[dict[str, object]], inputs["operations"])
    types = {kind.__name__: kind for kind in _INTENT_TYPES}
    return tuple(
        cast(
            planning.Intent,
            TypeAdapter(types[str(operation["type"])]).validate_json(
                json.dumps(operation["payload"])
            ),
        )
        for operation in operations
    )


class PlanMutationService:
    def __init__(
        self, session: Session, player_lookup_repository: PlayerLookupRepositoryPort
    ) -> None:
        self._session = session
        self._repository = PlanRepository(session)
        self._players = player_lookup_repository

    def _lookup(
        self,
        plan: planning.Plan,
        extra_ids: set[int] | None = None,
    ) -> dict[int, SquadPlayerLookupItem]:
        identifiers = {player.player_id for player in plan.boundary.players} | (extra_ids or set())
        for week in plan.gameweeks:
            for decision in week.transfers:
                identifiers.update((decision.outgoing_player_id, decision.incoming_player_id))
        return {
            player.player_id: player for player in self._players.get_by_ids(sorted(identifiers))
        }

    @staticmethod
    def _metadata(lookup: dict[int, SquadPlayerLookupItem]) -> dict[int, planning.PlayerRuleData]:
        return {
            identifier: planning.PlayerRuleData(
                identifier, PlayerPosition(player.position), player.team_id
            )
            for identifier, player in lookup.items()
        }

    @staticmethod
    def _fingerprint(lookup: dict[int, SquadPlayerLookupItem]) -> str:
        values = [
            (identifier, player.position, player.team_id)
            for identifier, player in sorted(lookup.items())
        ]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    @staticmethod
    def _operation_ids(intents: tuple[planning.Intent, ...]) -> set[int]:
        return {
            identifier
            for intent in intents
            if isinstance(intent, planning.AddTransfer | planning.EditTransfer)
            for identifier in (
                intent.decision.outgoing_player_id,
                intent.decision.incoming_player_id,
            )
        }

    def _capture(
        self,
        plan: planning.Plan,
        requests: list[bodies.PlannerIntent],
    ) -> tuple[tuple[planning.Intent, ...], dict[int, SquadPlayerLookupItem]]:
        extra_ids: set[int] = set()
        for request in requests:
            if isinstance(request, bodies.AddTransferIntent | bodies.EditTransferIntent):
                extra_ids.update(
                    identifier
                    for identifier in (request.outgoing_player_id, request.incoming_player_id)
                    if identifier is not None
                )
        lookup = self._lookup(plan, extra_ids)
        existing = {
            decision.decision_id: decision for week in plan.gameweeks for decision in week.transfers
        }
        operations: list[planning.Intent] = []
        captured_sources: dict[str, planning.TransferDecision] = {}
        for request in requests:
            if isinstance(request, bodies.RenamePlanIntent):
                _validate_name(request.name)
                operations.append(planning.RenamePlan(request.name))
            elif isinstance(request, bodies.ChangeHorizonIntent):
                operations.append(
                    planning.ChangeHorizon(
                        request.start_gameweek,
                        request.end_gameweek,
                        frozenset(request.used_chips) if request.used_chips is not None else None,
                        request.free_hit_gameweek_19,
                    )
                )
            elif isinstance(request, bodies.StartingTransfersIntent):
                operations.append(planning.SetStartingTransfers(request.value))
            elif isinstance(request, bodies.StartingChipsIntent):
                if len(set(request.used_chips)) != len(request.used_chips):
                    raise RuleViolationError("duplicate_chip", "Starting chips must be unique")
                operations.append(
                    planning.SetStartingChips(
                        frozenset(request.used_chips), request.free_hit_gameweek_19
                    )
                )
            elif isinstance(request, bodies.CorrectPurchaseIntent):
                operations.append(
                    planning.CorrectPurchasePrice(request.ownership_id, request.price_tenths)
                )
            elif isinstance(request, bodies.ConfirmPurchaseIntent):
                operations.append(planning.ConfirmPurchasePrice(request.ownership_id))
            elif isinstance(request, bodies.CaptainIntent):
                if request.kind == "change_captain":
                    operations.append(
                        planning.ChangeCaptain(request.gameweek_number, request.player_id)
                    )
                else:
                    operations.append(
                        planning.ChangeViceCaptain(request.gameweek_number, request.player_id)
                    )
            elif isinstance(request, bodies.SwapIntent):
                operations.append(
                    planning.SwapLineupPlayers(
                        request.gameweek_number, request.first_player_id, request.second_player_id
                    )
                )
            elif isinstance(request, bodies.ChipIntent):
                if request.kind == "activate_chip" and request.expected_chip is not None:
                    raise RuleViolationError("chip_conflict", "Activate only on an empty gameweek")
                operations.append(
                    planning.SetChip(
                        request.gameweek_number,
                        request.chip if request.kind == "activate_chip" else None,
                        request.expected_chip if request.kind == "activate_chip" else request.chip,
                    )
                )
            elif isinstance(request, bodies.MoveChipIntent):
                operations.append(
                    planning.MoveChip(
                        request.source_gameweek, request.target_gameweek, request.chip
                    )
                )
            elif isinstance(request, bodies.RemoveTransferIntent):
                operations.append(planning.RemoveTransfer(request.decision_id))
            elif isinstance(request, bodies.AddTransferIntent | bodies.EditTransferIntent):
                old = (
                    existing.get(request.decision_id)
                    if isinstance(request, bodies.EditTransferIntent)
                    else None
                )
                if isinstance(request, bodies.EditTransferIntent) and old is None:
                    raise RuleViolationError(
                        "decision_not_found", "Transfer decision no longer exists"
                    )
                outgoing = (
                    request.outgoing_player_id
                    if request.outgoing_player_id is not None
                    else (old.outgoing_player_id if old else 0)
                )
                incoming = (
                    request.incoming_player_id
                    if request.incoming_player_id is not None
                    else (old.incoming_player_id if old else 0)
                )
                ownership = request.outgoing_ownership_id or (
                    old.outgoing_ownership_id if old else None
                )
                if (
                    isinstance(request, bodies.EditTransferIntent)
                    and request.outgoing_source_decision_id is not None
                ):
                    source = captured_sources.get(str(request.outgoing_source_decision_id))
                    if (
                        request.outgoing_ownership_id is not None
                        or source is None
                        or source.incoming_player_id != outgoing
                    ):
                        raise RuleViolationError(
                            "invalid_ownership_reference",
                            "Outgoing acquisition must reference an earlier matching transfer "
                            "in this batch, without an ownership ID",
                        )
                    ownership = source.incoming_ownership_id
                if outgoing not in lookup or incoming not in lookup or ownership is None:
                    raise RuleViolationError(
                        "missing_price_observation", "Stored player/price observation missing"
                    )
                decision = planning.TransferDecision(
                    old.decision_id if old else uuid4(),
                    outgoing,
                    ownership,
                    incoming,
                    old.incoming_ownership_id
                    if old and old.incoming_player_id == incoming
                    else uuid4(),
                    checked_tenths(lookup[outgoing].current_price),
                    checked_tenths(lookup[incoming].current_price),
                    "stored_player_observation",
                    dt.datetime.now(dt.UTC).isoformat(),
                    "captured",
                )
                operations.append(
                    planning.EditTransfer(old.decision_id, decision)
                    if old
                    else planning.AddTransfer(
                        cast(bodies.AddTransferIntent, request).gameweek_number, decision
                    )
                )
                captured_sources[str(decision.decision_id)] = decision
        return tuple(operations), lookup

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise PlannerMutationError(
                "outcome_unknown",
                503,
                "Commit outcome is uncertain; reconcile the same mutation ID",
            ) from error

    def _pending(
        self,
        plan: planning.Plan,
        receipt: PlanMutationModel,
    ) -> tuple[planning.Plan, dict[int, SquadPlayerLookupItem]]:
        if (
            receipt.expected_revision != plan.revision
            or receipt.evaluator_version != EVALUATOR_VERSION
        ):
            raise PlannerMutationError(
                "stale_reprepare_required",
                409,
                "Accepted inputs need explicit revalidation with a new ID",
                plan=plan,
                intent_metadata=receipt.pending_inputs,
            )
        if receipt.pending_inputs is None:
            raise ValueError("Pending receipt has no semantic inputs")
        operations = _decode_operations(receipt.pending_inputs)
        lookup = self._lookup(plan, self._operation_ids(operations))
        if receipt.rule_fingerprint != self._fingerprint(lookup):
            raise PlannerMutationError(
                "stale_reprepare_required",
                409,
                "Rule context changed; explicitly revalidate with a new ID",
                plan=plan,
                intent_metadata=receipt.pending_inputs,
            )
        return apply_intents(plan, operations, self._metadata(lookup)).plan, lookup

    def mutate(self, plan_id: int, body: bodies.PlanMutationRequestBody) -> PlannerMutationOutcome:
        digest = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            self._repository.lock_plan(plan_id)
            receipt = self._repository.get_receipt(plan_id, body.mutation_id)
            if receipt is not None and receipt.digest != digest:
                raise PlannerMutationError(
                    "mutation_id_reused", 409, "Mutation ID has a different request"
                )
            plan = self._repository.load_canonical(plan_id)
            if receipt is not None and receipt.status == "committed":
                result = PlannerMutationOutcome(
                    "already_committed", body.mutation_id, receipt.committed_revision, plan
                )
                self._session.commit()
                return result
            if receipt is None:
                if plan.revision != body.expected_revision:
                    raise PlannerMutationError(
                        "revision_conflict", 409, "Plan revision has advanced", plan=plan
                    )
                operations, lookup = self._capture(plan, body.intents)
                apply_intents(plan, operations, self._metadata(lookup))
                self._repository.accept_mutation(
                    plan_id,
                    body.mutation_id,
                    digest=digest,
                    expected_revision=plan.revision,
                    evaluator_version=EVALUATOR_VERSION,
                    rule_fingerprint=self._fingerprint(lookup),
                    pending_inputs=_encode_operations(operations),
                )
            else:
                self._pending(plan, receipt)
            self._commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise PlannerMutationError(
                "not_accepted", 503, "Mutation was not durably accepted"
            ) from error
        except Exception:
            self._session.rollback()
            raise
        try:
            self._repository.lock_plan(plan_id)
            receipt = self._repository.get_receipt(plan_id, body.mutation_id)
            if receipt is None or receipt.digest != digest:
                raise PlannerMutationError("mutation_id_reused", 409, "Mutation receipt changed")
            plan = self._repository.load_canonical(plan_id)
            if receipt.status == "committed":
                result = PlannerMutationOutcome(
                    "already_committed", body.mutation_id, receipt.committed_revision, plan
                )
                self._session.commit()
                return result
            candidate, lookup = self._pending(plan, receipt)
            candidate = replace(candidate, revision=plan.revision + 1)
            from fpl_engine.planning.evaluate import evaluate_plan

            self._repository.save_canonical(
                plan_id, candidate, evaluate_plan(candidate, self._metadata(lookup))
            )
            self._repository.commit_mutation(receipt, candidate.revision)
            self._commit()
            return PlannerMutationOutcome(
                "committed", body.mutation_id, candidate.revision, candidate
            )
        except SQLAlchemyError as error:
            self._session.rollback()
            pending = self.lookup(plan_id, body.mutation_id)
            if pending.status == "already_committed":
                return pending
            raise PlannerMutationError(
                "accepted_not_saved",
                503,
                "Accepted edit is not saved; retry the same mutation ID",
                plan=pending.plan,
                candidate=pending.candidate,
            ) from error
        except Exception:
            self._session.rollback()
            raise

    def lookup(self, plan_id: int, mutation_id: UUID) -> PlannerMutationOutcome:
        try:
            self._repository.lock_plan(plan_id, shared=True)
            receipt = self._repository.get_receipt(plan_id, mutation_id)
            plan = self._repository.load_canonical(plan_id)
            if receipt is None:
                raise PlannerMutationError(
                    "mutation_not_found", 404, "Mutation receipt is not known"
                )
            candidate = None
            if receipt.status != "committed":
                candidate, _ = self._pending(plan, receipt)
            result = PlannerMutationOutcome(
                "already_committed" if receipt.status == "committed" else "accepted_not_saved",
                mutation_id,
                receipt.committed_revision,
                plan,
                candidate,
            )
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise
