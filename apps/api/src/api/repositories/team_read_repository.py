from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import TeamModel


@dataclass(frozen=True)
class TeamReadItem:
    id: int
    name: str
    short_name: str


class TeamReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_teams(self) -> list[TeamReadItem]:
        stmt = select(TeamModel.id, TeamModel.name, TeamModel.short_name).order_by(
            TeamModel.name.asc()
        )
        rows = self._session.execute(stmt).all()

        return [
            TeamReadItem(
                id=row[0],
                name=row[1],
                short_name=row[2],
            )
            for row in rows
        ]
