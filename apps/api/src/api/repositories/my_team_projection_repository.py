from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.models import GameweekModel, ProjectionModel


@dataclass(frozen=True)
class PlayerProjectionFixtureRecord:
    player_id: int
    gameweek_number: int
    projected_points: float


class MyTeamProjectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]:
        if not player_ids:
            return []

        latest_generated_at = self._session.execute(
            select(func.max(ProjectionModel.generated_at)).where(
                ProjectionModel.player_id.in_(player_ids)
            )
        ).scalar_one()

        if latest_generated_at is None:
            return []

        rows = self._session.execute(
            select(
                ProjectionModel.player_id,
                GameweekModel.number,
                ProjectionModel.projected_points,
            )
            .join(GameweekModel, GameweekModel.id == ProjectionModel.gameweek_id)
            .where(ProjectionModel.player_id.in_(player_ids))
            .where(ProjectionModel.generated_at == latest_generated_at)
            .order_by(ProjectionModel.player_id.asc(), GameweekModel.number.asc())
        ).all()

        return [
            PlayerProjectionFixtureRecord(
                player_id=row[0],
                gameweek_number=row[1],
                projected_points=float(row[2]),
            )
            for row in rows
        ]
