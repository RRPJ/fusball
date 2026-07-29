"""Apply ordered schema migrations to Neon/PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.neon_migrations import apply_migrations, discover_migrations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Fusball Neon schema migrations")
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL connection URL (defaults to DATABASE_URL)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply pending migrations; otherwise only list discovered migrations",
    )
    args = parser.parse_args()

    migrations = discover_migrations()
    for migration in migrations:
        print(f"{migration.version} {migration.name} {migration.checksum[:12]}")

    if not args.apply:
        print("Dry-run complete. Re-run with --apply to execute migrations.")
        return 0

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required when using --apply")

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required. Install dependencies first.") from exc

    with psycopg.connect(database_url, autocommit=False) as conn:
        applied = apply_migrations(conn, migrations)
        conn.commit()

    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("Schema is already current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
