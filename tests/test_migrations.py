"""Schema tests.

Two jobs. Prove the migration runner works, and prove the data model can
actually answer the question it exists to answer: given a document, what
governs now?
"""

from __future__ import annotations

import psycopg
import pytest

from vre.migrate import discover, migrate

EXPECTED_TABLES = {
    "documents",
    "document_relationships",
    "chunks",
    "eval_questions",
    "eval_runs",
    "eval_results",
    "schema_migrations",
}


def test_all_tables_exist(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    assert EXPECTED_TABLES <= {row[0] for row in rows}


def test_migrations_are_recorded(conn: psycopg.Connection) -> None:
    recorded = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row[0] for row in recorded] == [m.version for m in discover()]


def test_migrating_twice_applies_nothing(migrated_url: str) -> None:
    """Idempotency. Re-running must be a no-op, not an error."""
    with psycopg.connect(migrated_url) as connection:
        assert migrate(connection) == []


def test_chunks_reject_wrong_embedding_dimension(conn: psycopg.Connection) -> None:
    """The column is vector(1024). A mismatched vector must be refused.

    Catching this at the database rather than in application code means a
    half-configured embedding model fails immediately and loudly.
    """
    doc_id = _insert_document(conn, "doc-dim", "Dimension test")
    with pytest.raises(psycopg.errors.DataException):
        conn.execute(
            "INSERT INTO chunks (document_id, ordinal, content, embedding) "
            "VALUES (%s, 0, 'too short', %s::vector)",
            (doc_id, [0.1, 0.2, 0.3]),
        )


def test_full_text_column_is_generated(conn: psycopg.Connection) -> None:
    """content_tsv is maintained by Postgres, not by us."""
    doc_id = _insert_document(conn, "doc-fts", "Full text test")
    conn.execute(
        "INSERT INTO chunks (document_id, ordinal, content) "
        "VALUES (%s, 0, 'The assertion module provides a set of functions')",
        (doc_id,),
    )
    row = conn.execute(
        "SELECT content_tsv @@ to_tsquery('english', 'assertion') FROM chunks"
    ).fetchone()
    assert row is not None and row[0] is True


def test_supersession_is_answerable_by_join(conn: psycopg.Connection) -> None:
    """The point of the whole schema.

    Three versions of a document, chained by `supersedes`. Given any one of
    them, the system must be able to say which version governs now. Vector
    similarity cannot answer this; a join can.
    """
    v1 = _insert_document(conn, "guide-v1", "Guide v1", version="1.0", status="superseded")
    v2 = _insert_document(conn, "guide-v2", "Guide v2", version="2.0", status="superseded")
    v3 = _insert_document(conn, "guide-v3", "Guide v3", version="3.0", status="current")

    # Each newer document supersedes the one before it.
    conn.execute(
        "INSERT INTO document_relationships (from_doc, to_doc, relation) "
        "VALUES (%s, %s, 'supersedes'), (%s, %s, 'supersedes')",
        (v2, v1, v3, v2),
    )

    # Walk the supersedes chain forward from v1 to whatever is not superseded.
    governing = conn.execute(
        """
        WITH RECURSIVE chain AS (
            SELECT id FROM documents WHERE id = %s
            UNION ALL
            SELECT r.from_doc
            FROM document_relationships r
            JOIN chain c ON r.to_doc = c.id
            WHERE r.relation = 'supersedes'
        )
        SELECT d.id, d.version_label
        FROM chain
        JOIN documents d ON d.id = chain.id
        WHERE d.status = 'current'
        """,
        (v1,),
    ).fetchall()

    assert governing == [(v3, "3.0")]


def test_amendment_returns_both_documents(conn: psycopg.Connection) -> None:
    """An amendment does not replace the base document.

    Asking what governs must return the pair. Returning either one alone is
    the failure mode that naive retrieval hits, confidently.
    """
    base = _insert_document(conn, "agreement", "Base agreement")
    side = _insert_document(conn, "side-letter", "Side letter")

    conn.execute(
        "INSERT INTO document_relationships (from_doc, to_doc, relation) "
        "VALUES (%s, %s, 'amends')",
        (side, base),
    )

    governing = conn.execute(
        """
        SELECT d.external_id
        FROM documents d
        WHERE d.id = %(base)s
           OR d.id IN (
               SELECT from_doc FROM document_relationships
               WHERE to_doc = %(base)s AND relation = 'amends'
           )
        ORDER BY d.external_id
        """,
        {"base": base},
    ).fetchall()

    assert [row[0] for row in governing] == ["agreement", "side-letter"]


def test_self_referencing_relationship_is_rejected(conn: psycopg.Connection) -> None:
    doc_id = _insert_document(conn, "doc-self", "Self reference")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO document_relationships (from_doc, to_doc, relation) "
            "VALUES (%s, %s, 'supersedes')",
            (doc_id, doc_id),
        )


def _insert_document(
    conn: psycopg.Connection,
    external_id: str,
    title: str,
    *,
    version: str | None = None,
    status: str = "current",
) -> int:
    row = conn.execute(
        "INSERT INTO documents (external_id, title, doc_type, version_label, status) "
        "VALUES (%s, %s, 'test', %s, %s) RETURNING id",
        (external_id, title, version, status),
    ).fetchone()
    assert row is not None
    return row[0]
