"""Smoke-check shelve to Neon parity for Priority 0 cutover readiness."""

from __future__ import annotations

import argparse
import os
import shelve
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIR = ROOT_DIR / "app"


def _player_store_exists(db_dir: Path) -> bool:
    return any(db_dir.glob("playerdb*"))


def _history_store_exists(db_dir: Path) -> bool:
    return any(db_dir.glob("match_history*"))


def load_shelve_snapshot(db_dir: Path) -> dict[str, object]:
    players: list[str] = []
    recent_players: list[str] = []
    history_keys: list[str] = []

    if _player_store_exists(db_dir):
        with shelve.open(str(db_dir / "playerdb")) as playerdb:
            players = sorted(playerdb.keys())

    if any(db_dir.glob("recentplayers*")):
        with shelve.open(str(db_dir / "recentplayers")) as recentdb:
            raw = recentdb.get("names", [])
            if isinstance(raw, list):
                recent_players = [str(name).strip().lower() for name in raw if str(name).strip()]

    if _history_store_exists(db_dir):
        with shelve.open(str(db_dir / "match_history")) as historydb:
            history_keys = sorted(historydb.keys())

    return {
        "players": players,
        "recent_players": recent_players,
        "history_keys": history_keys,
    }


def load_neon_snapshot(database_url: str) -> dict[str, object]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required. Install dependencies from requirements.txt first.") from exc

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM players ORDER BY name")
            players = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT name FROM recent_players ORDER BY position")
            recent_players = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT id FROM match_history ORDER BY id")
            history_keys = [row[0] for row in cur.fetchall()]

    return {
        "players": players,
        "recent_players": recent_players,
        "history_keys": history_keys,
    }


def _print_check(label: str, ok: bool, details: str) -> None:
    marker = "OK" if ok else "FAIL"
    print(f"[{marker}] {label}: {details}")


def _compare_exact(label: str, left: list[str], right: list[str], failures: list[str]) -> None:
    if left == right:
        _print_check(label, True, f"{len(left)} items")
        return

    left_only = sorted(set(left) - set(right))
    right_only = sorted(set(right) - set(left))
    _print_check(
        label,
        False,
        f"left={len(left)} right={len(right)} left_only={len(left_only)} right_only={len(right_only)}",
    )

    sample_left = left_only[:10]
    sample_right = right_only[:10]
    details = [f"{label} mismatch"]
    if sample_left:
        details.append(f"left only sample: {sample_left}")
    if sample_right:
        details.append(f"right only sample: {sample_right}")
    failures.append(" | ".join(details))


def _compare_count(label: str, left: list[str], right: list[str], failures: list[str]) -> None:
    ok = len(left) == len(right)
    _print_check(label, ok, f"left={len(left)} right={len(right)}")
    if not ok:
        failures.append(f"{label} count mismatch: left={len(left)} right={len(right)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare local shelve snapshot with Neon tables")
    parser.add_argument("--db-dir", default=str(DEFAULT_DB_DIR), help="Directory containing local shelve files")
    parser.add_argument("--database-url", default=None, help="Postgres connection URL (defaults to DATABASE_URL env)")
    parser.add_argument(
        "--mode",
        choices=["counts", "strict"],
        default="strict",
        help="counts compares only row counts; strict compares full keys/lists",
    )
    args = parser.parse_args()

    db_dir = Path(args.db_dir).resolve()
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (or pass --database-url)")

    print(f"Comparing shelve at {db_dir} with Neon database")
    shelve_snapshot = load_shelve_snapshot(db_dir)
    neon_snapshot = load_neon_snapshot(database_url)

    failures: list[str] = []

    shelve_players = shelve_snapshot["players"]
    neon_players = neon_snapshot["players"]
    shelve_recent = shelve_snapshot["recent_players"]
    neon_recent = neon_snapshot["recent_players"]
    shelve_history = shelve_snapshot["history_keys"]
    neon_history = neon_snapshot["history_keys"]

    if args.mode == "counts":
        _compare_count("players", shelve_players, neon_players, failures)
        _compare_count("recent_players", shelve_recent, neon_recent, failures)
        _compare_count("match_history", shelve_history, neon_history, failures)
    else:
        _compare_exact("players", shelve_players, neon_players, failures)
        _compare_exact("recent_players", shelve_recent, neon_recent, failures)
        _compare_exact("match_history", shelve_history, neon_history, failures)

    if failures:
        print("\nParity check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nParity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
