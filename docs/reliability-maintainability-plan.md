# Reliability And Maintainability Implementation Record

## Status And Scope

The reliability modernization described here is implemented on the current
branch. This document records why the work was necessary, the resulting
architecture, the safety constraints that must remain true, and the repository
evidence for completed milestones.

Implemented capability is not evidence that an external environment has been
configured or exercised. Provider configuration, production cutover, backup
cadence, and recorded restore drills are therefore listed separately under
**Remaining External Rollout And Operational Actions**.

Future product ideas that are not part of this reliability program live in
`docs/backlog.md`.

## Architectural Rationale

The modernization addressed four coupled risks:

- Ratings are path-dependent. Voiding or restoring a historical match changes
  every later rating calculation, so a correction cannot safely copy one
  match's `before` values back into the current player table.
- Shared PINs identify a capability rather than a person. Hosted
  administration requires individual identity, independently revocable roles,
  and durable actor attribution.
- Process-local duplicate and presence state is unsuitable for an ephemeral,
  multi-instance hosted runtime.
- A monolithic runtime and unversioned persistence made behavior-preserving
  changes, recovery, and hosted operations unnecessarily difficult.

The implemented design therefore makes Neon authoritative for hosted
environments, keeps shelve as a local-development compatibility adapter, uses
Clerk for hosted identity with application roles in Neon, and models match
correction as an audited lifecycle change followed by deterministic replay
from a trusted rating baseline.

## Completed Implementation

### 1. Characterization And Safety Gates

- Regression coverage protects singles and doubles ordering, rating updates,
  scoped leaderboards, history and profile analytics, duplicate submission,
  authorization, lifecycle correction, and transaction rollback.
- Replay tests compare materialized ratings with ratings rebuilt from retained
  active history, allowing only the documented TrueSkill float tolerance.
- CI runs smoke and regression suites across the supported Python matrix and
  runs PostgreSQL-backed Neon integration coverage against an isolated service
  database.
- Cutover gates are documented in `docs/data-safety.md`: no migration or
  correction rollout without passing replay/parity checks and a restorable
  recovery artifact.

Primary evidence: `.github/workflows/ci.yml`, `test_phone_api.py`,
`test_match_flow.py`, `test_integration.py`, `test_neon_store.py`,
`test_neon_migrations.py`, `test_neon_data_safety.py`, and `test_auth.py`.

### 2. Versioned Persistence And Domain Boundaries

- Focused player, history, match, transaction, and presence contracts are
  shared by the shelve and Neon adapters.
- Shared domain models and history helpers provide one contract for current
  match payloads, replay, scope filtering, and analytics.
- Ordered, idempotent, checksum-verified Neon migrations replace ad hoc schema
  creation. Applied migration files are immutable.
- Neon is the hosted authority. Shelve remains supported for local development
  and compatibility, not as hosted failover.

Primary evidence: `app/services/store_contracts.py`,
`app/services/domain_models.py`, `app/services/match_history.py`,
`app/services/phone_write_store.py`, `app/services/neon_migrations.py`, and
`scripts/sql/migrations/0001_initial.sql` through
`0005_player_presence.sql`.

### 3. Managed Identity And Authorization

- Clerk verifies hosted sessions; active rows in Neon's `app_users` table
  resolve the application-owned `reader`, `operator`, and `admin` roles.
- The auth layer verifies managed requests and exposes a typed actor to route
  handlers. Disabled or unprovisioned users receive no application access.
- Operators can perform normal writes. Only managed admins can list lifecycle
  details or void and restore matches.
- The phone runtime supports `legacy`, `hybrid`, and `clerk` modes. Strict
  hosted production uses `clerk`; legacy PIN/token handling remains a local or
  explicit rollback compatibility path.
- The phone UI has dedicated login/logout handling and server-side
  authorization remains authoritative regardless of client rendering.

Primary evidence: `app/services/auth.py`, `app/blueprints/auth.py`,
`app/blueprints/admin.py`, `app/templates/login.html`,
`app/static/js/login.js`, migration `0002_app_users.sql`, and `test_auth.py`.

### 4. Audited Match Lifecycle And Deterministic Replay

