from __future__ import annotations

import datetime as dt

import pytest
from api.services.dual_write_projections import (
    MAX_MISSING_SNAPSHOT_FRACTION_DEFAULT,
    DualWriteProjectionsService,
    MissingSnapshotCoverageError,
)
from api.services.generate_projections import GenerateProjectionsService
from fpl_engine.domain import (
    Fixture,
    Player,
    PlayerGameweekStat,
    PlayerPosition,
    PlayerSnapshot,
    Projection,
)
from fpl_engine.projections import PriorComputationParameters

GENERATION = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)
FIXTURE_KICKOFF = dt.datetime(2026, 8, 20, 18, 30, tzinfo=dt.UTC)
ESTABLISHED_JOIN_DATE = dt.date(2019, 7, 1)

TEAM1_PLAYER_IDS = [1, 2, 3, 4, 5]
TEAM2_PLAYER_ID = 6


def _player(player_id: int, *, team_id: int, position: PlayerPosition) -> Player:
    return Player(
        id=player_id,
        external_fpl_id=1000 + player_id,
        first_name="First",
        second_name=f"Player{player_id}",
        web_name=f"Player{player_id}",
        team_id=team_id,
        position=position,
        current_price=6.0,
        status="a",
    )


def _snapshot(
    player_id: int,
    *,
    starts: int = 36,
    total_minutes: int = 2500,
    expected_goals: float = 8.0,
    expected_assists: float = 6.0,
    expected_goals_per_90: float = 0.29,
    expected_assists_per_90: float = 0.22,
    team_join_date: dt.date | None = ESTABLISHED_JOIN_DATE,
) -> PlayerSnapshot:
    return PlayerSnapshot(
        player_id=player_id,
        captured_at=GENERATION,
        gameweek_id=5,
        price=6.0,
        ownership_percent=10.0,
        transfers_in=0,
        transfers_out=0,
        status="a",
        chance_of_playing_next_round=None,
        total_minutes=total_minutes,
        starts=starts,
        expected_goals=expected_goals,
        expected_assists=expected_assists,
        expected_goals_per_90=expected_goals_per_90,
        expected_assists_per_90=expected_assists_per_90,
        team_join_date=team_join_date,
    )


class _FakeRepository:
    """One fixture, team 1 (5 established MID players) vs team 2 (1 FWD player).

    Subclasses override list_snapshots_for_generation to simulate missing
    coverage without touching the shared fixture/player/team setup.
    """

    def list_upcoming_fixtures(self) -> list[Fixture]:
        return [
            Fixture(
                id=101,
                external_fpl_id=1001,
                gameweek_id=5,
                home_team_id=1,
                away_team_id=2,
                kickoff_time=FIXTURE_KICKOFF,
                home_score=None,
                away_score=None,
                finished=False,
            )
        ]

    def list_players_for_team_ids(self, team_ids: set[int]) -> list[Player]:
        assert team_ids == {1, 2}
        return [
            _player(player_id, team_id=1, position=PlayerPosition.MIDFIELDER)
            for player_id in TEAM1_PLAYER_IDS
        ] + [_player(TEAM2_PLAYER_ID, team_id=2, position=PlayerPosition.FORWARD)]

    def list_recent_stats(self, player_ids: set[int]) -> list[PlayerGameweekStat]:
        return []

    def get_latest_snapshot_generation(self) -> dt.datetime | None:
        return GENERATION

    def list_snapshots_for_generation(
        self, player_ids: set[int], generated_at: dt.datetime
    ) -> list[PlayerSnapshot]:
        assert generated_at == GENERATION
        return [_snapshot(player_id) for player_id in TEAM1_PLAYER_IDS] + [
            _snapshot(
                TEAM2_PLAYER_ID,
                expected_goals=5.0,
                expected_assists=1.0,
                expected_goals_per_90=0.4,
                expected_assists_per_90=0.08,
            )
        ]


class _OnePlayerMissingSnapshot(_FakeRepository):
    def list_snapshots_for_generation(
        self, player_ids: set[int], generated_at: dt.datetime
    ) -> list[PlayerSnapshot]:
        snapshots = super().list_snapshots_for_generation(player_ids, generated_at)
        return [snapshot for snapshot in snapshots if snapshot.player_id != TEAM2_PLAYER_ID]


class _MostlyMissingSnapshots(_FakeRepository):
    def list_snapshots_for_generation(
        self, player_ids: set[int], generated_at: dt.datetime
    ) -> list[PlayerSnapshot]:
        snapshots = super().list_snapshots_for_generation(player_ids, generated_at)
        return [snapshot for snapshot in snapshots if snapshot.player_id in (1, 2)]


