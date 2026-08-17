from __future__ import annotations

import datetime as dt

from api.models import (
    FixtureModel,
    GameweekModel,
    PlayerModel,
    ProjectionModel,
    ProjectionRunModel,
    TeamModel,
)
from api.repositories.my_team_projection_repository import MyTeamProjectionRepository
from conftest import requires_database
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = requires_database

GENERATED_AT = dt.datetime(2026, 8, 20, 10, 0, tzinfo=dt.UTC)


def _clear(session: Session) -> None:
    session.execute(
        text(
            "TRUNCATE TABLE projections, projection_runs, fixtures, gameweeks, players, teams "
            "RESTART IDENTITY CASCADE"
        )
    )
    session.commit()


def _seed(session: Session) -> tuple[int, int, int]:
    """One player with one fixture in one gameweek. Returns (player_id,
    gameweek_id, fixture_id)."""
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)
    opponent = TeamModel(external_fpl_id=2, name="Chelsea", short_name="CHE", source_difficulty=3)
    session.add_all([team, opponent])
    session.flush()

    player = PlayerModel(
        external_fpl_id=101,
        first_name="Bukayo",
        second_name="Saka",
        web_name="Saka",
        team_id=team.id,
        position="MID",
        current_price=10.5,
        status="a",
    )
    session.add(player)

    gameweek = GameweekModel(
        number=5,
        name="Gameweek 5",
        deadline=dt.datetime(2026, 9, 20, 17, 30, tzinfo=dt.UTC),
        is_current=False,
        is_next=True,
        is_finished=False,
    )
    session.add(gameweek)
    session.flush()

    fixture = FixtureModel(
        external_fpl_id=1001,
        gameweek_id=gameweek.id,
        home_team_id=team.id,
        away_team_id=opponent.id,
        kickoff_time=dt.datetime(2026, 9, 20, 15, 0, tzinfo=dt.UTC),
        finished=False,
    )
    session.add(fixture)
    session.flush()

    return player.id, gameweek.id, fixture.id


def _create_run(session: Session, *, model_version: str, generated_at: dt.datetime) -> int:
    run = ProjectionRunModel(
        model_version=model_version,
        generated_at=generated_at,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot={},
        player_snapshot_generated_at=generated_at,
    )
    session.add(run)
    session.flush()
    return run.id


def _create_projection(
    session: Session,
    *,
    player_id: int,
    fixture_id: int,
    gameweek_id: int,
    run_id: int,
    model_version: str,
    generated_at: dt.datetime,
    projected_points: float,
) -> None:
    session.add(
        ProjectionModel(
            player_id=player_id,
            fixture_id=fixture_id,
            gameweek_id=gameweek_id,
            projected_points=projected_points,
            expected_minutes=80.0,
            generated_at=generated_at,
            model_version=model_version,
            run_id=run_id,
        )
    )


def test_returns_only_the_requested_runs_rows_even_when_models_share_a_timestamp(
    db_session: Session,
) -> None:
    """The regression for the mixing bug: baseline_v1/v2/component_v3 sharing
    one generated_at (as a real dual-write run produces) must never be
    confused with each other."""
    _clear(db_session)
    player_id, gameweek_id, fixture_id = _seed(db_session)

    v1_run_id = _create_run(db_session, model_version="baseline_v1", generated_at=GENERATED_AT)
    v2_run_id = _create_run(db_session, model_version="baseline_v2", generated_at=GENERATED_AT)
    v3_run_id = _create_run(db_session, model_version="component_v3", generated_at=GENERATED_AT)

    for run_id, model_version, points in (
        (v1_run_id, "baseline_v1", 2.0),
        (v2_run_id, "baseline_v2", 3.0),
        (v3_run_id, "component_v3", 4.0),
    ):
        _create_projection(
            db_session,
            player_id=player_id,
            fixture_id=fixture_id,
            gameweek_id=gameweek_id,
            run_id=run_id,
            model_version=model_version,
            generated_at=GENERATED_AT,
            projected_points=points,
        )
    db_session.commit()

    repository = MyTeamProjectionRepository(db_session)
    rows = repository.list_player_fixture_projections_for_run([player_id], v3_run_id)

    assert len(rows) == 1
    assert rows[0].projected_points == 4.0


