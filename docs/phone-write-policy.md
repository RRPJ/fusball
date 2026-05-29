# Phone Match Submit Policy

This document defines the implemented auth and write-conflict baseline for phone write operations.

Scope:
- This policy applies to the current remote operator baseline on the phone path.
- It intentionally covers only two write operations: adding a player and submitting a finished match result.
- It does not attempt to define full remote administration, match editing/deletion, or live score entry.

## Implemented Baseline

The current phone write path supports minimal operator writes without turning the phone UI into a second full control surface.

The implemented write scope is intentionally narrow:
- Add a new player (token-authenticated).
- Submit a finished match only.
- Match submit uses existing players only.
- Apply the same score validity rules as the current Fusball match model.
- Persist the result, update rankings, and refresh read views.
- Keep additional remote-admin workflows out of scope for now.

## Auth Policy

Implemented policy:
- No anonymous write access.
- Require an explicit operator credential on every write request.
- For the first rollout, a shared operator secret is acceptable.
- VPN or local-network reachability is not sufficient by itself; transport access and write authorization are separate concerns.

Current implementation:
- Use a single shared operator token configured locally on the host.
- Send it with the request in a dedicated auth header.
- Reject missing or invalid credentials with `401 Unauthorized`.

Out of scope for the first slice:
- Per-user accounts.
- Role-based permissions.
- Social login.
- Delegated player-specific write access.

## Write Scope Rules

The current phone write endpoints allow only these operations:
- Add one player name with default ratings.
- Submit one finished singles or doubles result using existing player identities.

The endpoints reject:
- Partial or in-progress matches.
- Match edits or deletes.
- Freeform player names that do not match existing stored players.
- Unsupported score shapes that do not match current result rules.

## Conflict Policy

The write path assumes a single active writer at a time.

Rules:
- If another write-sensitive operation is already in progress, remote submit should be rejected.
- If a phone submit is already being processed, a second concurrent submit should be rejected.
- Conflict responses should be explicit and non-destructive.

Current implementation:
- Introduce a short-lived write lock owned by the active writer.
- Acquire the lock before mutating shelve state.
- Release it immediately after persistence and ranking update complete.
- Return `409 Conflict` when the lock is already held.
- Use duplicate-submit detection for a short time window to reject accidental retries.

Implementation notes from `app/phone_api.py`:
- Lock file name: `phone_api_write.lock`
- Auth header name: `X-Operator-Token`
- Duplicate-submit window: 60 seconds (`MATCH_DUPLICATE_WINDOW_SECONDS`)

## Validation Rules

Before accepting a phone-submitted result:
- Confirm all referenced players exist.
- Confirm the same player is not selected twice.
- Confirm team sizes are valid for supported match types.
- Confirm the submitted score is a valid finished result under the current rules.

Before creating a player from phone:
- Confirm the name is non-empty and normalized consistently.
- Confirm the name does not already exist.
- Confirm basic format constraints (allowed characters and length).

On success:
- Persist the rating update.
- Append the existing audit log entry.
- Make the updated leaderboard visible through the read API.

## Failure Behavior

Failures should favor safety over convenience.

If validation fails:
- Reject the request with `400 Bad Request`.

If auth fails:
- Reject the request with `401 Unauthorized`.

If another writer is active:
- Reject the request with `409 Conflict`.

If persistence fails partway through:
- Return `500 Internal Server Error` and avoid leaving partially applied state behind.

## Verification Expectations

The first phone write slice ships with a small validation surface:
- One automated test for authorized successful submit.
- One automated test for rejected unauthorized submit.
- One automated test for rejected conflicting submit.
- One automated test for player creation success and duplicate rejection.
- One manual end-to-end check from phone to leaderboard refresh.

Priority remains on history/model hardening before expanding write scope. See `docs/backlog.md` for next slices.

## See Also

- API endpoint reference: `docs/phone-api.md`
- Execution status and sequencing: `docs/backlog.md`
