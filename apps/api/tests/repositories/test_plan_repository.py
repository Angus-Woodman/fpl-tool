from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from api.models.entities import PlanGameweekModel, PlanModel
from api.repositories.plan_repository import PlanRepository
from conftest import requires_database
from conftest import seed_planner_players as seed_players
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.models import Plan, PlayerRuleData
from sqlalchemy import delete, null, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = requires_database


@pytest.mark.parametrize("duplicate", [False, True])
def test_real_sql_competing_revisions_and_duplicate_final_lock(
    planner_session,
    planner_plan,
    planner_metadata,
    monkeypatch,
    duplicate,
):
    from uuid import UUID

    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.schemas.plans import PlanMutationRequestBody
    from api.services.plans import PlanMutationService, PlannerMutationError
    from conftest import seed_planner_players
    from fpl_engine.planning.evaluate import evaluate_plan
    from sqlalchemy.orm import Session

    seed_planner_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name=planner_plan.name,
        start_gameweek=8,
        end_gameweek=10,
        initial_bank=1.0,
        initial_free_transfers=1,
    )
    repository.save_canonical(plan_id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    planner_session.commit()
    engine = planner_session.get_bind()
    rendezvous = Barrier(2, timeout=10)
    original = PlanMutationService._commit
    commits: dict[int, int] = {}

    def synchronized_acceptance(service):
        original(service)
        identity = id(service)
        commits[identity] = commits.get(identity, 0) + 1
        if commits[identity] == 1:
            rendezvous.wait()

    monkeypatch.setattr(PlanMutationService, "_commit", synchronized_acceptance)

    def worker(number):
        with Session(engine) as session:
            service = PlanMutationService(session, SquadPlayerLookupRepository(session))
            body = PlanMutationRequestBody.model_validate(
                {
                    "mutation_id": str(UUID(int=1 if duplicate else number)),
                    "expected_revision": 0,
                    "intents": [{"kind": "rename_plan", "name": "Concurrent"}],
                }
            )
            try:
                return service.mutate(plan_id, body).status
            except PlannerMutationError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(worker, [1, 2]))
    assert outcomes == (
        ["already_committed", "committed"]
        if duplicate
        else ["committed", "stale_reprepare_required"]
    )
    assert repository.load_canonical(plan_id).revision == 1


