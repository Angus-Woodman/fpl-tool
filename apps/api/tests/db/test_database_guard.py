from __future__ import annotations

import pytest
from api.db.guards import UnsafeTestDatabaseError, ensure_test_database_url

DEVELOPMENT_URL = "postgresql+psycopg://fpl:fpl@localhost:5432/fpl"
TEST_URL = "postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test"


def test_accepts_a_distinct_test_database() -> None:
    assert ensure_test_database_url(TEST_URL, development_url=DEVELOPMENT_URL) == TEST_URL


def test_rejects_a_missing_test_database_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError) as error:
        ensure_test_database_url(None, development_url=DEVELOPMENT_URL)

    assert "TEST_DATABASE_URL" in str(error.value)


def test_rejects_a_blank_test_database_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        ensure_test_database_url("   ", development_url=DEVELOPMENT_URL)


def test_rejects_the_development_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError) as error:
        ensure_test_database_url(DEVELOPMENT_URL, development_url=DEVELOPMENT_URL)

    assert "development database" in str(error.value)


def test_rejects_a_database_name_that_is_not_marked_as_a_test_database() -> None:
    with pytest.raises(UnsafeTestDatabaseError) as error:
        ensure_test_database_url(
            "postgresql+psycopg://fpl:fpl@localhost:5432/fpl_staging",
            development_url=DEVELOPMENT_URL,
        )

    assert "_test" in str(error.value)


def test_rejects_the_development_database_name_on_another_host() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        ensure_test_database_url(
            "postgresql+psycopg://fpl:fpl@db.internal:5432/fpl",
            development_url=DEVELOPMENT_URL,
        )


def test_rejects_a_url_without_a_database_name() -> None:
    with pytest.raises(UnsafeTestDatabaseError) as error:
        ensure_test_database_url(
            "postgresql+psycopg://fpl:fpl@localhost:5432/",
            development_url=DEVELOPMENT_URL,
        )

    assert "database name" in str(error.value)


def test_rejects_an_unparsable_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        ensure_test_database_url("not-a-url", development_url=DEVELOPMENT_URL)


def test_ignores_surrounding_whitespace() -> None:
    assert ensure_test_database_url(f"  {TEST_URL}  ", development_url=DEVELOPMENT_URL) == TEST_URL


def test_comparison_with_the_development_url_ignores_whitespace() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        ensure_test_database_url(f" {DEVELOPMENT_URL} ", development_url=DEVELOPMENT_URL)