class _FakeProjectionRepository:
    def __init__(self) -> None:
        self.saved: list[Projection] = []

    def upsert_many(self, projections: list[Projection]) -> None:
        self.saved.extend(projections)


class _FakeTeamReadItem:
    def __init__(
        self, *, id: int, difficulty: int, source_difficulty: int, difficulty_override: int | None
    ) -> None:
        self.id = id
        self.difficulty = difficulty
        self.source_difficulty = source_difficulty
        self.difficulty_override = difficulty_override


class _FakeTeamRepository:
    def list_teams(self) -> list[_FakeTeamReadItem]:
        return [
            _FakeTeamReadItem(id=1, difficulty=3, source_difficulty=3, difficulty_override=None),
            _FakeTeamReadItem(id=2, difficulty=4, source_difficulty=4, difficulty_override=None),
        ]


class _FakeRunRepository:
    def __init__(self) -> None:
        self.created_runs: list[dict[str, object]] = []
        self.next_id = 1

    def create(self, **kwargs: object) -> int:
        run_id = self.next_id
        self.next_id += 1
        self.created_runs.append({"id": run_id, **kwargs})
        return run_id


def _build_service(
    source_repository: _FakeRepository,
    projection_repository: _FakeProjectionRepository,
    run_repository: _FakeRunRepository,
    *,
    max_missing_snapshot_fraction: float = MAX_MISSING_SNAPSHOT_FRACTION_DEFAULT,
) -> DualWriteProjectionsService:
    team_repository = _FakeTeamRepository()
    v1_service = GenerateProjectionsService(
        source_repository, projection_repository, team_repository, run_repository
    )
    return DualWriteProjectionsService(
        source_repository=source_repository,
        projection_repository=projection_repository,
        team_repository=team_repository,
        run_repository=run_repository,
        v1_service=v1_service,
        prior_computation_parameters=PriorComputationParameters(
            minimum_minutes_for_cohort_inclusion=450.0,
            minimum_cohort_size=5,
            established_cutoff_months=12,
        ),
        max_missing_snapshot_fraction=max_missing_snapshot_fraction,
    )


def test_dual_write_creates_two_runs_with_shared_provenance() -> None:
    projection_repository = _FakeProjectionRepository()
    run_repository = _FakeRunRepository()
    service = _build_service(_FakeRepository(), projection_repository, run_repository)

    summary = service.execute()

    assert len(run_repository.created_runs) == 2
    v1_run, v2_run = run_repository.created_runs
    assert v1_run["model_version"] == "baseline_v1"
    assert v2_run["model_version"] == "baseline_v2"
    assert v1_run["generated_at"] == v2_run["generated_at"] == summary.generated_at
    assert v1_run["team_strength_snapshot"] == v2_run["team_strength_snapshot"]
    assert (
        v1_run["player_snapshot_generated_at"]
        == v2_run["player_snapshot_generated_at"]
        == GENERATION
    )
    assert v1_run["gameweeks_covered"] == v2_run["gameweeks_covered"] == [5]
    assert summary.v1_run_id == v1_run["id"]
    assert summary.v2_run_id == v2_run["id"]
    assert summary.gameweeks_covered == [5]


def test_dual_write_persists_distinct_projections_for_both_models() -> None:
    projection_repository = _FakeProjectionRepository()
    run_repository = _FakeRunRepository()
    service = _build_service(_FakeRepository(), projection_repository, run_repository)

    summary = service.execute()

    v1_projections = [p for p in projection_repository.saved if p.model_version == "baseline_v1"]
    v2_projections = [p for p in projection_repository.saved if p.model_version == "baseline_v2"]
    assert len(v1_projections) == 6
    assert len(v2_projections) == 6
    assert summary.v2_projections_generated == 6
    assert summary.v2_players_skipped_missing_snapshot == 0
    assert all(p.run_id == summary.v1_run_id for p in v1_projections)
    assert all(p.run_id == summary.v2_run_id for p in v2_projections)