- Matches have additive lifecycle state and immutable original submission
  payloads. Match records are never hard-deleted.
- Append-only `match_events` record submit, void, and restore actions with
  actor, reason, request correlation, timestamp, and before/after state.
- Trusted `rating_baselines` provide the replay starting point. Corrections
  refuse missing baselines or drift between replayed and materialized ratings.
- One replay path excludes voided matches from rankings, profiles, H2H,
  history, streaks, and other aggregates.
- Hosted rating-changing writes serialize with a PostgreSQL advisory
  transaction lock and atomically commit lifecycle, audit, and rebuilt rating
  state. Failures roll back the complete operation.
- Match submission uses payload-bound idempotency in Neon. Administration
  requires a request key and replays it only for the same match and target
  state. The shelve adapter provides equivalent lifecycle/replay behavior for
  development, guarded by the local file lock.

Primary evidence: migrations `0003_match_lifecycle.sql` and
`0004_backfill_legacy_lifecycle.sql`, `app/services/match_history.py`,
`app/services/phone_write_store.py`, `app/blueprints/write.py`,
`app/blueprints/admin.py`, `test_match_flow.py`, and `test_neon_store.py`.

### 5. Safe Administration Workflow

- Admin endpoints list lifecycle state and audit events and perform reasoned,
  version-checked void or restore operations.
- Conflicts are explicit for stale versions, repeated lifecycle transitions,
  concurrent corrections, replay drift, and incompatible idempotency reuse.
- `/phone` contains a dedicated admin-only Match Corrections view with
  confirmation before recalculation.
- Successful corrections refresh ranking-dependent views while retaining
  voided records and their audit history.

Primary evidence: `app/blueprints/admin.py`,
`app/templates/phone.html`, `app/static/js/phone.js`, and the admin,
authorization, replay, and correction cases in `test_phone_api.py`,
`test_match_flow.py`, and `test_neon_store.py`.

### 6. Hosted Data Safety And Readiness

- Ordered migration, integrity, strict parity, encrypted logical export, and
  guarded isolated-restore commands are implemented under `scripts/`.
- Exports cover schema identity, players and exact ratings, baselines, matches,
  lifecycle events, recent players, hosted presence, and application users.
- Restore refuses a production target label, requires an empty explicitly
  isolated database, validates encryption and checksums, applies the ordered
  schema, and verifies deterministic replay before commit.
- `/api/health` reports store and schema readiness and returns `503` for an
  unavailable or incompatible store without exposing connection details.
- The PostgreSQL integration suite exercises rollback and export/restore
  behavior against an isolated database.

Primary evidence: `scripts/migrate_neon_schema.py`,
`scripts/check_neon_integrity.py`, `scripts/smoke_neon_parity.py`,
`scripts/export_neon_backup.py`, `scripts/restore_neon_backup.py`,
`app/services/neon_data_safety.py`, `app/blueprints/health.py`,
`test_neon_data_safety.py`, and `test_neon_store.py`.

### 7. Runtime Decomposition And Hosted Presence

- `app/phone_api.py` is the composition root used by local execution and
  `api/index.py`; route groups live in focused blueprints under
  `app/blueprints/`.
- Phone and login markup, CSS, and JavaScript live in `app/templates/` and
  `app/static/`. Content-derived asset versions provide cache-safe updates.
- `PhoneApiContext` carries auth, store, and lock dependencies into blueprint
  factories without circular imports or route-level global state.
- Hosted presence is durable in Neon's `player_presence` table and expires
  after eight hours. Local shelve presence remains in-process for the store
  lifetime.
- Match lifecycle listing batch-loads audit events rather than issuing one
  query per match. Superseded CWD-relative shelve helpers were removed while
  the separate local format upgrader `app/dbmigration.py` remains supported.

Primary evidence: `app/phone_api.py`, `api/index.py`, `app/blueprints/`,
`app/services/phone_request_context.py`, `app/templates/`, `app/static/`,
migration `0005_player_presence.sql`, and presence coverage in
`test_phone_api.py` and `test_neon_store.py`.

## Preserved Safety Constraints

These constraints are part of the implemented contract and must not be relaxed
by future refactors:

