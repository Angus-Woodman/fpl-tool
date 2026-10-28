from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from api.models import PlayerModel
from api.models.entities import PlanMutationModel
from api.repositories.plan_repository import PlanRepository
from api.schemas.plans import PlanMutationRequestBody
from api.services.plans import PlannerMutationError
from conftest import requires_database
from fpl_engine.planning.mutations import MutationRejectedError
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from test_plan_services import guarded_mutations as guarded_mutations
from test_plan_services import mutation_body
from test_plans_router import guarded_client as guarded_client


@pytest.fixture
def guarded(request: pytest.FixtureRequest) -> tuple[Any, int]:
    return request.getfixturevalue("guarded_mutations")  # type: ignore[no-any-return]


@pytest.fixture
def guarded_api(request: pytest.FixtureRequest) -> tuple[Any, int]:
    return request.getfixturevalue("guarded_client")  # type: ignore[no-any-return]


def add_transfer(
    incoming: int = 102, outgoing: int = 2, gameweek: int = 8, **guard: int
) -> dict[str, Any]:
    return {
        "kind": "add_transfer",
        "gameweek_number": gameweek,
        "outgoing_player_id": outgoing,
        "outgoing_ownership_id": str(UUID(int=1000 + outgoing)),
        "incoming_player_id": incoming,
        **guard,
    }


def set_player(session: Session, player_id: int, **values: object) -> None:
    session.execute(update(PlayerModel).where(PlayerModel.id == player_id).values(**values))
    session.commit()


def receipts(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(PlanMutationModel)) or 0


def parse(intent: dict[str, Any]) -> PlanMutationRequestBody:
    return PlanMutationRequestBody.model_validate_json(
        json.dumps({"mutation_id": str(UUID(int=1)), "expected_revision": 0, "intents": [intent]})
    )


