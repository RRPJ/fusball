"""Smoke-check phone API auth and core read/write behavior.

This script is intended for Priority 0 staging/production validation,
including Vercel + Neon deployments.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _request_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, method=method, headers=request_headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
            if payload:
                try:
                    return response.status, json.loads(payload)
                except json.JSONDecodeError:
                    return response.status, payload
            return response.status, None
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8") if exc.fp else ""
        try:
            return exc.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return exc.code, payload


def _print_check(label: str, ok: bool, actual: int, expected: int) -> None:
    marker = "OK" if ok else "FAIL"
    print(f"[{marker}] {label}: expected {expected}, got {actual}")


def _expect(
    label: str,
    actual_status: int,
    expected_status: int,
    failures: list[str],
) -> None:
    ok = actual_status == expected_status
    _print_check(label, ok, actual_status, expected_status)
    if not ok:
        failures.append(f"{label}: expected {expected_status}, got {actual_status}")


def _headers(read_pin: str | None = None, write_pin: str | None = None, token: str | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    if read_pin:
        out["X-Read-Pin"] = read_pin
    if write_pin:
        out["X-Write-Pin"] = write_pin
    if token:
        out["X-Operator-Token"] = token
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check phone API auth behavior")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Phone API base URL")
    parser.add_argument("--expect-auth", action="store_true", help="Assert split-auth matrix (401/403 paths)")
    parser.add_argument("--read-pin", default=None, help="Read PIN for authenticated read checks")
    parser.add_argument("--write-pin", default=None, help="Writer PIN for authenticated write checks")
    parser.add_argument("--operator-token", default=None, help="Legacy operator token (fallback mode checks)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    failures: list[str] = []

    print(f"Running phone API auth smoke checks against: {base}")

    health_status, _ = _request_json("GET", f"{base}/api/health")
    _expect("health", health_status, 200, failures)

    leaderboard_status, _ = _request_json("GET", f"{base}/api/leaderboard")
    if args.expect_auth:
        _expect("leaderboard without auth", leaderboard_status, 401, failures)
    else:
        _expect("leaderboard baseline", leaderboard_status, 200, failures)

    if args.read_pin:
        read_status, _ = _request_json(
            "GET",
            f"{base}/api/leaderboard",
            headers=_headers(read_pin=args.read_pin),
        )
        _expect("leaderboard with read pin", read_status, 200, failures)
    elif args.expect_auth:
        failures.append("read pin is required when --expect-auth is set")
        print("[FAIL] missing --read-pin while --expect-auth is enabled")

    if args.write_pin:
        writer_read_status, _ = _request_json(
            "GET",
            f"{base}/api/leaderboard",
            headers=_headers(write_pin=args.write_pin),
        )
        _expect("leaderboard with writer pin", writer_read_status, 200, failures)
    elif args.expect_auth:
        failures.append("write pin is required when --expect-auth is set")
        print("[FAIL] missing --write-pin while --expect-auth is enabled")

    clear_no_auth_status, _ = _request_json("POST", f"{base}/api/presence/clear")
    if args.expect_auth:
        _expect("presence clear without auth", clear_no_auth_status, 403, failures)
    else:
        expected = 200 if args.operator_token else 401
        _expect("presence clear baseline", clear_no_auth_status, expected, failures)

    if args.read_pin:
        clear_with_read_status, _ = _request_json(
            "POST",
            f"{base}/api/presence/clear",
            headers=_headers(read_pin=args.read_pin),
        )
        if args.expect_auth:
            _expect("presence clear with read pin", clear_with_read_status, 403, failures)

    if args.write_pin:
        clear_with_writer_status, _ = _request_json(
            "POST",
            f"{base}/api/presence/clear",
            headers=_headers(write_pin=args.write_pin),
        )
        _expect("presence clear with writer pin", clear_with_writer_status, 200, failures)

    if args.operator_token:
        clear_with_token_status, _ = _request_json(
            "POST",
            f"{base}/api/presence/clear",
            headers=_headers(token=args.operator_token),
        )
        if args.expect_auth:
            _expect("presence clear with legacy token", clear_with_token_status, 403, failures)
        else:
            _expect("presence clear with legacy token", clear_with_token_status, 200, failures)

    if failures:
        print("\nSmoke check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("\nSmoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
