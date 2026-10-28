from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from api.db.base import Base
from api.db.session import get_db_session
from api.main import app
from api.models import (
    FixtureModel,
    GameweekModel,
    PlayerModel,
    ProjectionModel,
    ProjectionRunModel,
)
from api.models.entities import PlanModel
from api.repositories.plan_repository import PlanRepository
from conftest import requires_database
from conftest import seed_planner_players as seed_players
from fastapi.testclient import TestClient
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.models import Plan, PlayerRuleData
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

pytestmark = requires_database

GENERATED_AT = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)


def table_counts(session: Session) -> dict[str, int]:
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in Base.metadata.sorted_tables
    }


def seed_plan_and_projections(
    session: Session, plan: Plan, metadata: dict[int, PlayerRuleData]
) -> int:
    seed_players(session, metadata)
    session.execute(update(PlayerModel).values(can_select=True, can_transact=True))
    repository = PlanRepository(session)
    plan_id = repository.create(
        name=plan.name,
        start_gameweek=plan.start_gameweek,
        end_gameweek=plan.end_gameweek,
        initial_bank=1.0,
        initial_free_transfers=1,
    )
    repository.save_canonical(plan_id, plan, evaluate_plan(plan, metadata))
    run = ProjectionRunModel(
        model_version="component_v3",
        generated_at=GENERATED_AT,
        gameweeks_covered=list(range(8, 13)),
        parameters={},
        team_strength_snapshot={},
        player_snapshot_generated_at=GENERATED_AT,
    )
    session.add(run)
    session.flush()
    teams = sorted({rule.team_id for rule in metadata.values()})
    for number in range(8, 13):
        gameweek = GameweekModel(
            number=number,
            name=f"Gameweek {number}",
            deadline=dt.datetime(2026, 10, 20, 17, 30, tzinfo=dt.UTC) + dt.timedelta(days=number),
            is_current=False,
            is_next=number == 8,
            is_finished=False,
        )
        session.add(gameweek)
        session.flush()
        fixture = FixtureModel(
            external_fpl_id=9000 + number,
            gameweek_id=gameweek.id,
            home_team_id=teams[0],
            away_team_id=teams[1],
            kickoff_time=dt.datetime(2026, 10, 25, 15, 0, tzinfo=dt.UTC)
            + dt.timedelta(days=number),
            finished=False,
        )
        session.add(fixture)
        session.flush()
        for player_id in metadata:
            session.add(
                ProjectionModel(
                    player_id=player_id,
                    fixture_id=fixture.id,
                    gameweek_id=gameweek.id,
                    projected_points=5.0 if player_id == 106 else 2.0,
                    expected_minutes=80.0,
                    generated_at=GENERATED_AT,
                    model_version="component_v3",
                    run_id=run.id,
                )
            )
    session.commit()
    return plan_id


@pytest.fixture
def client(planner_session: Session) -> Iterator[TestClient]:
    engine = planner_session.get_bind()

    def request_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
            assert not (session.new or session.dirty or session.deleted)

    app.dependency_overrides[get_db_session] = request_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_listing_candidates_writes_nothing_and_releases_the_plan_lock(
    client: TestClient,
    planner_session: Session,
    planner_plan: Plan,
    planner_metadata: dict[int, PlayerRuleData],
) -> None:
    plan_id = seed_plan_and_projections(planner_session, planner_plan, planner_metadata)
    before_counts = table_counts(planner_session)
    before_plan = planner_session.execute(
        select(PlanModel.revision, PlanModel.updated_at).where(PlanModel.id == plan_id)
    ).one()

    response = client.get(f"/plans/{plan_id}/gameweeks/8/transfers/6")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["planning_context"] == {
        "plan_id": plan_id,
        "gameweek": 8,
        "revision": before_plan.revision,
    }
    assert body["candidates"]
    top = next(item for item in body["candidates"] if item["player_id"] == 106)
    assert top["state"] == "available"
    assert top["plan_impact_by_horizon"]["3"]["saved_plan"] == pytest.approx(9.0)
    planner_session.expire_all()
    assert table_counts(planner_session) == before_counts
    after_plan = planner_session.execute(
        select(PlanModel.revision, PlanModel.updated_at).where(PlanModel.id == plan_id)
    ).one()
    assert after_plan == before_plan
    with Session(planner_session.get_bind()) as writer:
        locked = writer.scalar(
            select(PlanModel.id).where(PlanModel.id == plan_id).with_for_update(nowait=True)
        )
        assert locked == plan_id
        writer.rollback()


def test_unknown_plan_and_gameweek_are_explicit_on_real_sql(
    client: TestClient,
    planner_session: Session,
    planner_plan: Plan,
    planner_metadata: dict[int, PlayerRuleData],
) -> None:
    plan_id = seed_plan_and_projections(planner_session, planner_plan, planner_metadata)

    assert client.get("/plans/9999/gameweeks/8/transfers/6").json()["detail"]["code"] == (
        "plan_not_found"
    )
    outside = client.get(f"/plans/{plan_id}/gameweeks/20/transfers/6")
    assert outside.status_code == 422 and outside.json()["detail"]["code"] == "gameweek_not_in_plan"


def test_previewing_writes_nothing_and_confirming_goes_through_the_planner_writer(
    client: TestClient,
    planner_session: Session,
    planner_plan: Plan,
    planner_metadata: dict[int, PlayerRuleData],
) -> None:
    plan_id = seed_plan_and_projections(planner_session, planner_plan, planner_metadata)
    before_counts = table_counts(planner_session)

    preview = client.get(f"/plans/{plan_id}/gameweeks/8/transfers/6/preview?player_in_id=106")

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["confirmable"] is True
    planner_session.expire_all()
    assert table_counts(planner_session) == before_counts

    commit = body["commit"]
    envelope = {
        "mutation_id": "00000000-0000-0000-0000-00000000a001",
        "expected_revision": commit["expected_revision"],
        "intents": [{**commit["intent"], **commit["guard"]}],
    }
    confirmed = client.post(f"/plans/{plan_id}/mutations", json=envelope)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "committed"

    plan = client.get(f"/plans/{plan_id}").json()
    assert plan["revision"] == commit["expected_revision"] + 1
    for week in plan["gameweeks"]:
        players = {player["player_id"] for player in week["players"]}
        assert 106 in players and 6 not in players, week["gameweek_number"]
    planner_session.expire_all()
    after_counts = table_counts(planner_session)
    unrelated = {name for name in after_counts if not name.startswith("plan")}
    assert {name: after_counts[name] for name in unrelated} == {
        name: before_counts[name] for name in unrelated
    }

    receipts_before = after_counts["plan_mutations"]
    stale = client.post(
        f"/plans/{plan_id}/mutations",
        json={**envelope, "mutation_id": "00000000-0000-0000-0000-00000000a002"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"
    planner_session.expire_all()
    assert table_counts(planner_session)["plan_mutations"] == receipts_before
