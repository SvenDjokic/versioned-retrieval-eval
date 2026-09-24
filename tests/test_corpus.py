"""Corpus parsing and loading."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from vre.corpus import CORPUS_DIR, discover, families, parse_filename, read_text
from vre.load import load_corpus

EXPECTED_FAMILIES = {"nodejs-assert", "nodejs-errors", "bootstrap", "spark"}


def test_every_corpus_file_parses() -> None:
    """No file is skipped. If this fails the corpus is silently incomplete."""
    specs = discover()
    assert len(specs) == 34
    assert {s.family for s in specs} == EXPECTED_FAMILIES


def test_version_ordering_is_numeric_not_alphabetical() -> None:
    """The bug this guards against: "11.15.0" sorts before "5.3.1" as text."""
    node = families(discover())["nodejs-assert"]
    versions = [s.version for s in node]

    assert versions[0] == "11.15.0"
    assert versions[-1] == "23.11.0"
    # Text sorting would have put "11.15.0" after "23.11.0" only by accident;
    # the real giveaway is that 5.x would lead. Assert the key is numeric.
    assert node[0].version_key == (11, 15, 0)
    assert node[-1].version_key == (23, 11, 0)


def test_unknown_filename_raises_rather_than_skipping() -> None:
    with pytest.raises(ValueError, match="Unrecognised corpus filename"):
        parse_filename(Path("something unexpected.md"))


def test_markdown_extraction() -> None:
    spec = next(s for s in discover() if s.family == "nodejs-assert")
    text = read_text(spec.path)
    assert "assertion" in text
    assert len(text) > 1000


def test_content_actually_changes_between_versions() -> None:
    """The corpus has to contain real version drift, or it tests nothing.

    Concrete example: Node.js renamed the module from `assert` to `node:assert`
    partway through this chain. The oldest document does not contain the
    prefixed form and the newest does. A retrieval system that ignores which
    version it is reading will answer this kind of question wrongly.
    """
    versions = families(discover())["nodejs-assert"]
    oldest = read_text(versions[0].path)
    newest = read_text(versions[-1].path)

    assert "node:assert" not in oldest
    assert "node:assert" in newest
    assert oldest != newest


def test_pdf_extraction() -> None:
    """PDFs are the lossy path. Assert it produces usable prose, not that it
    is perfect, because it will not be."""
    spec = next(s for s in discover() if s.family == "spark")
    text = read_text(spec.path)
    assert "Spark" in text
    assert len(text) > 1000


def test_loading_creates_documents_and_version_chains(conn: psycopg.Connection) -> None:
    report = load_corpus(conn)

    assert report.documents == 34
    assert report.families == 4
    # One edge fewer than versions, per family: 13 + 9 + 6 + 6 documents
    # gives 12 + 8 + 5 + 5 = 30 edges.
    assert report.relationships == 30

    count = conn.execute("SELECT count(*) FROM documents").fetchone()
    assert count is not None and count[0] == 34


def test_exactly_one_current_version_per_family(conn: psycopg.Connection) -> None:
    load_corpus(conn)

    rows = conn.execute(
        """
        SELECT metadata ->> 'family' AS family, count(*)
        FROM documents
        WHERE status = 'current'
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()

    assert {row[0] for row in rows} == EXPECTED_FAMILIES
    assert all(count == 1 for _, count in rows)


def test_supersedes_chain_resolves_to_the_newest_version(conn: psycopg.Connection) -> None:
    """The real thing, on real documents rather than fixtures.

    Start at the oldest Node.js assert doc and walk forward. The answer must be
    the newest one, 23.11.0.
    """
    load_corpus(conn)

    oldest = conn.execute(
        "SELECT id FROM documents WHERE external_id = 'nodejs-assert@11.15.0'"
    ).fetchone()
    assert oldest is not None

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
        SELECT d.version_label
        FROM chain JOIN documents d ON d.id = chain.id
        WHERE d.status = 'current'
        """,
        (oldest[0],),
    ).fetchall()

    assert [row[0] for row in governing] == ["23.11.0"]


def test_loading_twice_does_not_duplicate(conn: psycopg.Connection) -> None:
    load_corpus(conn)
    load_corpus(conn)

    documents = conn.execute("SELECT count(*) FROM documents").fetchone()
    edges = conn.execute("SELECT count(*) FROM document_relationships").fetchone()

    assert documents is not None and documents[0] == 34
    assert edges is not None and edges[0] == 30


def test_corpus_directory_is_present() -> None:
    """Guards against the corpus not being committed."""
    assert CORPUS_DIR.is_dir()
    assert len(list(CORPUS_DIR.iterdir())) == 34
