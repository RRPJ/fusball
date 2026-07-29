"""Ordered, checksum-verified schema migrations for Neon/PostgreSQL."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATIONS_DIR = ROOT_DIR / "scripts" / "sql" / "migrations"
MIGRATION_FILE_PATTERN = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str
    accepted_checksums: frozenset[str]

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover_migrations(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    versions: set[str] = set()

    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")

        version = match.group("version")
        if version in versions:
            raise MigrationError(f"duplicate migration version: {version}")
        versions.add(version)

        content = path.read_bytes()
        canonical_content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        crlf_content = canonical_content.replace(b"\n", b"\r\n")
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=hashlib.sha256(canonical_content).hexdigest(),
                accepted_checksums=frozenset(
                    {
                        hashlib.sha256(content).hexdigest(),
                        hashlib.sha256(canonical_content).hexdigest(),
                        hashlib.sha256(crlf_content).hexdigest(),
                    }
                ),
            )
        )

    if not migrations:
        raise MigrationError(f"no migrations found in {migrations_dir}")
    return migrations


def apply_migrations(
    conn: Any,
    migrations: Sequence[Migration] | None = None,
) -> list[str]:
    ordered = list(migrations or discover_migrations())
    applied_now: list[str] = []

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("SELECT version, checksum FROM schema_migrations")
        applied = {str(version): str(checksum) for version, checksum in cur.fetchall()}

        for migration in ordered:
            existing_checksum = applied.get(migration.version)
            if existing_checksum is not None:
                if existing_checksum not in migration.accepted_checksums:
                    raise MigrationError(
                        f"checksum mismatch for applied migration {migration.version}"
                    )
                if existing_checksum != migration.checksum:
                    cur.execute(
                        """
                        UPDATE schema_migrations
                        SET checksum = %s
                        WHERE version = %s
                        """,
                        (migration.checksum, migration.version),
                    )
                continue

            cur.execute(migration.sql)
            cur.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum)
                VALUES (%s, %s, %s)
                """,
                (migration.version, migration.name, migration.checksum),
            )
            applied_now.append(migration.version)

    return applied_now
