"""Shared pytest fixtures.

The schema tests run against a database created from scratch for each test
session and dropped afterwards, so they can never corrupt real data and can
never pass because of something left behind by an earlier run.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from pgvector.psycopg import register_vector

from vre.config import settings
from vre.migrate import migrate

TEST_DB_NAME = "versioned_retrieval_test"


def _swap_database(url: str, database: str) -> str:
    """Return the same connection URL pointing at a different database."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


@pytest.fixture(scope="session")
def test_database() -> Iterator[str]:
    """Create a fresh test database, drop it when the session ends.

    CREATE DATABASE cannot run inside a transaction, so this connection uses
    autocommit. It connects to the always-present `postgres` database, because
    you cannot create a database from inside the one you are creating.
    """
    admin_url = _swap_database(settings.database_url, "postgres")
    test_url = _swap_database(settings.database_url, TEST_DB_NAME)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')

    try:
        yield test_url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')


@pytest.fixture(scope="session")
def migrated_url(test_database: str) -> str:
    """The test database with all migrations applied."""
    with psycopg.connect(test_database) as conn:
        migrate(conn)
    return test_database


@pytest.fixture
def conn(migrated_url: str) -> Iterator[psycopg.Connection]:
    """A connection to the migrated test database.

    Everything the test does is rolled back afterwards, so tests stay
    independent of each other regardless of what order they run in.
    """
    with psycopg.connect(migrated_url) as connection:
        register_vector(connection)
        transaction = connection.transaction(force_rollback=True)
        with transaction:
            yield connection
