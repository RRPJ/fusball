# Phone Write And Correction Policy

This document defines the current authorization, validation, concurrency,
idempotency, and audit policy for the phone API's mutating and
write-authorized endpoints.

## Deployment Policy

- Hosted production runs on Vercel with Neon as the authoritative store and
  `FUSBALL_AUTH_MODE=clerk`.
- Preview uses an isolated Vercel Preview deployment, Neon preview
  branch/project, and matching Clerk configuration.
- Local development may use the shelve adapter and legacy PIN/token
  compatibility, or an explicitly configured Neon/Clerk setup.

Shelve and shared credentials are compatibility paths. They are not hosted
production failover mechanisms.

## Authorization Policy

Clerk authenticates hosted users. Fusball authorizes them from active Neon
`app_users` rows keyed by immutable provider subject.

| Role | Permission |
| --- | --- |
| `reader` | Read-only API access |
| `operator` | Reader access plus operational writes |
| `admin` | Operator access plus match lifecycle corrections |

Auth modes:

- `legacy`: configured read/write PINs, with shared operator-token fallback
  when no writer PIN hash is configured.
- `hybrid`: managed identity first; configured legacy credentials remain a
  fallback when no managed actor resolves.
- `clerk`: managed identity only; legacy headers are ignored.

All operational write routes require `operator` or `admin` in strict Clerk
mode. Admin match routes always require a managed `admin`; no legacy PIN or
token grants correction access.

## Implemented Write Surface

| Endpoint | Required permission | Behavior |
| --- | --- | --- |
| `POST /api/presence` | write | Mark one existing player active/inactive |
| `POST /api/presence/clear` | write | Clear active presence |
| `POST /api/lineup/random` | write | Compute a lineup from active players |
| `POST /api/lineup/auto` | write | Compute a balanced four-player lineup |
| `POST /api/players` | write | Create a player with default ratings/baseline |
| `POST /api/matches` | write | Submit one finished singles/doubles match |
| `GET /api/admin/matches` | admin | Read match lifecycle and audit events |
| `POST /api/admin/matches/<id>/void` | admin | Void a match and replay ratings |
| `POST /api/admin/matches/<id>/restore` | admin | Restore a match and replay ratings |

Lineup helpers use POST because they are operator workflow actions, but they do
not persist a match. There is no API for live score entry, arbitrary match
editing, or deleting match history.

## Managed Actor Attribution

Managed match submissions persist the immutable Clerk subject in
`match_history.submitted_by` and in the submit event. Legacy submissions use
the explicit marker `legacy:shared-credential`.

Void and restore events always persist the managed admin subject, reason,
request ID, prior state, target state, and timestamp. Current presence and
player-creation records do not carry a separate actor audit field; the API
still enforces the caller's write permission.

## Validation Policy

### Presence

- The body must be a JSON object.
- `name` must normalize to a non-empty string.
- `active` must be Boolean.
- The player must already exist.

### Lineup Helpers

- Random lineup mode must be `singles` or `doubles`.
- Random selection uses only players who are both known and currently active.
- Auto lineup is doubles-only.
- Auto lineup requires all four named slots and four unique existing players.

### Player Creation

- The body must contain a string `name`.
- Names are normalized to lowercase.
- The length check is 2-30 characters.
- The current character rule is `[a-z][a-z\- ]+[a-z]`: lowercase letters,
  spaces, and hyphens, with a letter at both ends and a practical minimum of
  three characters.
- Existing names are rejected.

### Match Submission

- `team1` and `team2` must be arrays.
- Teams must be balanced singles or doubles.
- Every referenced player must already exist.
- A player may appear only once.
- Scores must be non-negative integers.
- Exactly one team must have a score of `5`.
- Only finished results are accepted.
- An optional `Idempotency-Key` must be at most 128 characters.

### Match Correction

- The match ID must resolve.
- `reason` is required and must contain 3-500 characters after trimming.
- `expected_version` is required and must be an integer.
- `Idempotency-Key` is required, non-empty, and at most 128 characters.
- The caller must be a managed `admin`.

## Hosted Neon Consistency

Neon operations use database transactions:

- Player creation inserts the player and rating baseline and updates recent
  player ordering in one transaction.
- Presence set/clear commits as a database transaction.
- Match submit acquires
  `pg_advisory_xact_lock(hashtext('fusball-rating-replay'))`, locks
  participating player rows with `FOR UPDATE`, updates ratings, inserts the
  history record, and appends the submit event before commit.