@pytest.mark.parametrize("invalid", ["slot", "ownership", "player", "zero_price", "missing_parent"])
def test_boundary_sql_constraints_are_plan_scoped(
    planner_session,
    planner_plan,
    planner_metadata,
    invalid,
):
    from api.models.entities import PlanStartingPlayerModel

    seed_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    row = new_plan(planner_session)
    repository.save_canonical(row.id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    first = planner_plan.boundary.players[0]
    values = dict(
        plan_id=row.id,
        player_id=102,
        slot_id=UUID(int=8001),
        ownership_id=UUID(int=8002),
        purchase_price_tenths=50,
        provenance={},
    )
    values.update(
        {
            "slot": {"slot_id": first.slot_id},
            "ownership": {"ownership_id": first.ownership_id},
            "player": {"player_id": first.player_id},
            "zero_price": {"purchase_price_tenths": 0},
            "missing_parent": {"plan_id": 999999},
        }[invalid]
    )
    with pytest.raises(IntegrityError), planner_session.begin_nested():
        planner_session.add(PlanStartingPlayerModel(**values))
        planner_session.flush()
    other = new_plan(planner_session)
    repository.save_canonical(other.id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    assert len(repository.load_canonical(other.id).boundary.players) == 15


@pytest.mark.parametrize(
    "invalid", ["outgoing_market_tenths", "incoming_price_tenths", "selling_price_tenths", "parent"]
)
def test_transfer_sql_money_and_parent_constraints(planner_session, planner_metadata, invalid):
    import datetime as dt

    from api.models.entities import PlanTransferDecisionModel

    seed_players(planner_session, planner_metadata)
    row = new_plan(planner_session)
    week = PlanGameweekModel(plan_id=row.id, gameweek_number=8)
    planner_session.add(week)
    planner_session.flush()
    values = dict(
        plan_gameweek_id=week.id,
        decision_id=UUID(int=8000),
        outgoing_player_id=2,
        outgoing_ownership_id=UUID(int=8001),
        incoming_player_id=102,
        incoming_ownership_id=UUID(int=8002),
        outgoing_market_tenths=54,
        incoming_price_tenths=50,
        selling_price_tenths=52,
        observation_source="test",
        observed_at=dt.datetime.now(dt.UTC),
        origin="captured",
    )
    values["plan_gameweek_id" if invalid == "parent" else invalid] = (
        999999 if invalid == "parent" else 0
    )
    with pytest.raises(IntegrityError), planner_session.begin_nested():
        planner_session.add(PlanTransferDecisionModel(**values))
        planner_session.flush()


def test_coherent_reader_blocks_canonical_child_revision_change(
    planner_session,
    planner_plan,
    planner_metadata,
):
    from threading import Event

    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.schemas.plans import PlanMutationRequestBody
    from api.services.plans import PlanMutationService
    from sqlalchemy import event

    seed_players(planner_session, planner_metadata)
    repository = PlanRepository(planner_session)
    row = new_plan(planner_session)
    plan_id = row.id
    repository.save_canonical(plan_id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    planner_session.commit()
    snapshot = repository.load_canonical(plan_id)
    engine = planner_session.get_bind()
    attempting_lock = Event()

    def on_statement(connection, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement:
            attempting_lock.set()

    def writer():
        with Session(engine) as session:
            request = PlanMutationRequestBody.model_validate(
                {
                    "mutation_id": str(UUID(int=9000)),
                    "expected_revision": 0,
                    "intents": [
                        {
                            "kind": "correct_purchase_price",
                            "ownership_id": str(snapshot.boundary.players[0].ownership_id),
                            "price_tenths": 49,
                        }
                    ],
                }
            )
            return PlanMutationService(session, SquadPlayerLookupRepository(session)).mutate(
                plan_id, request
            )

    event.listen(engine, "before_cursor_execute", on_statement)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(writer)
            try:
                assert attempting_lock.wait(10)
                assert not future.done()
                coherent = repository.load_canonical(plan_id)
                assert coherent.revision == 0
                assert coherent.boundary.players[0].purchase_price_tenths == 50
            finally:
                planner_session.rollback()
            assert future.result(timeout=10).committed_revision == 1
        reopened = repository.load_canonical(plan_id)
        assert reopened.revision == 1
        assert reopened.boundary.players[0].purchase_price_tenths == 49
    finally:
        event.remove(engine, "before_cursor_execute", on_statement)


def new_plan(session: Session) -> PlanModel:
    plan = PlanModel(name="SQL plan", start_gameweek=8, end_gameweek=9)
    session.add(plan)
    session.flush()
    return plan


def test_receipt_identity_constraints_and_plan_delete_cascade(planner_session: Session) -> None:
    from api.models.entities import PlanMutationModel

    plan = new_plan(planner_session)
    mutation_id = UUID(int=1)
    receipt = PlanMutationModel(
        plan_id=plan.id,
        mutation_id=mutation_id,
        digest="a" * 64,
        expected_revision=0,
        status="validated_pending",
        evaluator_version="test",
        rule_fingerprint="b" * 64,
        pending_inputs={"intents": []},
    )
    planner_session.add(receipt)
    planner_session.flush()
    with pytest.raises(IntegrityError), planner_session.begin_nested():
        planner_session.add(
            PlanMutationModel(
                plan_id=plan.id,
                mutation_id=mutation_id,
                digest="c" * 64,
                expected_revision=0,
                status="validated_pending",
                evaluator_version="test",
                rule_fingerprint="b" * 64,
                pending_inputs={"intents": []},
            )
        )
        planner_session.flush()
    with pytest.raises(IntegrityError), planner_session.begin_nested():
        planner_session.execute(
            update(PlanMutationModel)
            .where(PlanMutationModel.id == receipt.id)
            .values(status="committed", pending_inputs=null(), committed_revision=None)
        )
    planner_session.execute(delete(PlanModel).where(PlanModel.id == plan.id))
    assert planner_session.scalars(select(PlanMutationModel)).all() == []


def test_nullable_canonical_chip_is_independent_of_legacy_chip(planner_session: Session) -> None:
    from api.models.entities import PlanChip

    plan = new_plan(planner_session)
    week = PlanGameweekModel(
        plan_id=plan.id, gameweek_number=8, chip=PlanChip.WILDCARD, planned_chip=None
    )
    planner_session.add(week)
    planner_session.flush()
    planner_session.expire_all()
    stored = planner_session.get(PlanGameweekModel, week.id)
    assert stored.planned_chip is None
    assert stored.chip == PlanChip.WILDCARD


@pytest.mark.parametrize("revision", [-1])
def test_revision_cannot_be_negative(planner_session: Session, revision: int) -> None:
    with pytest.raises(IntegrityError), planner_session.begin_nested():
        planner_session.add(
            PlanModel(name="Invalid", start_gameweek=8, end_gameweek=9, revision=revision)
        )
        planner_session.flush()


def test_canonical_load_and_rollback_are_independent_of_legacy_fields(
    planner_session: Session, planner_plan: Plan, planner_metadata: dict[int, PlayerRuleData]
) -> None:
    from dataclasses import replace

    seed_players(planner_session, planner_metadata)
    stored = new_plan(planner_session)
    plan_id = stored.id
    repository = PlanRepository(planner_session)
    repository.save_canonical(plan_id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    planner_session.commit()
    loaded = repository.load_canonical(plan_id)
    assert loaded == planner_plan
    assert stored.initial_bank == 0.0
    assert stored.initial_free_transfers == 1
    repository.save_canonical(
        plan_id,
        replace(planner_plan, name="Uncommitted", revision=1),
        evaluate_plan(planner_plan, planner_metadata),
    )
    planner_session.rollback()
    assert repository.load_canonical(plan_id) == planner_plan


def test_pending_receipt_contains_only_inputs_and_commit_drops_redundant_payload(
    planner_session: Session,
) -> None:
    from api.models.entities import PlanMutationModel

    plan = new_plan(planner_session)
    repository = PlanRepository(planner_session)
    receipt = repository.accept_mutation(
        plan.id,
        UUID(int=7),
        digest="a" * 64,
        expected_revision=0,
        evaluator_version="test",
        rule_fingerprint="b" * 64,
        pending_inputs={"intents": [{"kind": "rename_plan", "name": "Renamed"}]},
    )
    planner_session.commit()
    assert repository.get_receipt(plan.id, UUID(int=7)).pending_inputs == {
        "intents": [{"kind": "rename_plan", "name": "Renamed"}]
    }
    repository.commit_mutation(receipt, 1)
    planner_session.commit()
    stored = planner_session.get(PlanMutationModel, receipt.id)
    assert stored.pending_inputs is None
    assert stored.committed_revision == 1
    assert stored.digest == "a" * 64


def _us4_service(session, planner_plan, planner_metadata):
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.plans import PlanMutationService

    seed_players(session, planner_metadata)
    repository = PlanRepository(session)
    plan_id = new_plan(session).id
    repository.save_canonical(plan_id, planner_plan, evaluate_plan(planner_plan, planner_metadata))
    session.commit()
    return PlanMutationService(session, SquadPlayerLookupRepository(session)), repository, plan_id


def _us4_body(number, revision, intents):
    from api.schemas.plans import PlanMutationRequestBody

    return PlanMutationRequestBody.model_validate(
        {"mutation_id": str(UUID(int=number)), "expected_revision": revision, "intents": intents}
    )


def _us4_transfer(week, outgoing, ownership, incoming):
    return {
        "kind": "add_transfer",
        "gameweek_number": week,
        "outgoing_player_id": outgoing,
        "outgoing_ownership_id": str(ownership),
        "incoming_player_id": incoming,
    }


def test_us4_frozen_quotes_survive_live_refresh_and_lineup_saves_across_reopen(
    planner_session, planner_plan, planner_metadata
):
    from api.models.entities import PlanTransferDecisionModel, PlayerModel

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = planner_plan.boundary.players[1]
    planner_session.get(PlayerModel, 2).current_price = 5.4
    planner_session.get(PlayerModel, 102).current_price = 6.2
    planner_session.commit()
    saved = service.mutate(
        plan_id, _us4_body(1, 0, [_us4_transfer(8, 2, owned.ownership_id, 102)])
    ).plan
    decision = saved.gameweeks[0].transfers[0]
    assert (decision.outgoing_market_tenths, decision.incoming_price_tenths) == (54, 62)
    for identifier, price in ((2, 5.0), (102, 5.0), (3, 9.9)):
        planner_session.get(PlayerModel, identifier).current_price = price
    planner_session.commit()
    lineup = service.mutate(
        plan_id,
        _us4_body(2, 1, [{"kind": "change_captain", "gameweek_number": 9, "player_id": 4}]),
    ).plan
    planner_session.expire_all()
    reopened = repository.load_canonical(plan_id)
    assert reopened == lineup
    assert reopened.gameweeks[0].transfers == (decision,)
    row = planner_session.scalar(select(PlanTransferDecisionModel))
    assert (row.outgoing_market_tenths, row.incoming_price_tenths, row.selling_price_tenths) == (
        54,
        62,
        52,
    )
    assert evaluate_plan(reopened, planner_metadata).gameweeks[0].closing_bank_tenths == 0


def test_us4_dependent_sales_materialize_atomically_and_roll_back_with_the_correction(
    planner_session, planner_plan, planner_metadata, monkeypatch
):
    from api.models.entities import PlanTransferDecisionModel, PlayerModel
    from api.services.plans import PlannerMutationError
    from sqlalchemy.exc import SQLAlchemyError

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = planner_plan.boundary.players[1]
    planner_session.get(PlayerModel, 2).current_price = 5.4
    planner_session.commit()
    first = service.mutate(
        plan_id, _us4_body(1, 0, [_us4_transfer(8, 2, owned.ownership_id, 102)])
    ).plan
    bought = first.gameweeks[0].transfers[0]
    service.mutate(
        plan_id, _us4_body(2, 1, [_us4_transfer(9, 102, bought.incoming_ownership_id, 2)])
    )
    before = {
        r.decision_id: r.selling_price_tenths
        for r in planner_session.scalars(select(PlanTransferDecisionModel))
    }
    original = PlanRepository.save_canonical

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise SQLAlchemyError("Injected failure after sale materialization")

    correction = _us4_body(
        3,
        2,
        [
            {
                "kind": "correct_purchase_price",
                "ownership_id": str(owned.ownership_id),
                "price_tenths": 48,
            }
        ],
    )
    monkeypatch.setattr(PlanRepository, "save_canonical", fail)
    with pytest.raises(PlannerMutationError):
        service.mutate(plan_id, correction)
    planner_session.rollback()
    monkeypatch.setattr(PlanRepository, "save_canonical", original)
    unchanged = {
        r.decision_id: r.selling_price_tenths
        for r in planner_session.scalars(select(PlanTransferDecisionModel))
    }
    assert unchanged == before
    service.mutate(plan_id, correction)
    after = {
        r.decision_id: r.selling_price_tenths
        for r in planner_session.scalars(select(PlanTransferDecisionModel))
    }
    assert after[bought.decision_id] == 51 and before[bought.decision_id] == 52
    assert len(after) == 2
    assert repository.load_canonical(plan_id).gameweeks[0].transfers[0] == bought


def test_us4_resolution_is_replay_only_after_reopen_and_moves_with_repairs(
    planner_session, planner_plan, planner_metadata
):
    from api.models.entities import PlanGameweekModel, PlayerModel

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = {p.player_id: p for p in planner_plan.boundary.players}
    for identifier, price in ((102, 6.0), (3, 5.4)):
        planner_session.get(PlayerModel, identifier).current_price = price
    planner_session.commit()
    service.mutate(plan_id, _us4_body(1, 0, [_us4_transfer(9, 2, owned[2].ownership_id, 102)]))
    plan = service.mutate(
        plan_id, _us4_body(2, 1, [_us4_transfer(10, 3, owned[3].ownership_id, 103)])
    ).plan
    banks = [w.closing_bank_tenths for w in evaluate_plan(plan, planner_metadata).gameweeks]
    assert banks == [10, 0, 2]
    service.mutate(
        plan_id,
        _us4_body(
            3,
            2,
            [
                {
                    "kind": "correct_purchase_price",
                    "ownership_id": str(owned[2].ownership_id),
                    "price_tenths": 40,
                }
            ],
        ),
    )
    planner_session.execute(
        update(PlanGameweekModel).values(bank=999.0, points_hit=0, free_transfers_available=5)
    )
    planner_session.commit()
    planner_session.expire_all()
    reopened = repository.load_canonical(plan_id)
    result = evaluate_plan(reopened, planner_metadata)
    assert [w.closing_bank_tenths for w in result.gameweeks] == [10, -5, -3]
    assert result.earliest_shortfall_gameweek == 9
    assert result.gameweeks[2].financial_issue_gameweeks == frozenset({9, 10})
    assert reopened.gameweeks[1].transfers[0].incoming_price_tenths == 60
    removed = reopened.gameweeks[1].transfers[0].decision_id
    repaired = service.mutate(
        plan_id, _us4_body(4, 3, [{"kind": "remove_transfer", "decision_id": str(removed)}])
    ).plan
    planner_session.expire_all()
    assert repository.load_canonical(plan_id) == repaired
    final = evaluate_plan(repaired, planner_metadata)
    assert final.earliest_shortfall_gameweek is None
    assert all(not w.financial_issue_gameweeks for w in final.gameweeks)


def test_us4_free_hit_branch_issue_stays_temporary_after_reopen(
    planner_session, planner_plan, planner_metadata
):
    from api.models.entities import PlayerModel

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = planner_plan.boundary.players[1]
    planner_session.get(PlayerModel, 102).current_price = 6.0
    planner_session.commit()
    service.mutate(
        plan_id,
        _us4_body(
            1,
            0,
            [
                {"kind": "activate_chip", "gameweek_number": 8, "chip": "FREE_HIT"},
                _us4_transfer(8, 2, owned.ownership_id, 102),
            ],
        ),
    )
    plan = service.mutate(
        plan_id,
        _us4_body(
            2,
            1,
            [
                {
                    "kind": "correct_purchase_price",
                    "ownership_id": str(owned.ownership_id),
                    "price_tenths": 40,
                }
            ],
        ),
    ).plan
    planner_session.expire_all()
    reopened = repository.load_canonical(plan_id)
    result = evaluate_plan(reopened, planner_metadata)
    assert reopened == plan
    assert [w.closing_bank_tenths for w in result.gameweeks[:2]] == [-5, 10]
    assert result.earliest_shortfall_gameweek == 8
    assert result.gameweeks[1].financial_issue_gameweeks == frozenset()
    assert result.gameweeks[1].shortfall_tenths == 0


def test_us5_duplicate_sequence_neither_writes_twice_nor_reprices_nor_advances_revision(
    planner_session, planner_plan, planner_metadata
):
    from api.models.entities import PlanMutationModel, PlanTransferDecisionModel, PlayerModel

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = planner_plan.boundary.players[1]
    planner_session.get(PlayerModel, 2).current_price = 5.4
    planner_session.get(PlayerModel, 102).current_price = 6.2
    planner_session.commit()
    body = _us4_body(1, 0, [_us4_transfer(8, 2, owned.ownership_id, 102)])
    first = service.mutate(plan_id, body)
    assert (first.status, first.committed_revision) == ("committed", 1)
    quote = first.plan.gameweeks[0].transfers[0]
    for identifier, price in ((2, 5.0), (102, 9.9)):
        planner_session.get(PlayerModel, identifier).current_price = price
    planner_session.commit()
    row_ids = {row.id for row in planner_session.scalars(select(PlanTransferDecisionModel)).all()}
    for _ in range(3):
        again = service.mutate(plan_id, body)
        assert (again.status, again.committed_revision) == ("already_committed", 1)
        assert again.plan.revision == 1
        assert again.plan.gameweeks[0].transfers == (quote,)
    service.mutate(plan_id, _us4_body(2, 1, [{"kind": "rename_plan", "name": "Later"}]))
    late = service.mutate(plan_id, body)
    assert (late.status, late.committed_revision, late.plan.revision) == ("already_committed", 1, 2)
    assert late.candidate is None
    assert late.plan.name == "Later"
    assert late.plan.gameweeks[0].transfers == (quote,)
    receipts = planner_session.scalars(select(PlanMutationModel)).all()
    assert sorted(r.committed_revision for r in receipts) == [1, 2]
    assert {
        r.id for r in planner_session.scalars(select(PlanTransferDecisionModel)).all()
    } == row_ids
    assert repository.load_canonical(plan_id).revision == 2


def test_us5_pending_candidate_ignores_live_prices_but_not_rule_metadata(
    planner_session, planner_plan, planner_metadata, monkeypatch
):
    from api.models.entities import PlayerModel
    from api.services.plans import PlannerMutationError
    from sqlalchemy.exc import SQLAlchemyError

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = planner_plan.boundary.players[1]
    planner_session.get(PlayerModel, 2).current_price = 5.4
    planner_session.get(PlayerModel, 102).current_price = 6.2
    planner_session.commit()
    body = _us4_body(1, 0, [_us4_transfer(8, 2, owned.ownership_id, 102)])
    original = PlanRepository.save_canonical

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Injected accepted write failure")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail)
    with pytest.raises(PlannerMutationError) as failed:
        service.mutate(plan_id, body)
    quote = failed.value.candidate.gameweeks[0].transfers[0]
    assert (quote.outgoing_market_tenths, quote.incoming_price_tenths) == (54, 62)
    for identifier, price in ((2, 5.0), (102, 9.9), (3, 4.5)):
        planner_session.get(PlayerModel, identifier).current_price = price
    planner_session.commit()
    pending = service.lookup(plan_id, body.mutation_id)
    assert pending.status == "accepted_not_saved"
    assert pending.candidate.gameweeks[0].transfers[0] == quote
    monkeypatch.setattr(PlanRepository, "save_canonical", original)
    committed = service.mutate(plan_id, body)
    assert committed.committed_revision == 1
    assert committed.plan.gameweeks[0].transfers[0] == quote
    planner_session.get(PlayerModel, 5).team_id = planner_metadata[15].team_id
    planner_session.commit()
    monkeypatch.setattr(PlanRepository, "save_canonical", fail)
    second = _us4_body(2, 1, [{"kind": "rename_plan", "name": "Pending"}])
    with pytest.raises(PlannerMutationError):
        service.mutate(plan_id, second)
    planner_session.get(PlayerModel, 5).team_id = planner_metadata[5].team_id
    planner_session.get(PlayerModel, 6).team_id = planner_metadata[15].team_id
    planner_session.commit()
    with pytest.raises(PlannerMutationError) as stale:
        service.lookup(plan_id, second.mutation_id)
    assert stale.value.code == "stale_reprepare_required"
    assert stale.value.candidate is None


def test_us5_accepted_correction_rollback_keeps_q7_context_and_retries_the_same_id(
    planner_session, planner_plan, planner_metadata, monkeypatch
):
    from api.models.entities import PlayerModel
    from api.services.plans import PlannerMutationError
    from sqlalchemy.exc import SQLAlchemyError

    service, repository, plan_id = _us4_service(planner_session, planner_plan, planner_metadata)
    owned = planner_plan.boundary.players[1]
    planner_session.get(PlayerModel, 2).current_price = 5.4
    planner_session.get(PlayerModel, 102).current_price = 6.2
    planner_session.commit()
    saved = service.mutate(
        plan_id, _us4_body(1, 0, [_us4_transfer(8, 2, owned.ownership_id, 102)])
    ).plan
    quote = saved.gameweeks[0].transfers[0]
    correction = _us4_body(
        2,
        1,
        [
            {
                "kind": "correct_purchase_price",
                "ownership_id": str(owned.ownership_id),
                "price_tenths": 48,
            }
        ],
    )
    original = PlanRepository.save_canonical

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise SQLAlchemyError("Injected failure after canonical flush")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail)
    with pytest.raises(PlannerMutationError) as failed:
        service.mutate(plan_id, correction)
    assert failed.value.code == "accepted_not_saved"
    assert evaluate_plan(failed.value.candidate, planner_metadata).earliest_shortfall_gameweek == 8
    planner_session.rollback()
    assert (
        evaluate_plan(
            repository.load_canonical(plan_id), planner_metadata
        ).earliest_shortfall_gameweek
        is None
    )
    assert repository.load_canonical(plan_id) == saved
    monkeypatch.setattr(PlanRepository, "save_canonical", original)
    retry = service.mutate(plan_id, correction)
    assert (retry.status, retry.committed_revision) == ("committed", 2)
    reopened = repository.load_canonical(plan_id)
    assert reopened.gameweeks[0].transfers == (quote,)
    result = evaluate_plan(reopened, planner_metadata)
    assert result.earliest_shortfall_gameweek == 8
    assert result.gameweeks[0].sales[0].selling_price_tenths == 51
    assert service.mutate(plan_id, correction).status == "already_committed"
    assert repository.load_canonical(plan_id).revision == 2