def test_dual_write_skips_missing_snapshot_players_for_v2_only() -> None:
    """The missing-player policy applies to v2 only: v1 keeps its existing
    fallback-to-player.status behaviour, unchanged."""
    projection_repository = _FakeProjectionRepository()
    run_repository = _FakeRunRepository()
    service = _build_service(
        _OnePlayerMissingSnapshot(),
        projection_repository,
        run_repository,
        # Isolate the skip behaviour from the coverage-threshold policy, which
        # has its own dedicated tests below.
        max_missing_snapshot_fraction=1.0,
    )

    summary = service.execute()

    assert summary.v2_players_skipped_missing_snapshot == 1
    assert summary.v2_missing_snapshot_fraction == pytest.approx(1 / 6)
    assert summary.v2_missing_snapshot_player_ids == (TEAM2_PLAYER_ID,)
    assert summary.v2_missing_snapshot_warning is not None
    assert str(TEAM2_PLAYER_ID) in summary.v2_missing_snapshot_warning
    v1_players = {
        p.player_id for p in projection_repository.saved if p.model_version == "baseline_v1"
    }
    v2_players = {
        p.player_id for p in projection_repository.saved if p.model_version == "baseline_v2"
    }
    assert TEAM2_PLAYER_ID in v1_players
    assert TEAM2_PLAYER_ID not in v2_players


def test_dual_write_raises_and_persists_nothing_when_missing_fraction_exceeds_threshold() -> None:
    """Never falls back to an older snapshot generation for the missing players --
    it fails the whole run instead, before persisting either model's output."""
    projection_repository = _FakeProjectionRepository()
    run_repository = _FakeRunRepository()
    service = _build_service(
        _MostlyMissingSnapshots(),
        projection_repository,
        run_repository,
        max_missing_snapshot_fraction=0.5,
    )

    with pytest.raises(MissingSnapshotCoverageError, match=r"player_ids=\(3, 4, 5, 6\)"):
        service.execute()

    assert run_repository.created_runs == []
    assert projection_repository.saved == []


def test_dual_write_default_threshold_is_strict() -> None:
    """A normal, complete snapshot generation should cover essentially every
    player -- the default tolerance is small (2%), not the old 50%."""
    projection_repository = _FakeProjectionRepository()
    run_repository = _FakeRunRepository()
    # 1 missing out of 6 is ~16.7%, comfortably over the real 2% default.
    service = _build_service(_OnePlayerMissingSnapshot(), projection_repository, run_repository)

    with pytest.raises(MissingSnapshotCoverageError):
        service.execute()

    assert run_repository.created_runs == []


def test_dual_write_no_warning_on_complete_coverage() -> None:
    run_repository = _FakeRunRepository()
    service = _build_service(_FakeRepository(), _FakeProjectionRepository(), run_repository)

    summary = service.execute()

    assert summary.v2_missing_snapshot_warning is None
    assert summary.v2_missing_snapshot_player_ids == ()


def test_dual_write_records_missing_player_ids_in_run_parameters() -> None:
    """So future v1-vs-v2 evaluation can restrict both models to their exact
    common player universe, not just a count."""
    run_repository = _FakeRunRepository()
    service = _build_service(
        _OnePlayerMissingSnapshot(),
        _FakeProjectionRepository(),
        run_repository,
        max_missing_snapshot_fraction=1.0,
    )

    service.execute()

    v2_parameters = run_repository.created_runs[1]["parameters"]
    assert v2_parameters["missing_snapshot_player_ids"] == [TEAM2_PLAYER_ID]  # type: ignore[index]


def test_dual_write_resolves_exposure_weighted_priors_from_the_shared_snapshots() -> None:
    run_repository = _FakeRunRepository()
    service = _build_service(_FakeRepository(), _FakeProjectionRepository(), run_repository)

    service.execute()

    v2_parameters = run_repository.created_runs[1]["parameters"]
    mid_priors = v2_parameters["resolved_priors_by_position"]["MID"]  # type: ignore[index]
    assert mid_priors["expected_goals_per_90"] == pytest.approx(90 * 40.0 / 12500.0)
    assert mid_priors["start_rate_is_fallback"] is False
    assert mid_priors["start_rate"] == pytest.approx((36 * 5) / (38 * 5))
    assert v2_parameters["missing_snapshot_players"] == 0  # type: ignore[index]
    assert v2_parameters["missing_snapshot_fraction"] == 0.0  # type: ignore[index]


def test_dual_write_running_twice_creates_distinct_historical_runs() -> None:
    run_repository = _FakeRunRepository()
    service = _build_service(_FakeRepository(), _FakeProjectionRepository(), run_repository)

    service.execute()
    service.execute()

    assert len(run_repository.created_runs) == 4
    ids = [run["id"] for run in run_repository.created_runs]
    assert len(set(ids)) == 4
