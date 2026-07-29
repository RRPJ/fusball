"""Encrypted Neon exports, guarded restores, and integrity diagnostics."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

import trueskill

from services.domain_models import MatchRecord, PlayerRating
from services.match_history import replay_ratings_from_records
from services.neon_migrations import apply_migrations, discover_migrations

EXPORT_FORMAT = "fusball-neon-export"
EXPORT_FORMAT_VERSION = 1
RATING_TOLERANCE = 1e-9

TABLE_SPECS: dict[str, tuple[tuple[str, ...], str]] = {
    "players": (
        (
            "name",
            "offense_mu",
            "offense_sigma",
            "defense_mu",
            "defense_sigma",
            "updated_at",
        ),
        "name",
    ),
    "app_users": (
        (
            "provider_subject",
            "display_name",
            "role",
            "status",
            "created_at",
            "updated_at",
        ),
        "provider_subject",
    ),
    "match_history": (
        (
            "id",
            "ts",
            "source",
            "team1",
            "team2",
            "winner",
            "score1",
            "score2",
            "players_payload",
            "record_payload",
            "status",
            "version",
            "submitted_by",
            "idempotency_key",
        ),
        "ts, id",
    ),
    "recent_players": (
        ("position", "name"),
        "position",
    ),
    "rating_baselines": (
        (
            "player_name",
            "offense_mu",
            "offense_sigma",
            "defense_mu",
            "defense_sigma",
            "source",
            "captured_at",
        ),
        "player_name",
    ),
    "match_events": (
        (
            "id",
            "match_id",
            "event_type",
            "actor_subject",
            "reason",
            "request_id",
            "from_status",
            "to_status",
            "created_at",
        ),
        "created_at, id",
    ),
}

RESTORE_ORDER = (
    "players",
    "app_users",
    "match_history",
    "recent_players",
    "rating_baselines",
    "match_events",
)

JSON_COLUMNS = {
    "match_history": {
        "team1",
        "team2",
        "winner",
        "players_payload",
        "record_payload",
    }
}


class DataSafetyError(RuntimeError):
    pass


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _json_value(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _migration_manifest() -> list[dict[str, str]]:
    return [
        {
            "version": migration.version,
            "name": migration.name,
            "checksum": migration.checksum,
        }
        for migration in discover_migrations()
    ]


def _read_schema_migrations(cur: Any) -> list[dict[str, str]]:
    cur.execute(
        """
        SELECT version, name, checksum
        FROM schema_migrations
        ORDER BY version
        """
    )
    recorded = [
        {"version": str(version), "name": str(name), "checksum": str(checksum)}
        for version, name, checksum in cur.fetchall()
    ]
    expected = {migration.version: migration for migration in discover_migrations()}
    for item in recorded:
        migration = expected.get(item["version"])
        if migration and item["checksum"] in migration.accepted_checksums:
            item["checksum"] = migration.checksum
    return recorded


def _read_tables(cur: Any) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for table, (columns, order_by) in TABLE_SPECS.items():
        cur.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order_by}")
        tables[table] = [
            {column: _json_value(value) for column, value in zip(columns, row, strict=True)}
            for row in cur.fetchall()
        ]
    return tables


def load_database_snapshot(conn: Any) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_setting('server_version')")
        database_name, server_version = cur.fetchone()
        migrations = _read_schema_migrations(cur)
        tables = _read_tables(cur)
    return {
        "database": {
            "name": str(database_name),
            "server_version": str(server_version),
        },
        "migrations": migrations,
        "tables": tables,
    }


def _ratings_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    name_column: str,
) -> dict[str, PlayerRating]:
    return {
        str(row[name_column]): (
            trueskill.Rating(
                mu=float(row["offense_mu"]),
                sigma=float(row["offense_sigma"]),
            ),
            trueskill.Rating(
                mu=float(row["defense_mu"]),
                sigma=float(row["defense_sigma"]),
            ),
        )
        for row in rows
    }


def _ratings_match(left: PlayerRating, right: PlayerRating) -> bool:
    return all(
        abs(left_rating.mu - right_rating.mu) <= RATING_TOLERANCE
        and abs(left_rating.sigma - right_rating.sigma) <= RATING_TOLERANCE
        for left_rating, right_rating in zip(left, right)
    )


def _records_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[MatchRecord]:
    records: list[MatchRecord] = []
    for row in rows:
        payload = row["record_payload"]
        if not isinstance(payload, Mapping):
            raise DataSafetyError(f"match {row['id']} has an invalid record payload")
        record = dict(payload)
        record["id"] = str(row["id"])
        record["status"] = str(row["status"])
        record["version"] = int(row["version"])
        records.append(record)  # type: ignore[arg-type]
    return records


def integrity_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    tables = snapshot["tables"]
    checks: dict[str, dict[str, Any]] = {}

    expected_migrations = _migration_manifest()
    actual_migrations = snapshot["migrations"]
    schema_ok = actual_migrations == expected_migrations
    checks["schema"] = {
        "ok": schema_ok,
        "expected_versions": [item["version"] for item in expected_migrations],
        "applied_versions": [item["version"] for item in actual_migrations],
    }

    players = _ratings_from_rows(tables["players"], name_column="name")
    baselines = _ratings_from_rows(
        tables["rating_baselines"],
        name_column="player_name",
    )
    coverage_ok = set(players) == set(baselines)
    checks["baseline_coverage"] = {
        "ok": coverage_ok,
        "missing": sorted(set(players) - set(baselines)),
        "extra": sorted(set(baselines) - set(players)),
    }

    payload_mismatches: list[str] = []
    for row in tables["match_history"]:
        payload = row["record_payload"]
        if not isinstance(payload, Mapping):
            payload_mismatches.append(str(row["id"]))
            continue
        expected_payload = {
            "team1": row["team1"],
            "team2": row["team2"],
            "winner": row["winner"],
            "score1": int(row["score1"]),
            "score2": int(row["score2"]),
        }
        if any(payload.get(key) != value for key, value in expected_payload.items()):
            payload_mismatches.append(str(row["id"]))
    checks["match_payloads"] = {
        "ok": not payload_mismatches,
        "mismatched_match_ids": payload_mismatches,
    }

    rating_mismatches: list[str] = []
    replay_hash = None
    materialized_hash = _sha256(
        {
            name: [
                rating[0].mu,
                rating[0].sigma,
                rating[1].mu,
                rating[1].sigma,
            ]
            for name, rating in sorted(players.items())
        }
    )
    if coverage_ok:
        records = _records_from_rows(tables["match_history"])
        replayed = replay_ratings_from_records(records, baselines)
        rating_mismatches = sorted(
            name
            for name in set(players) | set(replayed)
            if name not in players
            or name not in replayed
            or not _ratings_match(players[name], replayed[name])
        )
        replay_hash = _sha256(
            {
                name: [
                    rating[0].mu,
                    rating[0].sigma,
                    rating[1].mu,
                    rating[1].sigma,
                ]
                for name, rating in sorted(replayed.items())
            }
        )
    checks["rating_replay"] = {
        "ok": coverage_ok and not rating_mismatches,
        "mismatched_players": rating_mismatches,
        "materialized_sha256": materialized_hash,
        "replayed_sha256": replay_hash,
    }

    events_by_match: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in tables["match_events"]:
        events_by_match[str(event["match_id"])].append(event)
    audit_mismatches: list[str] = []
    for match in tables["match_history"]:
        match_id = str(match["id"])
        events = events_by_match.get(match_id, [])
        has_submit = any(event["event_type"] == "submit" for event in events)
        latest_status = events[-1]["to_status"] if events else None
        if not has_submit or latest_status != match["status"]:
            audit_mismatches.append(match_id)
    checks["lifecycle_audit"] = {
        "ok": not audit_mismatches,
        "mismatched_match_ids": audit_mismatches,
        "event_counts": {
            event_type: sum(
                1 for event in tables["match_events"] if event["event_type"] == event_type
            )
            for event_type in ("submit", "void", "restore")
        },
    }

    table_counts = {table: len(rows) for table, rows in tables.items()}
    table_checksums = {table: _sha256(rows) for table, rows in tables.items()}
    return {
        "ok": all(check["ok"] for check in checks.values()),
        "checks": checks,
        "table_counts": table_counts,
        "table_sha256": table_checksums,
    }


def build_export_artifact(conn: Any) -> dict[str, Any]:
    snapshot = load_database_snapshot(conn)
    artifact: dict[str, Any] = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": snapshot["database"],
        "schema": {"migrations": snapshot["migrations"]},
        "tables": snapshot["tables"],
        "integrity": integrity_report(snapshot),
    }
    artifact["artifact_sha256"] = _sha256(artifact)
    return artifact


def validate_export_artifact(artifact: Mapping[str, Any]) -> None:
    if artifact.get("format") != EXPORT_FORMAT:
        raise DataSafetyError("unsupported backup format")
    if artifact.get("format_version") != EXPORT_FORMAT_VERSION:
        raise DataSafetyError("unsupported backup format version")

    supplied_checksum = artifact.get("artifact_sha256")
    unsigned = dict(artifact)
    unsigned.pop("artifact_sha256", None)
    if supplied_checksum != _sha256(unsigned):
        raise DataSafetyError("backup artifact checksum mismatch")

    tables = artifact.get("tables")
    if not isinstance(tables, Mapping) or set(tables) != set(TABLE_SPECS):
        raise DataSafetyError("backup artifact table set is incomplete")
    for table, rows in tables.items():
        if not isinstance(rows, list):
            raise DataSafetyError(f"backup table {table} is invalid")
        expected_columns = set(TABLE_SPECS[table][0])
        if any(not isinstance(row, Mapping) or set(row) != expected_columns for row in rows):
            raise DataSafetyError(f"backup table {table} has incompatible columns")

    migrations = artifact.get("schema", {}).get("migrations")
    if migrations != _migration_manifest():
        raise DataSafetyError("backup schema is not compatible with this application version")

    integrity = artifact.get("integrity")
    if not isinstance(integrity, Mapping):
        raise DataSafetyError("backup integrity metadata is missing")
    expected_table_checksums = integrity.get("table_sha256")
    actual_table_checksums = {table: _sha256(rows) for table, rows in tables.items()}
    if expected_table_checksums != actual_table_checksums:
        raise DataSafetyError("backup table checksum mismatch")


def encrypt_export_artifact(artifact: Mapping[str, Any], encryption_key: str) -> bytes:
    try:
        from cryptography.fernet import Fernet
    except ModuleNotFoundError as exc:
        raise DataSafetyError("cryptography is required for encrypted backups") from exc
    validate_export_artifact(artifact)
    try:
        return Fernet(encryption_key.encode("ascii")).encrypt(_canonical_json(artifact))
    except (TypeError, ValueError) as exc:
        raise DataSafetyError("invalid backup encryption key") from exc


def decrypt_export_artifact(payload: bytes, encryption_key: str) -> dict[str, Any]:
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ModuleNotFoundError as exc:
        raise DataSafetyError("cryptography is required for encrypted backups") from exc
    try:
        decrypted = Fernet(encryption_key.encode("ascii")).decrypt(payload)
    except (InvalidToken, TypeError, ValueError) as exc:
        raise DataSafetyError("backup decryption failed") from exc
    try:
        artifact = json.loads(decrypted)
    except json.JSONDecodeError as exc:
        raise DataSafetyError("backup payload is not valid JSON") from exc
    if not isinstance(artifact, dict):
        raise DataSafetyError("backup payload must be an object")
    validate_export_artifact(artifact)
    return artifact


def _assert_restore_target_empty(cur: Any) -> None:
    nonempty: list[str] = []
    for table in TABLE_SPECS:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)")
        if cur.fetchone()[0]:
            nonempty.append(table)
    if nonempty:
        raise DataSafetyError(
            f"restore target is not empty; populated tables: {', '.join(nonempty)}"
        )


def restore_export_artifact(conn: Any, artifact: Mapping[str, Any]) -> dict[str, Any]:
    validate_export_artifact(artifact)
    apply_migrations(conn)

    with conn.cursor() as cur:
        if _read_schema_migrations(cur) != artifact["schema"]["migrations"]:
            raise DataSafetyError("restore target schema is incompatible with the backup")
        _assert_restore_target_empty(cur)

        try:
            from psycopg.types.json import Jsonb
        except ModuleNotFoundError as exc:
            raise DataSafetyError("psycopg is required for Neon restore") from exc

        for table in RESTORE_ORDER:
            columns = TABLE_SPECS[table][0]
            placeholders = ", ".join(["%s"] * len(columns))
            statement = f"INSERT INTO {table} ({', '.join(columns)}) " f"VALUES ({placeholders})"
            rows = []
            for row in artifact["tables"][table]:
                rows.append(
                    tuple(
                        (
                            Jsonb(row[column])
                            if column in JSON_COLUMNS.get(table, set())
                            else row[column]
                        )
                        for column in columns
                    )
                )
            if rows:
                cur.executemany(statement, rows)

    restored_snapshot = load_database_snapshot(conn)
    restored_integrity = integrity_report(restored_snapshot)
    if not restored_integrity["ok"]:
        raise DataSafetyError("restored data failed integrity verification")
    if restored_integrity["table_sha256"] != artifact["integrity"]["table_sha256"]:
        raise DataSafetyError("restored data does not match backup table checksums")
    return restored_integrity


def check_neon_readiness(database_url: str) -> dict[str, Any]:
    try:
        import psycopg
    except ModuleNotFoundError:
        return {"ok": False, "store": "neon", "reason": "driver_unavailable"}

    expected = _migration_manifest()
    try:
        with psycopg.connect(database_url, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                required_tables = ["schema_migrations", *TABLE_SPECS]
                cur.execute(
                    "SELECT name, to_regclass('public.' || name) "
                    "FROM unnest(%s::text[]) AS name",
                    (required_tables,),
                )
                missing_tables = [
                    str(name) for name, relation in cur.fetchall() if relation is None
                ]
                if missing_tables:
                    return {
                        "ok": False,
                        "store": "neon",
                        "reason": "schema_incompatible",
                        "missing_tables": missing_tables,
                    }
                applied = _read_schema_migrations(cur)
    except Exception:
        return {"ok": False, "store": "neon", "reason": "database_unavailable"}

    if applied != expected:
        return {
            "ok": False,
            "store": "neon",
            "reason": "schema_incompatible",
            "expected_versions": [item["version"] for item in expected],
            "applied_versions": [item["version"] for item in applied],
        }
    return {
        "ok": True,
        "store": "neon",
        "schema_version": expected[-1]["version"],
    }