def test_an_older_and_a_newer_run_for_the_same_model_are_never_mixed(
    db_session: Session,
) -> None:
    _clear(db_session)
    player_id, gameweek_id, fixture_id = _seed(db_session)

    older_generated_at = GENERATED_AT - dt.timedelta(days=1)
    older_run_id = _create_run(
        db_session, model_version="component_v3", generated_at=older_generated_at
    )
    newer_run_id = _create_run(db_session, model_version="component_v3", generated_at=GENERATED_AT)

    _create_projection(
        db_session,
        player_id=player_id,
        fixture_id=fixture_id,
        gameweek_id=gameweek_id,
        run_id=older_run_id,
        model_version="component_v3",
        generated_at=older_generated_at,
        projected_points=1.5,
    )
    _create_projection(
        db_session,
        player_id=player_id,
        fixture_id=fixture_id,
        gameweek_id=gameweek_id,
        run_id=newer_run_id,
        model_version="component_v3",
        generated_at=GENERATED_AT,
        projected_points=5.0,
    )
    db_session.commit()

    repository = MyTeamProjectionRepository(db_session)

    older_rows = repository.list_player_fixture_projections_for_run([player_id], older_run_id)
    newer_rows = repository.list_player_fixture_projections_for_run([player_id], newer_run_id)

    assert [row.projected_points for row in older_rows] == [1.5]
    assert [row.projected_points for row in newer_rows] == [5.0]


def test_returns_empty_for_a_player_with_no_projection_in_the_run(db_session: Session) -> None:
    _clear(db_session)
    player_id, _gameweek_id, _fixture_id = _seed(db_session)
    run_id = _create_run(db_session, model_version="component_v3", generated_at=GENERATED_AT)
    db_session.commit()

    repository = MyTeamProjectionRepository(db_session)
    rows = repository.list_player_fixture_projections_for_run([player_id], run_id)

    assert rows == []


def test_returns_empty_list_for_no_player_ids(db_session: Session) -> None:
    _clear(db_session)
    repository = MyTeamProjectionRepository(db_session)

    assert repository.list_player_fixture_projections_for_run([], 1) == []


def test_list_latest_never_mixes_models_sharing_a_generated_at(db_session: Session) -> None:
    """The regression behind duplicated opponent labels and inflated totals
    on My Team: dual-write's baseline_v1/v2/component_v3 sharing one
    generated_at must not all be returned as if they were "the latest"."""
    _clear(db_session)
    player_id, gameweek_id, fixture_id = _seed(db_session)

    v1_run_id = _create_run(db_session, model_version="baseline_v1", generated_at=GENERATED_AT)
    v2_run_id = _create_run(db_session, model_version="baseline_v2", generated_at=GENERATED_AT)
    v3_run_id = _create_run(db_session, model_version="component_v3", generated_at=GENERATED_AT)

    for run_id, model_version, points in (
        (v1_run_id, "baseline_v1", 2.0),
        (v2_run_id, "baseline_v2", 3.0),
        (v3_run_id, "component_v3", 4.0),
    ):
        _create_projection(
            db_session,
            player_id=player_id,
            fixture_id=fixture_id,
            gameweek_id=gameweek_id,
            run_id=run_id,
            model_version=model_version,
            generated_at=GENERATED_AT,
            projected_points=points,
        )
    db_session.commit()

    repository = MyTeamProjectionRepository(db_session)
    rows = repository.list_latest_player_fixture_projections([player_id])

    assert len(rows) == 1
    assert rows[0].projected_points == 4.0


def test_list_latest_can_request_a_different_model_explicitly(db_session: Session) -> None:
    _clear(db_session)
    player_id, gameweek_id, fixture_id = _seed(db_session)

    v1_run_id = _create_run(db_session, model_version="baseline_v1", generated_at=GENERATED_AT)
    v3_run_id = _create_run(db_session, model_version="component_v3", generated_at=GENERATED_AT)

    _create_projection(
        db_session,
        player_id=player_id,
        fixture_id=fixture_id,
        gameweek_id=gameweek_id,
        run_id=v1_run_id,
        model_version="baseline_v1",
        generated_at=GENERATED_AT,
        projected_points=2.0,
    )
    _create_projection(
        db_session,
        player_id=player_id,
        fixture_id=fixture_id,
        gameweek_id=gameweek_id,
        run_id=v3_run_id,
        model_version="component_v3",
        generated_at=GENERATED_AT,
        projected_points=4.0,
    )
    db_session.commit()

    repository = MyTeamProjectionRepository(db_session)
    rows = repository.list_latest_player_fixture_projections(
        [player_id], model_version="baseline_v1"
    )

    assert [row.projected_points for row in rows] == [2.0]
