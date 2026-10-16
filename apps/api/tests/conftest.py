from __future__ import annotations

import os
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from api.core.settings import get_settings
from api.db.base import Base
from api.db.guards import ensure_test_database_url
from api.models.entities import PlayerModel, TeamModel
from api.models.entities import PlayerPosition as StoredPosition
from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.models import (
    Boundary,
    GameweekDecision,
    LineupRole,
    Ownership,
    Plan,
    PlayerRuleData,
    PurchaseProvenance,
)
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

RUN_DB_TESTS_ENV_VAR = "RUN_DB_TESTS"


@pytest.fixture
def planner_identity() -> type[UUID]:
    return UUID


@pytest.fixture
def planner_quote() -> dict[str, int | str]:
    return {
        "outgoing_market_tenths": 54,
        "incoming_price_tenths": 50,
        "source": "stored_player_observation",
        "observed_at": "2026-10-14T12:00:00+00:00",
        "origin": "captured",
    }


@pytest.fixture
def planner_metadata() -> dict[int, PlayerRuleData]:
    positions = (
        [PlayerPosition.GOALKEEPER]
        + [PlayerPosition.DEFENDER] * 4
        + [PlayerPosition.MIDFIELDER] * 4
        + [PlayerPosition.FORWARD] * 2
        + [
            PlayerPosition.GOALKEEPER,
            PlayerPosition.DEFENDER,
            PlayerPosition.MIDFIELDER,
            PlayerPosition.FORWARD,
        ]
    )
    players = {
        index + 1: PlayerRuleData(index + 1, position, index % 5 + 1)
        for index, position in enumerate(positions)
    }
    return players | {
        number + 100: PlayerRuleData(number + 100, player.position, number + 20)
        for number, player in players.items()
    }


@pytest.fixture
def planner_plan() -> Plan:
    players = tuple(
        Ownership(
            UUID(int=number),
            UUID(int=1000 + number),
            number,
            50,
            PurchaseProvenance("stored_player_observation", 50),
        )
        for number in range(1, 16)
    )
    lineup = tuple(
        LineupRole(
            player.slot_id,
            index < 11,
            None if index < 11 else index - 10,
            index == 1,
            index == 2,
        )
        for index, player in enumerate(players)
    )
    boundary = Boundary(players, lineup, 10, 1)
    return Plan(
        "API plan",
        8,
        10,
        boundary,
        tuple(GameweekDecision(number, lineup) for number in range(8, 11)),
    )


def seed_planner_players(session: Session, metadata: dict[int, PlayerRuleData]) -> None:
    for team_id in sorted({player.team_id for player in metadata.values()}):
        session.add(
            TeamModel(
                id=team_id,
                external_fpl_id=team_id,
                name=f"Team {team_id}",
                short_name=f"T{team_id}",
            )
        )
    session.flush()
    for player in metadata.values():
        session.add(
            PlayerModel(
                id=player.player_id,
                external_fpl_id=player.player_id,
                first_name="Player",
                second_name=str(player.player_id),
                web_name=f"P{player.player_id}",
                team_id=player.team_id,
                position=StoredPosition(player.position.value),
                current_price=5.0,
                status="a",
            )
        )
    session.flush()


@pytest.fixture
def planner_session(test_database_engine: Engine) -> Generator[Session, None, None]:
    schema = f"planner_{uuid4().hex}"
    with test_database_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = test_database_engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        with Session(isolated) as session:
            yield session
            session.rollback()
    finally:
        with test_database_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))


def integration_tests_enabled() -> bool:
    return os.getenv(RUN_DB_TESTS_ENV_VAR) == "1"


requires_database = pytest.mark.skipif(
    not integration_tests_enabled(),
    reason=f"Set {RUN_DB_TESTS_ENV_VAR}=1 to run PostgreSQL integration tests.",
)


@pytest.fixture(scope="session")
def test_database_engine() -> Generator[Engine, None, None]:
    """Engine bound to the dedicated test database.

    The guard raises rather than skips, so a misconfigured run fails loudly
    instead of silently truncating development data.
    """
    settings = get_settings()
    url = ensure_test_database_url(
        settings.test_database_url, development_url=settings.database_url
    )

    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(test_database_engine: Engine) -> Generator[Session, None, None]:
    session_factory = sessionmaker(
        bind=test_database_engine, autocommit=False, autoflush=False, class_=Session
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
