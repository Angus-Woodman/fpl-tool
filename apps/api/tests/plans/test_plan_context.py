from __future__ import annotations

import dataclasses
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from api.repositories.plan_repository import PlanNotFoundError, PlanNotReadyError
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.services.plan_context import ContextRef, PlanningContext, resolve_planning_context
from conftest import requires_database
from conftest import seed_planner_players as seed_players
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.models import Plan, PlayerRuleData
from fpl_engine.rules import RuleViolationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session


class RecordingPlans:
    def __init__(self, plan: Plan | Exception, calls: list[str]) -> None:
        self._plan = plan
        self._calls = calls

    def load_canonical(self, plan_id: int) -> Plan:
        self._calls.append("load_canonical")
        if isinstance(self._plan, Exception):
            raise self._plan
        return self._plan


class RecordingPlayers:
    def __init__(self, metadata: dict[int, PlayerRuleData], calls: list[str]) -> None:
        self._metadata = metadata
        self._calls = calls

    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]:
        self._calls.append("get_by_ids")
        return [
            SquadPlayerLookupItem(
                player_id=rule.player_id,
                team_id=rule.team_id,
                web_name=f"P{rule.player_id}",
                position=rule.position.value,
                current_price=5.0,
            )
            for player_id in player_ids
            if (rule := self._metadata.get(player_id)) is not None
        ]


class RecordingTransaction:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def rollback(self) -> None:
        self._calls.append("rollback")


def resolve(
    plan: Plan | Exception,
    metadata: dict[int, PlayerRuleData],
    gameweek: int = 9,
) -> tuple[PlanningContext, list[str]]:
    calls: list[str] = []
    context = resolve_planning_context(
        plans=RecordingPlans(plan, calls),
        players=RecordingPlayers(metadata, calls),
        transaction=RecordingTransaction(calls),
        plan_id=7,
        gameweek=gameweek,
    )
    return context, calls


def test_a_ready_plan_resolves_to_an_immutable_context_with_its_baseline(
    planner_plan: Plan, planner_metadata: dict[int, PlayerRuleData]
) -> None:
    context, _ = resolve(planner_plan, planner_metadata)

    assert context.ref == ContextRef(plan_id=7, gameweek=9, revision=planner_plan.revision)
    assert context.plan is planner_plan
    assert {player.player_id for player in planner_plan.boundary.players} <= set(context.metadata)
    assert context.baseline == evaluate_plan(planner_plan, context.metadata)
    assert context.selected_week.gameweek_number == 9
    assert context.selected_week.players is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.ref = ContextRef(1, 1, 1)  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.plan = planner_plan  # type: ignore[misc]


def test_the_plan_read_transaction_ends_right_after_loading_and_nothing_else_is_touched(
    planner_plan: Plan, planner_metadata: dict[int, PlayerRuleData]
) -> None:
    _, calls = resolve(planner_plan, planner_metadata)

    assert calls == ["load_canonical", "rollback", "get_by_ids"]


def test_the_context_holds_no_repository_session_or_connection(
    planner_plan: Plan, planner_metadata: dict[int, PlayerRuleData]
) -> None:
    context, _ = resolve(planner_plan, planner_metadata)

    allowed = (ContextRef, Plan, dict, type(context.baseline))
    for field in dataclasses.fields(context):
        value: Any = getattr(context, field.name)
        assert isinstance(value, allowed), field.name
    assert not hasattr(context, "session") and not hasattr(context, "repository")


@pytest.mark.parametrize(
    ("failure", "expected"),
    [(PlanNotFoundError(7), PlanNotFoundError), (PlanNotReadyError(7), PlanNotReadyError)],
)
def test_a_missing_or_uninitialised_plan_fails_explicitly(
    planner_metadata: dict[int, PlayerRuleData], failure: Exception, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        resolve(failure, planner_metadata)


def test_a_gameweek_outside_the_plan_is_rejected(
    planner_plan: Plan, planner_metadata: dict[int, PlayerRuleData]
) -> None:
    with pytest.raises(RuleViolationError) as error:
        resolve(planner_plan, planner_metadata, gameweek=20)
    assert error.value.code == "gameweek_not_in_plan"


def test_a_gameweek_whose_squad_cannot_be_evaluated_is_blocked(
    planner_plan: Plan, planner_metadata: dict[int, PlayerRuleData]
) -> None:
    from fpl_engine.planning.models import TransferDecision

    broken = TransferDecision(
        decision_id=UUID(int=1),
        outgoing_player_id=2,
        outgoing_ownership_id=UUID(int=999_999),
        incoming_player_id=102,
        incoming_ownership_id=UUID(int=3000),
        outgoing_market_tenths=54,
        incoming_price_tenths=50,
        observation_source="stored_player_observation",
        observed_at="2026-10-14T12:00:00+00:00",
        origin="captured",
    )
    plan = replace(
        planner_plan,
        gameweeks=tuple(
            replace(week, transfers=(broken,)) if week.gameweek_number == 9 else week
            for week in planner_plan.gameweeks
        ),
    )
    with pytest.raises(RuleViolationError) as error:
        resolve(plan, planner_metadata, gameweek=9)
    assert error.value.code == "evaluation_blocked"


@requires_database
def test_resolving_releases_the_plan_lock_and_writes_nothing(
    planner_session: Session,
    planner_plan: Plan,
    planner_metadata: dict[int, PlayerRuleData],
) -> None:
    from api.models.entities import PlanModel, PlanMutationModel
    from api.repositories.plan_repository import PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository

    seed_players(planner_session, planner_metadata)
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
    before = planner_session.execute(
        select(PlanModel.revision, PlanModel.updated_at).where(PlanModel.id == plan_id)
    ).one()
    receipts_before = planner_session.scalar(
        select(text("count(*)")).select_from(PlanMutationModel)
    )

    engine = planner_session.get_bind()
    with Session(engine) as reader:
        context = resolve_planning_context(
            plans=PlanRepository(reader),
            players=SquadPlayerLookupRepository(reader),
            transaction=reader,
            plan_id=plan_id,
            gameweek=9,
        )
        assert context.ref.revision == before.revision
        # A writer must be able to take the plan row immediately: no lock is held.
        with Session(engine) as writer:
            locked = writer.scalar(
                select(PlanModel.id).where(PlanModel.id == plan_id).with_for_update(nowait=True)
            )
            assert locked == plan_id
            writer.rollback()

    after = planner_session.execute(
        select(PlanModel.revision, PlanModel.updated_at).where(PlanModel.id == plan_id)
    ).one()
    assert after == before
    assert (
        planner_session.scalar(select(text("count(*)")).select_from(PlanMutationModel))
        == receipts_before
    )
