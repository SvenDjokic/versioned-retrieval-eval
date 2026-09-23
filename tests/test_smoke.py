"""End-to-end smoke test.

Not testing logic yet, because there isn't any. This proves the chain works:
config is readable, the database is reachable, pgvector is installed, and
vectors can be written and compared. If this fails, nothing built on top of it
is worth debugging.
"""

import pytest

from vre.db import connect, healthcheck


def test_database_is_reachable_and_has_pgvector() -> None:
    versions = healthcheck()
    assert versions["postgres"].startswith("17")
    assert versions["pgvector"]


def test_vectors_can_be_stored_and_ranked_by_similarity() -> None:
    """Store three vectors and check the nearest-neighbour ordering.

    The `<=>` operator is cosine distance: 0 means the same direction,
    1 means unrelated. Ordering by it is exactly what semantic search does,
    just with 1024 dimensions instead of 3.
    """
    with connect() as conn:
        # A temporary table exists only for this connection and disappears
        # afterwards, so the test leaves no trace in the database.
        conn.execute(
            "CREATE TEMP TABLE smoke (label text, embedding vector(3))"
        )
        conn.execute(
            "INSERT INTO smoke VALUES (%s, %s), (%s, %s), (%s, %s)",
            ("apple", [1.0, 0.0, 0.0],
             "orange", [0.9, 0.1, 0.0],
             "tractor", [0.0, 0.0, 1.0]),
        )

        # The ::vector cast is required. psycopg sends a Python list as a
        # Postgres array (double precision[]), and there is no `vector <=>
        # double precision[]` operator. The INSERT above needed no cast
        # because the target column is declared vector(3), so Postgres had
        # something to coerce towards; a bare comparison gives it nothing.
        rows = conn.execute(
            "SELECT label, embedding <=> %s::vector AS distance "
            "FROM smoke ORDER BY distance",
            ([1.0, 0.0, 0.0],),
        ).fetchall()

    labels = [label for label, _ in rows]
    distances = dict(rows)

    assert labels == ["apple", "orange", "tractor"]
    assert distances["apple"] == pytest.approx(0.0, abs=1e-6)
    assert distances["orange"] < 0.05
    assert distances["tractor"] == pytest.approx(1.0, abs=1e-6)
