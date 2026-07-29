"""Health/readiness endpoint for the phone API."""

from __future__ import annotations

from flask import Blueprint, jsonify
from services.phone_request_context import PhoneApiContext


def create_health_blueprint(ctx: PhoneApiContext) -> Blueprint:
    bp = Blueprint("health", __name__)

    @bp.get("/api/health")
    def health() -> object:
        store, error_response = ctx.resolve_write_store()
        if error_response is not None or store is None:
            return jsonify({"ok": False, "reason": "store_unavailable"}), 503

        readiness = getattr(store, "readiness", None)
        if readiness is None:
            return jsonify({"ok": True, "store": "injected"})
        try:
            result = readiness()
        except Exception:
            return jsonify({"ok": False, "reason": "store_unavailable"}), 503
        if result.get("ok"):
            return jsonify({"ok": True})
        return jsonify(result), 503

    return bp
