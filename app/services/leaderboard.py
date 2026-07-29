"""Leaderboard row rendering shared by the phone API read routes and view."""

from __future__ import annotations

from string import capwords

import trueskill
from odds import playerLevel

from services.player_store import rank_labels_by_name, ranked_players
from services.store_contracts import BaseWriteStore


def load_leaderboard(
    store: BaseWriteStore, limit: int = 50, scope: str = "all"
) -> list[dict[str, object]]:
    ratings = store.leaderboard_ratings(scope)
    if not ratings:
        return []

    ranked = ranked_players(ratings.items())
    labels = rank_labels_by_name(ranked)

    rows = []
    for index, (name, rating) in enumerate(ranked[:limit], start=1):
        rows.append(
            {
                "position": index,
                "name": capwords(name),
                "rank": labels[name],
                "level": round(playerLevel(rating), 2),
                "offense_level": round(trueskill.expose(rating[0]), 2),
                "defense_level": round(trueskill.expose(rating[1]), 2),
                "offense_mu": round(rating[0].mu, 2),
                "offense_sigma": round(rating[0].sigma, 2),
                "defense_mu": round(rating[1].mu, 2),
                "defense_sigma": round(rating[1].sigma, 2),
            }
        )
    return rows
