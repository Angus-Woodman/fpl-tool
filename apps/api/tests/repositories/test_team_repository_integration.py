import os

import pytest
from api.db.session import SessionLocal
from api.models import TeamModel
from api.repositories.team_repository import TeamRepository
from fpl_engine.domain import Team
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run PostgreSQL integration tests.",
)


def test_team_repository_upsert_updates_existing_row() -> None:
    with SessionLocal() as session:
        _clear_teams(session)
        repository = TeamRepository(session)

        repository.upsert_many(
            [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", difficulty=4)]
        )
        session.commit()

        repository.upsert_many(
            [Team(id=0, external_fpl_id=1, name="Arsenal FC", short_name="ARS", difficulty=5)]
        )
        session.commit()

        rows = session.execute(select(TeamModel)).scalars().all()
        assert len(rows) == 1
        assert rows[0].name == "Arsenal FC"
        assert rows[0].difficulty == 5


def test_team_repository_update_difficulty_updates_existing_row() -> None:
    with SessionLocal() as session:
        _clear_teams(session)
        repository = TeamRepository(session)

        repository.upsert_many(
            [Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS", difficulty=3)]
        )
        session.commit()

        team_id = session.execute(select(TeamModel.id)).scalar_one()

        result = repository.update_difficulty(team_id, 5)
        session.commit()

        assert result is not None
        assert result.difficulty == 5
        assert session.execute(select(TeamModel.difficulty)).scalar_one() == 5


def test_team_repository_update_difficulty_returns_none_when_missing() -> None:
    with SessionLocal() as session:
        _clear_teams(session)
        repository = TeamRepository(session)

        result = repository.update_difficulty(999, 5)

        assert result is None


def _clear_teams(session: Session) -> None:
    session.execute(text("TRUNCATE TABLE teams RESTART IDENTITY CASCADE"))
    session.commit()
