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
from fpl_engine.planning import models as planning
from fpl_engine.rules import RuleViolationError


@pytest.fixture
def guarded_mutations(planner_session, planner_plan, planner_metadata):
    from api.models.entities import PlanModel
    from api.repositories.plan_repository import PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.plans import PlanMutationService
    from conftest import seed_planner_players
    from fpl_engine.planning.evaluate import evaluate_plan

    seed_planner_players(planner_session, planner_metadata)
    row = PlanModel(name=planner_plan.name, start_gameweek=8, end_gameweek=10)
    planner_session.add(row)
    planner_session.flush()
    plan_id = row.id
    repository = PlanRepository(planner_session)
    repository.save_canonical(plan_id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    planner_session.commit()
    return PlanMutationService(
        planner_session, SquadPlayerLookupRepository(planner_session)
    ), plan_id


def mutation_body(number=1, revision=0, intents=None):
    import json
    from uuid import UUID

    from api.schemas.plans import PlanMutationRequestBody

    return PlanMutationRequestBody.model_validate_json(
        json.dumps(
            {
                "mutation_id": str(UUID(int=number)),
                "expected_revision": revision,
                "intents": intents or [{"kind": "rename_plan", "name": "Renamed"}],
            }
        )
    )


@pytest.mark.parametrize("start", [1, 12, 20, 25])
@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_new_plan_captures_an_independent_ready_boundary_with_default_ft(planner_session, start):
    from dataclasses import replace

    from api.models.entities import PlanGameweekPlayerModel, PlanModel
    from api.repositories.plan_repository import PlanRepository
    from conftest import seed_planner_players
    from fpl_engine.domain import PlayerPosition
    from fpl_engine.planning.models import PlayerRuleData
    from sqlalchemy import func, select

    current = FakeCurrentSquadRepository().get_current()
    current = replace(
        current,
        free_transfers=4,
        players=[replace(player, team_id=player.player_id) for player in current.players],
    )
    seed_planner_players(
        planner_session,
        {
            player.player_id: PlayerRuleData(
                player.player_id, PlayerPosition(player.position), player.team_id
            )
            for player in current.players
        },
    )

    class MutableSquad:
        calls = 0

        def get_current(self):
            self.calls += 1
            return current

    squad = MutableSquad()
    repository = PlanRepository(planner_session)
    record = CreatePlanService(repository, squad).execute(
        CreatePlanRequest("Independent", start, start + 1)
    )
    planner_session.commit()
    assert record.canonical_plan is not None
    captured = repository.load_canonical(record.plan_id)
    assert captured.boundary.free_transfers == (None if start == 1 else 1)
    assert captured.boundary.bank_tenths == 5
    assert captured.boundary.origin == "my_team_capture"
    assert not captured.boundary.used_chips
    assert not captured.boundary.free_hit_gameweek_19
    assert {player.player_id for player in captured.boundary.players} == set(range(1, 16))
    assert all(player.purchase_price_tenths == 50 for player in captured.boundary.players)
    assert all(
        player.provenance.source == "my_team_stored_market"
        and player.provenance.confirmation == "assumed"
        for player in captured.boundary.players
    )
    assert all(not week.transfers for week in captured.gameweeks)
    assert planner_session.get(PlanModel, record.plan_id).foundation_state == "ready"
    assert planner_session.scalar(select(func.count()).select_from(PlanGameweekPlayerModel)) == 0
    current = replace(current, bank=99.0, free_transfers=5, players=[])
    planner_session.expire_all()
    assert repository.load_canonical(record.plan_id) == captured
    assert squad.calls == 1


@pytest.mark.parametrize("legacy_transfer", [False, True])
@pytest.mark.parametrize("start", [8, 18, 20])
@pytest.mark.parametrize("leading_fh", [False, True])
@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_legacy_initialization_is_once_only_and_preserves_original_rows(
    planner_session,
    planner_plan,
    planner_metadata,
    legacy_transfer,
    start,
    leading_fh,
):
    from api.models.entities import PlanModel
    from api.repositories.plan_repository import PlanPlayerSave, PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
    from conftest import seed_planner_players
    from sqlalchemy import select

    seed_planner_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name="Legacy",
        start_gameweek=start,
        end_gameweek=start + 2,
        initial_bank=0.7,
        initial_free_transfers=4,
    )
    for offset, week in enumerate(planner_plan.gameweeks):
        repository.save_gameweek(
            plan_id,
            start + offset,
            chip="FREE_HIT" if leading_fh and offset == 0 else None,
            bank=0.7,
            free_transfers_available=4,
            transfers_made=0,
            points_hit=0,
            players=[
                PlanPlayerSave(
                    102
                    if legacy_transfer and offset >= 1 and player.player_id == 2
                    else player.player_id,
                    role.is_starting,
                    role.bench_order,
                    role.is_captain,
                    role.is_vice_captain,
                )
                for player, role in zip(planner_plan.boundary.players, week.lineup, strict=True)
            ],
        )
    planner_session.commit()
    before = repository.get(plan_id)
    original_columns = select(
        PlanModel.name,
        PlanModel.start_gameweek,
        PlanModel.end_gameweek,
        PlanModel.initial_bank,
        PlanModel.initial_free_transfers,
        PlanModel.created_at,
        PlanModel.updated_at,
    ).where(PlanModel.id == plan_id)
    original = planner_session.execute(original_columns).one()
    service = InitializePlannerFoundationsService(
        planner_session, SquadPlayerLookupRepository(planner_session)
    )
    assert service.execute(plan_id, apply=False).status == "ready_to_initialize"
    assert service.execute(plan_id, apply=True).status == "initialized"
    after = repository.load_canonical(plan_id)
    assert after.boundary.free_transfers == 4
    assert after.boundary.bank_tenths == 7
    assert after.boundary.origin == "legacy_first_gameweek_assumed"
    assert not after.boundary.used_chips
    assert len(after.gameweeks[1].transfers) == int(legacy_transfer)
    assert repository.get(plan_id) == before
    assert planner_session.execute(original_columns).one() == original
    planner_session.commit()
    assert service.execute(plan_id, apply=True).status == "already_ready"
    assert repository.load_canonical(plan_id) == after


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
@pytest.mark.parametrize(
    ("stored_bank", "status"),
    [
        (0.7000000000000001, "initialized"),
        (0.6999999999999993, "initialized"),
        (0.75, "legacy_pending"),
    ],
)
def test_legacy_initialization_repairs_bank_noise_but_still_blocks_invalid_money(
    planner_session, planner_plan, planner_metadata, stored_bank, status
):
    from api.repositories.plan_repository import PlanPlayerSave, PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
    from conftest import seed_planner_players

    seed_planner_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name="Legacy noisy bank",
        start_gameweek=8,
        end_gameweek=10,
        initial_bank=stored_bank,
        initial_free_transfers=1,
    )
    for offset, week in enumerate(planner_plan.gameweeks):
        repository.save_gameweek(
            plan_id,
            8 + offset,
            chip=None,
            bank=stored_bank,
            free_transfers_available=1,
            transfers_made=0,
            points_hit=0,
            players=[
                PlanPlayerSave(
                    player.player_id,
                    role.is_starting,
                    role.bench_order,
                    role.is_captain,
                    role.is_vice_captain,
                )
                for player, role in zip(planner_plan.boundary.players, week.lineup, strict=True)
            ],
        )
    planner_session.commit()
    service = InitializePlannerFoundationsService(
        planner_session, SquadPlayerLookupRepository(planner_session)
    )

    report = service.execute(plan_id, apply=True)

    assert report.status == status
    if status == "initialized":
        assert repository.load_canonical(plan_id).boundary.bank_tenths == 7
    else:
        assert "Legacy initial bank must be" in report.diagnostics[0]


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_initialized_legacy_can_repair_one_independent_blocker_and_reopen(
    planner_session,
    planner_plan,
    planner_metadata,
):
    from api.repositories.plan_repository import PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
    from api.services.plans import PlanMutationService
    from conftest import seed_planner_players
    from fpl_engine.planning.evaluate import evaluate_plan

    seed_planner_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name="Legacy repair",
        start_gameweek=8,
        end_gameweek=10,
        initial_bank=1.0,
        initial_free_transfers=1,
    )
    for offset, week in enumerate(planner_plan.gameweeks):
        repository.save_gameweek(
            plan_id,
            week.gameweek_number,
            chip="FREE_HIT" if offset == 0 else None,
            bank=1.0,
            free_transfers_available=1,
            transfers_made=0,
            points_hit=0,
            players=[
                PlanPlayerSave(
                    player.player_id,
                    role.is_starting,
                    role.bench_order,
                    role.is_vice_captain if offset < 2 else role.is_captain,
                    role.is_vice_captain,
                )
                for player, role in zip(planner_plan.boundary.players, week.lineup, strict=True)
            ],
        )
    planner_session.commit()
    lookup = SquadPlayerLookupRepository(planner_session)
    report = InitializePlannerFoundationsService(planner_session, lookup).execute(
        plan_id, apply=True
    )
    assert report.status == "initialized"
    assert report.diagnostics
    captain = next(
        player.player_id
        for player, role in zip(
            planner_plan.boundary.players, planner_plan.boundary.lineup, strict=True
        )
        if role.is_captain
    )
    service = PlanMutationService(planner_session, lookup)
    assert (
        service.mutate(
            plan_id,
            mutation_body(
                intents=[{"kind": "change_captain", "gameweek_number": 8, "player_id": captain}]
            ),
        ).committed_revision
        == 1
    )
    reopened = repository.load_canonical(plan_id)
    evaluated = evaluate_plan(reopened, planner_metadata)
    assert not any(error.gameweek_number == 8 for error in evaluated.diagnostics)
    assert any(error.gameweek_number == 9 for error in evaluated.diagnostics)
    assert evaluated.gameweeks[1].closing_bank_tenths is None
    assert evaluated.gameweeks[2].shortfall_tenths is None


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
@pytest.mark.parametrize("bad_data", ["missing", "fraction", "zero", "nonfinite"])
def test_missing_legacy_observations_remain_retryable_without_partial_initialization(
    planner_session,
    planner_plan,
    planner_metadata,
    bad_data,
):
    from api.models.entities import PlanModel, PlanStartingPlayerModel
    from api.repositories.plan_repository import PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
    from conftest import seed_planner_players
    from sqlalchemy import func, select

    seed_planner_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name="Pending", start_gameweek=8, end_gameweek=8, initial_bank=1.0, initial_free_transfers=1
    )
    repository.save_gameweek(
        plan_id,
        8,
        chip=None,
        bank=1.0,
        free_transfers_available=1,
        transfers_made=0,
        points_hit=0,
        players=[
            PlanPlayerSave(
                player.player_id,
                role.is_starting,
                role.bench_order,
                role.is_captain,
                role.is_vice_captain,
            )
            for player, role in zip(
                planner_plan.boundary.players, planner_plan.boundary.lineup, strict=True
            )
        ],
    )
    planner_session.commit()
    stored_lookup = SquadPlayerLookupRepository(planner_session)

    class BrokenObservationLookup:
        def get_by_ids(self, identifiers):
            values = stored_lookup.get_by_ids(identifiers)
            if bad_data == "missing":
                return values[1:]
            price = {"fraction": 5.55, "zero": 0.0, "nonfinite": float("nan")}[bad_data]
            return [
                __import__("dataclasses").replace(player, current_price=price) for player in values
            ]

    report = InitializePlannerFoundationsService(
        planner_session, BrokenObservationLookup()
    ).execute(plan_id, apply=True)
    assert report.status == "legacy_pending"
    assert report.diagnostics
    assert planner_session.get(PlanModel, plan_id).foundation_state == "legacy_pending"
    assert planner_session.scalar(select(func.count()).select_from(PlanStartingPlayerModel)) == 0


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_rename_is_idempotent_even_after_a_later_revision(guarded_mutations):
    service, plan_id = guarded_mutations
    first = service.mutate(plan_id, mutation_body())
    assert (first.status, first.committed_revision, first.plan.name) == ("committed", 1, "Renamed")
    service.mutate(plan_id, mutation_body(2, 1, [{"kind": "set_starting_transfers", "value": 3}]))
    retry = service.mutate(plan_id, mutation_body())
    assert retry.status == "already_committed"
    assert retry.committed_revision == 1
    assert retry.plan.revision == 2
    assert retry.plan.boundary.free_transfers == 3


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us3_independent_legacy_repairs_reopen_with_unavailable_accounting(
    guarded_mutations, planner_session, planner_metadata
):
    from dataclasses import replace
    from uuid import UUID

    from api.models.entities import PlanTransferDecisionModel
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import TransferDecision
    from fpl_engine.rules import RuleViolationError
    from sqlalchemy import select

    service, plan_id = guarded_mutations
    repository = PlanRepository(planner_session)
    plan = repository.load_canonical(plan_id)

    def bad(number, player):
        return TransferDecision(
            UUID(int=8000 + number),
            player,
            UUID(int=9000 + number),
            player + 100,
            UUID(int=10000 + number),
            50,
            50,
            "legacy",
            "2026-10-14T12:00:00+00:00",
            "legacy_initialized_estimate",
        )

    first, second = bad(1, 2), bad(2, 3)
    plan = replace(
        plan, gameweeks=(replace(plan.gameweeks[0], transfers=(first, second)), *plan.gameweeks[1:])
    )
    valid = replace(
        plan,
        gameweeks=(
            replace(
                plan.gameweeks[0],
                transfers=tuple(
                    replace(
                        decision, outgoing_ownership_id=UUID(int=1000 + decision.outgoing_player_id)
                    )
                    for decision in (first, second)
                ),
            ),
            *plan.gameweeks[1:],
        ),
    )
    repository.save_canonical(plan_id, valid, evaluate_plan(valid, planner_metadata))
    for decision in (first, second):
        row = planner_session.scalar(
            select(PlanTransferDecisionModel).where(
                PlanTransferDecisionModel.decision_id == decision.decision_id
            )
        )
        row.outgoing_ownership_id = decision.outgoing_ownership_id
    planner_session.commit()
    repaired = service.mutate(
        plan_id,
        mutation_body(100, 0, [{"kind": "remove_transfer", "decision_id": str(first.decision_id)}]),
    ).plan
    assert repository.load_canonical(plan_id) == repaired
    evaluation = evaluate_plan(repaired, planner_metadata)
    assert any(error.decision_id == second.decision_id for error in evaluation.diagnostics)
    assert evaluation.gameweeks[1].closing_bank_tenths is None
    assert evaluation.gameweeks[1].shortfall_tenths is None
    assert evaluation.gameweeks[2].points_hit is None
    with pytest.raises(RuleViolationError):
        service.mutate(
            plan_id,
            mutation_body(
                101,
                1,
                [
                    {
                        "kind": "add_transfer",
                        "gameweek_number": 9,
                        "outgoing_player_id": 4,
                        "outgoing_ownership_id": str(UUID(int=1004)),
                        "incoming_player_id": 104,
                    }
                ],
            ),
        )
    assert repository.load_canonical(plan_id) == repaired
    with pytest.raises(RuleViolationError):
        service.mutate(
            plan_id,
            mutation_body(
                103, 1, [{"kind": "change_captain", "gameweek_number": 8, "player_id": 999}]
            ),
        )
    assert repository.load_canonical(plan_id) == repaired
    final = service.mutate(
        plan_id,
        mutation_body(
            102, 1, [{"kind": "remove_transfer", "decision_id": str(second.decision_id)}]
        ),
    ).plan
    assert not evaluate_plan(final, planner_metadata).diagnostics
    assert repository.load_canonical(plan_id) == final


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us3_explicit_rebinding_and_completed_week_edit_keep_identity_and_other_quotes(
    guarded_mutations, planner_session, planner_metadata
):
    import datetime as dt
    from dataclasses import replace
    from uuid import UUID

    from api.models.entities import GameweekModel, PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import TransferDecision
    from fpl_engine.rules import RuleViolationError

    service, plan_id = guarded_mutations
    planner_session.add(
        GameweekModel(
            number=8, name="GW8", deadline=dt.datetime(2026, 9, 1, tzinfo=dt.UTC), is_finished=True
        )
    )
    planner_session.commit()
    first_plan = service.mutate(
        plan_id,
        mutation_body(
            100,
            0,
            [
                {
                    "kind": "add_transfer",
                    "gameweek_number": 8,
                    "outgoing_player_id": 2,
                    "outgoing_ownership_id": str(UUID(int=1002)),
                    "incoming_player_id": 102,
                }
            ],
        ),
    ).plan
    first = first_plan.gameweeks[0].transfers[0]
    second_plan = service.mutate(
        plan_id,
        mutation_body(
            101,
            1,
            [
                {
                    "kind": "add_transfer",
                    "gameweek_number": 9,
                    "outgoing_player_id": 102,
                    "outgoing_ownership_id": str(first.incoming_ownership_id),
                    "incoming_player_id": 2,
                }
            ],
        ),
    ).plan
    second = second_plan.gameweeks[1].transfers[0]
    untouched = TransferDecision(
        UUID(int=8100),
        5,
        UUID(int=1005),
        105,
        UUID(int=8101),
        50,
        50,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )
    with_untouched = replace(
        second_plan,
        gameweeks=(
            *second_plan.gameweeks[:2],
            replace(second_plan.gameweeks[2], transfers=(untouched,)),
        ),
    )
    PlanRepository(planner_session).save_canonical(
        plan_id, with_untouched, evaluate_plan(with_untouched, planner_metadata)
    )
    planner_session.get(PlayerModel, 102).current_price = 9.0
    planner_session.get(PlayerModel, 103).current_price = 5.5
    planner_session.get(PlayerModel, 105).current_price = 8.0
    planner_session.commit()
    unchanged = service.mutate(
        plan_id,
        mutation_body(102, 2, [{"kind": "change_captain", "gameweek_number": 10, "player_id": 4}]),
    ).plan
    assert unchanged.gameweeks[0].transfers == (first,)
    assert unchanged.gameweeks[1].transfers == (second,)
    assert unchanged.gameweeks[2].transfers == (untouched,)
    edit = {
        "kind": "edit_transfer",
        "decision_id": str(first.decision_id),
        "incoming_player_id": 103,
    }
    with pytest.raises(RuleViolationError):
        service.mutate(plan_id, mutation_body(103, 3, [edit]))
    assert PlanRepository(planner_session).load_canonical(plan_id) == unchanged
    repaired = service.mutate(
        plan_id,
        mutation_body(
            104,
            3,
            [
                edit,
                {
                    "kind": "edit_transfer",
                    "decision_id": str(second.decision_id),
                    "outgoing_player_id": 103,
                    "outgoing_source_decision_id": str(first.decision_id),
                },
            ],
        ),
    ).plan
    assert repaired.gameweeks[0].transfers[0].decision_id == first.decision_id
    assert repaired.gameweeks[1].transfers[0].decision_id == second.decision_id
    assert repaired.gameweeks[1].transfers[0].outgoing_player_id == 103
    assert (
        repaired.gameweeks[1].transfers[0].outgoing_ownership_id
        == repaired.gameweeks[0].transfers[0].incoming_ownership_id
    )
    assert repaired.gameweeks[0].transfers[0].incoming_ownership_id != first.incoming_ownership_id
    assert repaired.gameweeks[1].transfers[0].incoming_ownership_id == second.incoming_ownership_id
    assert repaired.gameweeks[0].transfers[0].incoming_price_tenths == 55
    assert repaired.gameweeks[1].transfers[0].outgoing_market_tenths == 55
    assert repaired.gameweeks[1].transfers[0].incoming_price_tenths == second.incoming_price_tenths
    assert sum(len(week.transfers) for week in repaired.gameweeks) == 3
    assert repaired.gameweeks[2].transfers == (untouched,)
    assert repaired.gameweeks[0].transfers[0].outgoing_market_tenths == first.outgoing_market_tenths
    with pytest.raises(RuleViolationError):
        service.mutate(
            plan_id,
            mutation_body(
                105,
                4,
                [
                    {
                        "kind": "edit_transfer",
                        "decision_id": str(second.decision_id),
                        "outgoing_ownership_id": str(first.incoming_ownership_id),
                    }
                ],
            ),
        )
    assert PlanRepository(planner_session).load_canonical(plan_id) == repaired


