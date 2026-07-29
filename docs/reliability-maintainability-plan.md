# Reliability And Maintainability Plan

## Problem And Approach

The hosted Vercel/Neon runtime can submit matches transactionally, but it has no
safe match lifecycle, durable operator identity, or hosted backup/restore
workflow. Ratings are path-dependent: voiding an old match changes every later
rating calculation, so undo cannot safely copy that match's `before` values
back into `players`.

The proposed approach makes Neon authoritative for hosted environments, keeps
shelve as a local-development adapter, introduces managed user identity and
application-owned roles, and models match correction as an audited soft-delete
followed by deterministic replay of all active matches from a trusted baseline.
Refactoring is staged behind characterization tests so `/phone`, `/api/*`,
offense-first rating semantics, and current ranking behavior remain stable.

This document is the durable roadmap alongside `docs/backlog.md`. Material
implementation decisions and completed milestones should update both documents
rather than allowing the roadmap to become stale.

## Current-State Findings

- `app/phone_api.py` combines Flask setup, auth, handlers, and roughly 2,500
  lines of embedded HTML/CSS/JavaScript in one large module.
- `app/services/phone_write_store.py` combines repository contracts, shelve
  persistence, Neon SQL, history queries, analytics, and match transactions.
- Neon match submission correctly locks affected players and commits rating and
  history changes together, but match history is immutable and there is no
  void/restore operation, actor identity, reason, or audit-event table.
- Current ratings are materialized in `players`; historical rankings are
  recomputed in Python. Any historical correction therefore requires replay,
  not a one-row reversal.
- Existing records contain before/after snapshots, but there is no explicit,
  verified rating baseline for data that predates structured history. A safe
  replay cutover must first prove the retained history can reproduce current
  ratings or store a trusted baseline/checkpoint.
- Shared read/write PINs identify a capability, not a person. The UI stores
  them in `sessionStorage`; authorization cannot attribute a correction to an
  individual or revoke one user independently.
- Clerk is the recommended managed-auth target for this small hosted app:
  managed sessions and identity with lower operational overhead than Auth0,
  while application roles remain in Neon. Confirm the official Python/JWT
  integration in a short spike before committing to the SDK.
- In-memory duplicate detection and presence are process-local, so behavior can
  vary across Vercel instances and cold starts.
- Analytics repeatedly load all `record_payload` rows and duplicate history
  behavior between shelve and Neon, increasing drift and scaling risk.
- Local backup tooling copies shelve files only. There is no versioned Neon
  schema migration runner, logical export/restore command, restore drill, or
  hosted data-integrity report.
- The Neon parity check compares identities/counts but not rating values,
  complete match payloads, lifecycle state, or replayed leaderboard results.
- CI runs lint, formatting, and the smoke script, but not the substantial
  `test_phone_api.py`, `test_match_flow.py`, and `test_integration.py` suites.
- The analyzed local virtual environment could not run the full suite because
  Flask and Werkzeug were missing; dependency setup should be normalized
  rather than treating this as a product regression.

## Implementation Todos

### 0. Publish And Maintain The Durable Roadmap

- [Done] Publish this complete plan, retaining its rationale, findings, delivery order,
  and safety constraints.
- [Done] Link the roadmap from `README.md` and `docs/backlog.md`; keep the backlog
  concise and use this roadmap for implementation-level detail.
- [Ongoing] Update roadmap status and decision records in the same pull requests that
  materially change the approach or complete a milestone.

### 1. Establish Characterization And Safety Gates

- [Done] Add regression fixtures for singles/doubles ordering, score-to-rating
  behavior, scoped leaderboards, history/profile analytics, duplicate submits,
  and Neon transaction rollback.
- [Done] Add replay-parity tests that compare current player ratings with ratings
  rebuilt from retained active history, using tolerances for TrueSkill floats.
- [Done] Run all existing unit suites in CI on the supported Python matrix, with a
  separate optional Neon integration job against an isolated database.
- [Done] Define acceptance gates: no API response regressions outside intentional auth
  and administration changes, no production cutover when replay parity fails,
  and no migration without a verified restore artifact.

The safety gates are established. The regression suite passes locally; the
PostgreSQL rollback test runs in CI, where an isolated service database is
available. The pre-existing global Ruff/Black gate remains intentionally
visible and currently blocks a fully green pipeline until its baseline debt is
normalized.

### 2. Introduce Versioned Persistence And Domain Boundaries

- [Done] Split `BaseWriteStore` into focused player, match, history, and transaction
  interfaces; move shared record parsing, scope filtering, and analytics out of
  the Neon and shelve adapters.
