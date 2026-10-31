# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. For multiline bodies, use `--body-file <path>`.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue**: `gh issue create --parent <parent> ...`, or `gh issue edit <parent> --add-sub-issue <child>` afterwards (`gh` 2.94+). Older `gh`: `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`. The ID is the numeric database ID, not the issue number. Without sub-issues, put `Part of #<parent>` at the top of the child body.
- **Blocking**: Use GitHub's native issue dependencies. Add an edge with `gh issue create --blocked-by <n>,<n> ...` or `gh issue edit <child> --add-blocked-by <blocker>` (`gh` 2.94+). Older `gh`: `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. Obtain the numeric database ID with `gh api repos/<owner>/<repo>/issues/<n> --jq .id`. If dependencies aren't available, add `Blocked by: #<n>, #<n>` at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Count open blockers**: `gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by` (0 means startable). `gh issue view <n> --json blockedBy` also includes closed blockers; filter them out.
- **Comment**: `gh issue comment <number> --body "..."`.
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- **Close**: for implementation or spec issues, follow the delivery gate below. Once eligible, comment with the evidence and explanation, then run `gh issue close <number>`. `gh issue close --comment` drops the comment on an already-closed issue.

Infer the repo from `git remote -v`; `gh` does this automatically in a clone. File issues only in the user's own repo. Before the first `gh issue create` of a session, check the target with `gh repo view --json nameWithOwner` and confirm it with the user if it is not their repo.

## Implementation and spec issue delivery

The target branch is the branch specified for delivery, or the default branch
if none is specified. A pushed feature or integration branch is branch
completion, not delivery to that target. An implementation or spec issue is
eligible for closure only after its acceptance criteria are satisfied, required
verification has passed, and the changes have actually been merged into the
target branch. Confirm the merge using the merged PR or target branch history;
do not infer it from a push, an open PR, CI on another branch, or a proposed
merge. A merge into an intermediate integration branch does not satisfy a
different target branch.

- **With a PR:** reference the issue without a closing keyword in the PR or
  commits while the PR targets an intermediate branch or other closure gates
  remain outstanding.
  GitHub closing keywords can close an issue when a PR merges into the default
  branch; use them only when that merge and all other gates establish
  eligibility. If required checks happen after merge, use a plain reference
  and close manually after recording their results. Verify the actual merge
  and its base branch, not merely the PR's existence.
- **Without a PR:** verify that the target branch contains the delivered
  change, using its history and commit(s), and record the target and merge
  evidence before manually closing the issue. For squash or rebased changes,
  identify the resulting target commit rather than assuming the original
  commit SHA is present.

Track manual verification and deployment separately from branch checks: record
each required action, environment, owner or responsible party, status, and
evidence or blocker in the issue or a linked follow-up. Required acceptance
verification remains a closure gate; do not silently defer it. Work outside
the issue's acceptance criteria can be tracked in an explicitly owned linked
follow-up, with its remaining work and relationship to delivery stated. If
deployment or production verification is an acceptance criterion, it must be
completed before closure; otherwise an eligible implementation issue may close
while a separate rollout follow-up stays open. Do not describe deployment or
production rollout as complete without actual environment-specific evidence;
see [rollout evidence](../development.md#rollout-evidence).

When reporting unfinished work, state the working branch and commit, target
branch and actual merge status, checks performed and their results, and
outstanding manual verification, deployment, blockers, and follow-ups. Say
what was not run or is unknown; distinguish local, preview, and production
evidence. Record the same status on the issue when updating it, without
claiming delivery or closure before its gates are met.

## Pull requests as a triage surface

**PRs as a request surface: no.** Set to `yes` if external PRs should enter the triage queue.

When enabled, read PRs with `gh pr view <number>`, `gh pr view <number> --comments`, and `gh pr diff <number>`. List external PRs with `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open'` and select those whose `author_association` is not `OWNER`, `MEMBER`, or `COLLABORATOR`. Use `gh pr comment`, `gh pr edit --add-label` / `--remove-label`, and `gh pr close` to manage them. GitHub shares issue and PR numbers; resolve an ambiguous number with `gh pr view`, then `gh issue view`.

## Skill operations

- **Publish to the issue tracker**: create a GitHub issue.
- **Fetch the relevant ticket**: read the issue as above.

## Wayfinding operations

- **Map**: one issue labelled `wayfinder:map`, containing Notes / Decisions-so-far / Fog.
- **Child ticket**: link an issue as a sub-issue of the map; if unavailable, add it to the map's task list and put `Part of #<map>` in its body. Label it `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`). Once claimed, assign it to the driving developer.
- **Blocking**: use the conventions above.
- **Frontier query**: list the map's open children, exclude those with open blockers or an assignee, and choose the first in map order.
- **Claim**: `gh issue edit <n> --add-assignee @me` as the session's first write.
- **Resolve**: comment with the answer, close the ticket, and append a gist and link to the map's Decisions-so-far. For implementation or spec tickets, first satisfy the delivery gate above.
