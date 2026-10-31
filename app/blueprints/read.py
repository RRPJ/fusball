"""Read-only phone API endpoints: leaderboard, players, presence, and analytics."""

from __future__ import annotations

from string import capwords

from flask import Blueprint, jsonify, request
from services.leaderboard import load_leaderboard
from services.match_service import odds_ratio_for_teams
from services.phone_request_context import PhoneApiContext


def create_read_blueprint(ctx: PhoneApiContext) -> Blueprint:
    bp = Blueprint("read", __name__)

    def public_request() -> bool:
        return request.path.startswith("/api/public/")

    def pick(value: dict, keys: tuple[str, ...]) -> dict:
        return {key: value[key] for key in keys if key in value}

    def public_profile(profile: dict) -> dict:
        result = pick(profile, ("player",))
        result["summary"] = pick(
            profile.get("summary", {}),
            ("games", "wins", "win_rate", "streak", "recent_form_5", "last_match"),
        )
        result["trend"] = pick(profile.get("trend", {}), ("offense", "defense"))
        for key in ("best_partner", "toughest_opponent"):
            item = profile.get(key)
            result[key] = (
                pick(item, ("player", "wins", "losses", "draws", "matches")) if item else None
            )
        result["recent_matches"] = [
            {
                **pick(match, ("timestamp", "won", "score_for", "score_against")),
                "team": [name for name in match.get("team", []) if isinstance(name, str)],
                "opponents": [name for name in match.get("opponents", []) if isinstance(name, str)],
                "delta": pick(match.get("delta", {}), ("offense", "defense")),
            }
            for match in profile.get("recent_matches", [])
        ]
        return result

    @bp.after_request
    def noindex_public(response):
        if public_request():
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @bp.get("/api/public/leaderboard")
    @bp.get("/api/leaderboard")
    def leaderboard() -> object:
        denied = None if public_request() else ctx.require_read_access()
        if denied is not None:
            return denied

        limit = request.args.get("limit", default=50, type=int)
        limit = max(1, min(limit, 200))
        scope = request.args.get("scope", default="all", type=str)
        if scope not in {"all", "this_quarter", "this_month", "this_week"}:
            return jsonify({"error": "invalid scope"}), 400
        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        include_player_id = public_request() or request.args.get("include_player_id") == "1"
        rows = load_leaderboard(store, limit, scope=scope, include_player_id=include_player_id)
        if public_request():
            rows = [
                pick(
                    row,
                    (
                        "position",
                        "name",
                        "player_id",
                        "rank",
                        "level",
                        "offense_level",
                        "defense_level",
                    ),
                )
                for row in rows
            ]
        return jsonify({"count": len(rows), "items": rows})

    @bp.get("/api/players")
    def players() -> object:
        denied = ctx.require_read_access()
        if denied is not None:
            return denied

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None
        names = [capwords(name) for name in store.list_player_keys()]
        return jsonify({"count": len(names), "items": names})

    @bp.get("/api/presence")
    def presence_get() -> object:
        denied = ctx.require_read_access()
        if denied is not None:
            return denied

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None
        active = sorted(capwords(name) for name in store.list_active_presence())
        return jsonify({"count": len(active), "items": active})

    @bp.get("/api/h2h")
    def h2h() -> object:
        denied = ctx.require_read_access()
        if denied is not None:
            return denied

        p1 = request.args.get("p1", "").strip().lower()
        p2 = request.args.get("p2", "").strip().lower()
        if not p1 or not p2 or p1 == p2:
            return jsonify({"error": "two distinct player names required"}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None
        return jsonify(store.query_h2h(p1, p2))

    @bp.get("/api/team-h2h")
    def team_h2h() -> object:
        denied = ctx.require_read_access()
        if denied is not None:
            return denied

        team1_raw = request.args.get("team1", "").strip().lower()
        team2_raw = request.args.get("team2", "").strip().lower()
        if not team1_raw or not team2_raw:
            return jsonify({"error": "team1 and team2 are required"}), 400

        team1 = [name.strip() for name in team1_raw.split(",") if name.strip()]
        team2 = [name.strip() for name in team2_raw.split(",") if name.strip()]
        if len(team1) != len(team2) or len(team1) not in {1, 2}:
            return (
                jsonify({"error": "team1 and team2 must be balanced singles or doubles lineups"}),
                400,
            )

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None
        return jsonify(store.query_team_h2h(team1, team2))

    @bp.get("/api/public/stats")
    @bp.get("/api/stats")
    def player_stats() -> object:
        denied = None if public_request() else ctx.require_read_access()
        if denied is not None:
            return denied

        scope = request.args.get("scope", default="all", type=str)
        if scope not in {"all", "this_quarter", "this_month", "this_week"}:
            return jsonify({"error": "invalid scope"}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        try:
            stats = store.query_player_stats(scope=scope)
            if public_request():
                stats = {
                    name: pick(item, ("win_rate", "streak", "improved", "recent_form_5"))
                    for name, item in stats.items()
                }
            return jsonify(stats)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.get("/api/player/<name>/history")
    def player_history(name: str) -> object:
        denied = ctx.require_read_access()
        if denied is not None:
            return denied

        name = name.strip().lower()
        n = request.args.get("n", default=10, type=int)
        n = max(1, min(n, 50))

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None
        snapshots = store.query_rating_snapshots(name, n)
        return jsonify({"player": name, "count": len(snapshots), "snapshots": snapshots})

    @bp.get("/api/public/player/<name>/profile")
    @bp.get("/api/player/<name>/profile")
    def player_profile(name: str) -> object:
        denied = None if public_request() else ctx.require_read_access()
        if denied is not None:
            return denied

        name = name.strip().lower()
        scope = request.args.get("scope", default="all", type=str)
        if scope not in {"all", "this_quarter", "this_month", "this_week"}:
            return jsonify({"error": "invalid scope"}), 400
        recent_limit = request.args.get("recent_limit", default=5, type=int)
        recent_limit = max(1, min(recent_limit, 10))

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        try:
            profile = store.query_player_profile(name, scope=scope, recent_limit=recent_limit)
            return jsonify(public_profile(profile) if public_request() else profile)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.get("/api/odds")
    def match_odds() -> object:
        denied = ctx.require_read_access()
        if denied is not None:
            return denied

        red_off = request.args.get("red_off", "").strip().lower()
        blue_off = request.args.get("blue_off", "").strip().lower()
        red_def = request.args.get("red_def", "").strip().lower()
        blue_def = request.args.get("blue_def", "").strip().lower()
        mode = request.args.get("mode", "singles")
        if not red_off or not blue_off:
            return jsonify({"error": "offense players required"}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        team1 = [red_off, red_def] if mode == "doubles" and red_def else [red_off]
        team2 = [blue_off, blue_def] if mode == "doubles" and blue_def else [blue_off]

        ratings = store.get_player_ratings(team1 + team2)
        if not ratings:
            return jsonify({"error": "no player data"}), 503
        missing = [n for n in team1 + team2 if n not in ratings]
        if missing:
            return jsonify({"error": "unknown players"}), 400

        probability, ratio = odds_ratio_for_teams(ratings, team1, team2)
        return jsonify({"probability": round(probability, 3), "ratio": ratio})

    return bp
