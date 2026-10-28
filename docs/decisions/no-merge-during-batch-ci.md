# No merge while a batch's CI runs

## The ruling

The owner ruled on Oct 28 at 13:36 CDT: no one merges to main while a batch's CI runs. That includes the owner.

- Mechanism: the merge tool (`merge <pr> --confirm`) and the merge guard refuse to merge a PR while another open, non-draft PR on the same base has a required check pending on its head.
- The tool checks under the lock before any push. It checks again right before the merge call. So a batch that goes ready during the wait for the head's checks is refused.
- The preview prints a `batch:` line.
- A failed read refuses. Unknown is red, as in decision ci-unknown-is-red (an unknown read in CI is red).
- The refusal names the other PR, the check and the check's link. It says to wait. The session that watches the other PR wakes when its run ends. A red run also posts the CI-done comment (rule git-ci-done-comment-wakes).
- No reason flag lifts this refusal in the tool.

Not counted:

- Drafts. CI skips them.
- The PR's own run.
- A check that is not required, such as impeccable-sync.
- A PR on another base.
- The push run on main after a merge.

Limits:

- Pressing GitHub's own Merge button is not refused by a hook.
- A raw `gh api -X PUT .../pulls/<n>/merge` is not refused by a hook.
- The guard stops `gh pr merge` and the MCP merge tool. For the rest, the rule binds the owner by the owner's own word.
- A required check with no entry on the other head does not count. So in the seconds after a PR goes ready, before GitHub creates its checks, a merge is not refused.

Why: batch 13's lanes, roadmap steps c182 and c187 (PRs #777 and #778), each conflicted with batch 12 (PR #779). A merge to main under a running batch run moves the base that run tests. This rule is roadmap step c195.

- Risk: named incident, batch 13 against batch 12, Oct 28. Landed 2026-10-28.
- Check: `merge/test_merge.py` classes BatchRunningReads and BatchBrake, and the `hooks/test_guard.py` cases named `merge-batch:`.
- Cost: one batch read is one read of the open pull list. When another ready PR is on the base, it adds one read of the required checks and two reads (check runs, commit statuses) for each such PR. Per `--confirm`, two batch reads. Per preview, one. Per guarded merge call of a settled head, one, inside the guard's one read deadline. No process starts, no file written, no timer.

Kind: process
Home: merge/merge.py
