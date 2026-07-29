"""Shared per-request dependencies for phone API route blueprints.

`PhoneApiContext` bundles the store/auth/lock primitives that `create_app`
already builds today. Blueprint modules receive one context instance instead
of importing `phone_api` internals directly, which keeps route groups
decoupled from the composition root and avoids circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from services.auth import AuthActor
    from services.store_contracts import BaseWriteStore


@dataclass
class PhoneApiContext:
    """Bag of request-scoped dependencies shared across phone API blueprints."""

    data_dir: Path
    resolve_write_store: Callable[[], tuple["BaseWriteStore | None", object | None]]
    managed_actor: Callable[[], "AuthActor | None"]
    require_read_access: Callable[[], object | None]
    require_write_access: Callable[[], object | None]
    require_admin_access: Callable[[], object | None]
    acquire_write_lock: Callable[[str], bool]
    release_write_lock: Callable[[], None]
