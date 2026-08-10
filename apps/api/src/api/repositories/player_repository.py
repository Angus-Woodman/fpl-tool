from __future__ import annotations

from fpl_engine.domain import Player
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import PlayerModel
from api.models.entities import PlayerPosition as DbPlayerPosition


class PlayerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, players: list[Player]) -> None:
        if not players:
            return

        values = [
            {
                "external_fpl_id": player.external_fpl_id,
                "first_name": player.first_name,
                "second_name": player.second_name,
                "web_name": player.web_name,
                "team_id": player.team_id,
                "position": DbPlayerPosition(player.position.value),
                "current_price": player.current_price,
                "status": player.status,
            }
            for player in players
        ]

        statement = insert(PlayerModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[PlayerModel.external_fpl_id],
            set_={
                "first_name": statement.excluded.first_name,
                "second_name": statement.excluded.second_name,
                "web_name": statement.excluded.web_name,
                "team_id": statement.excluded.team_id,
                "position": statement.excluded.position,
                "current_price": statement.excluded.current_price,
                "status": statement.excluded.status,
            },
        )
        self._session.execute(statement)
