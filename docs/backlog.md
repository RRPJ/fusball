# Improvement Backlog

This file contains genuine future product work only. Completed reliability and
maintainability milestones are recorded in
`docs/reliability-maintainability-plan.md`.

## Operator UI Simplification

- [ ] Separate leaderboard browsing from the match-entry task so standings do
  not compete with lineup and score entry on the first step.
- [ ] Replace the current Mode/Players/Score/Confirm step menu with a
  lower-friction phone workflow while preserving validation, offline
  read-only behavior, authorization, and the dedicated admin view.
- [ ] Validate the revised flow with operators and measure time, taps, and
  correction frequency for singles and doubles entry.

## Tournament Exploration

- [ ] Define supported bracket and group-stage formats and how tournament
  results affect normal ratings.
- [ ] Decide whether tournaments are isolated events, season-scoped events, or
  both.
- [ ] Prototype the smallest tournament slice without disrupting normal match
  submission and replay semantics.

## Rivalries

- [ ] Create a rivalries hub using the existing player profile and H2H data,
  covering most-played, closest, and one-sided matchups.
- [ ] Define revenge tracking precisely, including the time window, eligible
  rematches, and treatment of voided matches.

## Rotation And Next-Match Suggestions

- [ ] Suggest the next participants from active presence and recent match
  history while keeping operator choice authoritative.
- [ ] Detect and surface players who have sat out unusually long or played too
  many consecutive matches.
- [ ] Connect rotation suggestions to the existing random and auto-balance
  lineup helpers so a suggested group can be assigned and balanced with one
  action.

## Post-Match Recap And Sessions

- [ ] After a successful submit, retain a result card showing upset
  classification, rating deltas, streak changes, and prediction accuracy,
  reusing the existing odds and quip logic.
- [ ] Define session boundaries and group matches into table sessions without
  changing rating or lifecycle semantics.
- [ ] Add a session recap for participation, notable matchups, activity peaks,
  and a clearly defined session title or award.
