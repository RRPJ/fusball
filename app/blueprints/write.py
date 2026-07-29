"""Write endpoints for the phone API: presence, lineup helpers, players, matches."""

from __future__ import annotations

import time
from string import capwords

from flask import Blueprint, jsonify, request
from services.match_service import best_balanced_lineup
from services.phone_request_context import PhoneApiContext
from services.phone_validation import (
    is_recent_duplicate,
    lineup_from_active_players,
    match_signature,
    normalize_player_name,
    remember_match_signature,
    validate_auto_payload,
    validate_match_payload,
    validate_new_player_name,
)


def create_write_blueprint(ctx: PhoneApiContext) -> Blueprint:
    bp = Blueprint("write", __name__)

    @bp.post("/api/presence")
    def presence_set() -> object:
        denied = ctx.require_write_access()
        if denied is not None:
            return denied

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "request body must be a JSON object"}), 400

        try:
            name = normalize_player_name(payload.get("name"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        active = payload.get("active")
        if not isinstance(active, bool):
            return jsonify({"error": "active must be true or false"}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        if store.missing_players([name]):
            return jsonify({"error": "unknown player"}), 400

        store.set_presence(name, active)

        return jsonify(
            {
                "ok": True,
                "name": capwords(name),
                "active": active,
                "count": len(store.list_active_presence()),
            }
        )

    @bp.post("/api/presence/clear")
    def presence_clear() -> object:
        denied = ctx.require_write_access()
        if denied is not None:
            return denied

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        store.clear_presence()
        return jsonify({"ok": True, "count": 0})

    @bp.post("/api/lineup/random")
    def random_lineup() -> object:
        denied = ctx.require_write_access()
        if denied is not None:
            return denied

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "request body must be a JSON object"}), 400

        mode = payload.get("mode")
        if mode not in {"singles", "doubles"}:
            return jsonify({"error": "mode must be 'singles' or 'doubles'"}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        known_players = set(store.list_player_keys())
        eligible = set(store.list_active_presence()).intersection(known_players)
        try:
            selected = lineup_from_active_players(eligible, mode)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify({"ok": True, "mode": mode, "selected": selected})

    @bp.post("/api/lineup/auto")
    def auto_lineup() -> object:
        denied = ctx.require_write_access()
        if denied is not None:
            return denied

        try:
            selected = validate_auto_payload(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        ratings = store.get_player_ratings(list(selected.values()))
        missing = [name for name in selected.values() if name not in ratings]
        if missing:
            return jsonify({"error": "all selected players must exist"}), 400

        lineup = best_balanced_lineup(
            ratings,
            defense_a=selected["red_defense"],
            offense_a=selected["red_offense"],
            offense_b=selected["blue_offense"],
            defense_b=selected["blue_defense"],
        )

        if lineup is None:
            return jsonify({"error": "could not compute balanced lineup"}), 400

        return jsonify(
            {
                "ok": True,
                "mode": "doubles",
                "selected": {
                    "red_defense": lineup[0],
                    "red_offense": lineup[1],
                    "blue_offense": lineup[2],
                    "blue_defense": lineup[3],
                },
            }
        )

    @bp.post("/api/players")
    def add_player() -> object:
        denied = ctx.require_write_access()
        if denied is not None:
            return denied

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        try:
            player_name = validate_new_player_name(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        uses_lock = store.uses_local_lock
        if uses_lock and not ctx.acquire_write_lock("phone"):
            return jsonify({"error": "another writer is active"}), 409

        try:
            result = store.add_player(player_name)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception:
            return jsonify({"error": "failed to persist player"}), 500
        finally:
            if uses_lock:
                ctx.release_write_lock()

        return jsonify(result), 201

    @bp.post("/api/matches")
    def submit_match() -> object:
        denied = ctx.require_write_access()
        if denied is not None:
            return denied

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        try:
            team1, team2, score1, score2 = validate_match_payload(
                store,
                request.get_json(silent=True),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        signature = match_signature(team1, team2, score1, score2)
        idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
        if idempotency_key and len(idempotency_key) > 128:
            return jsonify({"error": "idempotency key is too long"}), 400
        now_monotonic = time.monotonic()
        if not idempotency_key and is_recent_duplicate(signature, now_monotonic):
            return jsonify({"error": "duplicate match submission detected"}), 409

        uses_lock = store.uses_local_lock
        if uses_lock and not ctx.acquire_write_lock("phone"):
            return jsonify({"error": "another writer is active"}), 409

        try:
            if not idempotency_key and is_recent_duplicate(signature, time.monotonic()):
                return jsonify({"error": "duplicate match submission detected"}), 409
            actor = ctx.managed_actor()
            actor_subject = actor.subject if actor is not None else "legacy:shared-credential"
            result = store.submit_match(
                team1,
                team2,
                score1,
                score2,
                source="phone_api",
                actor_subject=actor_subject,
                idempotency_key=idempotency_key,
            )
            remember_match_signature(signature, time.monotonic())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "failed to persist match result"}), 500
        finally:
            if uses_lock:
                ctx.release_write_lock()

        return jsonify(result), 201

    return bp
