"""Helpers for append-only structured match history persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shelve
from typing import Mapping, Sequence
from uuid import uuid4

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


def query_player_stats(db_dir: str | Path) -> dict[str, dict]:
    """Return aggregate stats per player from all history records."""
    player_matches: dict[str, list[dict]] = {}

    for record in _all_records(db_dir):
        winner_team = [n.lower() for n in record.get("winner", [])]
        all_names = [n.lower() for n in record.get("team1", []) + record.get("team2", [])]
        entries = {e["name"].lower(): e for e in record.get("players", [])}

        for name in all_names:
            entry = entries.get(name, {})
            after = entry.get("after", {})
            level = (
                (after.get("offense_mu", 25.0) - 3.0 * after.get("offense_sigma", 8.333)) +
                (after.get("defense_mu", 25.0) - 3.0 * after.get("defense_sigma", 8.333))
            )
            player_matches.setdefault(name, []).append({
                "won": name in winner_team,
                "timestamp": record.get("timestamp", ""),
                "level_after": round(level, 2),
            })

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
        recent = matches[-10:]
        improved = round(recent[-1]["level_after"] - recent[0]["level_after"], 2) if len(recent) >= 2 else 0.0
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
