"""Database access.

One place that knows how to open a connection, so nothing else has to think
about connection strings or type registration.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from vre.config import settings


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Open a connection with pgvector types registered.

    `register_vector` teaches psycopg about Postgres's `vector` type, so a
    Python list goes in and a list comes back out. Without it you would be
    formatting and parsing strings like '[0.1,0.2]' by hand at every call site.

    Used as a context manager, so the connection is committed on a clean exit
    and rolled back if the block raises:

        with connect() as conn:
            conn.execute("SELECT 1")
    """
    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        yield conn


def healthcheck() -> dict[str, str]:
    """Confirm the database is reachable and pgvector is installed.

    Returns the server and extension versions. Raises if either is missing,
    which is the behaviour we want: fail loudly at startup, not mid-run.
    """
    with connect() as conn:
        server = conn.execute("SHOW server_version").fetchone()
        ext = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()

    if ext is None:
        raise RuntimeError(
            "The 'vector' extension is not installed in this database. "
            "Run: CREATE EXTENSION vector;"
        )

    assert server is not None
    return {"postgres": server[0], "pgvector": ext[0]}
