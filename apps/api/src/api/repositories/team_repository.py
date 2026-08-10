from __future__ import annotations

from fpl_engine.domain import Team
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import TeamModel


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
            }
            for team in teams
        ]

        statement = insert(TeamModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[TeamModel.external_fpl_id],
            set_={
                "name": statement.excluded.name,
                "short_name": statement.excluded.short_name,
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
