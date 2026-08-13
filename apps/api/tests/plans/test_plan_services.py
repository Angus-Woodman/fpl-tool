from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from api.repositories.current_squad_repository import (
    CurrentSquadPlayerRecord,
    CurrentSquadRecord,
)
from api.repositories.plan_repository import (
    PlanGameweekAccounting,
    PlanGameweekRecord,
    PlanPlayerRecord,
    PlanPlayerSave,
    PlanRecord,
    PlanSummaryRecord,
)
from api.services.plan_accounting import PlanPlayerSelection
from api.services.plans import (
    CreatePlanRequest,
    CreatePlanService,
    DeletePlanService,
    PlanNotFoundError,
    SavePlanGameweekRequest,
    SavePlanGameweekService,
    UpdatePlanRequest,
    UpdatePlanService,
)
from builders import (
    POSITIONS,
    PRICES,
    FakePlayerLookupRepository,
    build_squad,
    transfer,
)
from fpl_engine.rules import RuleViolationError


@dataclass
class _StoredGameweek:
    chip: str | None
    bank: float
    free_transfers_available: int
    transfers_made: int
    points_hit: int
    players: list[PlanPlayerSave]


@dataclass
class _StoredPlan:
    name: str
    start_gameweek: int
    end_gameweek: int
    initial_bank: float
    initial_free_transfers: int
    gameweeks: dict[int, _StoredGameweek] = field(default_factory=dict)


class FakePlanRepository:
    def __init__(self) -> None:
        self._plans: dict[int, _StoredPlan] = {}
        self._next_id = 1

    def list_plans(self) -> list[PlanSummaryRecord]:
        raise NotImplementedError

    def get(self, plan_id: int) -> PlanRecord | None:
        plan = self._plans.get(plan_id)
        if plan is None:
            return None
        return PlanRecord(
            plan_id=plan_id,
            name=plan.name,
            start_gameweek=plan.start_gameweek,
            end_gameweek=plan.end_gameweek,
            initial_bank=plan.initial_bank,
            initial_free_transfers=plan.initial_free_transfers,
            gameweeks=[
                PlanGameweekRecord(
                    gameweek_number=number,
                    chip=stored.chip,
                    bank=stored.bank,
                    free_transfers_available=stored.free_transfers_available,
                    transfers_made=stored.transfers_made,
                    points_hit=stored.points_hit,
                    players=[
                        PlanPlayerRecord(
                            player_id=player.player_id,
                            web_name=f"P{player.player_id}",
                            first_name="First",
                            second_name="Second",
                            team_id=player.player_id,
                            team_name=f"Team {player.player_id}",
                            team_short_name="TMX",
                            position=POSITIONS[player.player_id],
                            current_price=PRICES[player.player_id],
                            status="a",
                            is_starting=player.is_starting,
                            bench_order=player.bench_order,
                            is_captain=player.is_captain,
                            is_vice_captain=player.is_vice_captain,
                        )
                        for player in stored.players
                    ],
                )
                for number, stored in sorted(plan.gameweeks.items())
            ],
        )

    def create(
        self,
        *,
        name: str,
        start_gameweek: int,
        end_gameweek: int,
        initial_bank: float,
        initial_free_transfers: int,
    ) -> int:
        plan_id = self._next_id
        self._next_id += 1
        self._plans[plan_id] = _StoredPlan(
            name=name,
            start_gameweek=start_gameweek,
            end_gameweek=end_gameweek,
            initial_bank=initial_bank,
            initial_free_transfers=initial_free_transfers,
        )
        return plan_id

    def update_details(
        self,
        plan_id: int,
        *,
        name: str | None = None,
        start_gameweek: int | None = None,
        end_gameweek: int | None = None,
    ) -> None:
        plan = self._plans[plan_id]
        if name is not None:
            plan.name = name
        if start_gameweek is not None:
            plan.start_gameweek = start_gameweek
        if end_gameweek is not None:
            plan.end_gameweek = end_gameweek

    def delete(self, plan_id: int) -> None:
        del self._plans[plan_id]

    def delete_gameweeks_outside(self, plan_id: int, *, start: int, end: int) -> None:
        plan = self._plans[plan_id]
        plan.gameweeks = {
            number: stored for number, stored in plan.gameweeks.items() if start <= number <= end
        }

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
    ) -> None:
        self._plans[plan_id].gameweeks[gameweek_number] = _StoredGameweek(
            chip=chip,
            bank=bank,
            free_transfers_available=free_transfers_available,
            transfers_made=transfers_made,
            points_hit=points_hit,
            players=list(players),
        )

    def update_accounting(self, plan_id: int, entries: list[PlanGameweekAccounting]) -> None:
        plan = self._plans[plan_id]
        for entry in entries:
            stored = plan.gameweeks[entry.gameweek_number]
            stored.bank = entry.bank
            stored.free_transfers_available = entry.free_transfers_available
            stored.transfers_made = entry.transfers_made
            stored.points_hit = entry.points_hit


