# No merge while a batch's CI runs

## The ruling

The owner ruled on Oct 28 at 13:36 CDT: no one merges to main while a batch's CI runs. That includes the owner.

- Mechanism: the merge tool (`merge <pr> --confirm`) and the merge guard refuse to merge a PR while another open, non-draft PR on the same base is busy.
- What counts as busy (orchestrator ruling, Oct 28): its head has any workflow run not completed, or a required check or status reported and pending. A running workflow counts, required or not, because a required job can wait on another job: in checks.yml, `checks` needs `scope`, so `checks` has no row while `scope` runs. Runs and checks that merge.ignoreChecks names never count.
- The tool checks under the lock before any push. It checks again right before the merge call. So a batch that goes ready during the wait for the head's checks is refused.
- The preview prints a `batch:` line.
- Required names: the repo's pinned `merge.requiredChecks` list, else the branch protection. The guard's ruling (owner, Oct 28): with no branch protection (HTTP 404), every reported pending check on the other ready PR counts. The tool refuses a base with no protection and no pinned list.
- A failed read refuses. Unknown is red, as in decision ci-unknown-is-red (an unknown read in CI is red).
- The refusal names the other PR, and the check with its link or the workflow that runs. It says to wait. The session that watches the other PR wakes when its run ends. A red run also posts the CI-done comment (rule git-ci-done-comment-wakes).
- No reason flag lifts this refusal in the tool.

Not counted:

- Drafts. CI skips them.
- The PR's own run.
- A completed check, or a pending check that is not required, on a head with no workflow run open.
- A PR on another base.
- The push run on main after a merge.

Limits:

- Pressing GitHub's own Merge button is not refused by a hook.
- A raw `gh api -X PUT .../pulls/<n>/merge` is not refused by a hook.
- The guard stops `gh pr merge` and the MCP merge tool. For the rest, the rule binds the owner by the owner's own word.
- A required check with no entry and no workflow run on the other head does not count. So in the seconds after a PR goes ready, before GitHub creates its runs, a merge is not refused.

Why: batch 13's lanes, roadmap steps c182 and c187 (PRs #777 and #778), each conflicted with batch 12 (PR #779). A merge to main under a running batch run moves the base that run tests. This rule is roadmap step c195.

- Risk: named incident, batch 13 against batch 12, Oct 28. Landed 2026-10-28.
- Check: `merge/test_merge.py` classes BatchRunningReads and BatchBrake, and the `hooks/test_guard.py` cases named `merge-batch:`.
- Cost: one batch read is one read of the open pull list. When another ready PR is on the base, it adds one read of the required checks (none with a pinned list) and three reads (check runs, commit statuses, workflow runs) for each such PR. Per `--confirm`, two batch reads. Per preview, one. Per guarded merge call of a settled head, one, inside the guard's one read deadline. No process starts, no file written, no timer.

Kind: process
Home: merge/merge.py
