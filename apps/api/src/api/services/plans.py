from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import (
    FINAL_GAMEWEEK,
    FIRST_GAMEWEEK,
    Chip,
    RuleViolationError,
    SquadSlot,
    free_transfers_after,
    validate_chip_usage,
    validate_squad,
)

from api.repositories.current_squad_repository import CurrentSquadRecord
from api.repositories.plan_repository import (
    PlanGameweekAccounting as PlanGameweekAccountingSave,
)
from api.repositories.plan_repository import (
    PlanGameweekRecord,
    PlanNotFoundError,
    PlanPlayerSave,
    PlanRecord,
    PlanSummaryRecord,
)
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
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
    def __init__(self, repository: PlanRepositoryPort) -> None:
        self._repository = repository

    def execute(self, plan_id: int) -> PlanRecord | None:
        return self._repository.get(plan_id)


class DeletePlanService:
    def __init__(self, repository: PlanRepositoryPort) -> None:
        self._repository = repository

    def execute(self, plan_id: int) -> None:
        if self._repository.get(plan_id) is None:
            raise PlanNotFoundError(plan_id)
        self._repository.delete(plan_id)


class CreatePlanService:
    """Seed a new plan from the saved squad, copied into every gameweek in range."""

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

        plan_id = self._repository.create(
            name=request.name,
            start_gameweek=request.start_gameweek,
            end_gameweek=request.end_gameweek,
            initial_bank=current_squad.bank,
            initial_free_transfers=current_squad.free_transfers,
        )

        players = [
            PlanPlayerSave(
                player_id=player.player_id,
                is_starting=player.is_starting,
                bench_order=player.bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
            )
            for player in current_squad.players
        ]
        free_transfers = current_squad.free_transfers
        for gameweek_number in range(request.start_gameweek, request.end_gameweek + 1):
            self._repository.save_gameweek(
                plan_id,
                gameweek_number,
                chip=None,
                bank=current_squad.bank,
                free_transfers_available=free_transfers,
                transfers_made=0,
                points_hit=0,
                players=players,
            )
            free_transfers = free_transfers_after(
                available=free_transfers,
                transfers_made=0,
                chip=None,
                gameweek_number=gameweek_number,
            )

        return _require_plan(self._repository, plan_id)


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