- Internal doubles and rating calculations use offense-first ordering
  `[offense, defense]`; the phone UI presents doubles as Defense + Offense.
- Historical correction is deterministic replay in stable timestamp/ID order,
  never a one-row inverse or direct edit of materialized ratings.
- Match records are not hard-deleted, and lifecycle audit events are
  append-only.
- Hosted writes rely on Neon transactions, advisory serialization, baseline
  checks, and idempotency. Local writes rely on `phone_api_write.lock` and the
  process-local 60-second duplicate fallback when no idempotency key is used.
- Provider identity proves who signed in; Neon-owned roles decide what the
  actor may do.
- Hosted production uses Neon and strict Clerk. Shelve and legacy credentials
  are development or deliberate rollback compatibility mechanisms.
- Preview deployments must use an isolated Neon preview branch/project and
  matching Clerk configuration, never production database credentials.
- Secrets, database URLs, backup keys, and export artifacts must remain out of
  source control and API error payloads.
- A failed migration, replay, integrity, checksum, restore, or regression gate
  blocks rollout rather than becoming an accepted inconsistency.

## Delivery Decisions Retained

The completed work followed this dependency order:

1. Characterization and replay-parity gates preceded persistence changes.
2. Persistence/domain boundaries preceded managed identity and lifecycle work.
3. Individual identity preceded enabling admin correction.
4. Lifecycle state and deterministic replay preceded the admin API and UI.
5. Hosted export/restore capability preceded production correction readiness.
6. Broader runtime decomposition followed correctness-sensitive work.

This sequence remains useful for future changes: additive schema updates,
isolated preview verification, explicit rollback paths, and independently
deployable slices are preferred over broad rewrites.

## Remaining External Rollout And Operational Actions

The repository cannot prove completion of the following provider and
operational work. Verify or perform these actions outside the codebase and
retain evidence in the organization's operational system.

### Environment And Cutover Verification

1. Confirm Vercel Production uses the production Neon database and strict
   `FUSBALL_AUTH_MODE=clerk`.
2. Confirm every Vercel Preview uses an isolated Neon preview branch/project
   and matching Clerk instance/configuration; never expose production
   `DATABASE_URL` to Preview.
3. Configure the required Clerk, Neon, and backup secrets in the correct
   environment scopes and verify `CLERK_AUTHORIZED_PARTIES` contains only the
   intended origins.
4. Apply ordered migrations, provision active `app_users` with least-privilege
   roles, and verify disabled/unprovisioned subjects cannot access the app.
5. Run the full regression suite and Neon integrity report against the rollout
   target. For a shelve import, also run strict parity. Confirm `/api/health`
   is ready.
6. Create an encrypted pre-cutover export, restore it into an isolated Preview
   or restore-drill database, and record checksum, replay, application-read,
   and credential-revocation evidence.
7. Exercise managed login/logout, operator writes, admin void/restore, audit
   attribution, presence expiry, and rollback behavior in Preview before
   promoting the deployment.
8. If `hybrid` mode is temporarily used as a rollback bridge, set an owner and
   removal date; production's steady state is strict `clerk`.

### Recurring Operations

- Run encrypted hosted exports at the documented cadence and immediately
  before high-risk schema or correction changes.
- Perform and record an isolated restore drill at least quarterly and after
  material migration or recovery-tool changes.
- Monitor `/api/health`, migration compatibility, failed writes, correction
  conflicts, and provider availability.
- Review `app_users` regularly; disable departed users and keep admin
  membership minimal.
- Rotate exposed or scheduled Neon, Clerk, and backup credentials and verify
  revocation as part of incident response.
- Rehearse Neon provider recovery/PITR and preserve the application export as
  an independent recovery path.

Operational rollout is complete only when the environment mapping, strict
auth, user provisioning, integrity/parity results, encrypted backup, isolated
restore evidence, and rollback path have all been verified for the target
production deployment.

## Maintenance Rule

Update this record in the same change that materially alters these
architectural decisions, safety constraints, or completed capabilities. Add
unimplemented product ideas to `docs/backlog.md`; do not turn this record back
into a proposal or use repository implementation as proof of external rollout.
