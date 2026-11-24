# The green head's base is never compared with the current base

- **What.** `green-head.sh` names the newest earlier green run of the pull request, with no base check. `ci-scope.sh` takes the delta from that head to the pull request head, which holds only the PR's own commits, and checks only that the head is an ancestor. So a comment-only or records-only commit on a PR whose base moved skips the suites on the merge commit, which holds base code that the green run never ran with. The records-only skip has the same gap. Unmeasured: whether main's push run covers it. Claude meets it when main moves after a PR's green run and the next commit on that PR is a comment or docs edit.
- **Where.** `.github/scripts/green-head.sh` (lines 14-21, the run pick). `.github/scripts/ci-scope.sh` (lines 265-287, the delta skip).
- **Decision.** `push-skip-on-proven-tree` (a push skips on a proven tree; its deltas that run no suite).
- **Retire.** A fix that compares the green run's base with the current base, or takes the delta from that base, closes it. Closed by `lint/test_ci_scope.py`, with a case where the base moved after the green run.
