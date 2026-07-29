"""Compare local shelve state with hosted Neon data and replay integrity."""

from __future__ import annotations

import argparse
import os
import shelve
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIR = ROOT_DIR / "app"
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.neon_data_safety import (  # noqa: E402
    integrity_report,
    load_database_snapshot,
)


def _rating_payload(rating_pair: tuple[Any, Any]) -> list[float]:
    return [
        float(rating_pair[0].mu),
        float(rating_pair[0].sigma),
        float(rating_pair[1].mu),
        float(rating_pair[1].sigma),
    ]


def _normalized_match(match_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": match_id,
        "timestamp": str(record.get("timestamp", "")),
        "source": str(record.get("source", "unknown")),
        "team1": list(record.get("team1", [])),
        "team2": list(record.get("team2", [])),
        "winner": list(record.get("winner", [])),
        "score1": int(record.get("score1", 0)),
        "score2": int(record.get("score2", 0)),
        "players": list(record.get("players", [])),
        "status": str(record.get("status", "active")),
        "version": int(record.get("version", 1)),
    }


def load_shelve_snapshot(db_dir: Path) -> dict[str, Any]:
    players: dict[str, list[float]] = {}
    recent_players: list[str] = []
    matches: dict[str, dict[str, Any]] = {}

    if any(db_dir.glob("playerdb*")):
        with shelve.open(str(db_dir / "playerdb")) as playerdb:
            players = {
                str(name): _rating_payload(playerdb[name]) for name in sorted(playerdb.keys())
            }

    if any(db_dir.glob("recentplayers*")):
        with shelve.open(str(db_dir / "recentplayers")) as recentdb:
            raw = recentdb.get("names", [])
            if isinstance(raw, list):
                recent_players = [str(name).strip().lower() for name in raw if str(name).strip()]

    if any(db_dir.glob("match_history*")):
        with shelve.open(str(db_dir / "match_history")) as historydb:
            for key in sorted(historydb.keys()):
                record = historydb[key]
                if isinstance(record, Mapping):
                    matches[str(key)] = _normalized_match(str(key), record)

    return {
        "players": players,
        "recent_players": recent_players,
        "matches": matches,
    }


def load_neon_snapshot(database_url: str) -> dict[str, Any]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "psycopg is required. Install dependencies from requirements.txt first."
        ) from exc

    with psycopg.connect(database_url, autocommit=True) as conn:
        raw = load_database_snapshot(conn)
    report = integrity_report(raw)
    tables = raw["tables"]
    players = {
        str(row["name"]): [
            float(row["offense_mu"]),
            float(row["offense_sigma"]),
            float(row["defense_mu"]),
            float(row["defense_sigma"]),
        ]
        for row in tables["players"]
    }
    matches: dict[str, dict[str, Any]] = {}
    for row in tables["match_history"]:
        payload = row["record_payload"]
        if not isinstance(payload, Mapping):
            continue
        normalized = _normalized_match(str(row["id"]), payload)
        normalized["status"] = str(row["status"])
        normalized["version"] = int(row["version"])
        matches[str(row["id"])] = normalized

    return {
        "players": players,
        "recent_players": [str(row["name"]) for row in tables["recent_players"]],
        "matches": matches,
        "integrity": report,
    }


def _print_check(label: str, ok: bool, details: str) -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {details}")


def _compare_count(
    label: str,
    left: Mapping[str, Any] | list[Any],
    right: Mapping[str, Any] | list[Any],
    failures: list[str],
) -> None:
    ok = len(left) == len(right)
    _print_check(label, ok, f"shelve={len(left)} neon={len(right)}")
    if not ok:
        failures.append(f"{label} count mismatch: shelve={len(left)} neon={len(right)}")


def _compare_exact(
    label: str,
    left: Mapping[str, Any] | list[Any],
    right: Mapping[str, Any] | list[Any],
    failures: list[str],
) -> None:
    if left == right:
        _print_check(label, True, f"{len(left)} items")
        return
    _print_check(label, False, f"shelve={len(left)} neon={len(right)}")
    failures.append(f"{label} content mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare local shelve state with Neon tables and replay integrity"
    )
    parser.add_argument(
        "--db-dir",
        default=str(DEFAULT_DB_DIR),
        help="Directory containing local shelve files",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres connection URL (defaults to DATABASE_URL)",
    )
    parser.add_argument(
        "--mode",
        choices=["counts", "strict"],
        default="strict",
        help="counts compares row counts; strict compares ratings and match payloads",
    )
    args = parser.parse_args()

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (or pass --database-url)")

    db_dir = Path(args.db_dir).resolve()
    print(f"Comparing shelve at {db_dir} with Neon database")
    local = load_shelve_snapshot(db_dir)
    hosted = load_neon_snapshot(database_url)
    failures: list[str] = []

    for key, label in (
        ("players", "players"),
        ("recent_players", "recent players"),
        ("matches", "match history"),
    ):
        if args.mode == "counts":
            _compare_count(label, local[key], hosted[key], failures)
        else:
            _compare_exact(label, local[key], hosted[key], failures)

    integrity = hosted["integrity"]
    _print_check(
        "Neon replay and audit integrity",
        integrity["ok"],
        ", ".join(
            f"{name}={'ok' if check['ok'] else 'failed'}"
            for name, check in integrity["checks"].items()
        ),
    )
    if not integrity["ok"]:
        failures.append("Neon replay or audit integrity failed")

    event_counts = integrity["checks"]["lifecycle_audit"]["event_counts"]
    print("Audit events: " + ", ".join(f"{name}={count}" for name, count in event_counts.items()))

    if failures:
        print("\nParity check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nParity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