- [Done for current records] Define typed match and rating models so current
  JSON payload shapes have one shared contract. Actor and lifecycle types will
  be added with their corresponding authentication and correction milestones.
- [Done] Add an ordered, idempotent SQL migration mechanism rather than relying on one
  `CREATE TABLE IF NOT EXISTS` script.
- [Done] Keep shelve as a local-development adapter with the same public service
  contract, but document Neon as the only authoritative hosted store.

The persistence boundary milestone is complete: focused repository contracts
and shared domain types now sit outside the concrete adapters, scoped filtering
and replay are shared, and all schema creation/import paths use ordered,
checksum-verified migrations.

### 3. Replace Shared Secrets With Individual Identity

- [Done] Validate Clerk's hosted sign-in/session and Python token-verification path in
  a small spike; record Auth0 and Neon Auth as rejected alternatives with
  decision criteria covering Flask support, revocation, auditability, cost,
  and operational burden.
- [Done] Add an `app_users` table keyed by immutable provider subject, with display
  name, status, and application-owned roles: `reader`, `operator`, and `admin`.
- [Done] Add a focused auth module that verifies issuer, audience, signature, expiry,
  and session state, then exposes a typed current actor to handlers.
- [Done for current endpoints] Require `operator` for match/player/presence
  writes. Admin enforcement and persisted actor attribution are implemented
  with the audited match lifecycle because those operations do not yet exist.
- [Done] Replace PIN entry/sessionStorage handling with managed login/logout UI.
  Retain split PIN auth only behind an explicit, logged transition flag and
  remove it after deployment rollback criteria are met.
- [Done for identity] Add authorization-matrix, disabled-user, and mandatory
  authorized-party coverage. Clerk owns expired/revoked session verification;
  audit-attribution tests follow with persisted match events.

Managed identity is available in explicit `hybrid` and `clerk` modes, with
legacy behavior remaining the local default. The phone UI loads pinned Clerk
browser bundles from the configured instance, mounts sign-in/user controls,
and attaches a fresh bearer token to API requests.

### 4. Add Auditable Match Lifecycle And Deterministic Ranking Replay

- [Done] Extend matches additively with lifecycle state (`active` or `voided`) and
  lifecycle metadata without overwriting the original submitted payload.
- [Done] Add an append-only `match_events` audit table for submit, void, and restore,
  including match ID, actor, timestamp, reason, request correlation ID, and
  immutable before/after lifecycle state.
- [Done] Establish a trusted rating baseline/checkpoint at cutover. Refuse correction
  enablement if current Neon ratings cannot be reproduced from that baseline
  plus active matches in stable chronological/ID order.
- [Done] Implement one pure replay engine used by scoped leaderboards, integrity
  checks, void, and restore. It must preserve offense-first doubles semantics
  and exclude voided matches from every leaderboard, profile, H2H, streak, and
  history aggregate.
- [Done] In one serialized Neon transaction, lock correction/replay state, append the
  lifecycle event, rebuild affected materialized player ratings from the
  trusted baseline through all active matches, verify invariants, and commit.
  Any failure rolls back both lifecycle and ratings.
- [Done] Implement equivalent local shelve behavior using the existing write lock and
  backup-first policy, solely for development parity.
- [Done] Add idempotency keys for match submission and administration operations in
  Neon, replacing process-local duplicate protection for hosted writes.

The lifecycle foundation is complete. Corrections refuse baseline or
materialized-rating drift, use optimistic versions and payload-bound request
IDs, serialize hosted writes with an advisory transaction lock, append the
event, replay active history, and update materialized ratings atomically.
Shelve provides equivalent replay semantics with explicit rollback restoration;
the admin endpoint will acquire its existing file write lock.

### 5. Expose Safe Void And Restore Workflows

- [Done] Add admin-only match-history endpoints to list lifecycle state and audit
  events, void an active match with a mandatory reason, and restore a voided
  match with a mandatory reason.
- [Done] Return explicit conflicts for already-voided/restored records, concurrent
  corrections, stale versions, and reused idempotency keys.
- [Done] Add an admin section to `/phone` showing match ID, players, score, timestamp,
  state, actor, and reason; require a confirmation step before void or restore.
- [Done] Refresh leaderboard, profiles, H2H, stats, and match history after correction
  and visibly distinguish voided matches rather than deleting them.
- [Done] Test latest and historical corrections, restore symmetry, doubles ordering,
  scoped rankings, concurrent requests, transaction failures, unauthorized
  access, and full audit attribution.

