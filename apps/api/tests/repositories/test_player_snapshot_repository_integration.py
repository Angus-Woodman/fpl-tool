from __future__ import annotations

import datetime as dt

from api.models import PlayerModel, PlayerSnapshotModel, TeamModel
from api.models.entities import PlayerPosition
from api.repositories.player_snapshot_repository import PlayerSnapshotRepository
from conftest import requires_database
from fpl_engine.domain import PlayerSnapshot
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = requires_database

CAPTURED_AT = dt.datetime(2026, 8, 13, 12, 0, tzinfo=dt.UTC)


def _seed_player(session: Session) -> int:
    session.execute(
        text("TRUNCATE TABLE player_snapshots, players, teams RESTART IDENTITY CASCADE")
    )
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    session.add(team)
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
    return player.id


def _snapshot(player_id: int, *, price: float, status: str = "a") -> PlayerSnapshot:
    return PlayerSnapshot(
        player_id=player_id,
        captured_at=CAPTURED_AT,
        gameweek_id=None,
        price=price,
        ownership_percent=31.4,
        transfers_in=10,
        transfers_out=5,
        status=status,
        chance_of_playing_next_round=None,
        total_minutes=2810,
        total_points=206,
        starts=32,
        points_per_game=5.9,
        form=0.0,
        expected_goals=9.42,
        expected_assists=11.08,
    )


def test_snapshot_is_persisted_with_reported_totals(db_session: Session) -> None:
    player_id = _seed_player(db_session)
    repository = PlayerSnapshotRepository(db_session)

    repository.upsert_many([_snapshot(player_id, price=10.5)])
    db_session.commit()

    row = db_session.execute(select(PlayerSnapshotModel)).scalar_one()
    assert row.price == 10.5
    assert row.total_minutes == 2810
    assert row.total_points == 206
    assert row.expected_goals == 9.42


def test_repeating_a_capture_updates_rather_than_duplicates(db_session: Session) -> None:
    player_id = _seed_player(db_session)
    repository = PlayerSnapshotRepository(db_session)

    repository.upsert_many([_snapshot(player_id, price=10.5)])
    db_session.commit()

    repository.upsert_many([_snapshot(player_id, price=10.6, status="d")])
    db_session.commit()

    count = db_session.execute(select(func.count()).select_from(PlayerSnapshotModel)).scalar_one()
    row = db_session.execute(select(PlayerSnapshotModel)).scalar_one()
    assert count == 1
    assert row.price == 10.6
    assert row.status == "d"


def test_distinct_captures_are_retained_as_a_time_series(db_session: Session) -> None:
    player_id = _seed_player(db_session)
    repository = PlayerSnapshotRepository(db_session)

    repository.upsert_many([_snapshot(player_id, price=10.5)])
    later = PlayerSnapshot(
        **{
            **_snapshot(player_id, price=10.6).__dict__,
            "captured_at": CAPTURED_AT + dt.timedelta(days=1),
        }
    )
    repository.upsert_many([later])
    db_session.commit()

    prices = db_session.execute(
        select(PlayerSnapshotModel.price).order_by(PlayerSnapshotModel.captured_at.asc())
    ).scalars()
    assert list(prices) == [10.5, 10.6]
