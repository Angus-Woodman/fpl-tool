from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

TEST_DATABASE_SUFFIX = "_test"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when integration tests are pointed at a database they must not modify."""


def ensure_test_database_url(test_url: str | None, *, development_url: str) -> str:
    """Return `test_url` only if it is safe for destructive integration tests.

    Integration tests truncate tables, so the target must be a dedicated database
    whose name ends with `_test` and which is not the configured development database.
    """
    if test_url is None or not test_url.strip():
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is not set. Integration tests need a dedicated database "
            f"whose name ends with '{TEST_DATABASE_SUFFIX}'. Run `make db-test-up` first."
        )

    candidate = test_url.strip()

    if candidate == development_url.strip():
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL matches the development database. Integration tests "
            "truncate tables and must never run against development data."
        )

    try:
        parsed = make_url(candidate)
    except ArgumentError as error:
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL is not a valid database URL: {error}"
        ) from error

    if not parsed.database:
        raise UnsafeTestDatabaseError("TEST_DATABASE_URL does not include a database name.")

    if not parsed.database.endswith(TEST_DATABASE_SUFFIX):
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL points at database '{parsed.database}', which is not "
            f"marked as a test database. Its name must end with '{TEST_DATABASE_SUFFIX}'."
        )

    return candidate
