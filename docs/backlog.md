# Improvement Backlog

Use this file to prioritize changes in small, safe slices.
See `docs/reliability-maintainability-plan.md` for the detailed modernization,
authentication, match-correction, and hosted data-safety roadmap.

## Quarterly Leaderboard

- [x] Add a quarterly (calendar quarter: Jan-Mar, Apr-Jun, etc.) leaderboard view.
- [x] Display alongside existing time-window leaderboards (This Week, This Month).

## UI Revamp

- [ ] Simplify the operator UI by clearly separating leaderboard and match submission flows.
- [ ] Remove menu items (Players, Score, Submit) and reorganize for clearer navigation.
- [ ] Improve usability and reduce cognitive load for phone-based match entry.
- [ ] (Implementation details to be fleshed out during execution.)

## Tournament Exploration

- [ ] Explore tournament support requirements: bracket types, group stages, and ranking impact.
- [ ] Decide whether tournaments should be isolated events, season-scoped events, or both.
- [ ] Define the minimal tournament slice worth prototyping without disrupting normal match flow.

## Player Profiles and Rivalries

- [x] Build player detail page: recent matches, offense vs defense trend, current streak, best partner, toughest opponent.
- [ ] Create rivalries hub: most-played rivalries, closest rivalry, one-sided matchups, revenge tracking.

## Queue and Match Suggestions

- [ ] Add next-match suggestion UI based on active presence and lineup balance.
- [ ] Detect and warn when a player has been sitting out or playing too many consecutive matches.
- [ ] Suggest auto-balanced lineups when multiple players are active (pair with existing lineup balancing logic).

## Session Recap and Result Cards

- [ ] After each match submit, show a brief result card: upset/not upset, rating gain, streak impact, prediction accuracy.
- [ ] Add session grouping to identify who played together, when the table was hottest, and who earned the night's title.
- [ ] Layer in existing odds and quip logic to make match feedback more engaging and narrative-driven.
