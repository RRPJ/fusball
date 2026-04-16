# Priority 0 Cutover Runbook

This runbook is the ordered validation and cutover path for deploying the phone API with Neon-backed production data.

Use it for:
- preview/staging validation
- production cutover rehearsal
- production cutover itself

## Preconditions

Before starting:

1. `DATABASE_URL` points to the intended Neon database.
2. `READ_PIN_HASH` and `WRITE_PIN_HASH` are configured for the target environment.
3. Current local state has been backed up.
4. The latest shelve -> Neon import has completed.
5. The deployed app version contains the store-backed read/write path.

## Environment Mapping

Recommended operating model:

1. Vercel Production -> Neon Production
2. Vercel Preview -> Neon Preview
3. Local development -> local shelve sandbox by default

Suggested branch/deployment mapping:

1. Production branch (`master`) deploys to Vercel Production.
2. Feature branches / pull requests deploy to Vercel Preview.
3. Vercel Production uses production secrets and production `DATABASE_URL`.
4. Vercel Preview uses preview secrets and preview `DATABASE_URL`.

Why:

1. Preview deployments must not write into production rankings/history.
2. Production verification needs stable, production-only credentials and data.
3. Local day-to-day coding should remain fast and low-risk.

Minimum environment variables by Vercel environment:

- Production:
	- `DATABASE_URL` -> production Neon
	- `READ_PIN_HASH` -> production read PIN hash
	- `WRITE_PIN_HASH` -> production writer PIN hash

- Preview:
	- `DATABASE_URL` -> preview Neon
	- `READ_PIN_HASH` -> preview read PIN hash
	- `WRITE_PIN_HASH` -> preview writer PIN hash

Do not point Vercel Preview at production Neon.

## Stage 1: Local Backup

Create a fresh backup of local production-like data:

```bash
python scripts/backup_state.py
```

If this fails, stop here.

## Stage 2: Migration Dry Run

Inspect the source snapshot before applying import:

```bash
python scripts/migrate_shelve_to_neon.py --db-dir app
```

Expected outcome:
- player count looks correct
- recent player count looks correct
- history count looks correct

If counts are clearly wrong, stop here.

## Stage 3: Apply Import To Neon

Run the import against the target Neon database:

```bash
python scripts/migrate_shelve_to_neon.py --db-dir app --database-url <database-url> --apply
```

Use `--reset` only when you intentionally want to replace target table contents.

Preview recommendation:

1. Import into preview Neon first.
2. Validate preview deployment against preview Neon.
3. Only then repeat the process for production Neon.

## Stage 4: Parity Verification

Run strict parity validation:

```bash
python scripts/smoke_neon_parity.py --db-dir app --database-url <database-url> --mode strict
```

Expected outcome:
- `players` matches
- `recent_players` ordering matches
- `match_history` IDs match

If strict parity fails:
- do not cut over
- review migration/import inputs
- re-run import only after cause is understood

Fast follow-up check if needed:

```bash
python scripts/smoke_neon_parity.py --db-dir app --database-url <database-url> --mode counts
```

## Stage 5: Deploy And Auth Smoke Test

Deploy the current app version to the target environment, then run auth and core write validation:

```bash
python scripts/smoke_phone_api_auth.py --base-url https://<deployment-host> --expect-auth --read-pin <read-pin> --write-pin <write-pin>
```

Expected outcome:
- `GET /api/health` returns `200`
- unauthenticated read returns `401`
- read PIN grants read access
- writer PIN grants read access
- unauthenticated write returns `403`
- read PIN on write returns `403`
- writer PIN on write succeeds

If this fails, do not cut over.

## Stage 6: Manual Staging Verification

Verify these flows in a browser/phone:

1. Open `/phone` and confirm leaderboard renders.
2. Confirm leaderboard order matches expected production snapshot.
3. Submit one test write in staging environment only.
4. Confirm leaderboard refreshes after write.
5. Confirm `h2h`, `stats`, and player history endpoints still return plausible data.

## Stage 7: Production Cutover

Only proceed when Stages 1-6 pass.

Production cutover sequence:

1. Take one final local backup.
2. Re-run import if production source changed since the previous staging import.
3. Re-run strict parity verification.
4. Deploy the validated build.
5. Run auth smoke test against production URL.
6. Run one controlled post-deploy verification from phone/browser.

## Rollback Triggers

Roll back if any of these occur:

1. Parity check fails.
2. Auth smoke test fails.
3. Leaderboard data is incomplete or obviously misordered.
4. Write endpoint succeeds but data does not appear in subsequent reads.
5. Match history/stat endpoints return inconsistent or empty data unexpectedly.

## Rollback Actions

1. Stop using the new deployment endpoint.
2. Restore the previous deployment configuration.
3. Keep local shelve-backed data as source of truth.
4. If local state was modified during rehearsal, restore from the latest verified backup.
5. Re-run:

```bash
python scripts/smoke_check.py
python -m unittest test_phone_api.py
```

## Exit Criteria

Priority 0 deployment work is operationally ready when:

1. strict Neon parity passes
2. auth smoke passes
3. phone/manual verification passes
4. rollback steps are understood and immediately executable
