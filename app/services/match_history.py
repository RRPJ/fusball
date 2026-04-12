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
