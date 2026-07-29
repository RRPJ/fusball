"""Write-path persistence adapters for the phone API."""

from __future__ import annotations

import json
import shelve
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

import trueskill

from services.domain_models import (
    MatchLifecycleResult,
    MatchRecord,
    MatchWriteResult,
    PlayerRating,
)
from services.match_history import (
    append_match_history,
    query_player_profile_from_records,
    query_player_stats_from_records,
    query_rating_snapshots_from_records,
    query_team_h2h_from_records,
    records_in_scope,
    replay_ratings_from_records,
    replay_scope_ratings,
)
from services.match_history import query_h2h as shelve_query_h2h
from services.match_history import query_player_profile as shelve_query_player_profile
from services.match_history import query_player_stats as shelve_query_player_stats
from services.match_history import query_rating_snapshots as shelve_query_rating_snapshots
from services.match_history import query_team_h2h as shelve_query_team_h2h
from services.match_log import append_match_log
from services.match_service import calculate_rating_update
from services.neon_data_safety import check_neon_readiness
from services.store_contracts import (
    BaseWriteStore,
    LifecycleConflict,
    ReplayParityError,
    WriteStoreConfig,
)

RATING_TOLERANCE = 1e-9
# How long a player stays "checked in" for lineup assignment on the durable
# (Neon) presence store before it expires automatically. This bounds
# staleness if someone forgets to check out, without requiring a background
# sweeper: every read filters `expires_at > NOW()`.
PRESENCE_TTL_SECONDS = 8 * 60 * 60


def _ratings_match(left: PlayerRating, right: PlayerRating) -> bool:
    return all(
        abs(left_rating.mu - right_rating.mu) <= RATING_TOLERANCE
        and abs(left_rating.sigma - right_rating.sigma) <= RATING_TOLERANCE
        for left_rating, right_rating in zip(left, right)
    )


