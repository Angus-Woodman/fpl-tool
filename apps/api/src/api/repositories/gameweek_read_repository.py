from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import GameweekModel


@dataclass(frozen=True)
class GameweekReadItem:
    id: int
    number: int
    name: str
    is_current: bool
    is_next: bool
    is_finished: bool


class GameweekReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_gameweeks(self) -> list[GameweekReadItem]:
        stmt = select(
            GameweekModel.id,
            GameweekModel.number,
            GameweekModel.name,
            GameweekModel.is_current,
            GameweekModel.is_next,
            GameweekModel.is_finished,
        ).order_by(GameweekModel.number.asc())
        rows = self._session.execute(stmt).all()

        return [
            GameweekReadItem(
                id=row[0],
                number=row[1],
                name=row[2],
                is_current=row[3],
                is_next=row[4],
                is_finished=row[5],
            )
            for row in rows
        ]