class FakeCurrentSquadRepository:
    def __init__(self, players: list[PlanPlayerSelection] | None = None) -> None:
        self._players = players if players is not None else build_squad()

    def get_current(self) -> CurrentSquadRecord | None:
        if not self._players:
            return None
        return CurrentSquadRecord(
            squad_id=1,
            name="My Team",
            bank=0.5,
            free_transfers=1,
            players=[
                CurrentSquadPlayerRecord(
                    player_id=player.player_id,
                    web_name=f"P{player.player_id}",
                    first_name="First",
                    second_name="Second",
                    team_name=f"Team {player.player_id}",
                    team_short_name="TMX",
                    position=POSITIONS[player.player_id],
                    current_price=PRICES[player.player_id],
                    status="a",
                    is_starting=player.is_starting,
                    bench_order=player.bench_order,
                    is_captain=player.is_captain,
                    is_vice_captain=player.is_vice_captain,
                )
                for player in self._players
            ],
        )


@pytest.fixture
def repository() -> FakePlanRepository:
    return FakePlanRepository()


@pytest.fixture
def plan_id(repository: FakePlanRepository) -> int:
    service = CreatePlanService(repository, FakeCurrentSquadRepository())
    plan = service.execute(
        CreatePlanRequest(name="No Haaland GW1", start_gameweek=1, end_gameweek=4)
    )
    return plan.plan_id


def _save(
    repository: FakePlanRepository,
    plan_id: int,
    gameweek_number: int,
    players: list[PlanPlayerSelection],
    chip: str | None = None,
) -> PlanRecord:
    service = SavePlanGameweekService(repository, FakePlayerLookupRepository())
    return service.execute(
        SavePlanGameweekRequest(
            plan_id=plan_id,
            gameweek_number=gameweek_number,
            chip=chip,
            players=players,
        )
    )


