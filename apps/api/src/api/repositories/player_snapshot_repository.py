from __future__ import annotations

from fpl_engine.domain import PlayerSnapshot
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import PlayerSnapshotModel

UPSERT_BATCH_SIZE = 500


class PlayerSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, snapshots: list[PlayerSnapshot]) -> None:
        """Idempotent per (player, captured_at) so a repeated import is harmless."""
        if not snapshots:
            return

        for start in range(0, len(snapshots), UPSERT_BATCH_SIZE):
            batch = snapshots[start : start + UPSERT_BATCH_SIZE]
            values = [
                {
                    "player_id": snapshot.player_id,
                    "captured_at": snapshot.captured_at,
                    "gameweek_id": snapshot.gameweek_id,
                    "price": snapshot.price,
                    "ownership_percent": snapshot.ownership_percent,
                    "transfers_in": snapshot.transfers_in,
                    "transfers_out": snapshot.transfers_out,
                    "status": snapshot.status,
                    "chance_of_playing_next_round": snapshot.chance_of_playing_next_round,
                    "total_minutes": snapshot.total_minutes,
                    "total_points": snapshot.total_points,
                    "starts": snapshot.starts,
                    "points_per_game": snapshot.points_per_game,
                    "form": snapshot.form,
                    "expected_goals": snapshot.expected_goals,
                    "expected_assists": snapshot.expected_assists,
                }
                for snapshot in batch
            ]

            statement = insert(PlayerSnapshotModel).values(values)
            statement = statement.on_conflict_do_update(
                constraint="uq_player_snapshot_time",
                set_={
                    "gameweek_id": statement.excluded.gameweek_id,
                    "price": statement.excluded.price,
                    "ownership_percent": statement.excluded.ownership_percent,
                    "transfers_in": statement.excluded.transfers_in,
                    "transfers_out": statement.excluded.transfers_out,
                    "status": statement.excluded.status,
                    "chance_of_playing_next_round": (
                        statement.excluded.chance_of_playing_next_round
                    ),
                    "total_minutes": statement.excluded.total_minutes,
                    "total_points": statement.excluded.total_points,
                    "starts": statement.excluded.starts,
                    "points_per_game": statement.excluded.points_per_game,
                    "form": statement.excluded.form,
                    "expected_goals": statement.excluded.expected_goals,
                    "expected_assists": statement.excluded.expected_assists,
                },
            )
            self._session.execute(statement)
