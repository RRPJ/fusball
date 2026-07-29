"""Shared domain types for ratings and persisted match records."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

import trueskill

PlayerName = str
PlayerRating = tuple[trueskill.Rating, trueskill.Rating]
LeaderboardScope = Literal["all", "this_quarter", "this_month", "this_week"]


class RatingPayload(TypedDict):
    offense_mu: float
    offense_sigma: float
    defense_mu: float
    defense_sigma: float


class MatchPlayerPayload(TypedDict):
    name: PlayerName
    before: RatingPayload
    after: RatingPayload


class MatchRecord(TypedDict):
    timestamp: str
    source: str
    team1: list[PlayerName]
    team2: list[PlayerName]
    winner: list[PlayerName]
    score1: int
    score2: int
    players: list[MatchPlayerPayload]
    id: NotRequired[str]
    status: NotRequired[Literal["active", "voided"]]
    version: NotRequired[int]
    submitted_by: NotRequired[str]
    idempotency_key: NotRequired[str]


class MatchWriteResult(TypedDict):
    ok: bool
    team1: list[PlayerName]
    team2: list[PlayerName]
    score1: int
    score2: int
    winner: list[PlayerName]
    match_id: NotRequired[str]


class MatchLifecycleResult(TypedDict):
    match_id: str
    status: Literal["active", "voided"]
    version: int
    idempotent: bool
