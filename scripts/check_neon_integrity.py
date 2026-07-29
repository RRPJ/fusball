"""Report hosted schema, audit, payload, and rating replay integrity."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.neon_data_safety import (  # noqa: E402
    integrity_report,
    load_database_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Neon data integrity")
    parser.add_argument("--database-url", default=None, help="Defaults to DATABASE_URL")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    args = parser.parse_args()

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required. Install dependencies first.") from exc

    with psycopg.connect(database_url, autocommit=True) as conn:
        report = integrity_report(load_database_snapshot(conn))

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, check in report["checks"].items():
            print(f"[{'OK' if check['ok'] else 'FAIL'}] {name}")
        print(
            "Rows checked: "
            + ", ".join(f"{table}={count}" for table, count in report["table_counts"].items())
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
