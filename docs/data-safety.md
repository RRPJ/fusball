# Data Safety And Migration

This project stores operational data in Python shelve files. Treat these files as stateful assets.

## Before Any Refactor Or Dependency Upgrade

1. Stop the app.
2. Copy all shelve-related files from `app/` to a timestamped backup folder.
3. Copy `app/logfile.log` if present.
4. If phone API is in use, also back up `app/match_history*` and confirm whether writes were targeting `app/` or `sandbox/dev-data`.

Example backup layout:

- `backups/2026-04-09/playerdb*`
- `backups/2026-04-09/recentplayers*`
- `backups/2026-04-09/match_history*`
- `backups/2026-04-09/logfile.log`

Historical kiosk-only files may still exist in older backups. Keep them for archive purposes, but they are no longer part of the active runtime contract.

## Compatibility Caveat

Shelve backend formats are platform-dependent. Files created on one OS/Python build may not always be readable on another.

Recommended policy:
- Keep one canonical runtime environment for production data.
- Use exported snapshots (for example JSON) for cross-platform migration work.

## Existing Migration Helper

- `app/dbmigration.py` upgrades old player records from single-rating to offense/defense tuple format.
- Run it from the `app/` directory after creating a backup.

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

## Presence Migration (`0005_player_presence.sql`)

Migration `0005` adds an additive `player_presence` table (`player_name`
primary key referencing `players(name)` with `ON DELETE CASCADE`,
`marked_active_at`, `expires_at`) plus an index on `expires_at`, giving hosted
Neon deployments durable "who's currently present" state with an 8-hour
expiry (`PRESENCE_TTL_SECONDS` in `app/services/phone_write_store.py`). It
does not touch any existing table or column, needs no backfill, and rolls back
by simply not applying it (nothing else depends on the table existing; the
phone API falls back to whatever presence rows exist and treats an empty
table as "nobody present"). Local shelve mode is unaffected: presence there
remains an in-process, per-server-lifetime set, matching pre-refactor
behavior.

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

## Hosted Cutover Gates

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

## Restore Procedure (Rollback)

Use this when data corruption or a failed migration is suspected.

1. Stop phone API processes.
2. Identify the target backup folder under `backups/<timestamp>/`.
3. Copy backup artifacts back into `app/` for each relevant store:
	- `playerdb*`
	- `recentplayers*`
	- `match_history*` (if present)
	- `logfile.log` (optional legacy audit restore)
4. Start app from `app/` and run smoke validation:
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