- Void/restore acquires the same advisory transaction lock, verifies
  materialized-rating replay parity, locks the match row, enforces the expected
  version, updates lifecycle state, appends an event, recomputes ratings from
  active history, and commits atomically.

The shared advisory lock serializes operations that can change materialized
ratings or replay history. It replaces the local lock file for Neon-backed
deployments.

## Idempotency And Duplicate Handling

### Hosted Match Submit

`Idempotency-Key` is optional at the route boundary, but the phone UI sends a
new generated key for every submit and hosted clients should do the same.

With a key:

- Neon stores it on the match and submit event.
- The unique index prevents two matches from owning the same key.
- Repeating the same key and payload returns the original successful result.
- Reusing the key for another payload is rejected.

Without a key, the route uses a 60-second process-local signature tracker.
That tracker may reduce immediate accidental repeats, but it does not span
Vercel instances or cold starts and is not a hosted idempotency guarantee.

### Admin Correction

Every void/restore request requires an idempotency key. Repeating the same key
for the same match and target state returns the current lifecycle result with
`idempotent: true`. Reusing it for any other match submit or lifecycle
operation returns `409`.
`expected_version` prevents a stale screen from overwriting a newer correction.

## Local Shelve Concurrency

The shelve adapter sets `uses_local_lock = True`. The API acquires
`phone_api_write.lock` before:

- player creation,
- match submission, and
- void/restore.

If the file already exists, the request returns `409` without starting the
mutation. The lock is released in `finally` after the operation. Presence is
only an in-process set and lineup helpers are calculations, so they do not use
the lock file.

For match submissions without a key, local mode also relies on the 60-second
process-local duplicate signature check. When a key is supplied, the shelve
adapter scans stored history and returns the original result for the same key
and payload. These mechanisms protect the supported single-process local
workflow; they are not distributed locks.

## Presence Durability

- **Neon:** presence is stored in `player_presence`. Activating a player
  upserts `marked_active_at` and an expiry eight hours in the future.
  Deactivation deletes the row, clearing deletes all rows, and reads filter
  `expires_at > NOW()`.
- **Shelve:** presence is a set owned by the running store instance and is lost
  on restart.

Random lineup always reads the current presence repository, so hosted requests
see shared durable rows while local requests see only their process state.

## Match Lifecycle And Audit Guarantees

Corrections do not edit scores, teams, or the original match payload and do not
delete history. A correction changes only lifecycle state/version, appends a
`void` or `restore` event, and rematerializes ratings from active history.
Normal ranking, stats, profile, H2H, and history-derived calculations exclude
voided records.

Before a lifecycle change, replay parity must match the current materialized
ratings. A mismatch aborts the correction with `409` rather than building on
untrusted state. `rating_baselines` provide the trusted replay starting point.

## Ordering Policy

Internal doubles arrays are offense-first:

```text
[offense, defense]
```

The phone UI displays teams defense-first:

```text
Defense + Offense
```

Stored history, rating math, odds, team H2H, idempotency comparison, and replay
must retain offense-first order. Only presentation reverses a doubles team.

## Failure Behavior

| Status | Policy |
| --- | --- |
| `400 Bad Request` | Invalid payload or match idempotency-key reuse with another payload |
| `401 Unauthorized` | Missing/invalid identity for strict access, admin access, reads, or legacy token mode |
| `403 Forbidden` | Managed role lacks permission or writer PIN authorization fails |
| `404 Not Found` | Correction match does not exist |
| `409 Conflict` | Duplicate player/submit, local lock contention, stale lifecycle version/state, request-key conflict, or replay-parity failure |
| `500 Internal Server Error` | Persistence operation failed |
| `503 Service Unavailable` | Store unavailable/not ready or legacy write credential is not configured |

Neon transaction failures roll back uncommitted database changes. The local
match adapter restores player ratings if subsequent history/log persistence
raises, but local files and the legacy text log do not provide distributed
transaction semantics.

## Readiness Gate

`GET /api/health` is public and reports selected-store readiness:

- Neon must be reachable and have the complete, checksummed migration state.
- Shelve must have an accessible data directory and must be able to read the
  current player store when present.

An unavailable or incompatible store returns `503`; operators should not treat
a running process with failed readiness as safe for writes.

## See Also

- [Architecture](architecture.md)
- [Authentication](authentication.md)
- [Data safety](data-safety.md)
- [Phone API](phone-api.md)
