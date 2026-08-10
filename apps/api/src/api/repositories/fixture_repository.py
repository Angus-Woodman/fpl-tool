from __future__ import annotations

from fpl_engine.domain import Fixture
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import FixtureModel


class FixtureRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, fixtures: list[Fixture]) -> None:
        if not fixtures:
            return

        values = [
            {
                "external_fpl_id": fixture.external_fpl_id,
                "gameweek_id": fixture.gameweek_id,
                "home_team_id": fixture.home_team_id,
                "away_team_id": fixture.away_team_id,
                "kickoff_time": fixture.kickoff_time,
                "home_score": fixture.home_score,
                "away_score": fixture.away_score,
                "finished": fixture.finished,
            }
            for fixture in fixtures
        ]

        statement = insert(FixtureModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[FixtureModel.external_fpl_id],
            set_={
                "gameweek_id": statement.excluded.gameweek_id,
                "home_team_id": statement.excluded.home_team_id,
                "away_team_id": statement.excluded.away_team_id,
                "kickoff_time": statement.excluded.kickoff_time,
                "home_score": statement.excluded.home_score,
                "away_score": statement.excluded.away_score,
                "finished": statement.excluded.finished,
            },
        )
        self._session.execute(statement)