class ShelveWriteStore(BaseWriteStore):
    uses_local_lock = True

    def __init__(self, db_dir: Path):
        self.db_dir = db_dir
        # Presence has no shelve-backed persistence: it mirrors the
        # long-standing in-process behavior of the phone API, where a
        # single long-running server process tracks who is "checked in"
        # for the lifetime of that process.
        self._active_presence: set[str] = set()

    def _playerdb_exists(self) -> bool:
        return any(self.db_dir.glob("playerdb*"))

    def readiness(self) -> dict[str, object]:
        if not self.db_dir.exists() or not self.db_dir.is_dir():
            return {"ok": False, "store": "shelve", "reason": "data_directory_unavailable"}
        try:
            self.list_player_keys()
        except Exception:
            return {"ok": False, "store": "shelve", "reason": "store_unavailable"}
        return {"ok": True, "store": "shelve"}

    def list_player_keys(self) -> list[str]:
        if not self._playerdb_exists():
            return []
        with shelve.open(str(self.db_dir / "playerdb")) as players:
            return sorted(players.keys())

    def get_player_ratings(self, names: Sequence[str]) -> dict[str, PlayerRating]:
        with shelve.open(str(self.db_dir / "playerdb")) as players:
            return {name: players[name] for name in names if name in players}

    def leaderboard_ratings(self, scope: str) -> dict[str, PlayerRating]:
        if scope == "all":
            if not self._playerdb_exists():
                return {}
            with shelve.open(str(self.db_dir / "playerdb")) as players:
                return dict(players.items())
        return replay_scope_ratings(self.db_dir, scope)

    def query_h2h(self, p1: str, p2: str) -> dict:
        return shelve_query_h2h(self.db_dir, p1, p2)

    def query_team_h2h(self, team1: Sequence[str], team2: Sequence[str]) -> dict:
        return shelve_query_team_h2h(self.db_dir, team1, team2)

    def query_player_stats(self, scope: str = "all") -> dict[str, dict]:
        return shelve_query_player_stats(self.db_dir, scope)

    def query_player_profile(
        self, player: str, scope: str = "all", recent_limit: int = 5
    ) -> dict[str, object]:
        return shelve_query_player_profile(
            self.db_dir, player, scope=scope, recent_limit=recent_limit
        )

    def query_rating_snapshots(self, player: str, n: int = 10) -> list[dict]:
        return shelve_query_rating_snapshots(self.db_dir, player, n)

    def list_match_events(self, match_id: str) -> list[dict[str, object]]:
        if not any(self.db_dir.glob("match_events*")):
            return []
        with shelve.open(str(self.db_dir / "match_events")) as events:
            matching = [
                dict(event) for event in events.values() if event.get("match_id") == match_id
            ]
        return sorted(
            matching,
            key=lambda event: (str(event.get("created_at", "")), str(event.get("id", ""))),
        )

    def list_match_lifecycle(
        self,
        limit: int = 50,
        include_voided: bool = True,
    ) -> list[dict[str, object]]:
        records = self._all_history_records()
        result: list[dict[str, object]] = []
        for match_id in reversed(sorted(records)):
            record = records[match_id]
            status = record.get("status", "active")
            if not include_voided and status != "active":
                continue
            result.append(
                {
                    "id": match_id,
                    "timestamp": record.get("timestamp", ""),
                    "team1": list(record.get("team1", [])),
                    "team2": list(record.get("team2", [])),
                    "score1": int(record.get("score1", 0)),
                    "score2": int(record.get("score2", 0)),
                    "status": status,
                    "version": int(record.get("version", 1)),
                    "submitted_by": record.get("submitted_by"),
                    "events": self.list_match_events(match_id),
                }
            )
            if len(result) >= limit:
                break
        return result

    def list_active_presence(self) -> list[str]:
        return sorted(self._active_presence)

    def set_presence(self, name: str, active: bool) -> None:
        if active:
            self._active_presence.add(name)
        else:
            self._active_presence.discard(name)

    def clear_presence(self) -> None:
        self._active_presence.clear()

    def add_player(self, player_name: str) -> dict[str, object]:
        db_path = self.db_dir / "playerdb"
        with shelve.open(str(db_path)) as players:
            if player_name in players:
                raise ValueError("player already exists")
            players[player_name] = (trueskill.Rating(), trueskill.Rating())

        with shelve.open(str(self.db_dir / "recentplayers")) as recent:
            names = recent.get("names", [])
            merged = [player_name] + [n for n in names if n != player_name]
            recent["names"] = merged

        with shelve.open(str(self.db_dir / "rating_baselines")) as baselines:
            baselines[player_name] = (trueskill.Rating(), trueskill.Rating())

        return {"ok": True, "name": player_name.title()}

    def submit_match(
        self,
        team1: list[str],
        team2: list[str],
        score1: int,
        score2: int,
        source: str,
        actor_subject: str = "legacy:shared-credential",
        idempotency_key: str | None = None,
    ) -> MatchWriteResult:
        db_path = self.db_dir / "playerdb"
        logfile_path = self.db_dir / "logfile.log"
        winning_team = team1 if score1 > score2 else team2

        if idempotency_key and any(self.db_dir.glob("match_history*")):
            with shelve.open(str(self.db_dir / "match_history")) as history:
                for match_id in history:
                    record = history[match_id]
                    if record.get("idempotency_key") == idempotency_key:
                        if (
                            list(record["team1"]) != team1
                            or list(record["team2"]) != team2
                            or int(record["score1"]) != score1
                            or int(record["score2"]) != score2
                        ):
                            raise LifecycleConflict(
                                "idempotency key was already used for another match"
                            )
                        return {
                            "ok": True,
                            "team1": list(record["team1"]),
                            "team2": list(record["team2"]),
                            "score1": int(record["score1"]),
                            "score2": int(record["score2"]),
                            "winner": list(record["winner"]),
                            "match_id": match_id,
                        }

        with shelve.open(str(db_path)) as players:
            before_ratings = {name: players[name] for team in (team1, team2) for name in team}
            updated = calculate_rating_update(players, team1, team2, score1, score2)
            for name in team1 + team2:
                players[name] = updated[name]
            after_ratings = {name: players[name] for team in (team1, team2) for name in team}

        try:
            append_match_log(
                str(logfile_path),
                team1,
                team2,
                winning_team,
                before_ratings,
                after_ratings,
            )
            match_id = append_match_history(
                self.db_dir,
                team1,
                team2,
                winning_team,
                score1,
                score2,
                before_ratings,
                after_ratings,
                source=source,
                actor_subject=actor_subject,
                idempotency_key=idempotency_key,
            )
            with shelve.open(str(self.db_dir / "match_events")) as events:
                event_id = uuid4().hex
                events[event_id] = {
                    "id": event_id,
                    "match_id": match_id,
                    "event_type": "submit",
                    "actor_subject": actor_subject,
                    "reason": None,
                    "request_id": idempotency_key,
                    "from_status": None,
                    "to_status": "active",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception:
            with shelve.open(str(db_path)) as players:
                for name, rating in before_ratings.items():
                    players[name] = rating
            raise

        return {
            "ok": True,
            "team1": team1,
            "team2": team2,
            "score1": score1,
            "score2": score2,
            "winner": winning_team,
            "match_id": match_id,
        }

    def _all_history_records(self) -> dict[str, MatchRecord]:
        if not any(self.db_dir.glob("match_history*")):
            return {}
        with shelve.open(str(self.db_dir / "match_history")) as history:
            return {match_id: history[match_id] for match_id in history}

    def _baseline_ratings(
        self,
        records: dict[str, MatchRecord],
        current: dict[str, PlayerRating],
    ) -> dict[str, PlayerRating]:
        with shelve.open(str(self.db_dir / "rating_baselines")) as baseline_store:
            baselines = dict(baseline_store.items())
            missing = set(current) - set(baselines)
            for match_id in sorted(records):
                for player in records[match_id].get("players", []):
                    name = player["name"].lower()
                    if name not in missing:
                        continue
                    before = player["before"]
                    baselines[name] = (
                        trueskill.Rating(
                            mu=float(before["offense_mu"]),
                            sigma=float(before["offense_sigma"]),
                        ),
                        trueskill.Rating(
                            mu=float(before["defense_mu"]),
                            sigma=float(before["defense_sigma"]),
                        ),
                    )
                    missing.remove(name)
            for name in missing:
                baselines[name] = current[name]
            for name, rating in baselines.items():
                baseline_store[name] = rating
        return baselines

    def _replayed_local_ratings(
        self,
        records: dict[str, MatchRecord],
        current: dict[str, PlayerRating],
    ) -> dict[str, PlayerRating]:
        baselines = self._baseline_ratings(records, current)
        ordered = [records[match_id] for match_id in sorted(records)]
        return replay_ratings_from_records(ordered, baselines)

    def change_match_status(
        self,
        match_id: str,
        target_status: str,
        actor_subject: str,
        reason: str,
        request_id: str,
        expected_version: int | None = None,
    ) -> MatchLifecycleResult:
        if target_status not in {"active", "voided"}:
            raise ValueError("target status must be active or voided")

        with shelve.open(str(self.db_dir / "match_events")) as events:
            for event in events.values():
                if event.get("request_id") == request_id:
                    if event["match_id"] != match_id or event["to_status"] != target_status:
                        raise LifecycleConflict(
                            "request ID was already used for another lifecycle change"
                        )
                    record = self._all_history_records()[event["match_id"]]
                    return {
                        "match_id": event["match_id"],
                        "status": record.get("status", "active"),
                        "version": int(record.get("version", 1)),
                        "idempotent": True,
                    }

        records = self._all_history_records()
        if match_id not in records:
            raise KeyError(match_id)
        record = records[match_id]
        current_status = record.get("status", "active")
        current_version = int(record.get("version", 1))
        if expected_version is not None and expected_version != current_version:
            raise LifecycleConflict("match version changed")
        if current_status == target_status:
            raise LifecycleConflict(f"match is already {target_status}")

        with shelve.open(str(self.db_dir / "playerdb")) as players:
            current = dict(players.items())
        replayed_before = self._replayed_local_ratings(records, current)
        if set(replayed_before) != set(current) or any(
            not _ratings_match(replayed_before[name], current[name]) for name in current
        ):
            raise ReplayParityError("materialized ratings do not match active history replay")

        updated_record = dict(record)
        updated_record["status"] = target_status
        updated_record["version"] = current_version + 1
        records[match_id] = updated_record
        replayed_after = self._replayed_local_ratings(records, current)

        try:
            with shelve.open(str(self.db_dir / "playerdb")) as players:
                for name, rating in replayed_after.items():
                    players[name] = rating
            with shelve.open(str(self.db_dir / "match_history")) as history:
                history[match_id] = updated_record
            with shelve.open(str(self.db_dir / "match_events")) as events:
                event_id = uuid4().hex
                events[event_id] = {
                    "id": event_id,
                    "match_id": match_id,
                    "event_type": "restore" if target_status == "active" else "void",
                    "actor_subject": actor_subject,
                    "reason": reason,
                    "request_id": request_id,
                    "from_status": current_status,
                    "to_status": target_status,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception:
            with shelve.open(str(self.db_dir / "playerdb")) as players:
                for name, rating in current.items():
                    players[name] = rating
            with shelve.open(str(self.db_dir / "match_history")) as history:
                history[match_id] = record
            raise

        return {
            "match_id": match_id,
            "status": target_status,
            "version": current_version + 1,
            "idempotent": False,
        }


class NeonWriteStore(BaseWriteStore):
    uses_local_lock = False

    def __init__(self, database_url: str):
        self.database_url = database_url
        try:
            import psycopg  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required for Neon write store") from exc
        self._psycopg = psycopg

    def _connect(self):
        return self._psycopg.connect(self.database_url, autocommit=False)

    def readiness(self) -> dict[str, object]:
        return check_neon_readiness(self.database_url)

    def list_player_keys(self) -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM players ORDER BY name")
                return [row[0] for row in cur.fetchall()]

    def get_player_ratings(self, names: Sequence[str]) -> dict[str, PlayerRating]:
        if not names:
            return {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name, offense_mu, offense_sigma, defense_mu, defense_sigma
                    FROM players
                    WHERE name = ANY(%s)
                    """,
                    (list(names),),
                )
                rows = cur.fetchall()

        ratings: dict[str, PlayerRating] = {}
        for name, o_mu, o_sigma, d_mu, d_sigma in rows:
            ratings[name] = (
                trueskill.Rating(mu=float(o_mu), sigma=float(o_sigma)),
                trueskill.Rating(mu=float(d_mu), sigma=float(d_sigma)),
            )
        return ratings

    def leaderboard_ratings(self, scope: str) -> dict[str, PlayerRating]:
        if scope == "all":
            keys = self.list_player_keys()
            return self.get_player_ratings(keys)

        return replay_ratings_from_records(self._records_for_scope(scope))

    def _history_records(self) -> list[MatchRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, status, version, submitted_by, idempotency_key,
                           record_payload
                    FROM match_history
                    ORDER BY ts ASC, id ASC
                    """
                )
                rows = cur.fetchall()

        return [
            record
            for record in self._decode_history_rows(rows)
            if record.get("status", "active") == "active"
        ]

    @staticmethod
    def _decode_history_rows(rows) -> list[MatchRecord]:
        records: list[MatchRecord] = []
        for match_id, status, version, submitted_by, idempotency_key, payload in rows:
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    record = parsed
                else:
                    continue
            elif isinstance(payload, dict):
                record = payload
            else:
                continue
            record = dict(record)
            record["id"] = str(match_id)
            record["status"] = str(status)
            record["version"] = int(version)
            if submitted_by:
                record["submitted_by"] = str(submitted_by)
            if idempotency_key:
                record["idempotency_key"] = str(idempotency_key)
            records.append(record)
        return records

    @staticmethod
    def _ratings_from_rows(rows) -> dict[str, PlayerRating]:
        return {
            str(name): (
                trueskill.Rating(mu=float(o_mu), sigma=float(o_sigma)),
                trueskill.Rating(mu=float(d_mu), sigma=float(d_sigma)),
            )
            for name, o_mu, o_sigma, d_mu, d_sigma in rows
        }

    def _transaction_ratings(self, cur) -> dict[str, PlayerRating]:
        cur.execute(
            """
            SELECT name, offense_mu, offense_sigma, defense_mu, defense_sigma
            FROM players
            ORDER BY name
            """
        )
        return self._ratings_from_rows(cur.fetchall())

    def _transaction_baselines(self, cur) -> dict[str, PlayerRating]:
        cur.execute(
            """
            SELECT player_name, offense_mu, offense_sigma,
                   defense_mu, defense_sigma
            FROM rating_baselines
            ORDER BY player_name
            """
        )
        return self._ratings_from_rows(cur.fetchall())

    def _transaction_history(self, cur) -> list[MatchRecord]:
        cur.execute(
            """
            SELECT id, status, version, submitted_by, idempotency_key,
                   record_payload
            FROM match_history
            ORDER BY ts ASC, id ASC
            """
        )
        return self._decode_history_rows(cur.fetchall())

    def _replayed_transaction_ratings(self, cur) -> dict[str, PlayerRating]:
        current = self._transaction_ratings(cur)
        baselines = self._transaction_baselines(cur)
        if set(baselines) != set(current):
            missing = sorted(set(current) - set(baselines))
            extra = sorted(set(baselines) - set(current))
            raise ReplayParityError(
                f"rating baseline coverage mismatch; missing={missing}, extra={extra}"
            )
        return replay_ratings_from_records(self._transaction_history(cur), baselines)

    def _assert_transaction_replay_parity(self, cur) -> None:
        current = self._transaction_ratings(cur)
        replayed = self._replayed_transaction_ratings(cur)
        if set(replayed) != set(current):
            raise ReplayParityError("replayed player set does not match materialized players")
        mismatched = [name for name in current if not _ratings_match(current[name], replayed[name])]
        if mismatched:
            raise ReplayParityError(
                f"materialized ratings do not match active history replay: {mismatched}"
            )

    @staticmethod
    def _write_transaction_ratings(cur, ratings: dict[str, PlayerRating]) -> None:
        for name, rating in ratings.items():
            cur.execute(
                """
                UPDATE players
                SET offense_mu = %s,
                    offense_sigma = %s,
                    defense_mu = %s,
                    defense_sigma = %s,
                    updated_at = NOW()
                WHERE name = %s
                """,
                (
                    float(rating[0].mu),
                    float(rating[0].sigma),
                    float(rating[1].mu),
                    float(rating[1].sigma),
                    name,
                ),
            )

    def _records_for_scope(self, scope: str) -> list[MatchRecord]:
        return records_in_scope(self._history_records(), scope)

    def query_h2h(self, p1: str, p2: str) -> dict:
        p1, p2 = p1.lower(), p2.lower()
        p1_wins = p2_wins = draws = count = 0
        last_match: str | None = None

        for record in self._history_records():
            t1 = [n.lower() for n in record.get("team1", [])]
            t2 = [n.lower() for n in record.get("team2", [])]
            p1_t1 = p1 in t1
            p1_t2 = p1 in t2
            p2_t1 = p2 in t1
            p2_t2 = p2 in t2
            if not ((p1_t1 and p2_t2) or (p1_t2 and p2_t1)):
                continue

            count += 1
            last_match = record.get("timestamp")
            winner_team = [n.lower() for n in record.get("winner", [])]

            if p1_t1:
                p1_side, p2_side = t1, t2
            else:
                p1_side, p2_side = t2, t1

            if any(n in winner_team for n in p1_side):
                p1_wins += 1
            elif any(n in winner_team for n in p2_side):
                p2_wins += 1
            else:
                draws += 1

        return {
            "p1": p1,
            "p2": p2,
            "matches": count,
            "p1_wins": p1_wins,
            "p2_wins": p2_wins,
            "draws": draws,
            "last_match": last_match,
        }

    def query_team_h2h(self, team1: Sequence[str], team2: Sequence[str]) -> dict:
        return query_team_h2h_from_records(self._history_records(), team1, team2)

    def query_player_stats(self, scope: str = "all") -> dict[str, dict]:
        if scope not in {"all", "this_quarter", "this_month", "this_week"}:
            raise ValueError(f"unsupported scope: {scope}")

        all_records = self._history_records()
        scoped_records = self._records_for_scope(scope)
        return query_player_stats_from_records(all_records, scoped_records)

    def query_player_profile(
        self, player: str, scope: str = "all", recent_limit: int = 5
    ) -> dict[str, object]:
        if scope not in {"all", "this_quarter", "this_month", "this_week"}:
            raise ValueError(f"unsupported scope: {scope}")
        all_records = self._history_records()
        scoped_records = self._records_for_scope(scope)
        return query_player_profile_from_records(
            all_records, scoped_records, player, recent_limit=recent_limit
        )

    def query_rating_snapshots(self, player: str, n: int = 10) -> list[dict]:
        return query_rating_snapshots_from_records(self._history_records(), player, n)

    def list_match_events(self, match_id: str) -> list[dict[str, object]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, event_type, actor_subject, reason, request_id,
                           from_status, to_status, created_at
                    FROM match_events
                    WHERE match_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (match_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "id": str(event_id),
                "event_type": str(event_type),
                "actor_subject": str(actor_subject),
                "reason": reason,
                "request_id": request_id,
                "from_status": from_status,
                "to_status": str(to_status),
                "created_at": created_at.isoformat(),
            }
            for (
                event_id,
                event_type,
                actor_subject,
                reason,
                request_id,
                from_status,
                to_status,
                created_at,
            ) in rows
        ]

    def list_match_lifecycle(
        self,
        limit: int = 50,
        include_voided: bool = True,
    ) -> list[dict[str, object]]:
        where = "" if include_voided else "WHERE status = 'active'"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, status, version, submitted_by, idempotency_key,
                           record_payload
                    FROM match_history
                    {where}
                    ORDER BY ts DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                records = self._decode_history_rows(cur.fetchall())

            match_ids = [record["id"] for record in records]
            events_by_match = self._list_match_events_for_ids(conn, match_ids)

        return [
            {
                "id": record["id"],
                "timestamp": record.get("timestamp", ""),
                "team1": list(record.get("team1", [])),
                "team2": list(record.get("team2", [])),
                "score1": int(record.get("score1", 0)),
                "score2": int(record.get("score2", 0)),
                "status": record.get("status", "active"),
                "version": int(record.get("version", 1)),
                "submitted_by": record.get("submitted_by"),
                "events": events_by_match.get(record["id"], []),
            }
            for record in records
        ]

    @staticmethod
    def _list_match_events_for_ids(
        conn, match_ids: list[str]
    ) -> dict[str, list[dict[str, object]]]:
        """Batch-load lifecycle events for many matches in a single query.

        `list_match_lifecycle` previously called `list_match_events` once per
        match (each opening its own connection), an N+1 query pattern that
        scales linearly with the requested page size. Loading every match's
        events in one round trip keeps the admin match list query count
        constant regardless of `limit`.
        """
        grouped: dict[str, list[dict[str, object]]] = {match_id: [] for match_id in match_ids}
        if not match_ids:
            return grouped

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT match_id, id, event_type, actor_subject, reason, request_id,
                       from_status, to_status, created_at
                FROM match_events
                WHERE match_id = ANY(%s)
                ORDER BY match_id, created_at ASC, id ASC
                """,
                (match_ids,),
            )
            rows = cur.fetchall()

        for (
            match_id,
            event_id,
            event_type,
            actor_subject,
            reason,
            request_id,
            from_status,
            to_status,
            created_at,
        ) in rows:
            grouped.setdefault(str(match_id), []).append(
                {
                    "id": str(event_id),
                    "event_type": str(event_type),
                    "actor_subject": str(actor_subject),
                    "reason": reason,
                    "request_id": request_id,
                    "from_status": from_status,
                    "to_status": str(to_status),
                    "created_at": created_at.isoformat(),
                }
            )
        return grouped

    def list_active_presence(self) -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT player_name FROM player_presence WHERE expires_at > NOW() "
                    "ORDER BY player_name"
                )
                return [row[0] for row in cur.fetchall()]

    def set_presence(self, name: str, active: bool) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if active:
                    cur.execute(
                        """
                        INSERT INTO player_presence (player_name, marked_active_at, expires_at)
                        VALUES (%s, NOW(), NOW() + %s * INTERVAL '1 second')
                        ON CONFLICT (player_name) DO UPDATE
                        SET marked_active_at = NOW(),
                            expires_at = NOW() + %s * INTERVAL '1 second'
                        """,
                        (name, PRESENCE_TTL_SECONDS, PRESENCE_TTL_SECONDS),
                    )
                else:
                    cur.execute(
                        "DELETE FROM player_presence WHERE player_name = %s",
                        (name,),
                    )
            conn.commit()

    def clear_presence(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM player_presence")
            conn.commit()

    def add_player(self, player_name: str) -> dict[str, object]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM players WHERE name = %s", (player_name,))
                if cur.fetchone():
                    raise ValueError("player already exists")

                offense = trueskill.Rating()
                defense = trueskill.Rating()
                cur.execute(
                    """
                    INSERT INTO players (
                        name, offense_mu, offense_sigma,
                        defense_mu, defense_sigma, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    """,
                    (player_name, offense.mu, offense.sigma, defense.mu, defense.sigma),
                )
                cur.execute(
                    """
                    INSERT INTO rating_baselines (
                        player_name, offense_mu, offense_sigma,
                        defense_mu, defense_sigma, source
                    )
                    VALUES (%s, %s, %s, %s, %s, 'player_creation')
                    ON CONFLICT (player_name) DO NOTHING
                    """,
                    (player_name, offense.mu, offense.sigma, defense.mu, defense.sigma),
                )

                cur.execute("SELECT name FROM recent_players ORDER BY position")
                existing = [row[0] for row in cur.fetchall()]
                merged = [player_name] + [name for name in existing if name != player_name]
                cur.execute("DELETE FROM recent_players")
                for index, name in enumerate(merged, start=1):
                    cur.execute(
                        "INSERT INTO recent_players (position, name) VALUES (%s, %s)",
                        (index, name),
                    )

            conn.commit()

        return {"ok": True, "name": player_name.title()}

    @staticmethod
    def _rating_payload(rating: PlayerRating) -> dict[str, float]:
        return {
            "offense_mu": float(rating[0].mu),
            "offense_sigma": float(rating[0].sigma),
            "defense_mu": float(rating[1].mu),
            "defense_sigma": float(rating[1].sigma),
        }

    def submit_match(
        self,
        team1: list[str],
        team2: list[str],
        score1: int,
        score2: int,
        source: str,
        actor_subject: str = "legacy:shared-credential",
        idempotency_key: str | None = None,
    ) -> MatchWriteResult:
        winning_team = team1 if score1 > score2 else team2
        players_to_lock = team1 + team2

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('fusball-rating-replay'))")
                if idempotency_key:
                    cur.execute(
                        """
                        SELECT id, record_payload
                        FROM match_history
                        WHERE idempotency_key = %s
                        """,
                        (idempotency_key,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        payload = dict(existing[1])
                        if (
                            list(payload["team1"]) != team1
                            or list(payload["team2"]) != team2
                            or int(payload["score1"]) != score1
                            or int(payload["score2"]) != score2
                        ):
                            raise LifecycleConflict(
                                "idempotency key was already used for another match"
                            )
                        return {
                            "ok": True,
                            "team1": list(payload["team1"]),
                            "team2": list(payload["team2"]),
                            "score1": int(payload["score1"]),
                            "score2": int(payload["score2"]),
                            "winner": list(payload["winner"]),
                            "match_id": str(existing[0]),
                        }

                cur.execute(
                    """
                    SELECT name, offense_mu, offense_sigma, defense_mu, defense_sigma
                    FROM players
                    WHERE name = ANY(%s)
                    FOR UPDATE
                    """,
                    (players_to_lock,),
                )
                rows = cur.fetchall()
                if len(rows) != len(players_to_lock):
                    existing = {row[0] for row in rows}
                    missing = [name for name in players_to_lock if name not in existing]
                    raise ValueError(f"missing players: {', '.join(missing)}")

                current: dict[str, PlayerRating] = {}
                for name, o_mu, o_sigma, d_mu, d_sigma in rows:
                    current[name] = (
                        trueskill.Rating(mu=float(o_mu), sigma=float(o_sigma)),
                        trueskill.Rating(mu=float(d_mu), sigma=float(d_sigma)),
                    )

                before_ratings = {name: current[name] for name in players_to_lock}
                updated = calculate_rating_update(current, team1, team2, score1, score2)

                for name in players_to_lock:
                    rating = updated[name]
                    cur.execute(
                        """
                        UPDATE players
                        SET offense_mu = %s,
                            offense_sigma = %s,
                            defense_mu = %s,
                            defense_sigma = %s,
                            updated_at = NOW()
                        WHERE name = %s
                        """,
                        (
                            float(rating[0].mu),
                            float(rating[0].sigma),
                            float(rating[1].mu),
                            float(rating[1].sigma),
                            name,
                        ),
                    )

                after_ratings = {name: updated[name] for name in players_to_lock}
                timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                history_id = f"{timestamp_iso}_{uuid4().hex[:8]}"

                ordered_players = [name for name in players_to_lock]
                players_payload = []
                for name in ordered_players:
                    players_payload.append(
                        {
                            "name": name,
                            "before": self._rating_payload(before_ratings[name]),
                            "after": self._rating_payload(after_ratings[name]),
                        }
                    )

                record_payload: MatchRecord = {
                    "id": history_id,
                    "timestamp": timestamp_iso,
                    "source": source,
                    "team1": team1,
                    "team2": team2,
                    "winner": winning_team,
                    "score1": int(score1),
                    "score2": int(score2),
                    "players": players_payload,
                    "status": "active",
                    "version": 1,
                    "submitted_by": actor_subject,
                }
                if idempotency_key:
                    record_payload["idempotency_key"] = idempotency_key

                cur.execute(
                    """
                    INSERT INTO match_history (
                        id, ts, source, team1, team2, winner,
                        score1, score2, players_payload, record_payload,
                        status, version, submitted_by, idempotency_key
                    )
                    VALUES (
                        %s, %s, %s, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s, %s, %s::jsonb, %s::jsonb,
                        'active', 1, %s, %s
                    )
                    """,
                    (
                        history_id,
                        datetime.now(timezone.utc),
                        source,
                        json.dumps(team1),
                        json.dumps(team2),
                        json.dumps(winning_team),
                        int(score1),
                        int(score2),
                        json.dumps(players_payload),
                        json.dumps(record_payload),
                        actor_subject,
                        idempotency_key,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO match_events (
                        id, match_id, event_type, actor_subject, reason,
                        request_id, from_status, to_status
                    )
                    VALUES (%s, %s, 'submit', %s, NULL, %s, NULL, 'active')
                    """,
                    (
                        uuid4().hex,
                        history_id,
                        actor_subject,
                        idempotency_key,
                    ),
                )

            conn.commit()

        return {
            "ok": True,
            "team1": team1,
            "team2": team2,
            "score1": score1,
            "score2": score2,
            "winner": winning_team,
            "match_id": history_id,
        }

    def change_match_status(
        self,
        match_id: str,
        target_status: str,
        actor_subject: str,
        reason: str,
        request_id: str,
        expected_version: int | None = None,
    ) -> MatchLifecycleResult:
        if target_status not in {"active", "voided"}:
            raise ValueError("target status must be active or voided")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('fusball-rating-replay'))")
                cur.execute(
                    """
                    SELECT match_id, to_status
                    FROM match_events
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )
                existing_event = cur.fetchone()
                if existing_event:
                    if (
                        str(existing_event[0]) != match_id
                        or str(existing_event[1]) != target_status
                    ):
                        raise LifecycleConflict(
                            "request ID was already used for another lifecycle change"
                        )
                    cur.execute(
                        "SELECT status, version FROM match_history WHERE id = %s",
                        (existing_event[0],),
                    )
                    existing_match = cur.fetchone()
                    if existing_match is None:
                        raise RuntimeError("idempotent lifecycle event has no match")
                    return {
                        "match_id": str(existing_event[0]),
                        "status": str(existing_match[0]),
                        "version": int(existing_match[1]),
                        "idempotent": True,
                    }

                self._assert_transaction_replay_parity(cur)
                cur.execute(
                    """
                    SELECT status, version
                    FROM match_history
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (match_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(match_id)

                current_status = str(row[0])
                current_version = int(row[1])
                if expected_version is not None and expected_version != current_version:
                    raise LifecycleConflict("match version changed")
                if current_status == target_status:
                    raise LifecycleConflict(f"match is already {target_status}")

                next_version = current_version + 1
                cur.execute(
                    """
                    UPDATE match_history
                    SET status = %s, version = %s
                    WHERE id = %s
                    """,
                    (target_status, next_version, match_id),
                )
                cur.execute(
                    """
                    INSERT INTO match_events (
                        id, match_id, event_type, actor_subject, reason,
                        request_id, from_status, to_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid4().hex,
                        match_id,
                        "restore" if target_status == "active" else "void",
                        actor_subject,
                        reason,
                        request_id,
                        current_status,
                        target_status,
                    ),
                )

                replayed = self._replayed_transaction_ratings(cur)
                self._write_transaction_ratings(cur, replayed)

            conn.commit()

        return {
            "match_id": match_id,
            "status": target_status,
            "version": next_version,
            "idempotent": False,
        }


def create_write_store(config: WriteStoreConfig) -> BaseWriteStore:
    if config.database_url:
        return NeonWriteStore(config.database_url)
    return ShelveWriteStore(config.db_dir)
