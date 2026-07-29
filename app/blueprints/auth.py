"""Managed-identity introspection endpoint for the phone API."""

from __future__ import annotations

from flask import Blueprint, jsonify
from services.phone_request_context import PhoneApiContext


def create_auth_blueprint(ctx: PhoneApiContext) -> Blueprint:
    bp = Blueprint("auth", __name__)

    @bp.get("/api/auth/me")
    def auth_me() -> object:
        actor = ctx.managed_actor()
        if actor is None:
            return jsonify({"error": "authentication required"}), 401
        return jsonify(
            {
                "subject": actor.subject,
                "display_name": actor.display_name,
                "role": actor.role,
            }
        )

    return bp
