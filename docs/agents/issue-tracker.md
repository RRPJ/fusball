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
- **Close**: comment with the explanation, then run `gh issue close <number>`. `gh issue close --comment` drops the comment on an already-closed issue.

Infer the repo from `git remote -v`; `gh` does this automatically in a clone. File issues only in the user's own repo. Before the first `gh issue create` of a session, check the target with `gh repo view --json nameWithOwner` and confirm it with the user if it is not their repo.

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
- **Resolve**: comment with the answer, close the ticket, and append a gist and link to the map's Decisions-so-far.
