"""Write-path persistence adapters for the phone API."""

from __future__ import annotations

import json
import shelve
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

import trueskill

from services.match_history import append_match_history, replay_scope_ratings
from services.match_history import query_h2h as shelve_query_h2h
from services.match_history import query_player_stats as shelve_query_player_stats
from services.match_history import query_rating_snapshots as shelve_query_rating_snapshots
from services.match_log import append_match_log
from services.match_service import calculate_rating_update

PlayerRating = tuple[trueskill.Rating, trueskill.Rating]


@dataclass
class WriteStoreConfig:
    db_dir: Path
    database_url: str | None


class BaseWriteStore:
    uses_local_lock = True

    def list_player_keys(self) -> list[str]:
        raise NotImplementedError

    def get_player_ratings(self, names: Sequence[str]) -> dict[str, PlayerRating]:
        raise NotImplementedError

    def leaderboard_ratings(self, scope: str) -> dict[str, PlayerRating]:
        raise NotImplementedError

    def query_h2h(self, p1: str, p2: str) -> dict:
        raise NotImplementedError

    def query_player_stats(self, scope: str = "all") -> dict[str, dict]:
        raise NotImplementedError

    def query_rating_snapshots(self, player: str, n: int = 10) -> list[dict]:
        raise NotImplementedError

    def missing_players(self, names: Sequence[str]) -> list[str]:
        known = set(self.list_player_keys())
        return [name for name in names if name not in known]

    def add_player(self, player_name: str) -> dict[str, object]:
        raise NotImplementedError

    def submit_match(
        self,
        team1: list[str],
        team2: list[str],
        score1: int,
        score2: int,
        source: str,
    ) -> dict[str, object]:
        raise NotImplementedError