The correction workflow is complete. Only managed admins can list lifecycle
and audit details or submit reasoned void/restore requests. The phone panel
uses reviewed versions and unique request IDs, confirms recalculation, and
refreshes ranking-dependent views after success.

### 6. Add Hosted Data-Safety Operations

- [Done] Add a Neon logical export command covering schema version, players, rating
  baseline/checkpoints, matches, match events, users/roles, and integrity
  metadata; encrypt and retain artifacts outside the deployment database.
- [Done] Add a guarded restore command that targets a new/isolated database by default,
  validates checksums and schema compatibility, and runs replay/parity checks
  before any environment switch.
- [Done] Expand parity tooling to compare exact rating components, lifecycle state,
  audit-event counts, active match payloads, and replayed leaderboard output.
- [Done] Document backup cadence, Neon provider recovery/PITR usage, preview-versus-
  production isolation, restore drills, rollback criteria, and emergency
  credential revocation in `docs/data-safety.md`.
- [Done] Add health/readiness diagnostics for database connectivity and schema
  compatibility without exposing secrets or returning healthy when the store
  is unavailable.

Hosted data-safety operations are implemented. Exports are authenticated and
encrypted, restores require an empty explicitly isolated target and verify
checksums plus replay before commit, and health now reflects store/schema
availability. The PostgreSQL integration job performs the restore path against
its isolated service database; operational teams must still run and record the
first preview Neon drill before production cutover.

Preview validation found that an existing Neon database can already contain
history when lifecycle tables are introduced. Migration `0004` therefore
backfills trusted earliest-history baselines and legacy submit events without
using the incomplete local shelve history as an authority.

### 7. Decompose The Runtime Without Changing Behavior

- Move embedded UI into Flask templates and static assets with cache-safe
  versioning; preserve the current phone presentation and offense/defense
  display order.
- Split route groups into small blueprints for reads, match operations,
  administration, and authentication; keep `create_app` as the composition
  root used by both local mode and `api/index.py`.
- Move process-local presence to Neon with expiry if it must work reliably
  across Vercel instances; otherwise explicitly label it local/session-only and
  disable misleading hosted behavior.
- Push Neon filtering/aggregation into focused SQL queries where safe, add
  indexes for active match chronology and player-history access, and avoid
  loading every JSON record for each request.
- Remove superseded helpers such as direct working-directory `player_store`
  access and replace the unsafe one-off `dbmigration.py` with versioned,
  backup-aware migrations.

## Dependencies And Delivery Order

1. Publish the durable roadmap before implementation begins.
2. Characterization and replay-parity gates precede persistence changes.
3. Persistence/domain boundaries precede both identity and match lifecycle.
4. Individual identity precedes enabling admin void/restore in production.
5. Match lifecycle and replay precede the admin API/UI.
6. Hosted export/restore must be operational before production correction is
   enabled.
7. Large UI/runtime decomposition follows correctness-sensitive work, except
   for the minimal auth/admin extraction needed by earlier slices.

Each slice should be independently deployable with additive schema changes,
feature flags for auth/correction rollout, preview Neon validation, and an
explicit rollback path.

## Key Files And Components

- `app/phone_api.py`: app composition, routes, and embedded UI decomposition
- `app/services/phone_write_store.py`: repository split and Neon transactions
- `app/services/match_history.py`: shared lifecycle-aware queries and replay
- `app/services/match_service.py`: preserved TrueSkill domain behavior
- `api/index.py`: hosted configuration and auth wiring
- `scripts/sql/`: ordered schema migrations and indexes
- `scripts/migrate_shelve_to_neon.py`: one-way import and baseline cutover
- `scripts/smoke_neon_parity.py`: full rating/history/lifecycle parity
- new backup/export/restore scripts under `scripts/`
- `test_phone_api.py`, `test_match_flow.py`, `test_integration.py`: regression,
  authorization, replay, and correction coverage
- `.github/workflows/ci.yml`: full unit and optional Neon integration gates
- `docs/phone-api.md`, `docs/phone-write-policy.md`,
  `docs/data-safety.md`, `docs/architecture.md`, and `.env.example`
- `docs/reliability-maintainability-plan.md`: this durable roadmap

## Important Considerations

- Never hard-delete match records; lifecycle events are append-only.
- A historical void or restore is a ranking rebuild, not a local inverse.
- Replay order must be deterministic when timestamps collide.
- Legacy data may require a cutover baseline because structured history may not
  reproduce ratings from the beginning of time.
- Provider identity proves who signed in; Neon-owned roles determine what they
  may do.
- Secrets, provider keys, database URLs, and export artifacts must remain out
  of source control and API error payloads.
- Local shelve support is for development compatibility, not hosted failover.
