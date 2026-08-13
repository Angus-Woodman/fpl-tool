from __future__ import annotations

import datetime as dt

from api.models import GameweekModel, PlayerModel, PlayerSnapshotModel, TeamModel
from api.models.entities import PlayerPosition
from api.repositories.projection_generation_repository import ProjectionGenerationRepository
from conftest import requires_database
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = requires_database

GENERATION_ONE = dt.datetime(2026, 8, 10, 9, 0, tzinfo=dt.UTC)
GENERATION_TWO = dt.datetime(2026, 8, 12, 9, 0, tzinfo=dt.UTC)


def _seed(session: Session) -> tuple[int, int]:
    session.execute(
        text(
            "TRUNCATE TABLE player_snapshots, players, gameweeks, teams " "RESTART IDENTITY CASCADE"
        )
    )
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    gameweek = GameweekModel(
        number=1,
        name="Gameweek 1",
        deadline=dt.datetime(2026, 8, 21, 17, 30, tzinfo=dt.UTC),
        is_current=False,
        is_next=True,
        is_finished=False,
    )
    session.add_all([team, gameweek])
    session.flush()

    saka = PlayerModel(
        external_fpl_id=101,
        first_name="Bukayo",
        second_name="Saka",
        web_name="Saka",
        team_id=team.id,
        position=PlayerPosition.MIDFIELDER,
        current_price=10.5,
        status="a",
    )
    watkins = PlayerModel(
        external_fpl_id=102,
        first_name="Ollie",
        second_name="Watkins",
        web_name="Watkins",
        team_id=team.id,
        position=PlayerPosition.FORWARD,
        current_price=9.0,
        status="a",
    )
    session.add_all([saka, watkins])
    session.flush()
    return saka.id, watkins.id


def _snapshot(player_id: int, captured_at: dt.datetime, *, price: float) -> PlayerSnapshotModel:
    return PlayerSnapshotModel(
        player_id=player_id,
        captured_at=captured_at,
        price=price,
        ownership_percent=10.0,
        transfers_in=0,
        transfers_out=0,
        status="a",
    )


def test_get_latest_snapshot_generation_returns_the_newest_captured_at(
    db_session: Session,
) -> None:
    saka_id, watkins_id = _seed(db_session)
    db_session.add_all(
        [
            _snapshot(saka_id, GENERATION_ONE, price=10.0),
            _snapshot(saka_id, GENERATION_TWO, price=10.5),
            _snapshot(watkins_id, GENERATION_TWO, price=9.0),
        ]
    )
    db_session.commit()
    repository = ProjectionGenerationRepository(db_session)

    assert repository.get_latest_snapshot_generation() == GENERATION_TWO


def test_get_latest_snapshot_generation_returns_none_when_empty(db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    repository = ProjectionGenerationRepository(db_session)

    assert repository.get_latest_snapshot_generation() is None


def test_list_snapshots_for_generation_excludes_players_from_other_generations(
    db_session: Session,
) -> None:
    """The invariant: a run must consume one internally consistent generation, not
    each player's own independently-latest row (which could silently mix an old
    and a new import if only some players were re-captured)."""
    saka_id, watkins_id = _seed(db_session)
    db_session.add_all(
        [
            # Saka has an OLDER row only in generation one, then a NEWER one in
            # generation two. Watkins only has the older generation-one row.
            _snapshot(saka_id, GENERATION_ONE, price=10.0),
            _snapshot(saka_id, GENERATION_TWO, price=10.5),
            _snapshot(watkins_id, GENERATION_ONE, price=9.0),
        ]
    )
    db_session.commit()
    repository = ProjectionGenerationRepository(db_session)

    snapshots = repository.list_snapshots_for_generation({saka_id, watkins_id}, GENERATION_TWO)

    # Watkins has no row in this generation, so he is correctly absent rather
    # than silently falling back to his generation-one snapshot.
    assert {snapshot.player_id for snapshot in snapshots} == {saka_id}
    assert snapshots[0].captured_at == GENERATION_TWO
    assert snapshots[0].price == 10.5


def test_list_snapshots_for_generation_returns_empty_for_no_players(db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    repository = ProjectionGenerationRepository(db_session)

    assert repository.list_snapshots_for_generation(set(), GENERATION_ONE) == []
