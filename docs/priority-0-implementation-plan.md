## Plan: Priority 0 Delivery

Implement Priority 0 as three coordinated workstreams: remove VPN helper automation from Windows service controls, migrate Git remote workflow to personal origin while keeping master, and deliver a Vercel deployment path for the phone API with write support against production data. Because current storage is shelve on local disk, full Vercel write + production-data deployment requires pulling a minimal subset of Priority 2 (portable storage + lock strategy) forward as explicit prerequisites.

**Steps**
1. Phase A - Baseline and rollback safety.
2. Capture current script behavior and expected outputs for start/status/stop using existing service wrappers so post-change behavior can be compared. This includes runtime PID/log file expectations and health endpoint behavior. (blocks all later verification)
3. Record a rollback procedure for script changes and remote changes (single-file script revert and remote URL reset command set).
4. Phase B - Remove VPN helper lifecycle automation from service flow (core Priority 0 task).
5. Edit scripts/phone_stack_control.ps1 to remove VPN helper-specific variables, helper functions, and call sites from start/status/stop while preserving watchdog supervision, backup-before-start, token handling, and log paths. (depends on 1)
6. Confirm BAT wrappers still call the same actions unchanged: start_phone_api_service.bat, status_phone_api_service.bat, stop_phone_api_service.bat. No interface change expected. (parallel with 5)
7. Update docs that still describe automatic VPN helper startup/check/stop so service behavior documentation matches reality. (depends on 5)
8. Phase C - Move Git remote workflow to personal account (origin + master preserved).
9. Update local repository remote origin URL to https://github.com/RRPJ/fusball and verify fetch/push defaults still target master. (depends on 1)
10. Update contributor-facing docs where needed to reflect new canonical remote owner and any first-time clone/fork guidance. (depends on 9)
11. Phase D - Vercel deployment path for full phone API writes with production data.
12. Add explicit deployment architecture decision: keep the phone API deployable both as a local service and as a hosted web service. (depends on 1)
13. Implement Option 1 auth split: one read PIN for authenticated leaderboard/view access and a separate writer PIN for write endpoints (add player, submit match, presence updates). (depends on 12)
14. Introduce Vercel-compatible runtime for API routes and phone page, replacing direct Flask dev-server invocation pattern in deployment path (retain local run behavior for existing scripts). (depends on 12)
15. Pull forward minimal storage modernization prerequisite for production writes: replace shelve-backed mutable operations used by write endpoints with Neon Postgres as the persistent shared datastore for the Vercel deployment path, including schema/bootstrap path. (depends on 12)
16. Replace local filesystem write-lock mechanism with distributed-safe concurrency control suitable for multi-instance/serverless execution. (depends on 15)
17. Implement secure production secret handling for READ_PIN, WRITE_PIN, and data connection settings in Vercel project environment (store hashed PIN material server-side; never log raw PINs). (parallel with 15)
18. Add migration/import path from current app data into deployment datastore for production ranking continuity, with dry-run and rollback notes. (depends on 15)
19. Deploy to Vercel and run smoke validation for read and write endpoints against production-equivalent data, then cut over after acceptance. (depends on 13-18)
20. Phase E - Backlog and documentation closure.
21. Mark Priority 0 tasks complete in docs/backlog.md only after all three workstreams pass verification.
22. Add brief operations notes: how to start/stop locally without VPN helper automation, and how to monitor Vercel deployment health.

**Relevant files**
- c:/Users/Rutger.Jaspers/source/repos/fusball/docs/backlog.md — source Priority 0 scope and completion tracking.
- c:/Users/Rutger.Jaspers/source/repos/fusball/scripts/phone_stack_control.ps1 — remove VPN helper service/app orchestration while preserving watchdog/service behavior.
- c:/Users/Rutger.Jaspers/source/repos/fusball/start_phone_api_service.bat — validate unchanged wrapper behavior.
- c:/Users/Rutger.Jaspers/source/repos/fusball/status_phone_api_service.bat — validate status behavior remains clear after VPN helper removal.
- c:/Users/Rutger.Jaspers/source/repos/fusball/stop_phone_api_service.bat — validate stop flow without VPN app shutdown behavior.
- c:/Users/Rutger.Jaspers/source/repos/fusball/README.md — update setup/service notes if VPN helper automation is referenced.
- c:/Users/Rutger.Jaspers/source/repos/fusball/docs/development.md — update developer workflow notes for service control.
- c:/Users/Rutger.Jaspers/source/repos/fusball/docs/phone-api.md — update operational expectations for networking/service status.
- c:/Users/Rutger.Jaspers/source/repos/fusball/app/phone_api.py — current API/runtime behavior and write-lock semantics to refactor for deployment path.
- c:/Users/Rutger.Jaspers/source/repos/fusball/pyproject.toml — deployment/runtime dependency updates if needed.

**Verification**
1. Local service smoke: run start_phone_api_service.bat, status_phone_api_service.bat, and stop_phone_api_service.bat; verify watchdog + API status/logs report correctly and no VPN helper status output remains.
2. API smoke: confirm /api/health, /api/leaderboard, /phone, and one authenticated write endpoint still work in local PROD run path.
3. Docs consistency check: search docs and scripts for stale VPN helper startup/check/stop instructions; only intentional network-access guidance may remain.
4. Git remote validation: confirm origin URL equals https://github.com/RRPJ/fusball and default push branch remains master.
5. Deployment validation (staging then production): run read endpoint checks, authenticated write submission, and post-write leaderboard/ranking consistency checks against production datastore snapshot.
6. Auth validation: unauthenticated requests are denied, read PIN grants read-only access, and writer PIN is required for all write endpoints.
7. Data safety validation: perform pre-cutover backup, migration dry-run, rollback rehearsal, and post-cutover integrity checks (player counts, ranking order, recent history continuity).

