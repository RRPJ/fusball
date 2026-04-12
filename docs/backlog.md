# Improvement Backlog

Use this file to prioritize changes in small, safe slices.

Scope note:
- This file is the execution queue (ordered next actions).
- `docs/modernization-plan.md` is the longer-term strategy and rationale.

Sequencing note:
- Finishing Track C write-from-phone support is not a hard prerequisite for every later track.
- First deliver only a minimal authenticated phone match-submit proof, then shift focus to structured match history before expanding remote workflows.
- Track C2 should start immediately after, or in parallel with final validation of, the minimal remote write slice because structured history is a dependency for analytics, seasons, and safer future remote workflows.
- Track D becomes more important before remote write support expands beyond that minimal authenticated match-submit flow.
- Tracks E and G depend on the history/modeling work in C2 and should not be treated as immediate follow-ons to basic phone write support.

## Completed Foundation (Done)

- [x] Add startup diagnostic logging for missing assets and db files.
- [x] Add reproducible smoke checks for ranking/probability behavior.
- [x] Add CI checks for lint + smoke test.
- [x] Add lint/format tooling and pre-commit hooks.
- [x] Create `fusball.py` as canonical entrypoint while keeping `lcars.py` compatibility.
- [x] Extract service layer for player store, match logic, and match logging.
- [x] Archive Raspberry Pi kiosk/touchscreen deployment files under `legacy/`.

## Completed: Track A2 (Targeted Test Coverage)

- [x] Add test for rating update transitions (win/loss and draw cycles).
- [x] Add test for match save flow (persistence + logfile entry format).
- [x] Add regression test for auto-balance lineup selection behavior.

## Completed: Track A3 (Screen Refactor)

- [x] Split long methods in `app/screens/entermatch.py` into smaller helpers.
- [x] Split long methods in `app/screens/enteroutcome.py` into smaller helpers.
- [x] Add concise docstrings for complex screen/service methods.

## Track C: Smartphone Access Path

- [x] Confirm architecture split: kiosk Pygame UI stays local; phones use web/API path.
- [x] Select initial connectivity method for home testing (Tailscale preferred for early rollout).
- [x] Option 2 spike (read-only first): add thin operator HTTP API endpoint for leaderboard read.
- [x] Build minimal mobile web page that consumes leaderboard API on iOS/Android browsers.
- [x] Validate host-side read-only behavior (`/api/leaderboard` and `/phone`) against local player data.
- [x] Resolve phone reachability path: Tailscale installed on laptop and Android phone; leaderboard loads on phone browser.
- Goal of remaining Track C work: prove a minimal authenticated phone match-submit flow, not a broad remote feature set.
- [x] Define auth and write-conflict rules between local UI and remote API calls in `docs/phone-write-policy.md`.
- [x] Add the smallest useful write endpoint for finished match submit only after auth/conflict rules are in place.
- [x] Keep the first write slice intentionally narrow: submit result, verify persistence/ranking update, and stop there.
- [x] Add authenticated phone-side player creation (`POST /api/players`) for real-world onboarding from mobile.
- [x] Add production/development launcher split so real rankings and dev testing data stay isolated.
- [x] Add startup backup in production phone launcher before serving.
- [x] Run end-to-end at-home validation: match submit from phone, then leaderboard refresh (validated 2026-04-11).
- [ ] Run at-home validation on iOS: leaderboard read.
- [ ] Run at-the-office validation via Tailscale: confirm leaderboard loads from phone on a different network.


## Track C2: Structured Match History And Analytics Foundation

Start this immediately after the minimal phone write proof is working, before broader remote workflows.

- [ ] Add structured match history storage alongside `logfile.log` so analytics do not depend on log parsing.
- [ ] Keep the existing audit log append behavior for rollback/debugging while structured history is introduced.
- [ ] Add a small inspection/smoke path that verifies persisted match history matches ranking-impacting results.

## Track C3: Prediction And Insights

- [ ] Surface expected result context from existing odds logic (predicted winner / closeness / upset indicator).
- [ ] Add head-to-head records between players and common doubles pairings.
- [ ] Add recent-form views (for example last 10 matches) for players and teams.
- [ ] Add progression-over-time views for rating, including separate offense and defense trends.
- [ ] Add richer leaderboard modes: streaks, form, most improved, and upset performance.
- [ ] Extend compact leaderboard filters with time window / min games / season scope.

## Track D: Data Layer Modernization

- [ ] Define portable storage model (SQLite recommended).
- [ ] Add export/import snapshot path from shelve.
- [ ] Add migration prototype (shelve -> SQLite) with rollback notes.
- [ ] Keep compatibility reader for old backups until parity is verified.

## Track E: Seasons And Historical Views

- [ ] Define a season model that supports current season ranking plus all-time ranking.
- [ ] Decide season cadence support (manual seasons first; optional quarterly auto-rollover later).
- [ ] Preserve historical season standings when a new season starts instead of resetting all-time stats.
- [ ] Add season-aware leaderboard and analytics views.
- [ ] Document how season boundaries interact with ratings, logs, exports, and future migrations.

## Track F: Remote Match Operations

- [ ] After auth/conflict rules are defined, add authenticated phone match submission if Track C has not already delivered the minimal submit flow.
- [ ] Expand remote workflows beyond the minimal submit proof only after the structured history model is stable.
- [ ] Add live refresh for remote leaderboard/match state after a submitted result.
- [ ] Decide whether lightweight live session views are enough before considering broader web workflows.

## Track G: Tournament Exploration

- [ ] Explore tournament support requirements: bracket types, group stages, and ranking impact.
- [ ] Decide whether tournaments should be isolated events, season-scoped events, or both.
- [ ] Define the minimal tournament slice worth prototyping without disrupting normal match flow.

## Optional UX Enhancements

- [ ] Improve validation messages for invalid team composition.
- [ ] Improve keyboard/search feedback in match entry.
- [ ] Add match history analytics dashboard.
