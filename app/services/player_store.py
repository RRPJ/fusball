"""Helpers for reading and shaping player leaderboard data.

This module keeps ranking logic out of screen classes so UI code can stay focused
on rendering and interaction.
"""

from __future__ import annotations

import shelve
from typing import Dict, Iterable, List, Sequence, Tuple

import trueskill

from odds import playerLevel

PlayerName = str
PlayerRating = tuple
RankedPlayers = List[Tuple[PlayerName, PlayerRating]]


def ranked_players(players: Iterable[Tuple[PlayerName, PlayerRating]]) -> RankedPlayers:
    """Return players sorted by descending exposed skill level."""
    return sorted(players, key=lambda kv: playerLevel(kv[1]), reverse=True)


def rank_labels_by_name(ranked: Sequence[Tuple[PlayerName, PlayerRating]]) -> Dict[PlayerName, str]:
    """Build rank labels for each player.

    Players with the same rounded skill exposure share a rank range,
    for example "3-5".
    """
    rounded_levels = [round(playerLevel(rating)) for _, rating in ranked]
    labels: Dict[PlayerName, str] = {}

    for index, (name, _) in enumerate(ranked, start=1):
        level = rounded_levels[index - 1]
        matching_positions = [pos for pos, value in enumerate(rounded_levels, start=1) if value == level]
        min_rank = matching_positions[0]
        max_rank = matching_positions[-1]
        labels[name] = str(min_rank) if min_rank == max_rank else f"{min_rank}-{max_rank}"

    return labels


def player_names() -> List[PlayerName]:
    """Return all player names from persistent storage."""
    with shelve.open("playerdb") as players:
        return list(players.keys())


def player_exists(name: PlayerName) -> bool:
    """Return whether a player exists in persistent storage."""
    with shelve.open("playerdb") as players:
        return name in players


def add_player_if_missing(name: PlayerName) -> bool:
    """Create a default offense/defense rating entry when absent.

    Returns True when a new player was added, otherwise False.
    """
    with shelve.open("playerdb") as players:
        if name in players:
            return False
        players[name] = (trueskill.Rating(), trueskill.Rating())
        return True


def ensure_recent_players_initialized() -> None:
    """Ensure the recent player list exists in storage."""
    with shelve.open("recentplayers") as recentplayers:
        if "names" not in recentplayers:
            recentplayers["names"] = []


def recent_player_names() -> List[PlayerName]:
    """Return the stored list of recent player names."""
    ensure_recent_players_initialized()
    with shelve.open("recentplayers") as recentplayers:
        return list(recentplayers["names"])


def add_recent_player(name: PlayerName) -> None:
    """Insert a player at the front of recent names, keeping uniqueness."""
    lname = name.lower()
    with shelve.open("recentplayers") as recentplayers:
        names = recentplayers.get("names", [])
        merged = [lname]
        for existing in names:
            if existing not in merged:
                merged.append(existing)
        recentplayers["names"] = merged
