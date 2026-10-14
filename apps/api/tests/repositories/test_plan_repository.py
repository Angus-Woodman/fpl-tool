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
