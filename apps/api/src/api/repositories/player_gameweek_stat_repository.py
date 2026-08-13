from __future__ import annotations

from fpl_engine.domain import PlayerGameweekStat
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import PlayerGameweekStatModel

UPSERT_BATCH_SIZE = 500


class PlayerGameweekStatRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, stats: list[PlayerGameweekStat]) -> None:
        """Idempotent per (player, gameweek) so re-importing a gameweek is harmless."""
        if not stats:
            return

        for start in range(0, len(stats), UPSERT_BATCH_SIZE):
            batch = stats[start : start + UPSERT_BATCH_SIZE]
            values = [
                {
                    "player_id": stat.player_id,
                    "gameweek_id": stat.gameweek_id,
                    "fixture_id": stat.fixture_id,
                    "minutes": stat.minutes,
                    "total_points": stat.total_points,
                    "goals_scored": stat.goals_scored,
                    "assists": stat.assists,
                    "clean_sheets": stat.clean_sheets,
                    "goals_conceded": stat.goals_conceded,
                    "bonus": stat.bonus,
                    "bps": stat.bps,
                }
                for stat in batch
            ]

            statement = insert(PlayerGameweekStatModel).values(values)
            statement = statement.on_conflict_do_update(
                constraint="uq_player_gameweek_stat",
                set_={
                    "fixture_id": statement.excluded.fixture_id,
                    "minutes": statement.excluded.minutes,
                    "total_points": statement.excluded.total_points,
                    "goals_scored": statement.excluded.goals_scored,
                    "assists": statement.excluded.assists,
                    "clean_sheets": statement.excluded.clean_sheets,
                    "goals_conceded": statement.excluded.goals_conceded,
                    "bonus": statement.excluded.bonus,
                    "bps": statement.excluded.bps,
                },
            )
            self._session.execute(statement)
