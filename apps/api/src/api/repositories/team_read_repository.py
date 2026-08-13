from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.models import TeamModel

EFFECTIVE_DIFFICULTY = func.coalesce(TeamModel.difficulty_override, TeamModel.source_difficulty)


@dataclass(frozen=True)
class TeamReadItem:
    id: int
    name: str
    short_name: str
    difficulty: int
    source_difficulty: int
    difficulty_override: int | None


class TeamReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_teams(self) -> list[TeamReadItem]:
        stmt = select(
            TeamModel.id,
            TeamModel.name,
            TeamModel.short_name,
            EFFECTIVE_DIFFICULTY,
            TeamModel.source_difficulty,
            TeamModel.difficulty_override,
        ).order_by(TeamModel.name.asc())
        rows = self._session.execute(stmt).all()

        return [
            TeamReadItem(
                id=row[0],
                name=row[1],
                short_name=row[2],
                difficulty=row[3],
                source_difficulty=row[4],
                difficulty_override=row[5],
            )
            for row in rows
        ]
