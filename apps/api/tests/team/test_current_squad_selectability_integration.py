from __future__ import annotations

import pytest
from api.models import SquadPlayerModel, TeamModel
from api.repositories.current_squad_repository import CurrentSquadRepository
from api.repositories.player_repository import PlayerRepository
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.services.current_squad import (
    CurrentSquadPlayerSelection,
    UpsertCurrentSquadRequest,
    UpsertCurrentSquadService,
)
from conftest import requires_database
from fpl_engine.domain import Player, PlayerPosition
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = requires_database

# (external id, team index, position); starters 1-11 are a legal 1-4-4-2, bench 12-15.
_SQUAD_SPECS: list[tuple[int, int, PlayerPosition]] = [
    (1, 1, PlayerPosition.GOALKEEPER),
    (2, 2, PlayerPosition.DEFENDER),
    (3, 1, PlayerPosition.DEFENDER),
    (4, 2, PlayerPosition.DEFENDER),
    (5, 3, PlayerPosition.DEFENDER),
    (6, 4, PlayerPosition.MIDFIELDER),
    (7, 5, PlayerPosition.MIDFIELDER),
    (8, 6, PlayerPosition.MIDFIELDER),
    (9, 7, PlayerPosition.MIDFIELDER),
    (10, 8, PlayerPosition.FORWARD),
    (11, 9, PlayerPosition.FORWARD),
    (12, 10, PlayerPosition.GOALKEEPER),
    (13, 3, PlayerPosition.DEFENDER),
    (14, 4, PlayerPosition.MIDFIELDER),
    (15, 5, PlayerPosition.FORWARD),
]


def _seed_players(
    session: Session, *, can_select: bool | None, can_transact: bool | None
) -> dict[int, int]:
    session.execute(
        text("TRUNCATE TABLE squad_players, squads, players, teams RESTART IDENTITY CASCADE")
    )
    teams = [
        TeamModel(
            external_fpl_id=index,
            name=f"Team {index}",
            short_name=f"T{index:02d}",
            source_difficulty=3,
        )
        for index in range(1, 11)
    ]
    session.add_all(teams)
    session.flush()
    team_ids = {team.external_fpl_id: team.id for team in teams}

    PlayerRepository(session).upsert_many(
        [
            Player(
                id=0,
                external_fpl_id=external_id,
                first_name="First",
                second_name="Second",
                web_name=f"Player{external_id}",
                team_id=team_ids[team_index],
                position=position,
                current_price=5.0,
                status="a",
                can_select=can_select,
                can_transact=can_transact,
            )
            for external_id, team_index, position in _SQUAD_SPECS
        ]
    )
    session.flush()
    return PlayerRepository(session).get_internal_ids_by_external_ids(
        {external_id for external_id, _, _ in _SQUAD_SPECS}
    )


def _request(player_ids: dict[int, int]) -> UpsertCurrentSquadRequest:
    return UpsertCurrentSquadRequest(
        bank=1.5,
        free_transfers=2,
        players=[
            CurrentSquadPlayerSelection(
                player_id=player_ids[external_id],
                is_starting=external_id <= 11,
                bench_order=None if external_id <= 11 else external_id - 11,
                is_captain=external_id == 1,
                is_vice_captain=external_id == 2,
            )
            for external_id, _, _ in _SQUAD_SPECS
        ],
    )


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(False, False), (False, True), (None, None)],
    ids=["not-selectable", "select-false-transact-true", "unknown"],
)
def test_put_my_team_ignores_imported_selectability_flags(
    db_session: Session, can_select: bool | None, can_transact: bool | None
) -> None:
    player_ids = _seed_players(db_session, can_select=can_select, can_transact=can_transact)
    service = UpsertCurrentSquadService(
        CurrentSquadRepository(db_session), SquadPlayerLookupRepository(db_session)
    )

    record = service.execute(_request(player_ids))

    assert len(record.players) == 15
    assert record.bank == 1.5
    persisted = db_session.execute(select(SquadPlayerModel.player_id)).scalars().all()
    assert sorted(persisted) == sorted(player_ids.values())
