"""Restore an encrypted Neon export into an empty isolated database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.neon_data_safety import (  # noqa: E402
    DataSafetyError,
    decrypt_export_artifact,
    restore_export_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore an encrypted Neon backup into an isolated database"
    )
    parser.add_argument("backup", help="Encrypted backup path")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Target PostgreSQL URL (defaults to RESTORE_DATABASE_URL)",
    )
    parser.add_argument(
        "--target-environment",
        required=True,
        choices=["preview", "restore-drill"],
        help="Production is intentionally not accepted",
    )
    parser.add_argument(
        "--confirm-isolated-target",
        action="store_true",
        help="Confirm the target is disposable and isolated from production",
    )
    args = parser.parse_args()

    if not args.confirm_isolated_target:
        raise SystemExit("--confirm-isolated-target is required")
    database_url = args.database_url or os.environ.get("RESTORE_DATABASE_URL")
    encryption_key = os.environ.get("FUSBALL_BACKUP_KEY")
    if not database_url:
        raise SystemExit("RESTORE_DATABASE_URL is required")
    if not encryption_key:
        raise SystemExit("FUSBALL_BACKUP_KEY is required")

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required. Install dependencies first.") from exc

    artifact = decrypt_export_artifact(Path(args.backup).read_bytes(), encryption_key)
    try:
        with psycopg.connect(database_url, autocommit=False) as conn:
            integrity = restore_export_artifact(conn, artifact)
            conn.commit()
    except DataSafetyError as exc:
        raise SystemExit(f"restore refused: {exc}") from exc

    print(f"Restore completed in isolated {args.target_environment} target.")
    print(
        "Rows restored: "
        + ", ".join(f"{table}={count}" for table, count in integrity["table_counts"].items())
    )
    print("Checksums and replay integrity passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
