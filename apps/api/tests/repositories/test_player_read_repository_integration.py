from __future__ import annotations

from api.models import PlayerModel, TeamModel
from api.models.entities import PlayerPosition
from api.repositories.player_read_repository import PlayerReadRepository
from conftest import requires_database
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = requires_database


def _seed(
    session: Session,
) -> tuple[int, int, int]:
    """Returns the ids of a flagged-false player, a flagged-true player and a never-imported one."""
    session.execute(text("TRUNCATE TABLE players, teams RESTART IDENTITY CASCADE"))
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    session.add(team)
    session.flush()

    def player(external_id: int, **flags: bool | None) -> PlayerModel:
        return PlayerModel(
            external_fpl_id=external_id,
            first_name="First",
            second_name="Second",
            web_name=f"Player{external_id}",
            team_id=team.id,
            position=PlayerPosition.MIDFIELDER,
            current_price=6.5,
            status="a",
            **flags,
        )

    not_selectable = player(1, can_select=False, can_transact=True)
    selectable = player(2, can_select=True, can_transact=True)
    # No flags set: models a row that predates the selectability migration/refresh.
    never_imported = player(3)
    session.add_all([not_selectable, selectable, never_imported])
    session.commit()
    return not_selectable.id, selectable.id, never_imported.id


def test_get_by_id_returns_the_selectability_flags(db_session: Session) -> None:
    not_selectable_id, selectable_id, never_imported_id = _seed(db_session)
    repository = PlayerReadRepository(db_session)

    not_selectable = repository.get_by_id(not_selectable_id)
    selectable = repository.get_by_id(selectable_id)
    never_imported = repository.get_by_id(never_imported_id)

    assert not_selectable is not None
    assert (not_selectable.can_select, not_selectable.can_transact) == (False, True)
    assert selectable is not None
    assert (selectable.can_select, selectable.can_transact) == (True, True)
    assert never_imported is not None
    assert (never_imported.can_select, never_imported.can_transact) == (None, None)


def test_list_by_position_returns_the_selectability_flags(db_session: Session) -> None:
    _seed(db_session)
    repository = PlayerReadRepository(db_session)

    records = repository.list_by_position("MID")

    flags = {record.web_name: (record.can_select, record.can_transact) for record in records}
    assert flags == {
        "Player1": (False, True),
        "Player2": (True, True),
        "Player3": (None, None),
    }
