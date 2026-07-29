"""Phone API and mobile leaderboard page.

This module provides a small Flask app that reads the existing shelve-backed
player database and exposes:
- JSON API for leaderboard data
- Mobile-friendly HTML leaderboard view
- Minimal authenticated finished-match submission
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, redirect, render_template, request
from werkzeug.security import check_password_hash

from blueprints.admin import create_admin_blueprint
from blueprints.auth import create_auth_blueprint
from blueprints.health import create_health_blueprint
from blueprints.read import create_read_blueprint
from blueprints.write import create_write_blueprint
from services.auth import (
  AuthenticationError,
  RequestAuthenticator,
  build_clerk_authenticator,
  resolve_managed_display_names,
)
from services.leaderboard import load_leaderboard
from services.phone_request_context import PhoneApiContext
from services.phone_validation import reset_recent_match_signatures
from services.phone_write_store import BaseWriteStore, WriteStoreConfig, create_write_store


ROOT_DIR = Path(__file__).resolve().parent
WRITE_LOCK_NAME = "phone_api_write.lock"
OPERATOR_TOKEN_HEADER = "X-Operator-Token"
READ_PIN_HEADER = "X-Read-Pin"
WRITE_PIN_HEADER = "X-Write-Pin"
AUTH_MODES = {"legacy", "hybrid", "clerk"}


def _clerk_frontend_api_origin(
  publishable_key: str | None,
  configured_url: str | None,
) -> str | None:
  if publishable_key:
    try:
      encoded_domain = publishable_key.split("_", 2)[2]
      padding = "=" * (-len(encoded_domain) % 4)
      decoded_domain = base64.urlsafe_b64decode(
        encoded_domain + padding
      ).decode("ascii").removesuffix("$")
      if decoded_domain and "/" not in decoded_domain:
        return f"https://{decoded_domain}"
    except (IndexError, UnicodeDecodeError, ValueError):
      pass
  if configured_url:
    return configured_url.rstrip("/")
  return None


def _write_lock_path(db_dir: Path) -> Path:
    return db_dir / WRITE_LOCK_NAME


def _acquire_write_lock(db_dir: Path, owner: str) -> bool:
    lock_path = _write_lock_path(db_dir)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(owner)
    return True


def _release_write_lock(db_dir: Path) -> None:
    _write_lock_path(db_dir).unlink(missing_ok=True)


def _verify_secret(secret_hash: str | None, provided_secret: str | None) -> bool:
  if not secret_hash or not provided_secret:
    return False
  try:
    return check_password_hash(secret_hash, provided_secret)
  except Exception:
    return False


def _compute_asset_version(app: Flask) -> str:
  """Content-hash the phone UI's static assets for cache-busting query strings.

  Hashing (rather than a hardcoded constant) means browsers automatically
  fetch fresh CSS/JS after a deploy while still caching aggressively between
  deploys, without requiring a manual version bump.
  """
  static_folder = Path(app.static_folder) if app.static_folder else ROOT_DIR / "static"
  hasher = hashlib.sha256()
  for relative_path in ("css/phone.css", "js/login.js", "js/phone.js"):
    asset_path = static_folder / relative_path
    try:
      hasher.update(asset_path.read_bytes())
    except OSError:
      hasher.update(relative_path.encode("utf-8"))
  return hasher.hexdigest()[:12]


def _safe_local_next(candidate: str | None) -> str:
  if not candidate:
    return "/phone"
  parsed = urlsplit(candidate)
  if (
    parsed.scheme
    or parsed.netloc
    or not parsed.path.startswith("/")
    or parsed.path.startswith("//")
    or "\\" in candidate
  ):
    return "/phone"
  return candidate


def create_app(
  db_dir: Path | None = None,
  operator_token: str | None = None,
  read_pin_hash: str | None = None,
  write_pin_hash: str | None = None,
  database_url: str | None = None,
  write_store: BaseWriteStore | None = None,
  auth_mode: str = "legacy",
  authenticator: RequestAuthenticator | None = None,
  clerk_secret_key: str | None = None,
  clerk_authorized_parties: str | None = None,
  clerk_publishable_key: str | None = None,
  clerk_frontend_api_url: str | None = None,
) -> Flask:
  """Create the phone API app.

  Args:
    db_dir: Directory containing shelve files. Defaults to app directory.
    operator_token: Legacy shared secret required for write requests.
    read_pin_hash: Optional password hash for read access.
    write_pin_hash: Optional password hash for write access.
    database_url: Optional Postgres URL enabling Neon write-store mode.
    write_store: Optional explicit write-store override (primarily for tests).
    auth_mode: Authentication rollout mode: legacy, hybrid, or clerk.
    authenticator: Optional managed-identity authenticator override for tests.
    clerk_secret_key: Clerk backend secret used to verify sessions.
    clerk_authorized_parties: Comma-separated allowed frontend origins.
    clerk_publishable_key: Clerk browser publishable key.
    clerk_frontend_api_url: Clerk Frontend API origin for pinned browser SDKs.
  """
  if auth_mode not in AUTH_MODES:
    raise ValueError(f"unsupported auth mode: {auth_mode}")

  app = Flask(__name__)
  data_dir = db_dir or ROOT_DIR
  app.config["OPERATOR_TOKEN"] = operator_token
  app.config["READ_PIN_HASH"] = read_pin_hash
  app.config["WRITE_PIN_HASH"] = write_pin_hash
  app.config["DATABASE_URL"] = database_url or os.environ.get("DATABASE_URL")
  app.config["AUTH_MODE"] = auth_mode
  reset_recent_match_signatures()

  active_authenticator = authenticator
  if auth_mode in {"hybrid", "clerk"} and active_authenticator is None:
    if not clerk_publishable_key or not _clerk_frontend_api_origin(
      clerk_publishable_key,
      clerk_frontend_api_url,
    ):
      raise ValueError(
        "managed auth requires a valid CLERK_PUBLISHABLE_KEY"
      )
    active_authenticator = build_clerk_authenticator(
      secret_key=clerk_secret_key,
      authorized_parties=clerk_authorized_parties,
      database_url=app.config["DATABASE_URL"],
    )

  write_store_error: str | None = None
  active_write_store = write_store
  if active_write_store is None:
    try:
      active_write_store = create_write_store(
        WriteStoreConfig(
          db_dir=data_dir,
          database_url=app.config["DATABASE_URL"],
        )
      )
    except Exception as exc:
      write_store_error = str(exc)

  def _resolve_write_store() -> tuple[BaseWriteStore | None, object | None]:
    if active_write_store is not None:
      return active_write_store, None
    if write_store_error:
      return None, (jsonify({"error": f"write store unavailable: {write_store_error}"}), 503)
    return None, (jsonify({"error": "write store unavailable"}), 503)

  def _read_auth_enabled() -> bool:
    if app.config["AUTH_MODE"] == "clerk":
      return True
    return bool(app.config.get("READ_PIN_HASH") or app.config.get("WRITE_PIN_HASH"))

  def _write_pin_enabled() -> bool:
    return bool(app.config.get("WRITE_PIN_HASH"))

  def _request_supplied_read_credentials() -> bool:
    return bool(request.headers.get(READ_PIN_HEADER) or request.headers.get(WRITE_PIN_HEADER))

  def _managed_actor():
    if active_authenticator is None:
      return None
    if hasattr(g, "current_actor"):
      return g.current_actor
    try:
      g.current_actor = active_authenticator.authenticate(request)
    except AuthenticationError:
      g.current_actor = None
    return g.current_actor

  def _has_read_access() -> bool:
    actor = _managed_actor()
    if actor is not None:
      return actor.can("read")
    if app.config["AUTH_MODE"] == "clerk":
      return False
    if not _read_auth_enabled():
      return True

    read_pin = request.headers.get(READ_PIN_HEADER)
    write_pin = request.headers.get(WRITE_PIN_HEADER)
    read_ok = _verify_secret(app.config.get("READ_PIN_HASH"), read_pin)
    write_ok = _verify_secret(app.config.get("WRITE_PIN_HASH"), write_pin)
    return read_ok or write_ok

  def _check_write_access() -> tuple[bool, int, str]:
    actor = _managed_actor()
    if actor is not None:
      if actor.can("write"):
        return True, 200, ""
      return False, 403, "operator authorization required"
    if app.config["AUTH_MODE"] == "clerk":
      return False, 401, "authentication required"

    if _write_pin_enabled():
      write_pin = request.headers.get(WRITE_PIN_HEADER)
      if _verify_secret(app.config.get("WRITE_PIN_HASH"), write_pin):
        return True, 200, ""
      if write_pin:
        return False, 403, "incorrect writer PIN"
      return False, 403, "writer authorization required"

    token = app.config.get("OPERATOR_TOKEN")
    if not token:
      return False, 503, "write endpoint not configured"

    provided_token = request.headers.get(OPERATOR_TOKEN_HEADER)
    if provided_token != token:
      if provided_token:
        return False, 401, "incorrect operator token"
      return False, 401, "unauthorized"
    return True, 200, ""

  def require_read_access() -> object | None:
    if _has_read_access():
      return None
    if app.config["AUTH_MODE"] == "clerk":
      message = "authentication required"
    else:
      message = "incorrect reader or writer PIN" if _request_supplied_read_credentials() else "authentication required"
    return jsonify({"error": message}), 401

  def require_write_access() -> object | None:
    allowed, status, message = _check_write_access()
    if allowed:
      return None
    return jsonify({"error": message}), status

  def require_admin_access() -> object | None:
    actor = _managed_actor()
    if actor is None:
      return jsonify({"error": "authentication required"}), 401
    if not actor.can("admin"):
      return jsonify({"error": "admin authorization required"}), 403
    return None

  def resolve_display_names(subjects: list[str]) -> dict[str, str]:
    return resolve_managed_display_names(
      app.config.get("DATABASE_URL"),
      subjects,
    )

  ctx = PhoneApiContext(
    data_dir=data_dir,
    resolve_write_store=_resolve_write_store,
    managed_actor=_managed_actor,
    require_read_access=require_read_access,
    require_write_access=require_write_access,
    require_admin_access=require_admin_access,
    resolve_display_names=resolve_display_names,
    acquire_write_lock=lambda owner: _acquire_write_lock(data_dir, owner),
    release_write_lock=lambda: _release_write_lock(data_dir),
  )

  app.register_blueprint(create_health_blueprint(ctx))
  app.register_blueprint(create_auth_blueprint(ctx))
  app.register_blueprint(create_read_blueprint(ctx))
  app.register_blueprint(create_write_blueprint(ctx))
  app.register_blueprint(create_admin_blueprint(ctx))

  asset_version = _compute_asset_version(app)

  @app.get("/phone")
  def phone_view() -> str:
    resolved_frontend_api_url = _clerk_frontend_api_origin(
      clerk_publishable_key,
      clerk_frontend_api_url,
    )
    store, error_response = _resolve_write_store()
    rows: list[dict[str, object]] = []
    if auth_mode != "clerk" and error_response is None:
      assert store is not None
      rows = load_leaderboard(store, limit=50)
    return render_template(
      "phone.html",
      rows=rows,
      auth_mode=auth_mode,
      clerk_publishable_key=clerk_publishable_key,
      clerk_frontend_api_url=resolved_frontend_api_url,
      asset_version=asset_version,
    )

  @app.get("/login")
  def login_view() -> object:
    if auth_mode != "clerk":
      return redirect("/phone", code=302)
    resolved_frontend_api_url = _clerk_frontend_api_origin(
      clerk_publishable_key,
      clerk_frontend_api_url,
    )
    return render_template(
      "login.html",
      clerk_publishable_key=clerk_publishable_key,
      clerk_frontend_api_url=resolved_frontend_api_url,
      login_next=_safe_local_next(request.args.get("next")),
      asset_version=asset_version,
    )

  @app.get("/")
  def root() -> object:
    return redirect("/phone", code=302)

  return app


def main() -> None:
  parser = argparse.ArgumentParser(description="Run the Fusball phone API server")
  parser.add_argument(
    "--db-dir",
    default=os.environ.get("FUSBALL_PHONE_API_DB_DIR"),
    help="Directory containing playerdb/recentplayers/match_history/logfile files",
  )
  args = parser.parse_args()

  db_dir = Path(args.db_dir).resolve() if args.db_dir else ROOT_DIR
  app = create_app(
    db_dir=db_dir,
    operator_token=os.environ.get("FUSBALL_PHONE_API_TOKEN"),
    read_pin_hash=os.environ.get("READ_PIN_HASH"),
    write_pin_hash=os.environ.get("WRITE_PIN_HASH"),
    database_url=os.environ.get("DATABASE_URL"),
    auth_mode=os.environ.get("FUSBALL_AUTH_MODE", "legacy"),
    clerk_secret_key=os.environ.get("CLERK_SECRET_KEY"),
    clerk_authorized_parties=os.environ.get("CLERK_AUTHORIZED_PARTIES"),
    clerk_publishable_key=os.environ.get("CLERK_PUBLISHABLE_KEY"),
    clerk_frontend_api_url=os.environ.get("CLERK_FRONTEND_API_URL"),
  )
  app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()
