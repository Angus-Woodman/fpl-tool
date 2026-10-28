from __future__ import annotations

from api.models import PlayerModel, TeamModel
from api.repositories.squad_player_lookup_repository import (
    SquadPlayerLookupItem,
    SquadPlayerLookupRepository,
)
from conftest import requires_database
from sqlalchemy.orm import Session

pytestmark = requires_database


def _seed(session: Session) -> None:
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    session.add(team)
    session.flush()
    flags = {1: (True, True), 2: (False, True), 3: (True, False), 4: (None, None)}
    for number, (can_select, can_transact) in flags.items():
        session.add(
            PlayerModel(
                external_fpl_id=100 + number,
                first_name="Player",
                second_name=str(number),
                web_name=f"P{number}",
                team_id=team.id,
                position="MID",
                current_price=5.5,
                status="a",
                can_select=can_select,
                can_transact=can_transact,
            )
        )
    session.flush()


def test_lookup_returns_the_selectability_flags_and_none_when_unknown(
    planner_session: Session,
) -> None:
    _seed(planner_session)
    repository = SquadPlayerLookupRepository(planner_session)

    items = {item.web_name: item for item in repository.get_by_ids(list(range(1, 5)))}

    assert (items["P1"].can_select, items["P1"].can_transact) == (True, True)
    assert (items["P2"].can_select, items["P2"].can_transact) == (False, True)
    assert (items["P3"].can_select, items["P3"].can_transact) == (True, False)
    assert (items["P4"].can_select, items["P4"].can_transact) == (None, None)


def test_existing_lookup_fields_are_unchanged(planner_session: Session) -> None:
    _seed(planner_session)
    item = SquadPlayerLookupRepository(planner_session).get_by_ids([1])[0]

    assert (item.player_id, item.web_name, item.position, item.current_price) == (
        1,
        "P1",
        "MID",
        5.5,
    )
    assert item.team_id >= 1


def test_items_built_without_the_flags_default_to_unknown() -> None:
    item = SquadPlayerLookupItem(
        player_id=1, team_id=1, web_name="X", position="MID", current_price=5.0
    )

    assert item.can_select is None and item.can_transact is None
