from __future__ import annotations

from fpl_engine.domain import (
    Fixture,
    Player,
    PlayerGameweekStat,
    PlayerPosition,
    PlayerSnapshot,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.models import (
    FixtureModel,
    GameweekModel,
    PlayerGameweekStatModel,
    PlayerModel,
    PlayerSnapshotModel,
)


class ProjectionGenerationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_upcoming_fixtures(self) -> list[Fixture]:
        rows = self._session.execute(
            select(
                FixtureModel.id,
                FixtureModel.external_fpl_id,
                FixtureModel.gameweek_id,
                FixtureModel.home_team_id,
                FixtureModel.away_team_id,
                FixtureModel.kickoff_time,
                FixtureModel.home_score,
                FixtureModel.away_score,
                FixtureModel.finished,
            )
            .outerjoin(GameweekModel, GameweekModel.id == FixtureModel.gameweek_id)
            .where(FixtureModel.finished.is_(False))
            .order_by(GameweekModel.number.asc().nulls_last(), FixtureModel.kickoff_time.asc())
        ).all()

        return [
            Fixture(
                id=row[0],
                external_fpl_id=row[1],
                gameweek_id=row[2],
                home_team_id=row[3],
                away_team_id=row[4],
                kickoff_time=row[5],
                home_score=row[6],
                away_score=row[7],
                finished=row[8],
            )
            for row in rows
        ]

    def list_players_for_team_ids(self, team_ids: set[int]) -> list[Player]:
        if not team_ids:
            return []

        rows = self._session.execute(
            select(
                PlayerModel.id,
                PlayerModel.external_fpl_id,
                PlayerModel.first_name,
                PlayerModel.second_name,
                PlayerModel.web_name,
                PlayerModel.team_id,
                PlayerModel.position,
                PlayerModel.current_price,
                PlayerModel.status,
            ).where(PlayerModel.team_id.in_(team_ids))
        ).all()

        return [
            Player(
                id=row[0],
                external_fpl_id=row[1],
                first_name=row[2],
                second_name=row[3],
                web_name=row[4],
                team_id=row[5],
                position=PlayerPosition(row[6].value if hasattr(row[6], "value") else str(row[6])),
                current_price=float(row[7]),
                status=row[8],
            )
            for row in rows
        ]

    def list_recent_stats(self, player_ids: set[int]) -> list[PlayerGameweekStat]:
        if not player_ids:
            return []

        rows = self._session.execute(
            select(
                PlayerGameweekStatModel.player_id,
                PlayerGameweekStatModel.gameweek_id,
                PlayerGameweekStatModel.fixture_id,
                PlayerGameweekStatModel.minutes,
                PlayerGameweekStatModel.total_points,
                PlayerGameweekStatModel.goals_scored,
                PlayerGameweekStatModel.assists,
                PlayerGameweekStatModel.clean_sheets,
                PlayerGameweekStatModel.goals_conceded,
                PlayerGameweekStatModel.bonus,
                PlayerGameweekStatModel.bps,
            )
            .where(PlayerGameweekStatModel.player_id.in_(player_ids))
            .order_by(
                PlayerGameweekStatModel.player_id.asc(),
                PlayerGameweekStatModel.gameweek_id.desc(),
            )
        ).all()

        return [
            PlayerGameweekStat(
                player_id=row[0],
                gameweek_id=row[1],
                fixture_id=row[2],
                minutes=row[3],
                total_points=row[4],
                goals_scored=row[5],
                assists=row[6],
                clean_sheets=row[7],
                goals_conceded=row[8],
                bonus=row[9],
                bps=row[10],
            )
            for row in rows
        ]

    def list_latest_snapshots(self, player_ids: set[int]) -> list[PlayerSnapshot]:
        if not player_ids:
            return []

        latest_snapshot_subquery = (
            select(
                PlayerSnapshotModel.player_id.label("player_id"),
                func.max(PlayerSnapshotModel.captured_at).label("captured_at"),
            )
            .where(PlayerSnapshotModel.player_id.in_(player_ids))
            .group_by(PlayerSnapshotModel.player_id)
            .subquery()
        )

        rows = self._session.execute(
            select(
                PlayerSnapshotModel.player_id,
                PlayerSnapshotModel.captured_at,
                PlayerSnapshotModel.gameweek_id,
                PlayerSnapshotModel.price,
                PlayerSnapshotModel.ownership_percent,
                PlayerSnapshotModel.transfers_in,
                PlayerSnapshotModel.transfers_out,
                PlayerSnapshotModel.status,
                PlayerSnapshotModel.chance_of_playing_next_round,
            ).join(
                latest_snapshot_subquery,
                (PlayerSnapshotModel.player_id == latest_snapshot_subquery.c.player_id)
                & (PlayerSnapshotModel.captured_at == latest_snapshot_subquery.c.captured_at),
            )
        ).all()

        return [
            PlayerSnapshot(
                player_id=row[0],
                captured_at=row[1],
                gameweek_id=row[2],
                price=float(row[3]),
                ownership_percent=float(row[4]),
                transfers_in=row[5],
                transfers_out=row[6],
                status=row[7],
                chance_of_playing_next_round=row[8],
            )
            for row in rows
        ]
