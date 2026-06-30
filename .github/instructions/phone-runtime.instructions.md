---
applyTo: "app/phone_api.py,api/index.py,test_phone_api.py"
description: "Use when editing the phone runtime, embedded phone UI, request handlers, auth flow, or API contract. Preserves write-lock, auth, ordering, and verification expectations."
---

# Phone Runtime Instructions

- `app/phone_api.py` is the primary runtime and also contains the embedded phone UI template.
- Preserve the existing `/phone` and `/api/*` contract unless the task explicitly changes it.
- Before changing handlers, auth, or payload shape, check `docs/phone-api.md` and `docs/phone-write-policy.md`.
- Keep write-path behavior aligned with the current policy: `X-Operator-Token` auth, short-lived write lock, and explicit `409 Conflict` on active-writer collisions.
- Validate both success and failure paths for write endpoints; regressions here are easy to miss.
- Phone UI presentation may differ from internal team ordering. Internal doubles math/history uses offense-first ordering; do not assume stored/internal order is the display order.
- Prefer targeted verification with `python -m unittest test_phone_api.py` after phone runtime or UI edits.
- If request or operator workflow behavior changes, update `README.md` and the relevant docs under `docs/`.