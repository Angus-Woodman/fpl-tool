import datetime as dt

from api.services.generate_projections import GenerateProjectionsService
from fpl_engine.domain import (
    Fixture,
    Player,
    PlayerGameweekStat,
    PlayerPosition,
    PlayerSnapshot,
    Projection,
)


class _FakeProjectionGenerationRepository:
    def list_upcoming_fixtures(self) -> list[Fixture]:
        return [
            Fixture(
                id=101,
                external_fpl_id=1001,
                gameweek_id=5,
                home_team_id=1,
                away_team_id=2,
                kickoff_time=dt.datetime(2026, 8, 20, 18, 30, tzinfo=dt.UTC),
                home_score=None,
                away_score=None,
                finished=False,
            )
        ]

    def list_players_for_team_ids(self, team_ids: set[int]) -> list[Player]:
        assert team_ids == {1, 2}
        return [
            Player(
                id=1,
                external_fpl_id=501,
                first_name="Bukayo",
                second_name="Saka",
                web_name="Saka",
                team_id=1,
                position=PlayerPosition.MIDFIELDER,
                current_price=10.5,
                status="a",
            ),
            Player(
                id=2,
                external_fpl_id=601,
                first_name="Ollie",
                second_name="Watkins",
                web_name="Watkins",
                team_id=2,
                position=PlayerPosition.FORWARD,
                current_price=9.0,
                status="a",
            ),
        ]

    def list_recent_stats(self, player_ids: set[int]) -> list[PlayerGameweekStat]:
        assert player_ids == {1, 2}
        return [
            PlayerGameweekStat(
                player_id=1,
                gameweek_id=4,
                fixture_id=91,
                minutes=90,
                total_points=7,
                goals_scored=1,
                assists=0,
                clean_sheets=0,
                goals_conceded=0,
                bonus=1,
                bps=22,
            ),
            PlayerGameweekStat(
                player_id=1,
                gameweek_id=3,
                fixture_id=81,
                minutes=80,
                total_points=6,
                goals_scored=0,
                assists=1,
                clean_sheets=0,
                goals_conceded=0,
                bonus=0,
                bps=18,
            ),
        ]

    def list_latest_snapshots(self, player_ids: set[int]) -> list[PlayerSnapshot]:
        assert player_ids == {1, 2}
        return [
            PlayerSnapshot(
                player_id=1,
                captured_at=dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC),
                gameweek_id=5,
                price=10.5,
                ownership_percent=22.0,
                transfers_in=100000,
                transfers_out=12000,
                status="a",
                chance_of_playing_next_round=100,
            ),
            PlayerSnapshot(
                player_id=2,
                captured_at=dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC),
                gameweek_id=5,
                price=9.0,
                ownership_percent=18.0,
                transfers_in=80000,
                transfers_out=15000,
                status="d",
                chance_of_playing_next_round=75,
            ),
        ]


class _FakeProjectionRepository:
    def __init__(self) -> None:
        self.saved: list[Projection] = []

    def upsert_many(self, projections: list[Projection]) -> None:
        self.saved = projections


def test_generate_projections_service_creates_and_persists_projection_batch() -> None:
    sink = _FakeProjectionRepository()
    service = GenerateProjectionsService(_FakeProjectionGenerationRepository(), sink)

    summary = service.execute()

    assert summary.fixtures_considered == 1
    assert summary.players_considered == 2
    assert summary.projections_generated == 2
    assert summary.model_version == "baseline_v1"
    assert len(sink.saved) == 2
    assert sink.saved[0].model_version == "baseline_v1"
    assert sink.saved[0].fixture_id == 101
    assert sink.saved[0].components.total_points == sink.saved[0].projected_points
    assert sink.saved[1].expected_minutes < 75.0


def test_generate_projections_service_uses_position_fallback_without_recent_stats() -> None:
    class _NoStatsRepository(_FakeProjectionGenerationRepository):
        def list_recent_stats(self, player_ids: set[int]) -> list[PlayerGameweekStat]:
            return []

    sink = _FakeProjectionRepository()
    service = GenerateProjectionsService(_NoStatsRepository(), sink)

    service.execute()

    fallback_projection = next(projection for projection in sink.saved if projection.player_id == 2)
    assert fallback_projection.projected_points > 0.0
    assert fallback_projection.expected_minutes == 42.1875
