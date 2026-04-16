"""Prototype migration from shelve state to Neon Postgres.

Usage:
  python scripts/migrate_shelve_to_neon.py --db-dir app --apply

By default this script runs in dry-run mode and only reports counts.
"""

from __future__ import annotations

import argparse
import json
import os
import shelve
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIR = ROOT_DIR / "app"
SCHEMA_SQL_PATH = ROOT_DIR / "scripts" / "sql" / "neon_schema.sql"


@dataclass
class MigrationSnapshot:
    players: dict[str, tuple[Any, Any]]
    recent_players: list[str]
    history_rows: list[tuple[str, dict[str, Any]]]


def _history_store_exists(db_dir: Path) -> bool:
    return any(db_dir.glob("match_history*"))


def _player_store_exists(db_dir: Path) -> bool:
    return any(db_dir.glob("playerdb*"))


def load_shelve_snapshot(db_dir: Path) -> MigrationSnapshot:
    players: dict[str, tuple[Any, Any]] = {}
    recent_players: list[str] = []
    history_rows: list[tuple[str, dict[str, Any]]] = []

    if _player_store_exists(db_dir):
        with shelve.open(str(db_dir / "playerdb")) as playerdb:
            players = {name: playerdb[name] for name in playerdb.keys()}

    if any(db_dir.glob("recentplayers*")):
        with shelve.open(str(db_dir / "recentplayers")) as recentdb:
            names = recentdb.get("names", [])
            if isinstance(names, list):
                recent_players = [str(name).strip().lower() for name in names if str(name).strip()]

    if _history_store_exists(db_dir):
        with shelve.open(str(db_dir / "match_history")) as historydb:
            for key in sorted(historydb.keys()):
                record = historydb[key]
                if isinstance(record, dict):
                    history_rows.append((key, record))

    return MigrationSnapshot(players=players, recent_players=recent_players, history_rows=history_rows)


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def apply_schema(conn: Any) -> None:
    schema_sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema_sql)


def apply_snapshot(conn: Any, snapshot: MigrationSnapshot, reset: bool) -> None:
    with conn.cursor() as cur:
        if reset:
            cur.execute("DELETE FROM recent_players")
            cur.execute("DELETE FROM match_history")
            cur.execute("DELETE FROM players")

        for name, rating_pair in snapshot.players.items():
            offense = rating_pair[0]
            defense = rating_pair[1]
            cur.execute(
                """
                INSERT INTO players (name, offense_mu, offense_sigma, defense_mu, defense_sigma, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (name)
                DO UPDATE SET
                  offense_mu = EXCLUDED.offense_mu,
                  offense_sigma = EXCLUDED.offense_sigma,
                  defense_mu = EXCLUDED.defense_mu,
                  defense_sigma = EXCLUDED.defense_sigma,
                  updated_at = NOW()
                """,
                (
                    name,
                    float(offense.mu),
                    float(offense.sigma),
                    float(defense.mu),
                    float(defense.sigma),
                ),
            )

        cur.execute("DELETE FROM recent_players")
        for index, name in enumerate(snapshot.recent_players, start=1):
            if name not in snapshot.players:
                continue
            cur.execute(
                """
                INSERT INTO recent_players (position, name)
                VALUES (%s, %s)
                ON CONFLICT (position)
                DO UPDATE SET name = EXCLUDED.name
                """,
                (index, name),
            )

        for key, record in snapshot.history_rows:
            ts = _parse_timestamp(str(record.get("timestamp", "")))
            cur.execute(
                """
                INSERT INTO match_history (
                  id, ts, source, team1, team2, winner, score1, score2, players_payload, record_payload
                )
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (id)
                DO UPDATE SET
                  ts = EXCLUDED.ts,
                  source = EXCLUDED.source,
                  team1 = EXCLUDED.team1,
                  team2 = EXCLUDED.team2,
                  winner = EXCLUDED.winner,
                  score1 = EXCLUDED.score1,
                  score2 = EXCLUDED.score2,
                  players_payload = EXCLUDED.players_payload,
                  record_payload = EXCLUDED.record_payload
                """,
                (
                    key,
                    ts,
                    str(record.get("source", "unknown")),
                    json.dumps(record.get("team1", [])),
                    json.dumps(record.get("team2", [])),
                    json.dumps(record.get("winner", [])),
                    int(record.get("score1", 0)),
                    int(record.get("score2", 0)),
                    json.dumps(record.get("players", [])),
                    json.dumps(record),
                ),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate shelve state to Neon Postgres")
    parser.add_argument("--db-dir", default=str(DEFAULT_DB_DIR), help="Directory containing shelve files")
    parser.add_argument("--database-url", default=None, help="Postgres connection URL (defaults to DATABASE_URL env)")
    parser.add_argument("--apply", action="store_true", help="Apply migration (default is dry-run)")
    parser.add_argument("--reset", action="store_true", help="Delete target table contents before loading")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_dir = Path(args.db_dir).resolve()
    database_url = args.database_url or os.environ.get("DATABASE_URL")

    snapshot = load_shelve_snapshot(db_dir)

    print("Shelve snapshot summary:")
    print(f"- db_dir: {db_dir}")
    print(f"- players: {len(snapshot.players)}")
    print(f"- recent players: {len(snapshot.recent_players)}")
    print(f"- history records: {len(snapshot.history_rows)}")

    if not args.apply:
        print("Dry-run complete. Re-run with --apply to execute migration.")
        return 0

    if not database_url:
        raise SystemExit("DATABASE_URL is required when using --apply")

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required for --apply. Install dependencies from requirements.txt first.") from exc

    with psycopg.connect(database_url, autocommit=False) as conn:
        apply_schema(conn)
        apply_snapshot(conn, snapshot, reset=args.reset)
        conn.commit()

    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
