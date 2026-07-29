"""Managed identity verification and application-owned authorization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence, cast

import httpx
from flask import Request

AuthRole = Literal["reader", "operator", "admin"]
ROLE_PERMISSIONS: dict[AuthRole, frozenset[str]] = {
    "reader": frozenset({"read"}),
    "operator": frozenset({"read", "write"}),
    "admin": frozenset({"read", "write", "admin"}),
}


class AuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthActor:
    subject: str
    display_name: str
    role: AuthRole

    def can(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())


class UserRoleStore(Protocol):
    def resolve_actor(self, subject: str) -> AuthActor | None: ...


class RequestAuthenticator(Protocol):
    def authenticate(self, request: Request) -> AuthActor | None: ...


class NeonUserRoleStore:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def resolve_actor(self, subject: str) -> AuthActor | None:
        import psycopg

        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT provider_subject, display_name, role
                    FROM app_users
                    WHERE provider_subject = %s AND status = 'active'
                    """,
                    (subject,),
                )
                row = cur.fetchone()

        if row is None:
            return None
        role = str(row[2])
        if role not in ROLE_PERMISSIONS:
            raise AuthenticationError(f"unsupported application role: {role}")
        return AuthActor(
            subject=str(row[0]),
            display_name=str(row[1]),
            role=cast(AuthRole, role),
        )


def resolve_managed_display_names(
    database_url: str | None,
    subjects: Sequence[str],
) -> dict[str, str]:
    unique_subjects = sorted({subject.strip() for subject in subjects if subject.strip()})
    if not database_url or not unique_subjects:
        return {}

    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider_subject, display_name
                FROM app_users
                WHERE status = 'active' AND provider_subject = ANY(%s)
                """,
                (unique_subjects,),
            )
            rows = cur.fetchall()

    resolved: dict[str, str] = {}
    for provider_subject, display_name in rows:
        normalized_name = str(display_name).strip() if display_name is not None else ""
        if normalized_name:
            resolved[str(provider_subject)] = normalized_name
    return resolved


class ClerkRequestAuthenticator:
    def __init__(
        self,
        secret_key: str,
        authorized_parties: list[str],
        role_store: UserRoleStore,
    ):
        if not secret_key:
            raise ValueError("Clerk secret key is required")
        if not authorized_parties:
            raise ValueError("at least one Clerk authorized party is required")

        from clerk_backend_api import Clerk
        from clerk_backend_api.security.types import AuthenticateRequestOptions

        self._client = Clerk(bearer_auth=secret_key)
        self._options = AuthenticateRequestOptions(authorized_parties=authorized_parties)
        self._role_store = role_store

    def authenticate(self, request: Request) -> AuthActor | None:
        clerk_request = httpx.Request(
            method=request.method,
            url=request.url,
            headers=dict(request.headers),
        )
        request_state = self._client.authenticate_request(clerk_request, self._options)

        if not request_state.is_signed_in or not request_state.payload:
            return None

        subject = request_state.payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError("verified token has no subject")
        return self._role_store.resolve_actor(subject)


def build_clerk_authenticator(
    *,
    secret_key: str | None,
    authorized_parties: str | None,
    database_url: str | None,
) -> ClerkRequestAuthenticator:
    parties = [party.strip() for party in (authorized_parties or "").split(",") if party.strip()]
    if not secret_key or not database_url:
        raise ValueError("Clerk auth requires CLERK_SECRET_KEY and DATABASE_URL")
    return ClerkRequestAuthenticator(
        secret_key=secret_key,
        authorized_parties=parties,
        role_store=NeonUserRoleStore(database_url),
    )
