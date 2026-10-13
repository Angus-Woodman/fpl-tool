from __future__ import annotations

from api.models import PlayerModel, TeamModel
from api.models.entities import PlayerPosition
from api.repositories.player_read_repository import PlayerReadRepository
from conftest import requires_database
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = requires_database


def _seed(session: Session) -> None:
    session.execute(text("TRUNCATE TABLE players, teams RESTART IDENTITY CASCADE"))
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    session.add(team)
    session.flush()

    def player(
        external_id: int,
        status: str,
        position: PlayerPosition = PlayerPosition.MIDFIELDER,
        *,
        can_select: bool | None = True,
        can_transact: bool | None = True,
    ) -> PlayerModel:
        return PlayerModel(
            external_fpl_id=external_id,
            first_name="First",
            second_name="Second",
            web_name=f"{status}-{external_id}",
            team_id=team.id,
            position=position,
            current_price=6.0,
            status=status,
            can_select=can_select,
            can_transact=can_transact,
        )

    session.add_all(
        [
            player(1, "a"),
            player(2, "i"),
            player(3, "d"),
            player(4, "s"),
            player(5, "u", can_select=False),
            player(6, "n", can_select=None, can_transact=None),
            player(7, "a", can_select=False, can_transact=False),
            player(8, "a", PlayerPosition.FORWARD),
        ]
    )
    session.commit()


def test_list_by_position_returns_every_same_position_player_regardless_of_status(
    db_session: Session,
) -> None:
    _seed(db_session)

    records = PlayerReadRepository(db_session).list_by_position("MID")

    assert {record.status for record in records} == {"a", "i", "d", "s", "u", "n"}
    assert len(records) == 7


def test_list_by_position_includes_otherwise_eligible_non_available_players(
    db_session: Session,
) -> None:
    _seed(db_session)

    records = PlayerReadRepository(db_session).list_by_position("MID")

    by_status = {
        record.status: record for record in records if record.can_select and record.can_transact
    }
    assert {"i", "d", "s"} <= set(by_status)


def test_list_by_position_excludes_other_positions_and_keeps_flags_for_the_domain_helper(
    db_session: Session,
) -> None:
    _seed(db_session)

    records = PlayerReadRepository(db_session).list_by_position("MID")

    assert all(record.position == "MID" for record in records)
    flags = {record.web_name: (record.can_select, record.can_transact) for record in records}
    # Non-selectable and unknown players are still returned: eligibility is decided only by
    # the domain helper, not by SQL.
    assert flags["u-5"] == (False, True)
    assert flags["n-6"] == (None, None)
    assert flags["a-7"] == (False, False)