class TestCreatePlan:
    def test_seeds_every_gameweek_in_the_horizon(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        plan = repository.get(plan_id)
        assert plan is not None
        assert [gameweek.gameweek_number for gameweek in plan.gameweeks] == [1, 2, 3, 4]
        assert all(len(gameweek.players) == 15 for gameweek in plan.gameweeks)

    def test_rejects_blank_name(self, repository: FakePlanRepository) -> None:
        service = CreatePlanService(repository, FakeCurrentSquadRepository())
        with pytest.raises(RuleViolationError) as error:
            service.execute(CreatePlanRequest(name="  ", start_gameweek=1, end_gameweek=4))
        assert error.value.code == "plan_name"

    def test_rejects_backwards_horizon(self, repository: FakePlanRepository) -> None:
        service = CreatePlanService(repository, FakeCurrentSquadRepository())
        with pytest.raises(RuleViolationError) as error:
            service.execute(CreatePlanRequest(name="Plan", start_gameweek=6, end_gameweek=3))
        assert error.value.code == "plan_horizon"

    def test_requires_a_saved_squad(self, repository: FakePlanRepository) -> None:
        service = CreatePlanService(repository, FakeCurrentSquadRepository(players=[]))
        with pytest.raises(RuleViolationError) as error:
            service.execute(CreatePlanRequest(name="Plan", start_gameweek=1, end_gameweek=4))
        assert error.value.code == "no_squad"


class TestUpdatePlan:
    def test_renames_a_plan(self, repository: FakePlanRepository, plan_id: int) -> None:
        plan = UpdatePlanService(repository).execute(
            plan_id, UpdatePlanRequest(name="Haaland In GW2")
        )
        assert plan.name == "Haaland In GW2"

    def test_extending_the_horizon_copies_the_last_squad_forward(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        plan = UpdatePlanService(repository).execute(plan_id, UpdatePlanRequest(end_gameweek=6))

        assert [gameweek.gameweek_number for gameweek in plan.gameweeks] == [1, 2, 3, 4, 5, 6]
        assert len(plan.gameweeks[-1].players) == 15

    def test_shrinking_the_horizon_drops_gameweeks(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        plan = UpdatePlanService(repository).execute(plan_id, UpdatePlanRequest(end_gameweek=2))

        assert [gameweek.gameweek_number for gameweek in plan.gameweeks] == [1, 2]

    def test_unknown_plan_raises(self, repository: FakePlanRepository) -> None:
        with pytest.raises(PlanNotFoundError):
            UpdatePlanService(repository).execute(99, UpdatePlanRequest(name="Nope"))


class TestSavePlanGameweek:
    def test_bench_and_starters_can_be_reshuffled_for_free(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        squad = build_squad()
        swapped = [
            player
            if player.player_id not in (14, 15)
            else PlanPlayerSelection(
                player_id=player.player_id,
                is_starting=player.player_id == 15,
                bench_order=4 if player.player_id == 14 else None,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
            )
            for player in squad
        ]

        plan = _save(repository, plan_id, 2, swapped)

        assert plan.gameweeks[1].transfers_made == 0
        assert plan.gameweeks[1].points_hit == 0

    def test_transfer_consumes_a_free_transfer_and_carries_forward(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        plan = _save(repository, plan_id, 2, transfer(build_squad(), out_id=12, in_id=17))

        assert plan.gameweeks[1].transfers_made == 1
        assert plan.gameweeks[1].points_hit == 0
        assert all(
            17 in {player.player_id for player in gameweek.players}
            for gameweek in plan.gameweeks[1:]
        )

    def test_extra_transfers_in_one_gameweek_cost_four_points(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        squad = transfer(
            transfer(transfer(build_squad(), out_id=12, in_id=17), out_id=11, in_id=16),
            out_id=10,
            in_id=20,
        )

        plan = _save(repository, plan_id, 2, squad)

        assert plan.gameweeks[1].transfers_made == 3
        assert plan.gameweeks[1].points_hit == 8

    def test_wildcard_removes_the_hit(self, repository: FakePlanRepository, plan_id: int) -> None:
        squad = transfer(
            transfer(transfer(build_squad(), out_id=12, in_id=17), out_id=11, in_id=16),
            out_id=10,
            in_id=20,
        )

        plan = _save(repository, plan_id, 2, squad, chip="WILDCARD")

        assert plan.gameweeks[1].points_hit == 0
        assert plan.gameweeks[1].chip == "WILDCARD"

    def test_same_chip_cannot_be_used_twice_in_one_half(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        _save(repository, plan_id, 2, build_squad(), chip="BENCH_BOOST")

        with pytest.raises(RuleViolationError) as error:
            _save(repository, plan_id, 3, build_squad(), chip="BENCH_BOOST")
        assert error.value.code == "chip_already_used"

    def test_transfer_that_breaks_the_budget_is_rejected(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        with pytest.raises(RuleViolationError) as error:
            _save(repository, plan_id, 2, transfer(build_squad(), out_id=12, in_id=21))
        assert error.value.code == "budget"

    def test_illegal_formation_is_rejected(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        squad = [
            player
            if player.player_id not in (1, 2)
            else PlanPlayerSelection(
                player_id=player.player_id,
                is_starting=True,
                bench_order=None,
                is_captain=False,
                is_vice_captain=False,
            )
            for player in build_squad()
        ]

        with pytest.raises(RuleViolationError):
            _save(repository, plan_id, 2, squad)

    def test_gameweek_outside_the_plan_is_rejected(
        self, repository: FakePlanRepository, plan_id: int
    ) -> None:
        with pytest.raises(RuleViolationError) as error:
            _save(repository, plan_id, 9, build_squad())
        assert error.value.code == "gameweek_outside_plan"

    def test_unknown_plan_raises(self, repository: FakePlanRepository) -> None:
        with pytest.raises(PlanNotFoundError):
            _save(repository, 99, 1, build_squad())


class TestDeletePlan:
    def test_removes_the_plan(self, repository: FakePlanRepository, plan_id: int) -> None:
        DeletePlanService(repository).execute(plan_id)

        assert repository.get(plan_id) is None

    def test_unknown_plan_raises(self, repository: FakePlanRepository) -> None:
        with pytest.raises(PlanNotFoundError):
            DeletePlanService(repository).execute(99)
