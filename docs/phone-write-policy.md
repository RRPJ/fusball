# Phone Match Submit Policy

This document defines the minimum auth and write-conflict policy for the first phone write slice.

Scope:
- This policy applies only to the first remote write feature: submitting a finished match result from the phone path.
- It does not attempt to define full remote administration, player creation, match editing, or live score entry.

## First-Slice Goal

Prove that a phone can submit a completed match result safely enough for early real-world use, without turning the phone path into a second full control surface.

The first write slice should stay intentionally narrow:
- Submit a finished match only.
- Use existing players only.
- Apply the same score validity rules as the kiosk flow.
- Persist the result, update rankings, and refresh read views.
- Stop there until structured match history is in place.

## Auth Policy

Minimum policy for the first slice:
- No anonymous write access.
- Require an explicit operator credential on every write request.
- For the first rollout, a shared operator secret is acceptable.
- Tailscale or local-network reachability is not sufficient by itself; transport access and write authorization are separate concerns.

Recommended first implementation:
- Use a single shared operator token configured locally on the host.
- Send it with the request in a dedicated auth header.
- Reject missing or invalid credentials with `401 Unauthorized`.

Out of scope for the first slice:
- Per-user accounts.
- Role-based permissions.
- Social login.
- Delegated player-specific write access.

## Write Scope Rules

The first phone write endpoint should allow only this operation:
- Submit one finished singles or doubles result using existing player identities.

The endpoint should reject:
- New player creation.
- Partial or in-progress matches.
- Match edits or deletes.
- Freeform player names that do not match existing stored players.
- Unsupported score shapes that do not match kiosk result rules.

## Conflict Policy

The first slice should assume a single active writer at a time.

Rules:
- If the kiosk is in the middle of a local write-sensitive flow, remote submit should be rejected.
- If a phone submit is already being processed, a second concurrent submit should be rejected.
- Conflict responses should be explicit and non-destructive.

Recommended first implementation:
- Introduce a short-lived write lock owned by either `kiosk` or `phone`.
- Acquire the lock before mutating shelve state.
- Release it immediately after persistence and ranking update complete.
- Return `409 Conflict` when the lock is already held.

The initial lock can be simple as long as it is reliable enough for a single-host deployment.

## Validation Rules

Before accepting a phone-submitted result:
- Confirm all referenced players exist.
- Confirm the same player is not selected twice.
- Confirm team sizes are valid for supported match types.
- Confirm the submitted score is a valid finished result under the current rules.

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

The first phone write slice should ship with only a small validation surface:
- One automated test for authorized successful submit.
- One automated test for rejected unauthorized submit.
- One automated test for rejected conflicting submit.
- One manual end-to-end check from phone to leaderboard refresh.

After that proof works, priority should move to structured match history rather than expanding phone write scope.