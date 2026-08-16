from __future__ import annotations

import datetime as dt

import pytest
from api.models import PlayerModel, ProjectionModel, TeamModel
from api.repositories.projection_run_repository import ProjectionRunRepository
from conftest import requires_database
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = requires_database

GENERATED_AT = dt.datetime(2026, 8, 20, 10, 0, tzinfo=dt.UTC)


def _clear(session: Session) -> None:
    session.execute(
        text("TRUNCATE TABLE projections, projection_runs, teams RESTART IDENTITY CASCADE")
    )
    session.commit()


def _team_strength_snapshot() -> dict[str, object]:
    return {"1": {"source_difficulty": 4, "override": None, "effective_difficulty": 4}}


def test_create_persists_model_version_and_timestamp(db_session: Session) -> None:
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)

    run_id = repository.create(
        model_version="baseline_v1",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={"recent_stats_limit": 3},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    db_session.commit()

    record = repository.get(run_id)
    assert record is not None
    assert record.model_version == "baseline_v1"
    assert record.generated_at == GENERATED_AT


def test_parameters_round_trip_accurately(db_session: Session) -> None:
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)

    parameters = {
        "xg90_m0": 900.0,
        "goal_points": {"GK": 6.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0},
        "difficulty_multipliers": {"1": 1.15, "3": 1.0, "5": 0.85},
    }
    run_id = repository.create(
        model_version="baseline_v2",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5, 6],
        parameters=parameters,
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=None,
    )
    db_session.commit()

    record = repository.get(run_id)
    assert record is not None
    assert record.parameters == parameters
    assert record.gameweeks_covered == [5, 6]
    assert record.player_snapshot_generated_at is None


def test_team_strength_snapshot_round_trips_accurately(db_session: Session) -> None:
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)
    snapshot = {
        "1": {"source_difficulty": 5, "override": 2, "effective_difficulty": 2},
        "2": {"source_difficulty": 3, "override": None, "effective_difficulty": 3},
    }

    run_id = repository.create(
        model_version="baseline_v1",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=snapshot,
        player_snapshot_generated_at=GENERATED_AT,
    )
    db_session.commit()

    assert repository.get(run_id).team_strength_snapshot == snapshot


def test_multiple_runs_at_the_same_generated_at_remain_distinguishable(
    db_session: Session,
) -> None:
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)

    v1_id = repository.create(
        model_version="baseline_v1",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    v2_id = repository.create(
        model_version="baseline_v2",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    db_session.commit()

    assert v1_id != v2_id
    assert repository.get(v1_id).model_version == "baseline_v1"
    assert repository.get(v2_id).model_version == "baseline_v2"


def test_changing_a_team_override_does_not_alter_stored_run_provenance(
    db_session: Session,
) -> None:
    _clear(db_session)
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=5)
    db_session.add(team)
    db_session.flush()

    repository = ProjectionRunRepository(db_session)
    run_id = repository.create(
        model_version="baseline_v1",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot={
            "1": {"source_difficulty": 5, "override": None, "effective_difficulty": 5}
        },
        player_snapshot_generated_at=GENERATED_AT,
    )
    db_session.commit()

    team.difficulty_override = 1
    db_session.commit()

    record = repository.get(run_id)
    assert record.team_strength_snapshot["1"]["effective_difficulty"] == 5


def test_projection_run_id_must_reference_an_existing_run(db_session: Session) -> None:
    _clear(db_session)
    db_session.execute(text("TRUNCATE TABLE players RESTART IDENTITY CASCADE"))
    team = TeamModel(external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=3)
    db_session.add(team)
    db_session.flush()
    player = PlayerModel(
        external_fpl_id=101,
        first_name="A",
        second_name="B",
        web_name="AB",
        team_id=team.id,
        position="MID",
        current_price=5.0,
        status="a",
    )
    db_session.add(player)
    db_session.flush()

    bad_projection = ProjectionModel(
        player_id=player.id,
        fixture_id=None,
        gameweek_id=None,
        projected_points=1.0,
        expected_minutes=1.0,
        generated_at=GENERATED_AT,
        model_version="baseline_v1",
        run_id=999999,
    )
    db_session.add(bad_projection)

    try:
        with pytest.raises(IntegrityError):
            db_session.commit()
    finally:
        db_session.rollback()


def test_get_latest_selects_only_the_requested_model_version(db_session: Session) -> None:
    """The regression for the mixing bug: baseline_v1, baseline_v2 and
    component_v3 sharing one generated_at (as a real dual-write run produces)
    must never be confused with each other."""
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)

    v1_id = repository.create(
        model_version="baseline_v1",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    v2_id = repository.create(
        model_version="baseline_v2",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    v3_id = repository.create(
        model_version="component_v3",
        generated_at=GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    db_session.commit()

    v1_latest = repository.get_latest("baseline_v1")
    v2_latest = repository.get_latest("baseline_v2")
    v3_latest = repository.get_latest("component_v3")

    assert v1_latest is not None and v1_latest.id == v1_id
    assert v2_latest is not None and v2_latest.id == v2_id
    assert v3_latest is not None and v3_latest.id == v3_id


def test_get_latest_prefers_a_newer_run_over_an_older_one_for_the_same_model(
    db_session: Session,
) -> None:
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)

    older_id = repository.create(
        model_version="component_v3",
        generated_at=GENERATED_AT - dt.timedelta(days=1),
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT - dt.timedelta(days=1),
    )
    newer_id = repository.create(
        model_version="component_v3",
        generated_at=GENERATED_AT,
        gameweeks_covered=[6],
        parameters={},
        team_strength_snapshot=_team_strength_snapshot(),
        player_snapshot_generated_at=GENERATED_AT,
    )
    db_session.commit()

    latest = repository.get_latest("component_v3")

    assert latest is not None
    assert latest.id == newer_id
    assert latest.id != older_id


def test_get_latest_returns_none_when_the_model_has_no_runs(db_session: Session) -> None:
    _clear(db_session)
    repository = ProjectionRunRepository(db_session)

    assert repository.get_latest("component_v3") is None
