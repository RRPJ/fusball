"""Pure request-payload validation and lineup/duplicate helpers.

These helpers have no Flask or persistence-adapter dependency so they can be
shared by the phone runtime's blueprint modules without introducing circular
imports between `phone_api` and the route blueprints.
"""

from __future__ import annotations

import random
import re

from services.store_contracts import BaseWriteStore

MATCH_DUPLICATE_WINDOW_SECONDS = 60.0
_RECENT_MATCH_SIGNATURES: dict[str, float] = {}


def reset_recent_match_signatures() -> None:
    """Clear duplicate-submit tracking state (used on app creation/tests)."""
    _RECENT_MATCH_SIGNATURES.clear()


def match_signature(team1: list[str], team2: list[str], score1: int, score2: int) -> str:
    return f"{','.join(team1)}|{','.join(team2)}|{score1}|{score2}"


def is_recent_duplicate(signature: str, now_monotonic: float) -> bool:
    expiry = now_monotonic - MATCH_DUPLICATE_WINDOW_SECONDS
    stale = [sig for sig, ts in _RECENT_MATCH_SIGNATURES.items() if ts < expiry]
    for sig in stale:
        del _RECENT_MATCH_SIGNATURES[sig]
    return signature in _RECENT_MATCH_SIGNATURES


def remember_match_signature(signature: str, now_monotonic: float) -> None:
    _RECENT_MATCH_SIGNATURES[signature] = now_monotonic


def default_selected_slots() -> dict[str, str | None]:
    return {
        "red_offense": None,
        "red_defense": None,
        "blue_offense": None,
        "blue_defense": None,
    }


def required_slots_for_mode(mode: str) -> list[str]:
    if mode == "doubles":
        return ["red_defense", "red_offense", "blue_defense", "blue_offense"]
    if mode == "singles":
        return ["red_offense", "blue_offense"]
    raise ValueError("mode must be 'singles' or 'doubles'")


def lineup_from_active_players(active_players: set[str], mode: str) -> dict[str, str | None]:
    required_slots = required_slots_for_mode(mode)
    if len(active_players) < len(required_slots):
        raise ValueError(f"need at least {len(required_slots)} active players for {mode}")

    picked = random.sample(sorted(active_players), len(required_slots))
    selected = default_selected_slots()
    for index, slot in enumerate(required_slots):
        selected[slot] = picked[index]
    return selected


def validate_auto_payload(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    mode = payload.get("mode")
    if mode != "doubles":
        raise ValueError("auto lineup is only available for doubles")

    selected_raw = payload.get("selected")
    if not isinstance(selected_raw, dict):
        raise ValueError("selected must be an object")

    slots = ["red_defense", "red_offense", "blue_defense", "blue_offense"]
    selected: dict[str, str] = {}
    for slot in slots:
        value = selected_raw.get(slot)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("auto lineup requires all four selected players")
        selected[slot] = normalize_player_name(value)

    if len(set(selected.values())) != 4:
        raise ValueError("auto lineup requires four unique players")

    return selected


def normalize_player_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("player names must be strings")
    name = value.strip().lower()
    if not name:
        raise ValueError("player names must be non-empty")
    return name


def validate_finished_score(score1: object, score2: object) -> tuple[int, int]:
    if not isinstance(score1, int) or not isinstance(score2, int):
        raise ValueError("scores must be integers")
    if score1 < 0 or score2 < 0:
        raise ValueError("scores must be non-negative")
    if max(score1, score2) != 5 or min(score1, score2) == 5:
        raise ValueError("only finished foosball results are accepted")
    return score1, score2


def validate_match_payload(
    store: BaseWriteStore, payload: object
) -> tuple[list[str], list[str], int, int]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    team1_raw = payload.get("team1")
    team2_raw = payload.get("team2")
    if not isinstance(team1_raw, list) or not isinstance(team2_raw, list):
        raise ValueError("team1 and team2 must be arrays")

    team1 = [normalize_player_name(name) for name in team1_raw]
    team2 = [normalize_player_name(name) for name in team2_raw]

    if len(team1) == 0 or len(team1) > 2 or len(team1) != len(team2):
        raise ValueError("only balanced singles or doubles matches are accepted")

    all_players = team1 + team2
    if len(set(all_players)) != len(all_players):
        raise ValueError("a player may only appear once in a submitted match")

    score1, score2 = validate_finished_score(payload.get("score1"), payload.get("score2"))

    missing = store.missing_players(all_players)
    if missing:
        raise ValueError("all submitted players must already exist")

    return team1, team2, score1, score2


def validate_new_player_name(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    name = normalize_player_name(payload.get("name"))
    if len(name) < 2 or len(name) > 30:
        raise ValueError("player name must be 2-30 characters")
    if not re.fullmatch(r"[a-z][a-z\- ]+[a-z]", name):
        raise ValueError("player name may contain only letters, spaces, and hyphens")
    return name
