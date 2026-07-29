---
applyTo: "app/phone_api.py,api/index.py,app/blueprints/**/*.py,app/templates/**/*,app/static/**/*,test_phone_api.py,test_auth.py"
description: "Use when editing the phone composition root, blueprints, templates/static assets, auth flow, or API contracts."
---

# Phone Runtime Instructions

- Read `docs/architecture.md`, `docs/authentication.md`, `docs/phone-api.md`, and `docs/phone-write-policy.md` before changing this scope.
- `app/phone_api.py` is the composition root and local launcher; `api/index.py` is the Vercel entrypoint. Keep route logic in `app/blueprints/` and UI markup/assets in `app/templates/` and `app/static/`.
- Production is Vercel + Neon + `FUSBALL_AUTH_MODE=clerk`. Clerk verifies identity; active Neon `app_users` rows grant `reader`, `operator`, or `admin` permissions. Do not add legacy-header fallback to clerk mode.
- `legacy` PIN/token and `hybrid` fallback behavior are local/rollback compatibility contracts. Preserve them unless the task explicitly changes compatibility behavior.
- Preserve `/`, `/login`, `/phone`, and `/api/*` contracts, including `401` unauthenticated versus `403` unauthorized behavior and `/api/health` returning `503` when the store is unavailable or incompatible.
- Hosted writes use Neon transactions, a transaction-scoped advisory lock, row locking, persisted idempotency, managed actor attribution, and audit events. Do not wrap Neon writes in the local file lock.
- Local shelve writes use `phone_api_write.lock` and return `409 Conflict` on an active writer. Match submits without an `Idempotency-Key` retain the 60-second process-local duplicate fallback.
- Preserve `Idempotency-Key` semantics. Admin void/restore requires managed `admin` access, a reason, `expected_version`, deterministic replay parity, and an idempotency key.
- Hosted presence is durable in Neon with an eight-hour expiry; local shelve presence lasts only for the server process.
- Internal doubles/history ordering is offense-first `[offense, defense]`; phone UI presentation is Defense + Offense.
- Validate success and failure paths with `python -m unittest test_phone_api.py test_auth.py`. Run Neon/store tests when transactions, idempotency, presence, or readiness are affected.
- Update relevant docs when API, auth, operator, deployment, or asset workflows change.