**Endpoint Auth Matrix (Option 1)**
- Auth headers:
	- Read access header: `X-Read-Pin`
	- Write access header: `X-Write-Pin`
- Secret configuration:
	- `READ_PIN_HASH` for read PIN verification
	- `WRITE_PIN_HASH` for writer PIN verification
- Access rules:
	- No auth on health: `GET /api/health`
	- Read PIN required for all read views and data APIs.
	- Writer PIN required for all write APIs.
	- Writer PIN also grants read access to reduce client friction for operators.

- Public (no auth):
	- `GET /api/health`

- Read PIN or Writer PIN required:
	- `GET /phone`
	- `GET /api/leaderboard`
	- `GET /api/players`
	- `GET /api/presence`
	- `GET /api/h2h`
	- `GET /api/stats`
	- `GET /api/player/<name>/history`
	- `GET /api/odds`

- Writer PIN required:
	- `POST /api/matches`
	- `POST /api/players`
	- `POST /api/presence`
	- `POST /api/presence/clear`
	- `POST /api/lineup/random`
	- `POST /api/lineup/auto`

- Expected auth responses:
	- Missing/invalid read credentials on read endpoint: `401`
	- Missing/invalid writer credentials on write endpoint: `403`
	- Valid read PIN on write endpoint: `403`
	- Valid writer PIN on read/write endpoint: allow request

**Implementation Sketch (Auth Layer)**
1. Add auth configuration loader:
	- Read `READ_PIN_HASH` and `WRITE_PIN_HASH` from environment.
	- Fail startup in production profile if either hash is missing.
2. Add PIN verification helpers in API layer:
	- `_verify_read_pin(request)` checks `X-Read-Pin` and also accepts valid `X-Write-Pin`.
	- `_verify_write_pin(request)` checks `X-Write-Pin` only.
	- Use constant-time compare against hash verification results.
3. Add route guard wrappers:
	- `require_read_access()` returns `401` JSON when credentials are missing/invalid.
	- `require_write_access()` returns `403` JSON when writer credentials are missing/invalid.
4. Apply guards to endpoints per matrix:
	- Keep `/api/health` unguarded.
	- Guard all read endpoints with read-access guard.
	- Guard all write endpoints with write-access guard.
5. Keep response payloads consistent:
	- `{"error": "authentication required"}` for `401` read failures.
	- `{"error": "writer authorization required"}` for `403` write failures.
6. Logging and safety:
	- Never log incoming PIN values or headers.
	- Log only coarse auth result metadata (endpoint + allowed/denied).
7. Hashing recommendation:
	- Use Argon2id or bcrypt for PIN hash storage.
	- Add a small admin/dev script to generate hashes for Vercel secrets.
8. Test plan additions:
	- Read endpoint rejects no auth (`401`).
	- Read endpoint allows valid read PIN.
	- Read endpoint allows valid writer PIN.
	- Write endpoint rejects no auth (`403`).
	- Write endpoint rejects read PIN (`403`).
	- Write endpoint allows valid writer PIN.

**Decisions**
- Confirmed target remote URL: https://github.com/RRPJ/fusball.
- Branch strategy: keep master.
- Priority 0 interpretation includes full Vercel deployment with write endpoints enabled.
- Vercel deployment target is production ranking data, not sandbox.
- External database choice for deployment path: Neon Postgres.
- Auth approach: Option 1 with two shared credentials (read PIN and separate writer PIN).
- Scope boundary: Priority 0 deployment work targets the phone API/web surface only.
- Consequence: full Vercel write deployment cannot be safely completed without advancing a minimal subset of Priority 2 (storage + concurrency) into this implementation window.

**Further Considerations**
1. Sequence recommendation: complete Phases A-C first, then execute Phase D as a gated mini-project with explicit go/no-go checkpoint before production cutover.
2. Risk control recommendation: if Phase D datastore migration is not accepted in this cycle, close Priority 0 partially (VPN helper removal + Git remote) and split Vercel full-write deployment into a separate dependency-linked milestone.

**Neon Setup Checklist (For Vercel Deployment Path)**
1. Create Neon project and Postgres database for Fusball production.
2. Create separate Neon branch/database for preview/staging validation.
3. Create least-privilege database role for application runtime access.
4. Capture pooled connection string for Vercel runtime usage.
5. Add Vercel environment variables:
	- `DATABASE_URL` (Neon pooled connection string)
	- `READ_PIN_HASH`
	- `WRITE_PIN_HASH`
6. Ensure production and preview environments use different Neon connection strings.
7. Create schema migration scripts for players, ratings state, match history, and audit-compatible metadata.
8. Run shelve-to-Neon import in preview first, then validate parity:
	- Player counts and names
	- Leaderboard order and rank values
	- Match history counts and recent records
9. Perform rollback rehearsal before production cutover:
	- Confirm export snapshot exists
	- Confirm restore path from backup is documented and tested
10. Cut over production writes to Neon only after parity and rollback checks pass.
11. Monitor first-week production metrics:
	- Query errors
	- Write latency
	- Connection usage
	- Data growth versus free-plan thresholds
