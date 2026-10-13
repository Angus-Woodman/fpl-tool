from __future__ import annotations

from api.models import PlayerModel, TeamModel
from api.repositories.player_repository import PlayerRepository
from conftest import requires_database
from fpl_engine.domain import Player, PlayerPosition
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = requires_database


def _seed_team(session: Session) -> int:
    session.execute(text("TRUNCATE TABLE players, teams RESTART IDENTITY CASCADE"))
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    session.add(team)
    session.flush()
    return team.id


def _player(
    team_id: int,
    external_id: int,
    *,
    status: str = "a",
    can_select: bool | None = None,
    can_transact: bool | None = None,
) -> Player:
    return Player(
        id=0,
        external_fpl_id=external_id,
        first_name="First",
        second_name="Second",
        web_name=f"Player{external_id}",
        team_id=team_id,
        position=PlayerPosition.MIDFIELDER,
        current_price=6.5,
        status=status,
        can_select=can_select,
        can_transact=can_transact,
    )


def _flags(session: Session) -> dict[int, tuple[bool | None, bool | None]]:
    rows = session.execute(
        select(PlayerModel.external_fpl_id, PlayerModel.can_select, PlayerModel.can_transact)
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def test_upsert_persists_true_false_and_unknown_flags(db_session: Session) -> None:
    team_id = _seed_team(db_session)
    repository = PlayerRepository(db_session)

    repository.upsert_many(
        [
            _player(team_id, 1, can_select=True, can_transact=True),
            _player(team_id, 2, can_select=False, can_transact=True),
            _player(team_id, 3, can_select=None, can_transact=None),
        ]
    )
    db_session.commit()

    assert _flags(db_session) == {1: (True, True), 2: (False, True), 3: (None, None)}


def test_reimport_with_absent_flags_clears_previously_stored_values(db_session: Session) -> None:
    team_id = _seed_team(db_session)
    repository = PlayerRepository(db_session)
    repository.upsert_many([_player(team_id, 1, can_select=True, can_transact=False)])
    db_session.commit()

    repository.upsert_many([_player(team_id, 1, can_select=None, can_transact=None)])
    db_session.commit()

    assert _flags(db_session) == {1: (None, None)}


def test_reimport_overwrites_flags_with_the_latest_values(db_session: Session) -> None:
    team_id = _seed_team(db_session)
    repository = PlayerRepository(db_session)
    repository.upsert_many([_player(team_id, 1, can_select=True, can_transact=True)])
    db_session.commit()

    repository.upsert_many([_player(team_id, 1, can_select=False, can_transact=True)])
    db_session.commit()

    assert _flags(db_session) == {1: (False, True)}


def test_flags_are_persisted_independently_of_status(db_session: Session) -> None:
    team_id = _seed_team(db_session)
    repository = PlayerRepository(db_session)

    repository.upsert_many(
        [
            _player(team_id, 1, status="a", can_select=False, can_transact=False),
            _player(team_id, 2, status="i", can_select=True, can_transact=True),
            _player(team_id, 3, status="u", can_select=False, can_transact=True),
        ]
    )
    db_session.commit()

    statuses = dict(
        db_session.execute(select(PlayerModel.external_fpl_id, PlayerModel.status)).all()
    )
    assert statuses == {1: "a", 2: "i", 3: "u"}
    assert _flags(db_session) == {1: (False, False), 2: (True, True), 3: (False, True)}