@pytest.mark.parametrize(
    "guard",
    [
        {"expected_outgoing_market_tenths": 54},
        {"expected_incoming_price_tenths": 50},
        {"expected_outgoing_market_tenths": 0, "expected_incoming_price_tenths": 50},
        {"expected_outgoing_market_tenths": 54, "expected_incoming_price_tenths": -1},
        {"expected_outgoing_market_tenths": 10_001, "expected_incoming_price_tenths": 50},
        {"expected_outgoing_market_tenths": 5.4, "expected_incoming_price_tenths": 50},
    ],
)
def test_guard_fields_are_both_or_neither_positive_whole_tenths(guard: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        parse(add_transfer(**guard))
    edit = {"kind": "edit_transfer", "decision_id": str(UUID(int=7)), **guard}
    with pytest.raises(ValidationError):
        parse(edit)


def test_a_complete_guard_and_no_guard_are_both_valid() -> None:
    guard = {"expected_outgoing_market_tenths": 54, "expected_incoming_price_tenths": 50}
    assert parse(add_transfer(**guard)).intents
    assert parse(add_transfer()).intents
    assert parse({"kind": "edit_transfer", "decision_id": str(UUID(int=7)), **guard}).intents


@requires_database
def test_a_matching_guard_commits_at_the_servers_own_prices(
    guarded: tuple[Any, int],
) -> None:
    service, plan_id = guarded
    result = service.mutate(
        plan_id,
        mutation_body(
            intents=[
                add_transfer(expected_outgoing_market_tenths=50, expected_incoming_price_tenths=50)
            ]
        ),
    )

    decision = result.plan.gameweeks[0].transfers[0]
    assert (decision.outgoing_market_tenths, decision.incoming_price_tenths) == (50, 50)
    assert decision.observation_source == "stored_player_observation"


@requires_database
@pytest.mark.parametrize(
    ("guard", "player_id"),
    [
        ({"expected_outgoing_market_tenths": 54, "expected_incoming_price_tenths": 50}, 2),
        ({"expected_outgoing_market_tenths": 50, "expected_incoming_price_tenths": 49}, 102),
    ],
)
def test_a_changed_price_is_rejected_before_any_receipt_or_write(
    guarded: tuple[Any, int],
    planner_session: Session,
    guard: dict[str, int],
    player_id: int,
) -> None:
    service, plan_id = guarded
    before = receipts(planner_session)

    with pytest.raises(MutationRejectedError) as error:
        service.mutate(plan_id, mutation_body(intents=[add_transfer(**guard)]))

    assert error.value.code == "prices_changed"
    diagnostic = error.value.diagnostics[0]
    assert (diagnostic.code, diagnostic.gameweek_number, diagnostic.player_id) == (
        "prices_changed",
        8,
        player_id,
    )
    assert receipts(planner_session) == before
    assert PlanRepository(planner_session).load_canonical(plan_id).revision == 0


@requires_database
def test_the_guard_is_part_of_the_digest_and_a_same_id_retry_does_not_rerun_it(
    guarded: tuple[Any, int], planner_session: Session
) -> None:
    service, plan_id = guarded
    guarded = add_transfer(expected_outgoing_market_tenths=50, expected_incoming_price_tenths=50)
    first = service.mutate(plan_id, mutation_body(intents=[guarded]))
    assert first.status == "committed"

    set_player(planner_session, 102, current_price=5.2)
    retry = service.mutate(plan_id, mutation_body(intents=[guarded]))
    assert retry.status == "already_committed"

    changed = add_transfer(expected_outgoing_market_tenths=50, expected_incoming_price_tenths=52)
    with pytest.raises(PlannerMutationError) as reused:
        service.mutate(plan_id, mutation_body(intents=[changed]))
    assert reused.value.code == "mutation_id_reused"


@requires_database
@pytest.mark.parametrize(
    ("flags", "code"),
    [
        ({"can_select": False, "can_transact": True}, "player_not_selectable"),
        ({"can_select": True, "can_transact": False}, "player_not_selectable"),
        ({"can_select": False, "can_transact": None}, "player_not_selectable"),
        ({"can_select": None, "can_transact": None}, "selectability_unknown"),
        ({"can_select": True, "can_transact": None}, "selectability_unknown"),
    ],
)
def test_adding_a_non_selectable_or_unknown_player_is_rejected(
    guarded: tuple[Any, int],
    planner_session: Session,
    flags: dict[str, bool | None],
    code: str,
) -> None:
    service, plan_id = guarded
    set_player(planner_session, 102, **flags)

    with pytest.raises(MutationRejectedError) as error:
        service.mutate(plan_id, mutation_body(intents=[add_transfer()]))

    assert error.value.code == code
    assert error.value.diagnostics[0].player_id == 102
    assert PlanRepository(planner_session).load_canonical(plan_id).revision == 0


@requires_database
def test_playing_status_never_rejects_a_selectable_player(
    guarded: tuple[Any, int], planner_session: Session
) -> None:
    service, plan_id = guarded
    set_player(planner_session, 102, status="i")

    assert service.mutate(plan_id, mutation_body(intents=[add_transfer()])).status == "committed"


@requires_database
def test_an_edit_is_checked_only_when_it_changes_the_incoming_player(
    guarded: tuple[Any, int], planner_session: Session
) -> None:
    service, plan_id = guarded
    added = service.mutate(plan_id, mutation_body(intents=[add_transfer()]))
    decision = added.plan.gameweeks[0].transfers[0]
    set_player(planner_session, 103, can_select=False)

    with pytest.raises(MutationRejectedError) as error:
        service.mutate(
            plan_id,
            mutation_body(
                2,
                1,
                [
                    {
                        "kind": "edit_transfer",
                        "decision_id": str(decision.decision_id),
                        "incoming_player_id": 103,
                    }
                ],
            ),
        )
    assert error.value.code == "player_not_selectable"

    set_player(planner_session, 102, can_select=False, can_transact=False)
    unchanged = service.mutate(
        plan_id,
        mutation_body(
            3,
            1,
            [{"kind": "edit_transfer", "decision_id": str(decision.decision_id)}],
        ),
    )
    assert unchanged.status == "committed"
    assert unchanged.plan.gameweeks[0].transfers[0].incoming_player_id == 102


@requires_database
def test_saved_decisions_are_never_rechecked_on_replay(
    guarded: tuple[Any, int], planner_session: Session
) -> None:
    service, plan_id = guarded
    service.mutate(plan_id, mutation_body(intents=[add_transfer()]))
    set_player(planner_session, 102, can_select=False, can_transact=False)

    renamed = service.mutate(plan_id, mutation_body(2, 1))

    assert renamed.status == "committed"
    assert renamed.plan.gameweeks[0].transfers[0].incoming_player_id == 102


@requires_database
def test_the_router_maps_the_guard_and_selectability_rejections_to_422(
    guarded_api: tuple[Any, int], planner_session: Session
) -> None:
    client, plan_id = guarded_api

    def post(number: int, intent: dict[str, Any]) -> Any:
        return client.post(
            f"/plans/{plan_id}/mutations",
            json={
                "mutation_id": str(UUID(int=number)),
                "expected_revision": 0,
                "intents": [intent],
            },
        )

    half = post(1, add_transfer(expected_outgoing_market_tenths=50))
    assert half.status_code == 422

    changed = post(
        2, add_transfer(expected_outgoing_market_tenths=50, expected_incoming_price_tenths=49)
    )
    assert changed.status_code == 422
    body = changed.json()["detail"]
    assert body["code"] == "prices_changed"
    assert body["diagnostics"][0]["code"] == "prices_changed"
    assert body["diagnostics"][0]["player_id"] == 102

    set_player(planner_session, 102, can_select=None)
    unknown = post(3, add_transfer())
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "selectability_unknown"
    assert receipts(planner_session) == 0
