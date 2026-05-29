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


def _adjusted_share(wins: int, losses: int, draws: int = 0) -> float:
    total = wins + losses + draws
    if total <= 0:
        return 0.0
    return (wins + (0.5 * draws)) / total


def _format_player_summary(name: str, *, wins: int, losses: int, draws: int = 0) -> dict[str, object]:
    matches = wins + losses + draws
    return {
        "player": name,
        "matches": matches,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_share": round(_adjusted_share(wins, losses, draws), 3),
    }


def _pair_lineup_context(record: dict, player: str) -> tuple[list[str], list[str], bool] | None:
    team1 = [name.lower() for name in record.get("team1", [])]
    team2 = [name.lower() for name in record.get("team2", [])]
    if player in team1:
        return team1, team2, True
    if player in team2:
        return team2, team1, False
    return None


def _display_team_order(team: Sequence[str]) -> list[str]:
    names = [name.title() for name in team]
    if len(names) == 2:
        return [names[1], names[0]]
    return names


def _recent_matches_from_records(records: Sequence[dict], player: str, limit: int) -> list[dict]:
    recent_matches: list[dict] = []
    for record in reversed(list(records)):
        lineup = _pair_lineup_context(record, player)
        if lineup is None:
            continue

        own_team, opp_team, on_team1 = lineup
        entries = {entry["name"].lower(): entry for entry in record.get("players", [])}
        entry = entries.get(player)
        if not entry:
            continue

        before = entry.get("before", {})
        after = entry.get("after", {})
        winner_team = [name.lower() for name in record.get("winner", [])]
        recent_matches.append(
            {
                "timestamp": record.get("timestamp", ""),
                "won": player in winner_team,
                "team": _display_team_order(own_team),
                "opponents": _display_team_order(opp_team),
                "score_for": int(record.get("score1", 0) if on_team1 else record.get("score2", 0)),
                "score_against": int(record.get("score2", 0) if on_team1 else record.get("score1", 0)),
                "delta": {
                    "offense": round(float(after.get("offense_mu", 0.0)) - float(before.get("offense_mu", 0.0)), 2),
                    "defense": round(float(after.get("defense_mu", 0.0)) - float(before.get("defense_mu", 0.0)), 2),
                },
            }
        )
        if len(recent_matches) >= limit:
            break

    return recent_matches


def _partner_and_opponent_summaries(records: Sequence[dict], player: str) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    partner_results: dict[str, dict[str, int]] = {}
    opponent_results: dict[str, dict[str, int]] = {}

    for record in records:
        lineup = _pair_lineup_context(record, player)
        if lineup is None:
            continue

        own_team, opp_team, _ = lineup
        winner_team = [name.lower() for name in record.get("winner", [])]
        won = player in winner_team

        for teammate in own_team:
            if teammate == player:
                continue
            bucket = partner_results.setdefault(teammate, {"wins": 0, "losses": 0, "draws": 0})
            if won:
                bucket["wins"] += 1
            elif any(name in winner_team for name in opp_team):
                bucket["losses"] += 1
            else:
                bucket["draws"] += 1

        for opponent in opp_team:
            bucket = opponent_results.setdefault(opponent, {"wins": 0, "losses": 0, "draws": 0})
            if won:
                bucket["wins"] += 1
            elif any(name in winner_team for name in opp_team):
                bucket["losses"] += 1
            else:
                bucket["draws"] += 1

    best_partner = None
    if partner_results:
        best_partner_name, best_partner_stats = max(
            partner_results.items(),
            key=lambda item: (
                _adjusted_share(item[1]["wins"], item[1]["losses"], item[1]["draws"]),
                item[1]["wins"] + item[1]["losses"] + item[1]["draws"],
                -item[1]["losses"],
            ),
        )
        best_partner = _format_player_summary(
            best_partner_name.title(),
            wins=best_partner_stats["wins"],
            losses=best_partner_stats["losses"],
            draws=best_partner_stats["draws"],
        )

    toughest_opponent = None
    if opponent_results:
        toughest_name, toughest_stats = max(
            opponent_results.items(),
            key=lambda item: (
                _adjusted_share(item[1]["losses"], item[1]["wins"], item[1]["draws"]),
                item[1]["wins"] + item[1]["losses"] + item[1]["draws"],
                -item[1]["wins"],
            ),
        )
        toughest_opponent = _format_player_summary(
            toughest_name.title(),
            wins=toughest_stats["losses"],
            losses=toughest_stats["wins"],
            draws=toughest_stats["draws"],
        )

    return best_partner, toughest_opponent


