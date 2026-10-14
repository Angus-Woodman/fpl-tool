from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import requires_database
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = requires_database


def migration_module():
    path = Path(__file__).parents[2] / "alembic/versions/c6f91a2d83b0_add_planner_foundations.py"
    spec = importlib.util.spec_from_file_location("planner_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backfill", [False, True])
def test_isolated_upgrade_downgrade_reupgrade_preserves_legacy_values(
    planner_session: Session,
    planner_plan,
    planner_metadata,
    backfill,
) -> None:
    engine = planner_session.get_bind()
    schema = engine.get_execution_options()["schema_translate_map"][None]
    migration = migration_module()
    with engine.begin() as connection:
        connection.execute(select(func.set_config("search_path", schema, True)))
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            connection.execute(
                text(
                    "INSERT INTO plans (id, name, start_gameweek, end_gameweek, initial_bank, "
                    "initial_free_transfers, created_at, updated_at) "
                    "VALUES (1, 'Original', 8, 9, 0.7, 4, now(), now())"
                )
            )
            before = connection.execute(text("SELECT * FROM plans WHERE id=1")).mappings().one()
            migration.upgrade()
            assert (
                connection.execute(
                    text("SELECT foundation_state FROM plans WHERE id=1")
                ).scalar_one()
                == "legacy_pending"
            )
            if backfill:
                from api.models.entities import PlanModel
                from api.repositories.plan_repository import PlanPlayerSave, PlanRepository
                from api.repositories.squad_player_lookup_repository import (
                    SquadPlayerLookupRepository,
                )
                from api.services.initialize_planner_foundations import (
                    InitializePlannerFoundationsService,
                )
                from conftest import seed_planner_players

                with Session(connection, join_transaction_mode="create_savepoint") as session:
                    seed_planner_players(session, planner_metadata)
                    repository = PlanRepository(session)
                    for number in (8, 9):
                        repository.save_gameweek(
                            1,
                            number,
                            chip="BENCH_BOOST" if number == 8 else None,
                            bank=0.7,
                            free_transfers_available=4,
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
                                    planner_plan.boundary.players,
                                    planner_plan.boundary.lineup,
                                    strict=True,
                                )
                            ],
                        )
                    session.commit()
                    before = (
                        connection.execute(
                            select(*(PlanModel.__table__.c[name] for name in before.keys())).where(
                                PlanModel.id == 1
                            )
                        )
                        .mappings()
                        .one()
                    )
                    legacy = repository.get(1)
                    service = InitializePlannerFoundationsService(
                        session, SquadPlayerLookupRepository(session)
                    )
                    assert service.execute(1, apply=True).status == "initialized"
                    assert repository.get(1) == legacy
                    assert repository.load_canonical(1).gameweeks[0].chip.value == "BENCH_BOOST"
            migration.downgrade()
            after = connection.execute(text("SELECT * FROM plans WHERE id=1")).mappings().one()
            assert dict(after) == dict(before)
            migration.upgrade()
            assert (
                connection.execute(text("SELECT revision FROM plans WHERE id=1")).scalar_one() == 0
            )


@pytest.mark.parametrize("new_write", ["revision", "new_plan"])
def test_downgrade_refuses_loss_of_new_only_data(planner_session: Session, new_write: str) -> None:
    engine = planner_session.get_bind()
    schema = engine.get_execution_options()["schema_translate_map"][None]
    with engine.begin() as connection:
        connection.execute(select(func.set_config("search_path", schema, True)))
        connection.execute(
            text(
                "INSERT INTO plans (id, name, start_gameweek, end_gameweek, initial_bank, "
                "initial_free_transfers, created_at, updated_at, revision, "
                "foundation_state, boundary_origin) "
                "VALUES (1, 'New', 8, 9, 0, 1, now(), now(), :revision, 'ready', :origin)"
            ),
            {
                "revision": 1 if new_write == "revision" else 0,
                "origin": "legacy_first_gameweek_assumed"
                if new_write == "revision"
                else "my_team_capture",
            },
        )
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="Back up/export"):
                migration_module().downgrade()
        assert connection.execute(text("SELECT name FROM plans WHERE id=1")).scalar_one() == "New"
