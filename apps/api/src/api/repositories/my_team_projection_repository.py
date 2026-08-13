from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from api.models import FixtureModel, GameweekModel, PlayerModel, ProjectionModel, TeamModel


@dataclass(frozen=True)
class PlayerProjectionFixtureRecord:
    player_id: int
    fixture_id: int | None
    gameweek_number: int
    projected_points: float
    kickoff_time: str
    opponent_team_short_name: str | None
    is_home: bool | None


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

        home_team = aliased(TeamModel)
        away_team = aliased(TeamModel)

        rows = self._session.execute(
            select(
                ProjectionModel.player_id,
                ProjectionModel.fixture_id,
                GameweekModel.number,
                ProjectionModel.projected_points,
                FixtureModel.kickoff_time,
                PlayerModel.team_id,
                FixtureModel.home_team_id,
                FixtureModel.away_team_id,
                home_team.short_name,
                away_team.short_name,
            )
            .join(PlayerModel, PlayerModel.id == ProjectionModel.player_id)
            .join(GameweekModel, GameweekModel.id == ProjectionModel.gameweek_id)
            .outerjoin(FixtureModel, FixtureModel.id == ProjectionModel.fixture_id)
            .outerjoin(home_team, home_team.id == FixtureModel.home_team_id)
            .outerjoin(away_team, away_team.id == FixtureModel.away_team_id)
            .where(ProjectionModel.player_id.in_(player_ids))
            .where(ProjectionModel.generated_at == latest_generated_at)
            .order_by(
                ProjectionModel.player_id.asc(),
                GameweekModel.number.asc(),
                FixtureModel.kickoff_time.asc().nulls_last(),
            )
        ).all()

        return [
            PlayerProjectionFixtureRecord(
                player_id=row[0],
                fixture_id=row[1],
                gameweek_number=row[2],
                projected_points=float(row[3]),
                kickoff_time=row[4].isoformat() if row[4] is not None else "",
                opponent_team_short_name=(
                    row[9] if row[6] == row[5] else row[8] if row[7] == row[5] else None
                ),
                is_home=(True if row[6] == row[5] else False if row[7] == row[5] else None),
            )
            for row in rows
        ]
