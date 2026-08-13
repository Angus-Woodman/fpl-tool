from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from api.core.settings import get_settings
from api.db.guards import ensure_test_database_url
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

RUN_DB_TESTS_ENV_VAR = "RUN_DB_TESTS"


def integration_tests_enabled() -> bool:
    return os.getenv(RUN_DB_TESTS_ENV_VAR) == "1"


requires_database = pytest.mark.skipif(
    not integration_tests_enabled(),
    reason=f"Set {RUN_DB_TESTS_ENV_VAR}=1 to run PostgreSQL integration tests.",
)


@pytest.fixture(scope="session")
def test_database_engine() -> Generator[Engine, None, None]:
    """Engine bound to the dedicated test database.

    The guard raises rather than skips, so a misconfigured run fails loudly
    instead of silently truncating development data.
    """
    settings = get_settings()
    url = ensure_test_database_url(
        settings.test_database_url, development_url=settings.database_url
    )

    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(test_database_engine: Engine) -> Generator[Session, None, None]:
    session_factory = sessionmaker(
        bind=test_database_engine, autocommit=False, autoflush=False, class_=Session
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
