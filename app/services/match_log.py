"""Helpers for writing match audit logs consistently."""

from __future__ import annotations

import time
from typing import Mapping, Sequence

PlayerName = str
PlayerRating = tuple


def _write_player_lines(
    log, name: PlayerName, before: PlayerRating, after: PlayerRating
) -> None:
    """Write before/after offensive and defensive rating lines for one player."""
    log.write(
        "                   : {}: offensive before: {}/{}  after: {}/{}\n".format(
            name, before[0].mu, before[0].sigma, after[0].mu, after[0].sigma
        )
    )
    log.write(
        "                   : {}: defensive before: {}/{}  after: {}/{}\n".format(
            name, before[1].mu, before[1].sigma, after[1].mu, after[1].sigma
        )
    )


def append_match_log(
    logfile_path: str,
    team1: Sequence[PlayerName],
    team2: Sequence[PlayerName],
    winning_team: Sequence[PlayerName],
    before_ratings: Mapping[PlayerName, PlayerRating],
    after_ratings: Mapping[PlayerName, PlayerRating],
) -> None:
    """Append a full match entry with before/after ratings per player."""
    with open(logfile_path, "a") as log:
        log.write(
            "{}: match played between {} and {}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"), team1, team2
            )
        )
        log.write("                   : won by {}\n".format(winning_team))

        ordered_players = [team1[0], team2[0]]
        if len(team1) >= 2:
            ordered_players.append(team1[1])
        if len(team2) >= 2:
            ordered_players.append(team2[1])

        for name in ordered_players:
            _write_player_lines(log, name, before_ratings[name], after_ratings[name])
