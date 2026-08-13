from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import PlayerModel, TeamModel


@dataclass(frozen=True)
class SquadPlayerLookupItem:
    player_id: int
    team_id: int
    web_name: str
    position: str
    current_price: float


class SquadPlayerLookupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]:
        if not player_ids:
            return []

        rows = self._session.execute(
            select(
                PlayerModel.id,
                PlayerModel.team_id,
                PlayerModel.web_name,
                PlayerModel.position,
                PlayerModel.current_price,
            )
            .join(TeamModel, TeamModel.id == PlayerModel.team_id)
            .where(PlayerModel.id.in_(player_ids))
        ).all()

        return [
            SquadPlayerLookupItem(
                player_id=row[0],
                team_id=row[1],
                web_name=row[2],
                position=row[3].value if hasattr(row[3], "value") else str(row[3]),
                current_price=float(row[4]),
            )
            for row in rows
        ]
