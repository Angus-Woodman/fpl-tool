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


class _FakeTeamReadItem:
    def __init__(
        self, *, id: int, difficulty: int, source_difficulty: int, difficulty_override: int | None
    ) -> None:
        self.id = id
        self.difficulty = difficulty
        self.source_difficulty = source_difficulty
        self.difficulty_override = difficulty_override


class _FakeTeamRepository:
    def __init__(self, teams: list[_FakeTeamReadItem] | None = None) -> None:
        self._teams = teams or [
            _FakeTeamReadItem(id=1, difficulty=4, source_difficulty=4, difficulty_override=None),
            _FakeTeamReadItem(id=2, difficulty=2, source_difficulty=3, difficulty_override=2),
        ]

    def list_teams(self) -> list[_FakeTeamReadItem]:
        return self._teams


class _FakeRunRepository:
    def __init__(self) -> None:
        self.created_runs: list[dict[str, object]] = []
        self.next_id = 1

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
        run_id = self.next_id
        self.next_id += 1
        self.created_runs.append(
            {
                "id": run_id,
                "model_version": model_version,
                "generated_at": generated_at,
                "gameweeks_covered": gameweeks_covered,
                "parameters": parameters,
                "team_strength_snapshot": team_strength_snapshot,
                "player_snapshot_generated_at": player_snapshot_generated_at,
            }
        )
        return run_id


def _service(
    source_repository: _FakeProjectionGenerationRepository,
    projection_repository: _FakeProjectionRepository,
    *,
    team_repository: _FakeTeamRepository | None = None,
    run_repository: _FakeRunRepository | None = None,
) -> GenerateProjectionsService:
    return GenerateProjectionsService(
        source_repository,
        projection_repository,
        team_repository=team_repository or _FakeTeamRepository(),
        run_repository=run_repository or _FakeRunRepository(),
    )


def test_generate_projections_service_creates_and_persists_projection_batch() -> None:
    sink = _FakeProjectionRepository()
    service = _service(_FakeProjectionGenerationRepository(), sink)

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
    service = _service(_NoStatsRepository(), sink)

    service.execute()

    fallback_projection = next(projection for projection in sink.saved if projection.player_id == 2)
    assert fallback_projection.projected_points > 0.0
    assert fallback_projection.expected_minutes == 42.1875


def test_generate_projections_service_creates_a_run_and_links_every_projection() -> None:
    sink = _FakeProjectionRepository()
    runs = _FakeRunRepository()
    service = _service(_FakeProjectionGenerationRepository(), sink, run_repository=runs)

    service.execute()

    assert len(runs.created_runs) == 1
    run = runs.created_runs[0]
    assert run["model_version"] == "baseline_v1"
    assert run["gameweeks_covered"] == [5]
    assert all(projection.run_id == run["id"] for projection in sink.saved)


def test_generate_projections_service_records_the_effective_team_strength() -> None:
    sink = _FakeProjectionRepository()
    runs = _FakeRunRepository()
    teams = _FakeTeamRepository(
        [
            _FakeTeamReadItem(id=1, difficulty=4, source_difficulty=4, difficulty_override=None),
            _FakeTeamReadItem(id=2, difficulty=2, source_difficulty=3, difficulty_override=2),
        ]
    )
    service = _service(
        _FakeProjectionGenerationRepository(), sink, team_repository=teams, run_repository=runs
    )

    service.execute()

    snapshot = runs.created_runs[0]["team_strength_snapshot"]
    assert snapshot["1"] == {"source_difficulty": 4, "override": None, "effective_difficulty": 4}
    assert snapshot["2"] == {"source_difficulty": 3, "override": 2, "effective_difficulty": 2}


def test_generate_projections_service_records_the_freshest_snapshot_generation() -> None:
    sink = _FakeProjectionRepository()
    runs = _FakeRunRepository()
    service = _service(_FakeProjectionGenerationRepository(), sink, run_repository=runs)

    service.execute()

    assert runs.created_runs[0]["player_snapshot_generated_at"] == dt.datetime(
        2026, 8, 19, 12, 0, tzinfo=dt.UTC
    )


def test_generate_projections_service_none_snapshot_generation_without_snapshots() -> None:
    class _NoSnapshotsRepository(_FakeProjectionGenerationRepository):
        def list_latest_snapshots(self, player_ids: set[int]) -> list[PlayerSnapshot]:
            return []

    sink = _FakeProjectionRepository()
    runs = _FakeRunRepository()
    service = _service(_NoSnapshotsRepository(), sink, run_repository=runs)

    service.execute()

    assert runs.created_runs[0]["player_snapshot_generated_at"] is None
