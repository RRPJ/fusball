"""Vercel entrypoint for the phone API Flask app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"

# Ensure modules from the legacy app directory are importable on Vercel.
if str(APP_DIR) not in sys.path:
  sys.path.insert(0, str(APP_DIR))

from phone_api import create_app

_db_dir = os.environ.get("FUSBALL_PHONE_API_DB_DIR")
_db_path = Path(_db_dir).resolve() if _db_dir else APP_DIR

app = create_app(
  db_dir=_db_path,
  operator_token=os.environ.get("FUSBALL_PHONE_API_TOKEN"),
)
