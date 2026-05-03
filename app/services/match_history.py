"""Helpers for append-only structured match history persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import shelve
from typing import Mapping, Sequence
from uuid import uuid4

import trueskill

from services.match_service import calculate_rating_update

PlayerName = str
PlayerRating = tuple

HISTORY_DB_NAME = "match_history"


def _rating_pair_dict(rating: PlayerRating) -> dict[str, float]:
    return {
        "offense_mu": float(rating[0].mu),
        "offense_sigma": float(rating[0].sigma),
        "defense_mu": float(rating[1].mu),
        "defense_sigma": float(rating[1].sigma),
    }


def _history_key(timestamp_iso: str) -> str:
    # Timestamp prefix keeps natural sort order by time for basic scans.
    return f"{timestamp_iso}_{uuid4().hex[:8]}"


def append_match_history(
    db_dir: str | Path,
    team1: Sequence[PlayerName],
    team2: Sequence[PlayerName],
    winning_team: Sequence[PlayerName],
    score1: int,
    score2: int,
    before_ratings: Mapping[PlayerName, PlayerRating],
    after_ratings: Mapping[PlayerName, PlayerRating],
    source: str,
) -> str:
    """Append one structured match history record and return its key."""
    path = Path(db_dir)
    timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    key = _history_key(timestamp_iso)

    ordered_players = [name for name in list(team1) + list(team2)]
    players_payload = []
    for name in ordered_players:
        players_payload.append(
            {
                "name": name,
                "before": _rating_pair_dict(before_ratings[name]),
                "after": _rating_pair_dict(after_ratings[name]),
            }
        )

    record = {
        "timestamp": timestamp_iso,
        "source": source,
        "team1": list(team1),
        "team2": list(team2),
        "winner": list(winning_team),
        "score1": int(score1),
        "score2": int(score2),
        "players": players_payload,
    }

    with shelve.open(str(path / HISTORY_DB_NAME)) as history:
        history[key] = record

    return key


def _all_records(db_dir: str | Path) -> list[dict]:
    """Return all history records sorted by ISO timestamp key (ascending)."""
    path = Path(db_dir)
    if not any(path.glob(f"{HISTORY_DB_NAME}*")):
        return []
    with shelve.open(str(path / HISTORY_DB_NAME)) as history:
        return [history[k] for k in sorted(history.keys())]


def _level_from_rating_dict(rating: dict) -> float:
    offense_level = float(rating.get("offense_mu", 25.0)) - 3.0 * float(rating.get("offense_sigma", 8.333))
    defense_level = float(rating.get("defense_mu", 25.0)) - 3.0 * float(rating.get("defense_sigma", 8.333))
    return (offense_level + defense_level) / 2


def _parse_timestamp_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


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


def records_for_scope(db_dir: str | Path, scope: str, now_utc: datetime | None = None) -> list[dict]:
    records = _all_records(db_dir)
    window = _scope_window_utc(scope, now_utc)
    if window is None:
        return records

    start_utc, end_utc = window
    filtered: list[dict] = []
    for record in records:
        ts = _parse_timestamp_utc(record.get("timestamp", ""))
        if ts is None:
            continue
        if start_utc <= ts <= end_utc:
            filtered.append(record)
    return filtered


def replay_scope_ratings(
    db_dir: str | Path,
    scope: str,
    now_utc: datetime | None = None,
) -> dict[str, PlayerRating]:
    """Replay ratings from fresh defaults using only matches in the selected scope."""
    scoped_records = records_for_scope(db_dir, scope, now_utc)
    active_players: set[str] = set()
    for record in scoped_records:
        active_players.update(name.lower() for name in record.get("team1", []))
        active_players.update(name.lower() for name in record.get("team2", []))

    ratings: dict[str, PlayerRating] = {
        name: (trueskill.Rating(), trueskill.Rating())
        for name in sorted(active_players)
    }

    for record in scoped_records:
        team1 = [name.lower() for name in record.get("team1", [])]
        team2 = [name.lower() for name in record.get("team2", [])]
        score1 = int(record.get("score1", 0))
        score2 = int(record.get("score2", 0))
        if not team1 or not team2:
            continue
        if any(name not in ratings for name in team1 + team2):
            continue

        updated = calculate_rating_update(ratings, team1, team2, score1, score2)
        for name in team1 + team2:
            ratings[name] = updated[name]

    return ratings


def query_h2h(db_dir: str | Path, p1: str, p2: str) -> dict:
    """Return head-to-head stats for two players playing on opposing teams."""
    p1, p2 = p1.lower(), p2.lower()
    p1_wins = p2_wins = draws = count = 0
    last_match: str | None = None

    for record in _all_records(db_dir):
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


def query_player_stats(db_dir: str | Path, scope: str = "all") -> dict[str, dict]:
    """Return aggregate stats per player and scope-aware improved delta."""
    if scope not in {"all", "this_month", "this_week"}:
        raise ValueError(f"unsupported scope: {scope}")

    all_records = _all_records(db_dir)
    scoped_records = records_for_scope(db_dir, scope)
    stat_records = all_records if scope == "all" else scoped_records

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
            level = _level_from_rating_dict(after)
            player_matches.setdefault(name, []).append({
                "won": name in winner_team,
                "timestamp": record.get("timestamp", ""),
                "level_after": round(level, 2),
            })
            latest_level_after[name] = level

    player_matches = {}
    for record in stat_records:
        winner_team = [n.lower() for n in record.get("winner", [])]
        all_names = [n.lower() for n in record.get("team1", []) + record.get("team2", [])]

        for name in all_names:
            player_matches.setdefault(name, []).append({
                "won": name in winner_team,
                "timestamp": record.get("timestamp", ""),
            })

    for record in scoped_records:
        entries = {e["name"].lower(): e for e in record.get("players", [])}
        for name, entry in entries.items():
            if name in scope_baseline_level:
                continue
            before = entry.get("before", {})
            scope_baseline_level[name] = _level_from_rating_dict(before)

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


def query_rating_snapshots(db_dir: str | Path, player: str, n: int = 10) -> list[dict]:
    """Return the last n rating snapshots for one player from history."""
    player = player.lower()
    snapshots = []
    for record in _all_records(db_dir):
        all_names = [nm.lower() for nm in record.get("team1", []) + record.get("team2", [])]
        if player not in all_names:
            continue
        entries = {e["name"].lower(): e for e in record.get("players", [])}
        entry = entries.get(player)
        if not entry:
            continue
        snapshots.append({
            "timestamp": record.get("timestamp", ""),
            "won": player in [nm.lower() for nm in record.get("winner", [])],
            "before": entry.get("before", {}),
            "after": entry.get("after", {}),
        })
    return snapshots[-n:]