@pytest.mark.parametrize(
    "reference", ["unknown", "forward", "mismatched", "conflicting", "same_gameweek"]
)
@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_same_batch_ownership_reference_rejects_invalid_or_same_week_sources(
    guarded_mutations, planner_session, planner_plan, planner_metadata, reference
):
    from dataclasses import replace
    from uuid import UUID

    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import TransferDecision
    from fpl_engine.rules import RuleViolationError

    service, plan_id = guarded_mutations

    def decision(number, outgoing, ownership, incoming):
        return TransferDecision(
            UUID(int=8000 + number),
            outgoing,
            UUID(int=ownership),
            incoming,
            UUID(int=8100 + number),
            50,
            50,
            "stored_player_observation",
            "2026-10-14T12:00:00+00:00",
            "captured",
        )

    first = decision(1, 2, 1002, 102)
    second = decision(2, 102, 8101, 2)
    third = decision(3, 3, 1003, 103)
    plan = replace(
        planner_plan,
        gameweeks=(
            replace(planner_plan.gameweeks[0], transfers=(first,)),
            replace(
                planner_plan.gameweeks[1],
                transfers=(second, third) if reference == "same_gameweek" else (second,),
            ),
            planner_plan.gameweeks[2],
        ),
    )
    repository = PlanRepository(planner_session)
    repository.save_canonical(plan_id, plan, evaluate_plan(plan, planner_metadata))
    planner_session.commit()
    upstream = {
        "kind": "edit_transfer",
        "decision_id": str(first.decision_id),
        "incoming_player_id": 103,
    }
    repair = {
        "kind": "edit_transfer",
        "decision_id": str(second.decision_id),
        "outgoing_player_id": 103,
        "outgoing_source_decision_id": str(first.decision_id),
    }
    if reference == "unknown":
        repair["outgoing_source_decision_id"] = str(UUID(int=9999))
    elif reference == "mismatched":
        repair["outgoing_player_id"] = 104
    elif reference == "conflicting":
        repair["outgoing_ownership_id"] = str(first.incoming_ownership_id)
    elif reference == "same_gameweek":
        upstream["decision_id"] = str(third.decision_id)
        repair["outgoing_source_decision_id"] = str(third.decision_id)
    intents = [repair, upstream] if reference == "forward" else [upstream, repair]
    with pytest.raises(RuleViolationError):
        service.mutate(plan_id, mutation_body(900, 0, intents))
    assert repository.load_canonical(plan_id) == plan


