from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from api.models import FixtureModel, GameweekModel, TeamModel


@dataclass(frozen=True)
class FixtureTickerItem:
    fixture_id: int
    gameweek_number: int | None
    kickoff_time: str
    home_team_short_name: str
    away_team_short_name: str
    finished: bool


@dataclass(frozen=True)
class FixtureTickerResult:
    items: list[FixtureTickerItem]
    total: int
    page: int
    page_size: int


class FixtureReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_upcoming(
        self,
        *,
        page: int,
        page_size: int,
        team_id: int | None,
        gameweek: int | None,
    ) -> FixtureTickerResult:
        home_team = aliased(TeamModel)
        away_team = aliased(TeamModel)

        stmt = (
            select(
                FixtureModel.id,
                GameweekModel.number,
                FixtureModel.kickoff_time,
                home_team.short_name,
                away_team.short_name,
                FixtureModel.finished,
            )
            .join(home_team, home_team.id == FixtureModel.home_team_id)
            .join(away_team, away_team.id == FixtureModel.away_team_id)
            .outerjoin(GameweekModel, GameweekModel.id == FixtureModel.gameweek_id)
            .where(FixtureModel.finished.is_(False))
        )

        count_stmt = (
            select(func.count())
            .select_from(FixtureModel)
            .outerjoin(GameweekModel, GameweekModel.id == FixtureModel.gameweek_id)
            .where(FixtureModel.finished.is_(False))
        )

        if team_id is not None:
            stmt = stmt.where(
                or_(
                    FixtureModel.home_team_id == team_id,
                    FixtureModel.away_team_id == team_id,
                )
            )
            count_stmt = count_stmt.where(
                or_(
                    FixtureModel.home_team_id == team_id,
                    FixtureModel.away_team_id == team_id,
                )
            )

        if gameweek is not None:
            stmt = stmt.where(GameweekModel.number == gameweek)
            count_stmt = count_stmt.where(GameweekModel.number == gameweek)

        offset = (page - 1) * page_size
        stmt = stmt.order_by(FixtureModel.kickoff_time.asc()).offset(offset).limit(page_size)

        rows = self._session.execute(stmt).all()
        total = self._session.execute(count_stmt).scalar_one()

        items = [
            FixtureTickerItem(
                fixture_id=row[0],
                gameweek_number=row[1],
                kickoff_time=row[2].isoformat(),
                home_team_short_name=row[3],
                away_team_short_name=row[4],
                finished=row[5],
            )
            for row in rows
        ]

        return FixtureTickerResult(items=items, total=total, page=page, page_size=page_size)
