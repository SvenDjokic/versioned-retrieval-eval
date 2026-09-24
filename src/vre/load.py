"""Loading the corpus into the database.

Two steps, deliberately separate:

1. Insert every document
2. Wire the supersedes edges within each family

They are separate because step 2 needs the ids from step 1, and because the
edges are the interesting part. A loader that inserts documents but forgets the
relationships produces a corpus that looks fine and answers version questions
wrongly.

Loading is idempotent: running it twice updates rather than duplicating, so it
is safe to re-run after changing the parser.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from vre.corpus import DocumentSpec, discover, families, read_text


@dataclass
class LoadReport:
    documents: int
    relationships: int
    families: int

    def __str__(self) -> str:
        return (
            f"{self.documents} documents across {self.families} families, "
            f"{self.relationships} supersedes edges"
        )


def load_documents(conn: psycopg.Connection, specs: list[DocumentSpec]) -> dict[str, int]:
    """Insert or update every document. Returns external_id -> database id.

    The newest version in each family is marked 'current' and the rest
    'superseded', which is what the version ordering means for this corpus.

    ON CONFLICT makes this an upsert: a second run updates the existing row
    instead of failing on the unique constraint. That matters because the
    parser will change as the corpus grows, and re-running should be boring.
    """
    ids: dict[str, int] = {}
    grouped = families(specs)

    for versions in grouped.values():
        newest = versions[-1]
        for spec in versions:
            status = "current" if spec is newest else "superseded"
            row = conn.execute(
                """
                INSERT INTO documents
                    (external_id, title, doc_type, source, version_label,
                     status, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_id) DO UPDATE SET
                    title         = EXCLUDED.title,
                    doc_type      = EXCLUDED.doc_type,
                    source        = EXCLUDED.source,
                    version_label = EXCLUDED.version_label,
                    status        = EXCLUDED.status,
                    metadata      = EXCLUDED.metadata
                RETURNING id
                """,
                (
                    spec.external_id,
                    spec.title,
                    spec.doc_type,
                    spec.path.name,
                    spec.version,
                    status,
                    psycopg.types.json.Jsonb(
                        {
                            "family": spec.family,
                            "family_title": spec.family_title,
                            # Stored so ordering survives without re-parsing.
                            "version_key": list(spec.version_key),
                        }
                    ),
                ),
            ).fetchone()
            assert row is not None
            ids[spec.external_id] = row[0]

    return ids


def link_versions(
    conn: psycopg.Connection,
    specs: list[DocumentSpec],
    ids: dict[str, int],
) -> int:
    """Create a supersedes edge from each version to the one before it.

    Only consecutive versions are linked. Walking the chain is then a recursive
    query, which is correct and keeps the edge count linear. Linking every
    version to every older one would be quadratic and would say something
    subtly different: that v5 directly replaced v1, which it did not.
    """
    created = 0
    for versions in families(specs).values():
        for older, newer in zip(versions, versions[1:]):
            conn.execute(
                """
                INSERT INTO document_relationships (from_doc, to_doc, relation)
                VALUES (%s, %s, 'supersedes')
                ON CONFLICT (from_doc, to_doc, relation) DO NOTHING
                """,
                (ids[newer.external_id], ids[older.external_id]),
            )
            created += 1
    return created


def load_corpus(conn: psycopg.Connection) -> LoadReport:
    specs = discover()
    ids = load_documents(conn, specs)
    edges = link_versions(conn, specs, ids)
    return LoadReport(
        documents=len(ids),
        relationships=edges,
        families=len(families(specs)),
    )


def main() -> None:
    """Entry point: `uv run python -m vre.load`."""
    from vre.db import connect

    with connect() as conn:
        report = load_corpus(conn)

    print(report)


if __name__ == "__main__":
    main()
