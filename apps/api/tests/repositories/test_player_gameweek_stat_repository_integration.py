from __future__ import annotations

import datetime as dt

from api.models import GameweekModel, PlayerGameweekStatModel, PlayerModel, TeamModel
from api.models.entities import PlayerPosition
from api.repositories.player_gameweek_stat_repository import PlayerGameweekStatRepository
from conftest import requires_database
from fpl_engine.domain import PlayerGameweekStat
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = requires_database


def _seed(session: Session) -> tuple[int, int]:
    session.execute(
        text(
            "TRUNCATE TABLE player_gameweek_stats, players, gameweeks, teams "
            "RESTART IDENTITY CASCADE"
        )
    )
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    gameweek = GameweekModel(
        number=1,
        name="Gameweek 1",
        deadline=dt.datetime(2026, 8, 21, 17, 30, tzinfo=dt.UTC),
        is_current=False,
        is_next=True,
        is_finished=True,
    )
    session.add_all([team, gameweek])
    session.flush()

    player = PlayerModel(
        external_fpl_id=101,
        first_name="Bukayo",
        second_name="Saka",
        web_name="Saka",
        team_id=team.id,
        position=PlayerPosition.MIDFIELDER,
        current_price=10.5,
        status="a",
    )
    session.add(player)
    session.flush()
    return player.id, gameweek.id


def _stat(player_id: int, gameweek_id: int, *, minutes: int, points: int) -> PlayerGameweekStat:
    return PlayerGameweekStat(
        player_id=player_id,
        gameweek_id=gameweek_id,
        minutes=minutes,
        total_points=points,
        goals_scored=1,
        assists=0,
        clean_sheets=0,
        goals_conceded=1,
        bonus=2,
        bps=34,
    )


def test_stat_is_persisted_without_a_fixture(db_session: Session) -> None:
    player_id, gameweek_id = _seed(db_session)
    repository = PlayerGameweekStatRepository(db_session)

    repository.upsert_many([_stat(player_id, gameweek_id, minutes=90, points=8)])
    db_session.commit()

    row = db_session.execute(select(PlayerGameweekStatModel)).scalar_one()
    assert row.fixture_id is None
    assert row.minutes == 90
    assert row.total_points == 8


def test_reimporting_a_gameweek_updates_rather_than_duplicates(db_session: Session) -> None:
    player_id, gameweek_id = _seed(db_session)
    repository = PlayerGameweekStatRepository(db_session)

    repository.upsert_many([_stat(player_id, gameweek_id, minutes=90, points=8)])
    db_session.commit()

    repository.upsert_many([_stat(player_id, gameweek_id, minutes=90, points=11)])
    db_session.commit()

    count = db_session.execute(
        select(func.count()).select_from(PlayerGameweekStatModel)
    ).scalar_one()
    row = db_session.execute(select(PlayerGameweekStatModel)).scalar_one()
    assert count == 1
    assert row.total_points == 11