def query_player_profile_from_records(
    all_records: Sequence[dict],
    scoped_records: Sequence[dict],
    player: str,
    *,
    recent_limit: int = 5,
) -> dict[str, object]:
    player = player.lower()
    recent_limit = max(1, recent_limit)

    stats = query_player_stats_from_records(all_records, scoped_records)
    player_stats = stats.get(player)
    latest_matches = _recent_matches_from_records(scoped_records, player, recent_limit)
    best_partner, toughest_opponent = _partner_and_opponent_summaries(scoped_records, player)

    trend = {
        "offense": round(sum(float(match["delta"].get("offense", 0.0)) for match in latest_matches), 2),
        "defense": round(sum(float(match["delta"].get("defense", 0.0)) for match in latest_matches), 2),
    }

    return {
        "player": player,
        "summary": {
            "games": player_stats["games"] if player_stats else 0,
            "wins": player_stats["wins"] if player_stats else 0,
            "win_rate": player_stats["win_rate"] if player_stats else 0.0,
            "streak": player_stats["streak"] if player_stats else 0,
            "recent_form_5": player_stats["recent_form_5"] if player_stats else "",
            "last_match": player_stats["last_match"] if player_stats else None,
        },
        "trend": trend,
        "best_partner": best_partner,
        "toughest_opponent": toughest_opponent,
        "recent_matches": latest_matches,
    }


def query_player_stats_from_records(all_records: Sequence[dict], scoped_records: Sequence[dict]) -> dict[str, dict]:
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
    for record in scoped_records:
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
        if scope_baseline_level and name in scope_baseline_level:
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


def query_rating_snapshots_from_records(records: Sequence[dict], player: str, n: int = 10) -> list[dict]:
    player = player.lower()
    snapshots = []
    for record in records:
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


def _parse_timestamp_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _current_utc() -> datetime:
    return datetime.now(timezone.utc)


def _scope_window_utc(scope: str, now_utc: datetime | None = None) -> tuple[datetime, datetime] | None:
    if scope == "all":
        return None

    now_utc = now_utc or _current_utc()
    local_now = now_utc.astimezone()

    if scope == "this_month":
        start_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif scope == "this_quarter":
        quarter_start_month = ((local_now.month - 1) // 3) * 3 + 1
        start_local = local_now.replace(
            month=quarter_start_month,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
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


def query_team_h2h_from_records(records: Sequence[dict], team1: Sequence[str], team2: Sequence[str]) -> dict:
    team1_names = tuple(name.lower() for name in team1)
    team2_names = tuple(name.lower() for name in team2)
    team1_wins = team2_wins = draws = count = 0
    last_match: str | None = None

    for record in records:
        left = tuple(name.lower() for name in record.get("team1", []))
        right = tuple(name.lower() for name in record.get("team2", []))
        if left == team1_names and right == team2_names:
            own_side, opp_side = left, right
        elif left == team2_names and right == team1_names:
            own_side, opp_side = right, left
        else:
            continue

        count += 1
        last_match = record.get("timestamp")
        winner_team = [name.lower() for name in record.get("winner", [])]

        if any(name in winner_team for name in own_side):
            team1_wins += 1
        elif any(name in winner_team for name in opp_side):
            team2_wins += 1
        else:
            draws += 1

    return {
        "team1": _display_team_order(team1_names),
        "team2": _display_team_order(team2_names),
        "matches": count,
        "team1_wins": team1_wins,
        "team2_wins": team2_wins,
        "draws": draws,
        "last_match": last_match,
    }


def query_team_h2h(db_dir: str | Path, team1: Sequence[str], team2: Sequence[str]) -> dict:
    return query_team_h2h_from_records(_all_records(db_dir), team1, team2)


def query_player_stats(db_dir: str | Path, scope: str = "all") -> dict[str, dict]:
    """Return aggregate stats per player and scope-aware improved delta."""
    if scope not in {"all", "this_quarter", "this_month", "this_week"}:
        raise ValueError(f"unsupported scope: {scope}")

    all_records = _all_records(db_dir)
    scoped_records = records_for_scope(db_dir, scope)
    return query_player_stats_from_records(all_records, scoped_records)


def query_player_profile(
    db_dir: str | Path,
    player: str,
    *,
    scope: str = "all",
    recent_limit: int = 5,
) -> dict[str, object]:
    if scope not in {"all", "this_quarter", "this_month", "this_week"}:
        raise ValueError(f"unsupported scope: {scope}")

    all_records = _all_records(db_dir)
    scoped_records = records_for_scope(db_dir, scope)
    return query_player_profile_from_records(all_records, scoped_records, player, recent_limit=recent_limit)


def query_rating_snapshots(db_dir: str | Path, player: str, n: int = 10) -> list[dict]:
    """Return the last n rating snapshots for one player from history."""
    return query_rating_snapshots_from_records(_all_records(db_dir), player, n)
