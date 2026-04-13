"""Shared match domain logic used by multiple screens.

This module centralizes odds and rating update calculations so gameplay logic
stays consistent across UI flows.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

import trueskill
from odds import odds_texts, win_probability

PlayerName = str
PlayerRating = tuple


def _team_ratings(players: Mapping[PlayerName, PlayerRating], names: Sequence[PlayerName]) -> list:
    """Return existing player ratings for team names in order."""
    return [players[name] for name in names if name in players]


def odds_ratio_for_teams(
    players: Mapping[PlayerName, PlayerRating],
    team1: Sequence[PlayerName],
    team2: Sequence[PlayerName],
) -> Tuple[float, str]:
    """Return win probability and nearest display ratio for two teams."""
    team1_ratings = _team_ratings(players, team1)
    team2_ratings = _team_ratings(players, team2)

    probability = 0.5
    if len(team1_ratings) > 0 and len(team2_ratings) > 0:
        probability = win_probability(team1_ratings, team2_ratings)

    ratio = sorted(odds_texts, key=lambda x: abs(x[1] - probability))[0][0]
    return probability, ratio


def calculate_rating_update(
    players: Mapping[PlayerName, PlayerRating],
    team1: Sequence[PlayerName],
    team2: Sequence[PlayerName],
    score1: int,
    score2: int,
) -> Dict[PlayerName, PlayerRating]:
    """Compute updated offense/defense ratings for a finished match."""
    # Start with offensive players.
    new_ratings = [[players[team1[0]][0]], [players[team2[0]][0]]]

    # For 1v1, use the same player's defensive rating.
    if len(team1) > 1:
        new_ratings[0].append(players[team1[1]][1])
    else:
        new_ratings[0].append(players[team1[0]][1])

    if len(team2) > 1:
        new_ratings[1].append(players[team2[1]][1])
    else:
        new_ratings[1].append(players[team2[0]][1])

    rating_pairs = (tuple(new_ratings[0]), tuple(new_ratings[1]))

    draws = min(score1, score2)
    wins = max(score1, score2) - draws

    for _ in range(draws):
        rating_pairs = trueskill.rate(rating_pairs, ranks=[1, 1])

    team1_won = score1 > score2
    for _ in range(wins):
        rating_pairs = trueskill.rate(rating_pairs, ranks=[0, 1] if team1_won else [1, 0])

    updated = dict(players.items())
    updated[team1[0]] = (rating_pairs[0][0], updated[team1[0]][1])
    updated[team2[0]] = (rating_pairs[1][0], updated[team2[0]][1])

    if len(team1) > 1:
        updated[team1[1]] = (updated[team1[1]][0], rating_pairs[0][1])
    else:
        updated[team1[0]] = (updated[team1[0]][0], rating_pairs[0][1])

    if len(team2) > 1:
        updated[team2[1]] = (updated[team2[1]][0], rating_pairs[1][1])
    else:
        updated[team2[0]] = (updated[team2[0]][0], rating_pairs[1][1])

    return updated


def best_balanced_lineup(
    players: Mapping[PlayerName, PlayerRating],
    defense_a: PlayerName,
    offense_a: PlayerName,
    offense_b: PlayerName,
    defense_b: PlayerName,
) -> Optional[list[PlayerName]]:
    """Return the best lineup ordering for balanced match quality.

    The returned order is compatible with the UI selected player slots:
    [team A defense, team A offense, team B offense, team B defense].
    Returns None when any referenced player is missing.
    """
    names = [defense_a, offense_a, offense_b, defense_b]
    if any(name not in players for name in names):
        return None

    p = players  # short alias for readability in the options table below
    options = [
        ([offense_a, defense_a, offense_b, defense_b],
         [(p[defense_a][0], p[offense_a][1]), (p[offense_b][0], p[defense_b][1])]),
        ([offense_a, defense_a, defense_b, offense_b],
         [(p[defense_a][0], p[offense_a][1]), (p[defense_b][0], p[offense_b][1])]),
        ([defense_a, offense_a, offense_b, defense_b],
         [(p[offense_a][0], p[defense_a][1]), (p[offense_b][0], p[defense_b][1])]),
        ([defense_a, offense_a, defense_b, offense_b],
         [(p[offense_a][0], p[defense_a][1]), (p[defense_b][0], p[offense_b][1])]),
        ([offense_b, defense_a, offense_a, defense_b],
         [(p[defense_a][0], p[offense_b][1]), (p[offense_a][0], p[defense_b][1])]),
        ([offense_b, defense_a, defense_b, offense_a],
         [(p[defense_a][0], p[offense_b][1]), (p[defense_b][0], p[offense_a][1])]),
        ([defense_a, offense_b, offense_a, defense_b],
         [(p[offense_b][0], p[defense_a][1]), (p[offense_a][0], p[defense_b][1])]),
        ([defense_a, offense_b, defense_b, offense_a],
         [(p[offense_b][0], p[defense_a][1]), (p[defense_b][0], p[offense_a][1])]),
        ([defense_b, defense_a, offense_a, offense_b],
         [(p[defense_a][0], p[defense_b][1]), (p[offense_a][0], p[offense_b][1])]),
        ([defense_b, defense_a, offense_b, offense_a],
         [(p[defense_a][0], p[defense_b][1]), (p[offense_b][0], p[offense_a][1])]),
        ([defense_a, defense_b, offense_a, offense_b],
         [(p[defense_b][0], p[defense_a][1]), (p[offense_a][0], p[offense_b][1])]),
        ([defense_a, defense_b, offense_b, offense_a],
         [(p[defense_b][0], p[defense_a][1]), (p[offense_b][0], p[offense_a][1])]),
    ]
    return max(options, key=lambda option: trueskill.quality(option[1]))[0]
