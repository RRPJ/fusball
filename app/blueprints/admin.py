"""Admin-only match lifecycle (void/restore) endpoints for the phone API."""

from __future__ import annotations

from urllib.parse import unquote

from flask import Blueprint, jsonify, request
from services.phone_request_context import PhoneApiContext
from services.store_contracts import LifecycleConflict, ReplayParityError


def create_admin_blueprint(ctx: PhoneApiContext) -> Blueprint:
    bp = Blueprint("admin", __name__)

    @bp.get("/api/admin/matches")
    def admin_matches() -> object:
        denied = ctx.require_admin_access()
        if denied is not None:
            return denied

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None

        limit = request.args.get("limit", default=30, type=int)
        limit = max(1, min(limit, 100))
        items = store.list_match_lifecycle(limit=limit, include_voided=True)
        subjects = [
            str(subject).strip()
            for subject in (item.get("submitted_by") for item in items)
            if isinstance(subject, str) and subject.strip()
        ]
        display_names = ctx.resolve_display_names(subjects)
        enriched_items: list[dict[str, object]] = []
        for item in items:
            enriched = dict(item)
            subject = enriched.get("submitted_by")
            if isinstance(subject, str):
                enriched["submitted_by_display_name"] = display_names.get(subject.strip())
            else:
                enriched["submitted_by_display_name"] = None
            enriched_items.append(enriched)
        return jsonify({"count": len(enriched_items), "items": enriched_items})

    def _change_match_lifecycle(match_id: str, target_status: str) -> object:
        match_id = unquote(match_id)
        denied = ctx.require_admin_access()
        if denied is not None:
            return denied

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "request body must be a JSON object"}), 400
        reason = payload.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 3:
            return jsonify({"error": "reason must contain at least 3 characters"}), 400
        reason = reason.strip()
        if len(reason) > 500:
            return jsonify({"error": "reason must not exceed 500 characters"}), 400
        expected_version = payload.get("expected_version")
        if not isinstance(expected_version, int) or isinstance(expected_version, bool):
            return jsonify({"error": "expected_version must be an integer"}), 400
        request_id = request.headers.get("Idempotency-Key", "").strip()
        if not request_id:
            return jsonify({"error": "Idempotency-Key header is required"}), 400
        if len(request_id) > 128:
            return jsonify({"error": "idempotency key is too long"}), 400

        store, error_response = ctx.resolve_write_store()
        if error_response is not None:
            return error_response
        assert store is not None
        actor = ctx.managed_actor()
        assert actor is not None

        uses_lock = store.uses_local_lock
        if uses_lock and not ctx.acquire_write_lock("admin-correction"):
            return jsonify({"error": "another writer is active"}), 409
        try:
            result = store.change_match_status(
                match_id=match_id,
                target_status=target_status,
                actor_subject=actor.subject,
                reason=reason,
                request_id=request_id,
                expected_version=expected_version,
            )
        except KeyError:
            return jsonify({"error": "match not found"}), 404
        except LifecycleConflict as exc:
            return jsonify({"error": str(exc)}), 409
        except ReplayParityError as exc:
            return jsonify({"error": str(exc)}), 409
        finally:
            if uses_lock:
                ctx.release_write_lock()
        return jsonify(result)

    @bp.post("/api/admin/matches/<match_id>/void")
    def void_match(match_id: str) -> object:
        return _change_match_lifecycle(match_id, "voided")

    @bp.post("/api/admin/matches/<match_id>/restore")
    def restore_match(match_id: str) -> object:
        return _change_match_lifecycle(match_id, "active")

    return bp
