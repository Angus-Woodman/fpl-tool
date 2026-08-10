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

        repository.upsert_many([Team(id=0, external_fpl_id=1, name="Arsenal", short_name="ARS")])
        session.commit()

        repository.upsert_many([Team(id=0, external_fpl_id=1, name="Arsenal FC", short_name="ARS")])
        session.commit()

        rows = session.execute(select(TeamModel)).scalars().all()
        assert len(rows) == 1
        assert rows[0].name == "Arsenal FC"


def _clear_teams(session: Session) -> None:
    session.execute(text("TRUNCATE TABLE teams RESTART IDENTITY CASCADE"))
    session.commit()
