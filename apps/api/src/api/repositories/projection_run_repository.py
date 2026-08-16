from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import ProjectionRunModel


@dataclass(frozen=True)
class ProjectionRunRecord:
    id: int
    model_version: str
    generated_at: dt.datetime
    gameweeks_covered: list[int]
    parameters: dict[str, object]
    team_strength_snapshot: dict[str, object]
    player_snapshot_generated_at: dt.datetime | None


class ProjectionRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        model_version: str,
        generated_at: dt.datetime,
        gameweeks_covered: list[int],
        parameters: dict[str, object],
        team_strength_snapshot: dict[str, object],
        player_snapshot_generated_at: dt.datetime | None,
    ) -> int:
        run = ProjectionRunModel(
            model_version=model_version,
            generated_at=generated_at,
            gameweeks_covered=gameweeks_covered,
            parameters=parameters,
            team_strength_snapshot=team_strength_snapshot,
            player_snapshot_generated_at=player_snapshot_generated_at,
        )
        self._session.add(run)
        self._session.flush()
        return run.id

    def get(self, run_id: int) -> ProjectionRunRecord | None:
        run = self._session.get(ProjectionRunModel, run_id)
        if run is None:
            return None

        return ProjectionRunRecord(
            id=run.id,
            model_version=run.model_version,
            generated_at=run.generated_at,
            gameweeks_covered=list(run.gameweeks_covered),
            parameters=dict(run.parameters),
            team_strength_snapshot=dict(run.team_strength_snapshot),
            player_snapshot_generated_at=run.player_snapshot_generated_at,
        )

    def get_latest(self, model_version: str) -> ProjectionRunRecord | None:
        """The latest successful run for one explicit model -- never an
        implicit "latest across all models" concept. Ties on generated_at
        (e.g. dual-write runs sharing a timestamp) break on id, so this is
        always exactly one run, deterministically."""
        run = self._session.execute(
            select(ProjectionRunModel)
            .where(ProjectionRunModel.model_version == model_version)
            .order_by(ProjectionRunModel.generated_at.desc(), ProjectionRunModel.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if run is None:
            return None

        return ProjectionRunRecord(
            id=run.id,
            model_version=run.model_version,
            generated_at=run.generated_at,
            gameweeks_covered=list(run.gameweeks_covered),
            parameters=dict(run.parameters),
            team_strength_snapshot=dict(run.team_strength_snapshot),
            player_snapshot_generated_at=run.player_snapshot_generated_at,
        )
