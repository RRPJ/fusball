# Data Safety And Migration

## Storage Authority By Environment

| Environment | Authoritative state | Recovery model |
| --- | --- | --- |
| Vercel Production | Dedicated Neon production database | Neon provider recovery plus encrypted application exports |
| Vercel Preview | Isolated Neon preview branch/project | Disposable/reseedable; may be used as an isolated restore target |
| Local development | Shelve under `app/`, `sandbox/dev-data`, or `FUSBALL_PHONE_API_DB_DIR` | Timestamped file copies |

Neon is authoritative for hosted production. Shelve is a supported local and
rollback compatibility store, not a hosted failover mechanism. Never connect
Vercel Preview, a restore drill, or local experiments to the production Neon
database.

## Hosted Safety Baseline

Before a hosted schema change, data import, correction rollout, or other
high-risk operation:

1. Confirm the target URL belongs to the intended Neon environment.
2. Create an encrypted application export and confirm its source integrity
   result.
3. Confirm provider recovery/point-in-time recovery is available for the
   production recovery window.
4. Apply only ordered migrations from `scripts/sql/migrations/`.
5. Run `check_neon_integrity.py`.
6. Validate the change against isolated Preview before Production.
7. Record redacted evidence; never record credentials or connection strings.

The repository contains the safety tooling, but repository history alone does
not prove that a provider backup, restore drill, Preview validation, or
Production rollout has occurred.

## Neon Parity Verification

Apply pending ordered schema migrations before import or parity verification:

```bash
python scripts/migrate_neon_schema.py --database-url <database-url> --apply
```

Migration files are immutable after application. The runner rejects checksum
changes to previously applied versions. Checksums normalize line endings so
the same migration has one identity on Windows and Linux; legacy raw CRLF/LF
checksums are accepted and upgraded to the canonical value.

The lifecycle migration adds `rating_baselines`. The shelve import derives each
player's baseline from their earliest structured history `before` snapshot. A
player without retained history uses their imported current rating and is
tagged `shelve_current_no_history`. Correction features must remain disabled
until replay from these baselines matches materialized player ratings.

For an existing Neon database upgraded in place, migration `0004` derives the
same baseline from each player's earliest retained Neon history snapshot and
adds an attributed legacy `submit` event for every pre-lifecycle match. Players
without retained history are tagged `neon_current_no_history`. Applying the
migration does not prove parity by itself; `check_neon_integrity.py` must pass
before corrections are enabled.

Imported matches receive an append-only `submit` event attributed to
`migration:shelve`; original match payloads are not rewritten.

The current shelve importer reads only `playerdb*`, `recentplayers*`, and
`match_history*`. It derives new baselines and submit events rather than
importing local `rating_baselines*` or `match_events*`; relational lifecycle
columns are written as `active`, version `1`, with
`submitted_by='migration:shelve'` and no relational idempotency key. Before
applying it, inspect the source history. If any record is voided, has a
non-default lifecycle version, or requires existing actor/request-key audit
state to remain authoritative, do not cut over with this importer. Preserve a
complete local backup and implement a dedicated validated migration path.
Strict parity detects status/version differences, but it is not a substitute
for lifecycle and idempotency migration review.

## Presence Migration (`0005_player_presence.sql`)

Migration `0005` adds an additive `player_presence` table (`player_name`
primary key referencing `players(name)` with `ON DELETE CASCADE`,
`marked_active_at`, `expires_at`) plus an index on `expires_at`, giving hosted
Neon deployments durable "who's currently present" state with an 8-hour
expiry (`PRESENCE_TTL_SECONDS` in `app/services/phone_write_store.py`). It
does not touch any existing table or column and needs no backfill. A hosted
runtime using this branch expects the migration to exist; do not drop the
table as an application rollback. Roll back the deployment/database
environment together or restore an isolated known-good state. Local shelve
mode is unaffected: presence there remains an in-process,
per-server-lifetime set.

Before void or restore, the persistence adapter compares every materialized
rating component with deterministic replay from `rating_baselines` and active
history. Missing baselines or any mismatch abort the correction. Neon then
serializes rating-changing operations with a transaction advisory lock and
commits lifecycle state, audit event, and rebuilt ratings together.

Do not bypass `change_match_status` with direct SQL updates.

After running shelve -> Neon import, verify parity before any cutover:

```bash
python scripts/smoke_neon_parity.py --db-dir app --database-url <database-url> --mode strict
```

Notes:
- `--mode strict` compares exact player rating components, recent ordering,
  complete match payloads, lifecycle state, and replay/audit integrity.
- Use `--mode counts` for a faster count-only comparison.

## Hosted Neon Backup

Neon is authoritative for hosted environments. Create an encrypted logical
export before migrations, correction rollout, or other high-risk operations:

```bash
python scripts/export_neon_backup.py \
  --database-url <production-url> \
  --output <encrypted-storage-path>/fusball-<timestamp>.fusball-backup
```

The export contains:

- applied migration versions and checksums;
- players and exact offense/defense rating components;
- rating baselines, matches, lifecycle state, and append-only match events;
- recent-player ordering, expiring hosted presence, and application users/roles;
- per-table SHA-256 checksums and replay/audit integrity results.

`FUSBALL_BACKUP_KEY` must be a Fernet key held in the deployment secret manager.
Generate it once with an approved administrative environment:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit the key or artifact. Store copies in encrypted storage outside
Neon and outside the application repository. Recommended cadence is daily plus
immediately before schema or correction changes. Retain enough daily and
monthly generations to cover the organization's recovery window.

An export still completes if source integrity fails so the current state is
not lost, but exits with status 2 and must not be treated as a cutover-ready
backup.

## Guarded Hosted Restore