class ShelveWriteStore(BaseWriteStore):
    uses_local_lock = True

    def __init__(self, db_dir: Path):
        self.db_dir = db_dir

    def _playerdb_exists(self) -> bool:
        return any(self.db_dir.glob("playerdb*"))

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

    def query_player_stats(self, scope: str = "all") -> dict[str, dict]:
        return shelve_query_player_stats(self.db_dir, scope)

    def query_rating_snapshots(self, player: str, n: int = 10) -> list[dict]:
        return shelve_query_rating_snapshots(self.db_dir, player, n)

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

        return {"ok": True, "name": player_name.title()}

    def submit_match(
        self,
        team1: list[str],
        team2: list[str],
        score1: int,
        score2: int,
        source: str,
    ) -> dict[str, object]:
        db_path = self.db_dir / "playerdb"
        logfile_path = self.db_dir / "logfile.log"
        winning_team = team1 if score1 > score2 else team2

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
            append_match_history(
                self.db_dir,
                team1,
                team2,
                winning_team,
                score1,
                score2,
                before_ratings,
                after_ratings,
                source=source,
            )
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

        records = self._records_for_scope(scope)
        active_players: set[str] = set()
        for record in records:
            active_players.update(str(name).strip().lower() for name in record.get("team1", []))
            active_players.update(str(name).strip().lower() for name in record.get("team2", []))

        ratings: dict[str, PlayerRating] = {
            name: (trueskill.Rating(), trueskill.Rating())
            for name in sorted(name for name in active_players if name)
        }

        for record in records:
            team1 = [str(name).strip().lower() for name in record.get("team1", [])]
            team2 = [str(name).strip().lower() for name in record.get("team2", [])]
            if not team1 or not team2:
                continue
            if any(name not in ratings for name in team1 + team2):
                continue

            score1 = int(record.get("score1", 0))
            score2 = int(record.get("score2", 0))
            updated = calculate_rating_update(ratings, team1, team2, score1, score2)
            for name in team1 + team2:
                ratings[name] = updated[name]

        return ratings

    @staticmethod
    def _parse_timestamp_utc(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _scope_window_utc(scope: str, now_utc: datetime | None = None) -> tuple[datetime, datetime] | None:
        if scope == "all":
            return None

        now_utc = now_utc or datetime.now(timezone.utc)
        local_now = now_utc.astimezone()

        if scope == "this_month":
            start_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif scope == "this_week":
            start_local = (local_now - timedelta(days=local_now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        else:
            raise ValueError(f"unsupported scope: {scope}")

        return start_local.astimezone(timezone.utc), now_utc

    def _history_records(self) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT record_payload FROM match_history ORDER BY ts ASC")
                rows = cur.fetchall()

        records: list[dict] = []
        for (payload,) in rows:
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    records.append(parsed)
            elif isinstance(payload, dict):
                records.append(payload)
        return records

    def _records_for_scope(self, scope: str) -> list[dict]:
        records = self._history_records()
        window = self._scope_window_utc(scope)
        if window is None:
            return records

        start_utc, end_utc = window
        filtered: list[dict] = []
        for record in records:
            ts = self._parse_timestamp_utc(str(record.get("timestamp", "")))
            if ts is None:
                continue
            if start_utc <= ts <= end_utc:
                filtered.append(record)
        return filtered

    @staticmethod
    def _level_from_rating_dict(rating: dict) -> float:
        return (
            (float(rating.get("offense_mu", 25.0)) - 3.0 * float(rating.get("offense_sigma", 8.333)))
            + (float(rating.get("defense_mu", 25.0)) - 3.0 * float(rating.get("defense_sigma", 8.333)))
        )

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

    def query_player_stats(self, scope: str = "all") -> dict[str, dict]:
        if scope not in {"all", "this_month", "this_week"}:
            raise ValueError(f"unsupported scope: {scope}")

        all_records = self._history_records()
        scoped_records = self._records_for_scope(scope)

        player_matches: dict[str, list[dict]] = {}
        latest_level_after: dict[str, float] = {}
        scope_baseline_level: dict[str, float] = {}

        for record in all_records:
            winner_team = [n.lower() for n in record.get("winner", [])]
            all_names = [n.lower() for n in record.get("team1", []) + record.get("team2", [])]
            entries = {e["name"].lower(): e for e in record.get("players", [])}

            for name in all_names:
                entry = entries.get(name, {})
                after = entry.get("after", {})
                level = self._level_from_rating_dict(after)
                player_matches.setdefault(name, []).append(
                    {
                        "won": name in winner_team,
                        "timestamp": record.get("timestamp", ""),
                        "level_after": round(level, 2),
                    }
                )
                latest_level_after[name] = level

        for record in scoped_records:
            entries = {e["name"].lower(): e for e in record.get("players", [])}
            for name, entry in entries.items():
                if name in scope_baseline_level:
                    continue
                before = entry.get("before", {})
                scope_baseline_level[name] = self._level_from_rating_dict(before)

        result: dict[str, dict] = {}
        for name, matches in player_matches.items():
            games = len(matches)
            wins = sum(1 for m in matches if m["won"])
            streak = 0
            for m in reversed(matches):
                if m["won"]:
                    streak += 1
                else:
                    break
            improved = 0.0
            if scope != "all" and name in scope_baseline_level:
                improved = round(latest_level_after.get(name, 0.0) - scope_baseline_level[name], 2)
            recent_form_5 = "".join("W" if m["won"] else "L" for m in matches[-5:])
            last_match = matches[-1]["timestamp"] if matches else None

            result[name] = {
                "games": games,
                "wins": wins,
                "win_rate": round(wins / games, 3) if games else 0.0,
                "streak": streak,
                "improved": improved,
                "recent_form_5": recent_form_5,
                "last_match": last_match,
            }

        return result

    def query_rating_snapshots(self, player: str, n: int = 10) -> list[dict]:
        player = player.lower()
        snapshots = []
        for record in self._history_records():
            all_names = [nm.lower() for nm in record.get("team1", []) + record.get("team2", [])]
            if player not in all_names:
                continue
            entries = {e["name"].lower(): e for e in record.get("players", [])}
            entry = entries.get(player)
            if not entry:
                continue
            snapshots.append(
                {
                    "timestamp": record.get("timestamp", ""),
                    "won": player in [nm.lower() for nm in record.get("winner", [])],
                    "before": entry.get("before", {}),
                    "after": entry.get("after", {}),
                }
            )
        return snapshots[-n:]

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
                    INSERT INTO players (name, offense_mu, offense_sigma, defense_mu, defense_sigma, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
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
    ) -> dict[str, object]:
        winning_team = team1 if score1 > score2 else team2
        players_to_lock = team1 + team2

        with self._connect() as conn:
            with conn.cursor() as cur:
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

                record_payload = {
                    "timestamp": timestamp_iso,
                    "source": source,
                    "team1": team1,
                    "team2": team2,
                    "winner": winning_team,
                    "score1": int(score1),
                    "score2": int(score2),
                    "players": players_payload,
                }

                cur.execute(
                    """
                    INSERT INTO match_history (
                        id, ts, source, team1, team2, winner, score1, score2, players_payload, record_payload
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb)
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
        }


def create_write_store(config: WriteStoreConfig) -> BaseWriteStore:
    if config.database_url:
        return NeonWriteStore(config.database_url)
    return ShelveWriteStore(config.db_dir)
