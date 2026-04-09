"""Helpers for reading and shaping player leaderboard data.

This module keeps ranking logic out of screen classes so UI code can stay focused
on rendering and interaction.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

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
