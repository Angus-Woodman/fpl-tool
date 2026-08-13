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
                    "expected_goals_per_90": snapshot.expected_goals_per_90,
                    "expected_assists_per_90": snapshot.expected_assists_per_90,
                    "expected_goals_conceded_per_90": snapshot.expected_goals_conceded_per_90,
                    "goals_conceded_per_90": snapshot.goals_conceded_per_90,
                    "clean_sheets_per_90": snapshot.clean_sheets_per_90,
                    "saves_per_90": snapshot.saves_per_90,
                    "starts_per_90": snapshot.starts_per_90,
                    "defensive_contribution_per_90": snapshot.defensive_contribution_per_90,
                    "penalties_order": snapshot.penalties_order,
                    "direct_freekicks_order": snapshot.direct_freekicks_order,
                    "corners_order": snapshot.corners_order,
                    "team_join_date": snapshot.team_join_date,
                    "ep_next": snapshot.ep_next,
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
                    "expected_goals_per_90": statement.excluded.expected_goals_per_90,
                    "expected_assists_per_90": statement.excluded.expected_assists_per_90,
                    "expected_goals_conceded_per_90": (
                        statement.excluded.expected_goals_conceded_per_90
                    ),
                    "goals_conceded_per_90": statement.excluded.goals_conceded_per_90,
                    "clean_sheets_per_90": statement.excluded.clean_sheets_per_90,
                    "saves_per_90": statement.excluded.saves_per_90,
                    "starts_per_90": statement.excluded.starts_per_90,
                    "defensive_contribution_per_90": (
                        statement.excluded.defensive_contribution_per_90
                    ),
                    "penalties_order": statement.excluded.penalties_order,
                    "direct_freekicks_order": statement.excluded.direct_freekicks_order,
                    "corners_order": statement.excluded.corners_order,
                    "team_join_date": statement.excluded.team_join_date,
                    "ep_next": statement.excluded.ep_next,
                },
            )
            self._session.execute(statement)
