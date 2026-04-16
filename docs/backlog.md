# Improvement Backlog

Use this file to prioritize changes in small, safe slices.

Scope note:
- This file is the execution queue (ordered next actions).
- `docs/modernization-plan.md` is the longer-term strategy and rationale.

Sequencing note:
- Finishing Priority 1 smartphone write/read validation is not a hard prerequisite for every later priority.
- First deliver only a minimal authenticated phone match-submit proof, then shift focus to structured match history before expanding remote workflows.
- Priority 2 should start immediately after, or in parallel with final validation of, the minimal remote write slice because structured history is a dependency for analytics, seasons, and safer future remote workflows.
- Priority 2 becomes more important before remote write support expands beyond that minimal authenticated match-submit flow.
- Priorities 3 and 5 depend on the history/modeling work in Priority 2 and should not be treated as immediate follow-ons to basic phone write support.

## Priority 0: Immediate Repository And Deployment Tasks

- Implementation plan: `docs/priority-0-implementation-plan.md`

- [x] Remove VPN helper startup / check / stop automation from service scripts and documentation (follow-up to manual prod runner simplification).
- [x] Select Neon Postgres as the external database for the Vercel deployment path.
- [x] Move the origin/master to personal account instead of cadmin.
- [x] Add initial Vercel deployment scaffold (`vercel.json`, `api/index.py`, `.env.example`).
- [x] Add initial Neon migration prototype scaffold (`scripts/sql/neon_schema.sql`, `scripts/migrate_shelve_to_neon.py`).
- [x] Run first shelve -> Neon import (`--apply --reset`) and verify parity counts (`players`, `recent_players`, `match_history`).
- [x] Deploy phone API to Vercel with Neon Postgres backing production data.

## Priority 1: Smartphone Access Path

- Goal of remaining Priority 1 work: prove a minimal authenticated phone match-submit flow, not a broad remote feature set.
- [ ] Run at-home validation on iOS: leaderboard read.
- [ ] Run at-the-office validation from a different network: confirm leaderboard loads from phone.

## Priority 2: Data Layer Modernization

- [ ] Define portable storage model (Neon Postgres for Vercel path; local fallback may remain optional).
- [ ] Add export/import snapshot path from shelve.
- [ ] Add migration prototype (shelve -> Neon Postgres) with rollback notes.
- [ ] Keep compatibility reader for old backups until parity is verified.

## Priority 3: Seasons And Historical Views

- [ ] Define a season model that supports current season ranking plus all-time ranking.
- [ ] Decide season cadence support (manual seasons first; optional quarterly auto-rollover later).
- [ ] Preserve historical season standings when a new season starts instead of resetting all-time stats.
- [ ] Add season-aware leaderboard and analytics views.
- [ ] Document how season boundaries interact with ratings, logs, exports, and future migrations.

## Priority 4: Remote Match Operations

- [ ] After auth/conflict rules are defined, add authenticated phone match submission if Priority 1 has not already delivered the minimal submit flow.
- [ ] Expand remote workflows beyond the minimal submit proof only after the structured history model is stable.
- [ ] Add live refresh for remote leaderboard/match state after a submitted result.
- [ ] Decide whether lightweight live session views are enough before considering broader web workflows.

## Priority 5: Tournament Exploration

- [ ] Explore tournament support requirements: bracket types, group stages, and ranking impact.
- [ ] Decide whether tournaments should be isolated events, season-scoped events, or both.
- [ ] Define the minimal tournament slice worth prototyping without disrupting normal match flow.

## Priority 6: Optional UX Enhancements

- [ ] Improve validation messages for invalid team composition.
- [ ] Improve keyboard/search feedback in match entry.
- [ ] Add match history analytics dashboard.
