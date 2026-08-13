from __future__ import annotations

from fpl_engine.domain import Gameweek
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import GameweekModel


class GameweekRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, gameweeks: list[Gameweek]) -> None:
        if not gameweeks:
            return

        values = [
            {
                "number": gw.number,
                "name": gw.name,
                "deadline": gw.deadline,
                "is_current": gw.is_current,
                "is_next": gw.is_next,
                "is_finished": gw.is_finished,
            }
            for gw in gameweeks
        ]

        statement = insert(GameweekModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[GameweekModel.number],
            set_={
                "name": statement.excluded.name,
                "deadline": statement.excluded.deadline,
                "is_current": statement.excluded.is_current,
                "is_next": statement.excluded.is_next,
                "is_finished": statement.excluded.is_finished,
            },
        )
        self._session.execute(statement)

    def get_internal_ids_by_numbers(self, numbers: set[int]) -> dict[int, int]:
        if not numbers:
            return {}

        statement = select(GameweekModel.number, GameweekModel.id).where(
            GameweekModel.number.in_(numbers)
        )
        rows = self._session.execute(statement).all()
        return {number: internal_id for number, internal_id in rows}

    def list_finished(self) -> list[Gameweek]:
        rows = self._session.execute(
            select(GameweekModel)
            .where(GameweekModel.is_finished.is_(True))
            .order_by(GameweekModel.number.asc())
        ).scalars()

        return [
            Gameweek(
                id=row.id,
                number=row.number,
                name=row.name,
                deadline=row.deadline,
                is_current=row.is_current,
                is_next=row.is_next,
                is_finished=row.is_finished,
            )
            for row in rows
        ]
