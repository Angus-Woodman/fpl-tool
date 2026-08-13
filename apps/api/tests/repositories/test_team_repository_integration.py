from __future__ import annotations

from api.models import TeamModel
from api.repositories.team_repository import TeamRepository
from conftest import requires_database
from fpl_engine.domain import Team
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = requires_database


def test_team_repository_upsert_updates_existing_row(db_session: Session) -> None:
    _clear_teams(db_session)
    repository = TeamRepository(db_session)

    repository.upsert_many(
        [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)]
    )
    db_session.commit()

    repository.upsert_many(
        [Team(id=0, external_fpl_id=1, name="Arsenal FC", short_name="ARS", source_difficulty=5)]
    )
    db_session.commit()

    rows = db_session.execute(select(TeamModel)).scalars().all()
    assert len(rows) == 1
    assert rows[0].name == "Arsenal FC"
    assert rows[0].source_difficulty == 5


def test_team_repository_upsert_preserves_a_manual_override(db_session: Session) -> None:
    _clear_teams(db_session)
    repository = TeamRepository(db_session)

    repository.upsert_many(
        [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=3)]
    )
    db_session.commit()
    team_id = db_session.execute(select(TeamModel.id)).scalar_one()
    repository.update_difficulty(team_id, 5)
    db_session.commit()

    repository.upsert_many(
        [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=4)]
    )
    db_session.commit()

    row = db_session.execute(select(TeamModel)).scalar_one()
    assert row.source_difficulty == 4
    assert row.difficulty_override == 5
    assert row.effective_difficulty == 5


def test_team_repository_update_difficulty_sets_an_override(db_session: Session) -> None:
    _clear_teams(db_session)
    repository = TeamRepository(db_session)

    repository.upsert_many(
        [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=3)]
    )
    db_session.commit()

    team_id = db_session.execute(select(TeamModel.id)).scalar_one()

    result = repository.update_difficulty(team_id, 5)
    db_session.commit()

    assert result is not None
    assert result.difficulty == 5
    assert result.source_difficulty == 3
    assert db_session.execute(select(TeamModel.difficulty_override)).scalar_one() == 5


def test_team_repository_clearing_the_override_restores_the_imported_value(
    db_session: Session,
) -> None:
    _clear_teams(db_session)
    repository = TeamRepository(db_session)

    repository.upsert_many(
        [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", source_difficulty=3)]
    )
    db_session.commit()
    team_id = db_session.execute(select(TeamModel.id)).scalar_one()
    repository.update_difficulty(team_id, 5)
    db_session.commit()

    result = repository.update_difficulty(team_id, None)
    db_session.commit()

    assert result is not None
    assert result.difficulty == 3
    assert result.difficulty_override is None


def test_team_repository_update_difficulty_returns_none_when_missing(db_session: Session) -> None:
    _clear_teams(db_session)
    repository = TeamRepository(db_session)

    result = repository.update_difficulty(999, 5)

    assert result is None


def _clear_teams(session: Session) -> None:
    session.execute(text("TRUNCATE TABLE teams RESTART IDENTITY CASCADE"))
    session.commit()
