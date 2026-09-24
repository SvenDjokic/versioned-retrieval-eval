"""Minimal forward-only migration runner.

Alembic is the standard choice, but it generates a lot of machinery for a
project with one developer and a handful of tables. Twenty lines you fully
understand beat a framework you half do, and this can be replaced later
without anything else changing.

How it works: `migrations/` holds files named `NNN_description.sql`. A
`schema_migrations` table records which have run. Applying is idempotent, so
running it twice is safe, and each file runs inside a transaction so a failure
part-way leaves nothing behind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
FILENAME_PATTERN = re.compile(r"^(\d+)_.+\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Find migration files, ordered by their numeric prefix.

    Sorting on the parsed integer rather than the filename matters: string
    sorting puts '10' before '2'.
    """
    migrations = []
    for path in directory.glob("*.sql"):
        match = FILENAME_PATTERN.match(path.name)
        if match is None:
            raise ValueError(
                f"Migration filename does not match NNN_description.sql: {path.name}"
            )
        migrations.append(
            Migration(version=int(match.group(1)), name=path.stem, path=path)
        )

    versions = [m.version for m in migrations]
    duplicates = {v for v in versions if versions.count(v) > 1}
    if duplicates:
        raise ValueError(f"Duplicate migration versions: {sorted(duplicates)}")

    return sorted(migrations, key=lambda m: m.version)


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     int         PRIMARY KEY,
            name        text        NOT NULL,
            applied_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def applied_versions(conn: psycopg.Connection) -> set[int]:
    _ensure_tracking_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Apply any migrations that have not run yet. Returns those applied."""
    already = applied_versions(conn)
    pending = [m for m in discover(directory) if m.version not in already]

    for migration in pending:
        # Each migration gets its own transaction, so a failure in one leaves
        # the earlier ones applied and this one entirely rolled back.
        with conn.transaction():
            conn.execute(migration.sql)  # type: ignore[arg-type]
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (migration.version, migration.name),
            )

    return pending


def main() -> None:
    """Entry point: `uv run python -m vre.migrate`."""
    from vre.config import settings

    with psycopg.connect(settings.database_url) as conn:
        applied = migrate(conn)

    if applied:
        for migration in applied:
            print(f"applied {migration.version:03d} {migration.name}")
    else:
        print("no pending migrations")


if __name__ == "__main__":
    main()
