"""Create an encrypted logical export of the authoritative Neon database."""

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
    build_export_artifact,
    encrypt_export_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an encrypted Neon backup")
    parser.add_argument("--database-url", default=None, help="Defaults to DATABASE_URL")
    parser.add_argument("--output", required=True, help="Encrypted output path")
    args = parser.parse_args()

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    encryption_key = os.environ.get("FUSBALL_BACKUP_KEY")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    if not encryption_key:
        raise SystemExit("FUSBALL_BACKUP_KEY is required")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite existing backup: {output_path}")

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required. Install dependencies first.") from exc

    with psycopg.connect(database_url, autocommit=True) as conn:
        artifact = build_export_artifact(conn)
    output_path.write_bytes(encrypt_export_artifact(artifact, encryption_key))

    integrity = artifact["integrity"]
    print(f"Encrypted backup written: {output_path}")
    print(
        "Rows exported: "
        + ", ".join(f"{table}={count}" for table, count in integrity["table_counts"].items())
    )
    if not integrity["ok"]:
        print("WARNING: backup completed, but source integrity checks failed.")
        return 2
    print("Source integrity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