@pytest.mark.parametrize("violation", ["formation", "club", "squad", "captain"])
@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us3_direct_api_rejects_illegal_state_after_propagation(
    guarded_mutations, planner_session, violation
):
    from uuid import UUID

    from api.models.entities import PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.rules import RuleViolationError

    service, plan_id = guarded_mutations
    accepted = service.mutate(
        plan_id,
        mutation_body(
            900,
            0,
            [
                {
                    "kind": "add_transfer",
                    "gameweek_number": 8,
                    "outgoing_player_id": 2,
                    "outgoing_ownership_id": str(UUID(int=1002)),
                    "incoming_player_id": 102,
                }
            ],
        ),
    ).plan
    if violation == "club":
        planner_session.get(PlayerModel, 103).team_id = planner_session.get(PlayerModel, 1).team_id
        planner_session.commit()
    intents = {
        "formation": [
            {
                "kind": "swap_lineup_players",
                "gameweek_number": 9,
                "first_player_id": 102,
                "second_player_id": 14,
            },
            {
                "kind": "swap_lineup_players",
                "gameweek_number": 9,
                "first_player_id": 3,
                "second_player_id": 15,
            },
        ],
        "club": [
            {
                "kind": "add_transfer",
                "gameweek_number": 9,
                "outgoing_player_id": 3,
                "outgoing_ownership_id": str(UUID(int=1003)),
                "incoming_player_id": 103,
            }
        ],
        "squad": [
            {
                "kind": "add_transfer",
                "gameweek_number": 9,
                "outgoing_player_id": 3,
                "outgoing_ownership_id": str(UUID(int=1003)),
                "incoming_player_id": 101,
            }
        ],
        "captain": [{"kind": "change_captain", "gameweek_number": 9, "player_id": 999}],
    }[violation]
    with pytest.raises(RuleViolationError):
        service.mutate(plan_id, mutation_body(901, 1, intents))
    assert PlanRepository(planner_session).load_canonical(plan_id) == accepted


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_core_handlers_and_explicit_dependency_repair(guarded_mutations, planner_session):
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.rules import RuleViolationError

    service, plan_id = guarded_mutations
    initial = PlanRepository(planner_session).load_canonical(plan_id)
    owned = next(player for player in initial.boundary.players if player.player_id == 2)
    upstream = service.mutate(
        plan_id,
        mutation_body(
            intents=[
                {
                    "kind": "add_transfer",
                    "gameweek_number": 8,
                    "outgoing_player_id": 2,
                    "outgoing_ownership_id": str(owned.ownership_id),
                    "incoming_player_id": 102,
                }
            ]
        ),
    ).plan
    first = upstream.gameweeks[0].transfers[0]
    downstream = (
        service.mutate(
            plan_id,
            mutation_body(
                2,
                1,
                [
                    {
                        "kind": "add_transfer",
                        "gameweek_number": 9,
                        "outgoing_player_id": 102,
                        "outgoing_ownership_id": str(first.incoming_ownership_id),
                        "incoming_player_id": 2,
                    }
                ],
            ),
        )
        .plan.gameweeks[1]
        .transfers[0]
    )
    edit = {
        "kind": "edit_transfer",
        "decision_id": str(first.decision_id),
        "incoming_player_id": 103,
    }
    with pytest.raises(RuleViolationError, match="Gameweek 9"):
        service.mutate(plan_id, mutation_body(3, 2, [edit]))
    repaired = service.mutate(
        plan_id,
        mutation_body(
            4,
            2,
            [
                edit,
                {
                    "kind": "remove_transfer",
                    "decision_id": str(downstream.decision_id),
                },
            ],
        ),
    ).plan
    assert repaired.revision == 3
    assert not repaired.gameweeks[1].transfers
    frozen = repaired.gameweeks[0].transfers
    operations = [
        {"kind": "activate_chip", "gameweek_number": 8, "chip": "FREE_HIT"},
        {"kind": "move_chip", "source_gameweek": 8, "target_gameweek": 9, "chip": "FREE_HIT"},
        {"kind": "remove_chip", "gameweek_number": 9, "chip": "FREE_HIT"},
        {"kind": "change_captain", "gameweek_number": 8, "player_id": 4},
        {"kind": "change_horizon", "start_gameweek": 9, "end_gameweek": 11},
    ]
    for number, operation in enumerate(operations, start=5):
        result = service.mutate(plan_id, mutation_body(number, number - 2, [operation]))
    assert result.plan.revision == 8
    assert result.plan.start_gameweek == 9
    assert any(player.player_id == 103 for player in result.plan.boundary.players)
    assert frozen[0].observation_source in next(
        player.provenance.source
        for player in result.plan.boundary.players
        if player.player_id == 103
    )
    assert PlanRepository(planner_session).load_canonical(plan_id) == result.plan


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
@pytest.mark.parametrize("incompatible", ["rule_context", "revision"])
def test_guarded_stale_pending_preserves_intent_without_reconstructed_candidate(
    guarded_mutations,
    planner_session,
    planner_metadata,
    monkeypatch,
    incompatible,
):
    from api.models.entities import PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from api.services.plans import PlannerMutationError
    from sqlalchemy import update
    from sqlalchemy.exc import SQLAlchemyError

    service, plan_id = guarded_mutations
    original = PlanRepository.save_canonical

    def fail_save(*args, **kwargs):
        raise SQLAlchemyError("Injected accepted write failure")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail_save)
    request = mutation_body()
    with pytest.raises(PlannerMutationError, match="not saved"):
        service.mutate(plan_id, request)
    monkeypatch.setattr(PlanRepository, "save_canonical", original)
    if incompatible == "rule_context":
        planner_session.execute(
            update(PlayerModel)
            .where(PlayerModel.id == 1)
            .values(team_id=planner_metadata[15].team_id)
        )
        planner_session.commit()
    else:
        service.mutate(plan_id, mutation_body(2, 0, [{"kind": "rename_plan", "name": "Other tab"}]))
    with pytest.raises(PlannerMutationError) as stale:
        service.lookup(plan_id, request.mutation_id)
    assert stale.value.code == "stale_reprepare_required"
    assert stale.value.candidate is None
    assert stale.value.intent_metadata is not None


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_stale_rename_and_changed_digest_never_write(guarded_mutations):
    from api.services.plans import PlannerMutationError

    service, plan_id = guarded_mutations
    service.mutate(plan_id, mutation_body())
    with pytest.raises(PlannerMutationError) as stale:
        service.mutate(plan_id, mutation_body(2))
    assert stale.value.code == "revision_conflict"
    with pytest.raises(PlannerMutationError) as changed:
        service.mutate(plan_id, mutation_body(1, 0, [{"kind": "rename_plan", "name": "Changed"}]))
    assert changed.value.code == "mutation_id_reused"


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_failure_after_acceptance_keeps_same_id_retryable(guarded_mutations, monkeypatch):
    from api.repositories.plan_repository import PlanRepository
    from api.services.plans import PlannerMutationError
    from sqlalchemy.exc import SQLAlchemyError

    service, plan_id = guarded_mutations
    original = PlanRepository.save_canonical

    def fail_write(*args, **kwargs):
        raise SQLAlchemyError("Injected canonical write failure")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail_write)
    with pytest.raises(PlannerMutationError) as failed:
        service.mutate(plan_id, mutation_body())
    assert failed.value.code == "accepted_not_saved"
    pending = service.lookup(plan_id, mutation_body().mutation_id)
    assert pending.status == "accepted_not_saved"
    assert pending.candidate.name == "Renamed"
    assert pending.plan.revision == 0
    monkeypatch.setattr(PlanRepository, "save_canonical", original)
    assert service.mutate(plan_id, mutation_body()).committed_revision == 1


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
@pytest.mark.parametrize("stage", ["before_acceptance", "partial_write", "uncertain_commit"])
def test_guarded_sql_fault_boundaries(guarded_mutations, planner_session, monkeypatch, stage):
    from api.repositories.plan_repository import PlanRepository
    from api.services.plans import PlannerMutationError
    from sqlalchemy.exc import SQLAlchemyError

    service, plan_id = guarded_mutations
    original_save = PlanRepository.save_canonical
    original_commit = planner_session.commit
    commits = 0

    def fail_acceptance(*args, **kwargs):
        raise SQLAlchemyError("Injected before acceptance")

    def fail_partial_write(repository, *args, **kwargs):
        original_save(repository, *args, **kwargs)
        raise SQLAlchemyError("Injected after canonical flush")

    def uncertain_commit():
        nonlocal commits
        original_commit()
        commits += 1
        if commits == 2:
            raise SQLAlchemyError("Injected lost COMMIT acknowledgement")

    if stage == "before_acceptance":
        monkeypatch.setattr(PlanRepository, "accept_mutation", fail_acceptance)
    elif stage == "partial_write":
        monkeypatch.setattr(PlanRepository, "save_canonical", fail_partial_write)
    else:
        monkeypatch.setattr(planner_session, "commit", uncertain_commit)
    with pytest.raises(PlannerMutationError) as failed:
        service.mutate(plan_id, mutation_body())
    expected = {
        "before_acceptance": "not_accepted",
        "partial_write": "accepted_not_saved",
        "uncertain_commit": "outcome_unknown",
    }[stage]
    assert failed.value.code == expected
    monkeypatch.undo()
    repository = PlanRepository(planner_session)
    assert repository.load_canonical(plan_id).revision == int(stage == "uncertain_commit")
    if stage == "before_acceptance":
        assert repository.get_receipt(plan_id, mutation_body().mutation_id) is None
    else:
        lookup = service.lookup(plan_id, mutation_body().mutation_id)
        assert lookup.status == (
            "already_committed" if stage == "uncertain_commit" else "accepted_not_saved"
        )
        assert service.mutate(plan_id, mutation_body()).committed_revision == 1


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_pending_quotes_survive_live_refresh_and_q7_reprices_saved_market(
    guarded_mutations,
    planner_session,
    monkeypatch,
):
    from api.models.entities import PlanTransferDecisionModel, PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from api.services.plans import PlannerMutationError
    from sqlalchemy import select, update
    from sqlalchemy.exc import SQLAlchemyError

    service, plan_id = guarded_mutations
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 2).values(current_price=5.4)
    )
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 102).values(current_price=6.2)
    )
    planner_session.commit()
    plan = PlanRepository(planner_session).load_canonical(plan_id)
    owned = next(player for player in plan.boundary.players if player.player_id == 2)
    request = mutation_body(
        intents=[
            {
                "kind": "add_transfer",
                "gameweek_number": 8,
                "outgoing_player_id": 2,
                "outgoing_ownership_id": str(owned.ownership_id),
                "incoming_player_id": 102,
            }
        ]
    )
    original = PlanRepository.save_canonical

    def fail_save(*args, **kwargs):
        raise SQLAlchemyError("Injected accepted write failure")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail_save)
    with pytest.raises(PlannerMutationError, match="not saved"):
        service.mutate(plan_id, request)
    pending = service.lookup(plan_id, request.mutation_id)
    frozen = pending.candidate.gameweeks[0].transfers[0]
    assert (frozen.outgoing_market_tenths, frozen.incoming_price_tenths) == (54, 62)
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id.in_([2, 102])).values(current_price=5.6)
    )
    planner_session.commit()
    monkeypatch.setattr(PlanRepository, "save_canonical", original)
    committed = service.mutate(plan_id, request)
    assert committed.plan.gameweeks[0].transfers[0] == frozen
    corrected = service.mutate(
        plan_id,
        mutation_body(
            2,
            1,
            [
                {
                    "kind": "correct_purchase_price",
                    "ownership_id": str(owned.ownership_id),
                    "price_tenths": 48,
                }
            ],
        ),
    )
    assert corrected.plan.boundary.bank_tenths == 10
    assert corrected.plan.boundary.players[1].provenance.original_price_tenths == 50
    assert corrected.plan.gameweeks[0].transfers[0] == frozen
    sale = planner_session.scalar(select(PlanTransferDecisionModel.selling_price_tenths))
    assert sale == 51


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_rebased_boundary_remains_editable_through_repeated_horizon_changes(
    guarded_mutations,
    planner_session,
):
    from api.models.entities import PlanTransferDecisionModel, PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from sqlalchemy import select, update

    service, plan_id = guarded_mutations
    repository = PlanRepository(planner_session)
    initial = repository.load_canonical(plan_id)
    owned = next(player for player in initial.boundary.players if player.player_id == 2)
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 2).values(current_price=5.4)
    )
    planner_session.commit()
    revision = 0

    def mutate(intent):
        nonlocal revision
        result = service.mutate(plan_id, mutation_body(100 + revision, revision, [intent]))
        revision = result.plan.revision
        return result.plan

    bought = mutate(
        {
            "kind": "add_transfer",
            "gameweek_number": 8,
            "outgoing_player_id": 2,
            "outgoing_ownership_id": str(owned.ownership_id),
            "incoming_player_id": 102,
        }
    )
    prefix_decision = bought.gameweeks[0].transfers[0]
    sold = mutate(
        {
            "kind": "add_transfer",
            "gameweek_number": 9,
            "outgoing_player_id": 102,
            "outgoing_ownership_id": str(prefix_decision.incoming_ownership_id),
            "incoming_player_id": 2,
        }
    )
    retained = sold.gameweeks[1]
    rebased = mutate({"kind": "change_horizon", "start_gameweek": 9, "end_gameweek": 10})
    carried = next(player for player in rebased.boundary.players if player.player_id == 102)
    assert carried.slot_id == owned.slot_id
    assert carried.ownership_id == prefix_decision.incoming_ownership_id
    assert carried.provenance.basis_kind == "planned_acquisition"
    assert carried.provenance.confirmation is None
    assert rebased.boundary.bank_tenths == 12
    assert owned.ownership_id in rebased.boundary.bank_assumptions
    assert rebased.gameweeks[0] == retained
    corrected = mutate(
        {
            "kind": "correct_purchase_price",
            "ownership_id": str(carried.ownership_id),
            "price_tenths": 48,
        }
    )
    corrected_player = next(
        player for player in corrected.boundary.players if player.player_id == 102
    )
    assert corrected_player.provenance == carried.provenance
    assert corrected_player.provenance.original_price_tenths == 50
    assert corrected.boundary.bank_tenths == 12
    assert corrected.gameweeks[0] == retained
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 102).values(current_price=5.6)
    )
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 2).values(current_price=5.2)
    )
    planner_session.commit()
    edited = mutate(
        {
            "kind": "edit_transfer",
            "decision_id": str(retained.transfers[0].decision_id),
            "incoming_player_id": 2,
        }
    )
    decision = edited.gameweeks[0].transfers[0]
    assert (decision.outgoing_market_tenths, decision.incoming_price_tenths) == (56, 52)
    assert decision.incoming_ownership_id == retained.transfers[0].incoming_ownership_id
    assert edited.gameweeks[0].lineup == retained.lineup
    extended = mutate({"kind": "change_horizon", "start_gameweek": 9, "end_gameweek": 12})
    assert extended.gameweeks[0] == edited.gameweeks[0]
    trimmed = mutate({"kind": "change_horizon", "start_gameweek": 9, "end_gameweek": 10})
    assert trimmed.gameweeks == extended.gameweeks[:2]
    mutate({"kind": "set_starting_transfers", "value": 0})
    mutate(
        {"kind": "set_starting_chips", "used_chips": ["WILDCARD"], "free_hit_gameweek_19": False}
    )
    planner_session.expire_all()
    reopened = repository.load_canonical(plan_id)
    assert reopened.boundary.free_transfers == 0
    assert reopened.boundary.bank_tenths == 12
    assert reopened.boundary.players == corrected.boundary.players
    assert reopened.gameweeks[0].transfers == (decision,)
    assert set(planner_session.scalars(select(PlanTransferDecisionModel.decision_id))) == {
        decision.decision_id
    }
    assert reopened.boundary.players[1].provenance.source == carried.provenance.source


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_repeated_horizons_rebase_chip_period_and_fh19_without_inventing_history(
    guarded_mutations,
    planner_session,
):
    from api.repositories.plan_repository import PlanRepository

    service, plan_id = guarded_mutations
    operations = [
        {"kind": "change_horizon", "start_gameweek": 18, "end_gameweek": 21},
        {"kind": "activate_chip", "gameweek_number": 18, "chip": "WILDCARD"},
        {"kind": "activate_chip", "gameweek_number": 19, "chip": "FREE_HIT"},
        {"kind": "change_horizon", "start_gameweek": 20, "end_gameweek": 21},
        {"kind": "set_starting_transfers", "value": 0},
        {
            "kind": "change_horizon",
            "start_gameweek": 19,
            "end_gameweek": 21,
            "used_chips": [],
            "free_hit_gameweek_19": False,
        },
        {"kind": "change_horizon", "start_gameweek": 25, "end_gameweek": 26},
        {"kind": "set_starting_chips", "used_chips": ["WILDCARD"], "free_hit_gameweek_19": False},
    ]
    for revision, operation in enumerate(operations):
        result = service.mutate(plan_id, mutation_body(200 + revision, revision, [operation])).plan
        if revision == 3:
            assert result.boundary.free_hit_gameweek_19
            assert not result.boundary.used_chips
            assert result.boundary.free_transfers == 5
        if revision == 5:
            assert result.boundary.origin == "earlier_horizon_assumed"
            assert result.boundary.free_transfers == 0
            assert result.gameweeks[0].chip is None
            assert not result.gameweeks[0].transfers
    planner_session.expire_all()
    assert PlanRepository(planner_session).load_canonical(plan_id) == result
    assert result.boundary.bank_tenths == 10
    assert not result.boundary.free_hit_gameweek_19
    assert result.boundary.used_chips == frozenset({"WILDCARD"})


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_start_later_rejects_an_unresolved_prefix_without_erasing_it(
    guarded_mutations, planner_session
):
    from api.models.entities import PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from sqlalchemy import update

    service, plan_id = guarded_mutations
    repository = PlanRepository(planner_session)
    owned = repository.load_canonical(plan_id).boundary.players[1]
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 102).values(current_price=6.0)
    )
    planner_session.commit()
    service.mutate(
        plan_id,
        mutation_body(
            intents=[
                {
                    "kind": "add_transfer",
                    "gameweek_number": 8,
                    "outgoing_player_id": 2,
                    "outgoing_ownership_id": str(owned.ownership_id),
                    "incoming_player_id": 102,
                }
            ]
        ),
    )
    corrected = service.mutate(
        plan_id,
        mutation_body(
            2,
            1,
            [
                {
                    "kind": "correct_purchase_price",
                    "ownership_id": str(owned.ownership_id),
                    "price_tenths": 30,
                }
            ],
        ),
    ).plan
    with pytest.raises(RuleViolationError, match="unresolved plan prefix"):
        service.mutate(
            plan_id,
            mutation_body(
                3,
                2,
                [
                    {
                        "kind": "change_horizon",
                        "start_gameweek": 9,
                        "end_gameweek": 10,
                    }
                ],
            ),
        )
    assert repository.load_canonical(plan_id) == corrected


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_extension_after_final_free_hit_uses_permanent_boundary(
    guarded_mutations, planner_session, planner_metadata
):
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan

    service, plan_id = guarded_mutations
    owned = PlanRepository(planner_session).load_canonical(plan_id).boundary.players[1]
    temporary = service.mutate(
        plan_id,
        mutation_body(
            intents=[
                {"kind": "activate_chip", "gameweek_number": 10, "chip": "FREE_HIT"},
                {
                    "kind": "add_transfer",
                    "gameweek_number": 10,
                    "outgoing_player_id": 2,
                    "outgoing_ownership_id": str(owned.ownership_id),
                    "incoming_player_id": 102,
                },
            ]
        ),
    ).plan
    extended = service.mutate(
        plan_id,
        mutation_body(
            2,
            1,
            [
                {
                    "kind": "change_horizon",
                    "start_gameweek": 8,
                    "end_gameweek": 12,
                }
            ],
        ),
    ).plan
    assert extended.gameweeks[:3] == temporary.gameweeks
    assessed = evaluate_plan(extended, planner_metadata)
    assert 102 in {player.player_id for player in assessed.gameweeks[2].players}
    assert 2 in {player.player_id for player in assessed.gameweeks[3].players}
    assert 102 not in {player.player_id for player in assessed.gameweeks[3].players}
    assert assessed.gameweeks[3].starting_bank_tenths == 10
    rebased = service.mutate(
        plan_id,
        mutation_body(
            3,
            2,
            [
                {
                    "kind": "change_horizon",
                    "start_gameweek": 11,
                    "end_gameweek": 12,
                }
            ],
        ),
    ).plan
    assert rebased.boundary.players == temporary.boundary.players
    assert rebased.boundary.bank_tenths == 10
    assert PlanRepository(planner_session).load_canonical(plan_id) == rebased


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_legacy_pairing_is_position_first_then_player_id(
    planner_session, planner_plan, planner_metadata
):
    from api.repositories.plan_repository import PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
    from conftest import seed_planner_players
    from fpl_engine.domain import PlayerPosition
    from fpl_engine.planning.models import PlayerRuleData

    metadata = planner_metadata | {
        120: PlayerRuleData(120, PlayerPosition.MIDFIELDER, 30),
        130: PlayerRuleData(130, PlayerPosition.DEFENDER, 31),
    }
    seed_planner_players(planner_session, metadata)
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name="Pairing", start_gameweek=8, end_gameweek=9, initial_bank=1.0, initial_free_transfers=3
    )
    for offset in range(2):
        repository.save_gameweek(
            plan_id,
            8 + offset,
            chip=None,
            bank=1.0,
            free_transfers_available=3,
            transfers_made=offset * 2,
            points_hit=0,
            players=[
                PlanPlayerSave(
                    {2: 130, 6: 120}.get(player.player_id, player.player_id)
                    if offset
                    else player.player_id,
                    role.is_starting,
                    role.bench_order,
                    role.is_captain,
                    role.is_vice_captain,
                )
                for player, role in zip(
                    planner_plan.boundary.players, planner_plan.boundary.lineup, strict=True
                )
            ],
        )
    planner_session.commit()
    service = InitializePlannerFoundationsService(
        planner_session, SquadPlayerLookupRepository(planner_session)
    )
    assert service.execute(plan_id, apply=True).status == "initialized"
    canonical = repository.load_canonical(plan_id)
    assert {
        (decision.outgoing_player_id, decision.incoming_player_id)
        for decision in canonical.gameweeks[1].transfers
    } == {(2, 130), (6, 120)}
    assert canonical.boundary.free_transfers == 3
    assert service.execute(plan_id, apply=True).status == "already_ready"
    assert repository.load_canonical(plan_id) == canonical


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
        self._canonical: dict[int, planning.Plan] = {}
        self._next_id = 1

    def list_plans(self) -> list[PlanSummaryRecord]:
        raise NotImplementedError

    def get_for_view(self, plan_id: int) -> PlanRecord | None:
        from dataclasses import replace

        record = self.get(plan_id)
        return replace(record, canonical_plan=self._canonical.get(plan_id)) if record else None

    def save_canonical(self, plan_id, plan, evaluation):
        self._canonical[plan_id] = plan
        for week, assessed in zip(plan.gameweeks, evaluation.gameweeks, strict=True):
            assert not week.transfers
            assert assessed.closing_bank_tenths is not None
            self.save_gameweek(
                plan_id,
                week.gameweek_number,
                chip=None,
                bank=assessed.closing_bank_tenths / 10,
                free_transfers_available=assessed.free_transfers_available or 0,
                transfers_made=0,
                points_hit=0,
                players=[
                    PlanPlayerSave(
                        player.player_id,
                        role.is_starting,
                        role.bench_order,
                        role.is_captain,
                        role.is_vice_captain,
                    )
                    for player, role in zip(plan.boundary.players, week.lineup, strict=True)
                ],
            )

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
    def __init__(self, players: list[PlanPlayerSelection] | None = None, bank: float = 0.5) -> None:
        self._players = players if players is not None else build_squad()
        self._bank = bank

    def get_current(self) -> CurrentSquadRecord | None:
        if not self._players:
            return None
        return CurrentSquadRecord(
            squad_id=1,
            name="My Team",
            bank=self._bank,
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
                    team_id=player.player_id,
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

    @pytest.mark.parametrize("stored", [0.5000000000000062, 0.4999999999999938, 0.5])
    def test_repairs_float_noise_in_the_saved_bank(
        self, repository: FakePlanRepository, stored: float
    ) -> None:
        service = CreatePlanService(repository, FakeCurrentSquadRepository(bank=stored))

        plan = service.execute(CreatePlanRequest(name="Plan", start_gameweek=1, end_gameweek=4))

        assert repository._canonical[plan.plan_id].boundary.bank_tenths == 5
        assert repr(plan.initial_bank) == "0.5"

    @pytest.mark.parametrize("stored", [0.55, 0.05, float("nan"), float("inf"), 1e308])
    def test_rejects_a_genuinely_invalid_saved_bank_with_a_readable_error(
        self, repository: FakePlanRepository, stored: float
    ) -> None:
        service = CreatePlanService(repository, FakeCurrentSquadRepository(bank=stored))

        with pytest.raises(RuleViolationError) as error:
            service.execute(CreatePlanRequest(name="Plan", start_gameweek=1, end_gameweek=4))

        assert error.value.code == "invalid_money"
        assert error.value.message.startswith("Saved bank")
        assert repository._plans == {}

    def test_strict_checked_tenths_still_rejects_noise(self) -> None:
        from api.services.plans import checked_tenths

        with pytest.raises(ValueError, match="whole number of tenths"):
            checked_tenths(0.5000000000000062, positive=False)
        with pytest.raises(ValueError, match="positive"):
            checked_tenths(0.0)
        assert checked_tenths(0.5, positive=False) == 5


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


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us4_correction_then_explicit_edit_recaptures_only_the_edited_record(
    guarded_mutations, planner_session, planner_metadata
):
    from api.models.entities import PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan
    from sqlalchemy import update

    service, plan_id = guarded_mutations
    repository = PlanRepository(planner_session)
    boundary = {p.player_id: p for p in repository.load_canonical(plan_id).boundary.players}
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 2).values(current_price=5.4)
    )
    planner_session.commit()

    def add(number, revision, week, outgoing, incoming):
        return service.mutate(
            plan_id,
            mutation_body(
                number,
                revision,
                [
                    {
                        "kind": "add_transfer",
                        "gameweek_number": week,
                        "outgoing_player_id": outgoing,
                        "outgoing_ownership_id": str(boundary[outgoing].ownership_id),
                        "incoming_player_id": incoming,
                    }
                ],
            ),
        ).plan

    add(100, 0, 8, 2, 102)
    saved = add(101, 1, 9, 3, 103)
    first, other = saved.gameweeks[0].transfers[0], saved.gameweeks[1].transfers[0]
    assert (first.outgoing_market_tenths, first.incoming_price_tenths) == (54, 50)
    for identifier, price in ((2, 5.6), (3, 5.8), (103, 5.9)):
        planner_session.execute(
            update(PlayerModel).where(PlayerModel.id == identifier).values(current_price=price)
        )
    planner_session.commit()
    corrected = service.mutate(
        plan_id,
        mutation_body(
            102,
            2,
            [
                {
                    "kind": "correct_purchase_price",
                    "ownership_id": str(boundary[2].ownership_id),
                    "price_tenths": 48,
                }
            ],
        ),
    ).plan
    weeks = evaluate_plan(corrected, planner_metadata).gameweeks
    assert corrected.gameweeks[0].transfers == (first,)
    assert corrected.gameweeks[1].transfers == (other,)
    assert (weeks[0].sales[0].selling_price_tenths, weeks[0].closing_bank_tenths) == (51, 11)
    edited = service.mutate(
        plan_id,
        mutation_body(
            103,
            3,
            [
                {
                    "kind": "edit_transfer",
                    "decision_id": str(first.decision_id),
                    "incoming_player_id": 104,
                }
            ],
        ),
    ).plan
    decision = edited.gameweeks[0].transfers[0]
    assert (decision.outgoing_market_tenths, decision.incoming_price_tenths) == (56, 50)
    assert decision.decision_id == first.decision_id
    assert edited.gameweeks[1].transfers == (other,)
    assert (other.outgoing_market_tenths, other.incoming_price_tenths) == (50, 50)
    after = evaluate_plan(edited, planner_metadata).gameweeks
    assert (after[0].sales[0].selling_price_tenths, after[0].closing_bank_tenths) == (52, 12)
    assert after[1].sales[0].selling_price_tenths == 50


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
@pytest.mark.parametrize("price", [0, -1, 4.8, True])
def test_us4_purchase_correction_requires_a_positive_integer_tenths_value(guarded_mutations, price):
    from api.repositories.plan_repository import PlanRepository
    from pydantic import ValidationError

    service, plan_id = guarded_mutations
    before = PlanRepository(service._session).load_canonical(plan_id)
    with pytest.raises(ValidationError):
        mutation_body(
            1,
            0,
            [
                {
                    "kind": "correct_purchase_price",
                    "ownership_id": str(before.boundary.players[1].ownership_id),
                    "price_tenths": price,
                }
            ],
        )
    assert PlanRepository(service._session).load_canonical(plan_id) == before


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
@pytest.mark.parametrize("stored", ["unknown_player", "fraction", "zero"])
def test_us4_transfer_capture_rejects_missing_or_invalid_observations_without_writes(
    guarded_mutations, planner_session, stored
):
    from api.models.entities import PlanMutationModel, PlayerModel
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.rules import RuleViolationError
    from sqlalchemy import func, select

    service, plan_id = guarded_mutations
    before = PlanRepository(planner_session).load_canonical(plan_id)
    owned = before.boundary.players[1]
    incoming = 999 if stored == "unknown_player" else 102
    if stored != "unknown_player":
        planner_session.get(PlayerModel, 102).current_price = {"fraction": 5.55, "zero": 0.0}[
            stored
        ]
        planner_session.commit()
    expected = RuleViolationError if stored == "unknown_player" else ValueError
    with pytest.raises(expected, match="observation missing|whole number|positive"):
        service.mutate(
            plan_id,
            mutation_body(
                1,
                0,
                [
                    {
                        "kind": "add_transfer",
                        "gameweek_number": 8,
                        "outgoing_player_id": 2,
                        "outgoing_ownership_id": str(owned.ownership_id),
                        "incoming_player_id": incoming,
                    }
                ],
            ),
        )
    planner_session.rollback()
    assert PlanRepository(planner_session).load_canonical(plan_id) == before
    assert planner_session.scalar(select(func.count()).select_from(PlanMutationModel)) == 0


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us4_mixed_correction_and_planning_batch_rejects_atomically(
    guarded_mutations, planner_session
):
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.rules import RuleViolationError

    service, plan_id = guarded_mutations
    before = PlanRepository(planner_session).load_canonical(plan_id)
    owned = before.boundary.players[1]
    with pytest.raises(RuleViolationError, match="mix"):
        service.mutate(
            plan_id,
            mutation_body(
                1,
                0,
                [
                    {
                        "kind": "correct_purchase_price",
                        "ownership_id": str(owned.ownership_id),
                        "price_tenths": 48,
                    },
                    {"kind": "rename_plan", "name": "Smuggled"},
                ],
            ),
        )
    assert PlanRepository(planner_session).load_canonical(plan_id) == before


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us4_rebased_correction_has_no_dangling_source_and_is_independent_of_my_team(
    guarded_mutations, planner_session, planner_metadata
):
    from uuid import UUID

    from api.models.entities import (
        PlanTransferDecisionModel,
        PlayerModel,
        SquadModel,
        SquadPlayerModel,
    )
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan
    from sqlalchemy import delete, select, update

    service, plan_id = guarded_mutations
    repository = PlanRepository(planner_session)
    owned = next(p for p in repository.load_canonical(plan_id).boundary.players if p.player_id == 2)
    planner_session.execute(
        update(PlayerModel).where(PlayerModel.id == 2).values(current_price=5.4)
    )
    planner_session.commit()
    revision = 0

    def mutate(intent):
        nonlocal revision
        plan = service.mutate(plan_id, mutation_body(300 + revision, revision, [intent])).plan
        revision = plan.revision
        return plan

    mutate(
        {
            "kind": "add_transfer",
            "gameweek_number": 8,
            "outgoing_player_id": 2,
            "outgoing_ownership_id": str(owned.ownership_id),
            "incoming_player_id": 102,
        }
    )
    rebased = mutate({"kind": "change_horizon", "start_gameweek": 9, "end_gameweek": 10})
    carried = next(p for p in rebased.boundary.players if p.player_id == 102)
    assert "decision:" in carried.provenance.source
    removed_decision = carried.provenance.source.split("decision:")[1].split("@")[0]
    assert not planner_session.scalars(
        select(PlanTransferDecisionModel).where(
            PlanTransferDecisionModel.decision_id == UUID(removed_decision)
        )
    ).all()
    planner_session.add(SquadModel(id=1, name="My Team", bank=99.9))
    planner_session.flush()
    planner_session.add(SquadPlayerModel(squad_id=1, player_id=5, is_starting=True))
    planner_session.commit()
    corrected = mutate(
        {
            "kind": "correct_purchase_price",
            "ownership_id": str(carried.ownership_id),
            "price_tenths": 48,
        }
    )
    planner_session.execute(delete(SquadPlayerModel))
    planner_session.execute(update(SquadModel).values(bank=0.0))
    planner_session.commit()
    planner_session.expire_all()
    reopened = repository.load_canonical(plan_id)
    assert reopened == corrected
    again = next(p for p in reopened.boundary.players if p.player_id == 102)
    assert (again.purchase_price_tenths, again.provenance.original_price_tenths) == (48, 50)
    assert again.provenance.source == carried.provenance.source
    assert reopened.boundary.bank_tenths == rebased.boundary.bank_tenths == 12
    assert not evaluate_plan(reopened, planner_metadata).diagnostics
    after_edit = mutate({"kind": "change_captain", "gameweek_number": 9, "player_id": 4})
    assert after_edit.boundary == reopened.boundary


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_database_outage_during_post_failure_lookup_is_outcome_unknown_not_a_crash(
    guarded_mutations, monkeypatch
):
    from api.repositories.plan_repository import PlanRepository
    from api.services.plans import PlanMutationService, PlannerMutationError
    from sqlalchemy.exc import SQLAlchemyError

    service, plan_id = guarded_mutations

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Injected outage")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail)
    monkeypatch.setattr(PlanMutationService, "lookup", fail)
    with pytest.raises(PlannerMutationError) as failed:
        service.mutate(plan_id, mutation_body())
    assert (failed.value.code, failed.value.status_code) == ("outcome_unknown", 503)
    assert "same mutation ID" in failed.value.message