Restore accepts only an empty `preview` or `restore-drill` database and requires
an explicit isolation confirmation:

```bash
python scripts/restore_neon_backup.py <backup-path> \
  --database-url <isolated-target-url> \
  --target-environment restore-drill \
  --confirm-isolated-target
```

The command refuses production as a target label, validates encryption and
artifact checksums, applies the ordered schema, requires all application tables
to be empty, restores in foreign-key-safe order, then verifies table checksums
and deterministic rating replay before committing. A failure rolls back the
restore transaction.

Do not point `RESTORE_DATABASE_URL` at production. Create a separate Neon
branch/project, revoke its credential after the drill, and delete the isolated
target when evidence has been recorded.

## Hosted Integrity And Readiness

Run a full hosted integrity report with:

```bash
python scripts/check_neon_integrity.py --database-url <database-url>
```

It verifies schema checksums, baseline coverage, exact match payload columns,
lifecycle audit continuity, and materialized ratings against deterministic
replay. Any failed check blocks correction enablement and cutover.

`GET /api/health` now checks the configured store. Neon health requires a
working database connection and the exact ordered schema version. Failures
return HTTP 503 with a non-secret reason code; connection URLs and driver
errors are never returned.

## Provider Recovery And Incident Response

- Use Neon point-in-time recovery or branch restore for the fastest provider
  rollback when available, but keep application exports as an independent
  recovery path.
- Keep Vercel Preview connected only to a Neon preview/restore branch. Never
  share the production connection string with preview deployments.
- During an incident, disable writes or stop deployments, revoke exposed Neon,
  Clerk, and backup credentials, and issue replacements from their providers.
- Restore into isolation first. Run `check_neon_integrity.py`, strict shelve
  parity when applicable, API regression tests, and one manual leaderboard/
  match inspection before switching an environment connection.
- Roll back the environment switch if schema, checksum, replay, audit, or API
  verification fails. Preserve the failed database for investigation rather
  than modifying it in place.

Perform and record a restore drill at least quarterly and after material schema
or recovery-tool changes. A drill is complete only when the isolated restore
passes checksums and replay, the app can read it, and temporary credentials are
revoked.

## Hosted Rollout Gates

Do not enable a persistence migration or match-correction feature in production
unless all of these gates pass:

1. Existing phone API, match-flow, and integration regression suites pass.
2. Materialized player ratings match deterministic replay from the trusted
   baseline and retained active history within the documented float tolerance.
3. The target Neon schema and imported data pass strict parity checks.
4. A restorable export or provider recovery point exists and its restore path
   has been exercised against an isolated database.
5. Forced transaction-failure coverage proves player ratings and match history
   cannot commit independently.

Intentional API or authorization changes must be documented before cutover.
Any failed gate blocks deployment rather than being accepted as a known
difference.

## External Rollout Evidence

For each Preview or Production rollout, retain a redacted operational record:

- Vercel deployment URL/ID and commit SHA;
- Neon project/branch identity and intended environment mapping;
- migration list/output and integrity report with timestamps;
- encrypted export result and storage location identifier;
- isolated restore-drill result, including checksum/replay success and
  temporary credential revocation;
- `/api/health` result and controlled application read;
- Clerk role and negative authorization checks;
- operator/admin write evidence against the intended environment.

Do not claim deployment or recovery readiness from automated repository tests
alone. Do not include full URLs, passwords, keys, session tokens, or decrypted
backup data in evidence.

## Local Shelve Safety

Local shelve state is still operationally important. Before changing local
persistence logic, migrations, dependency versions that may affect shelve, or
data-shape assumptions:

1. Stop every process using the selected data directory.
2. Confirm whether the runtime targets `app/`, `sandbox/dev-data`, or
   `FUSBALL_PHONE_API_DB_DIR`.
3. Run:

   ```powershell
   python scripts\backup_state.py
   ```

   This script copies the repo's `app/playerdb*`, `app/recentplayers*`,
   `app/match_history*`, and `app/logfile.log` into
   `backups/<timestamp>/`.
4. The script does not currently copy `match_events*` or
   `rating_baselines*`. If those lifecycle shelves exist, copy them from the
   active data directory into protected storage as well.
5. If the active directory is not `app/`, copy all equivalent artifacts from
   that directory to protected storage.
6. Verify the copied files exist before changing state.

Historical kiosk-only files may remain in old backups. Keep them as archives;
they are not part of the current runtime contract.

Shelve backend formats are platform-dependent. Files created on one OS or
Python build may not be readable on another. Prefer a controlled export/import
path for cross-platform migration rather than opening the only copy in a new
environment.

`app/dbmigration.py` upgrades legacy player records from a single rating to the
offense/defense tuple format. Run it from `app/` only after backing up the
actual target data.

## Local Shelve Restore (Rollback)

Use this when data corruption or a failed migration is suspected.

1. Stop every phone API process using the target data.
2. Identify the target backup folder under `backups/<timestamp>/`.
3. Copy backup artifacts back into the original selected data directory:
   - `playerdb*`
   - `recentplayers*`
   - `match_history*` (if present)
   - `match_events*` (if present)
   - `rating_baselines*` (if present)
   - `logfile.log` (optional legacy audit restore)
4. Start the local app and run smoke validation:
   - `python scripts/smoke_check.py`
5. Run targeted API/unit checks if phone write path was involved:
   - `python -m unittest test_phone_api.py`
6. Manually verify leaderboard and one match flow before reopening normal use.

Rollback decision note:
- If smoke/tests fail after restore, stop and restore from an earlier known-good snapshot.
- Do not run migrations repeatedly against uncertain state; re-back up first.

## See Also

- `docs/development.md`
- `docs/architecture.md`
- `docs/backlog.md`
