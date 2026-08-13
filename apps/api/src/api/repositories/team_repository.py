from __future__ import annotations

from fpl_engine.domain import Team
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import TeamModel
from api.repositories.team_read_repository import TeamReadItem


class TeamRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, teams: list[Team]) -> None:
        if not teams:
            return

        values = [
            {
                "external_fpl_id": team.external_fpl_id,
                "name": team.name,
                "short_name": team.short_name,
                "source_difficulty": team.source_difficulty,
                "strength_overall_home": team.strength_overall_home,
                "strength_overall_away": team.strength_overall_away,
            }
            for team in teams
        ]

        statement = insert(TeamModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[TeamModel.external_fpl_id],
            set_={
                "name": statement.excluded.name,
                "short_name": statement.excluded.short_name,
                "source_difficulty": statement.excluded.source_difficulty,
                "strength_overall_home": statement.excluded.strength_overall_home,
                "strength_overall_away": statement.excluded.strength_overall_away,
            },
        )
        self._session.execute(statement)

    def get_internal_ids_by_external_ids(self, external_ids: set[int]) -> dict[int, int]:
        if not external_ids:
            return {}

        statement = select(TeamModel.external_fpl_id, TeamModel.id).where(
            TeamModel.external_fpl_id.in_(external_ids)
        )
        rows = self._session.execute(statement).all()
        return {external_id: internal_id for external_id, internal_id in rows}

    def update_difficulty(self, team_id: int, difficulty: int | None) -> TeamReadItem | None:
        """Set or, when `difficulty` is None, clear the manual override."""
        statement = (
            update(TeamModel)
            .where(TeamModel.id == team_id)
            .values(difficulty_override=difficulty)
            .returning(
                TeamModel.id,
                TeamModel.name,
                TeamModel.short_name,
                TeamModel.source_difficulty,
                TeamModel.difficulty_override,
            )
        )
        row = self._session.execute(statement).first()
        if row is None:
            return None

        override = row[4]
        return TeamReadItem(
            id=row[0],
            name=row[1],
            short_name=row[2],
            difficulty=override if override is not None else row[3],
            source_difficulty=row[3],
            difficulty_override=override,
        )
