# No merge while a batch's CI runs

## The ruling

No one merges to main while a batch's CI runs, unless the running batch's head already contains the merging PR's head. That includes the owner (ruled Oct 28 at 13:36 CDT).

The owner's reading, Nov 1 20:54 CST: the rule keeps main from moving under a running batch. It does not forbid testing batch N+1 on top of batch N. A merge of N moves main to a tree that N+1's head already holds, so N+1's run still tests what lands.

- Mechanism: the merge tool (`merge <pr> --confirm`) and the merge guard refuse to merge a PR while another open, non-draft PR on the same base is busy. The refusal stands only when that PR's head does not contain this PR's head.
- Contains: both reads must pass.
  - The busy PR's head holds this head: GitHub's compare of this PR's head to the other head (`compare/<this>...<other>`) reads `ahead` or `identical`.
  - This head holds the base tip: GitHub's compare of the base to this head (`compare/<base>...<this>`) reads `ahead` or `identical`.
  - Either failed read refuses. The tool reads both only for a busy PR.
- What counts as busy (orchestrator ruling, Oct 28): its head has any workflow run not completed, or a required check or status reported and pending. A running workflow counts, required or not, because a required job can wait on another job: in checks.yml, `checks` needs `scope`, so `checks` has no row while `scope` runs. Runs and checks that merge.ignoreChecks names never count.
- The tool checks under the lock before any push. It checks again right before the merge call. So a batch that goes ready during the wait for the head's checks is refused. That second refusal reverts the claim, and the revert push starts a new run on the refused PR.
- The preview prints a `batch:` line.
- Required names: the repo's pinned `merge.requiredChecks` list, else the branch protection. The guard's ruling (orchestrator, Oct 28): with no branch protection (HTTP 404), every reported pending check on the other ready PR counts. The tool refuses a base with no protection and no pinned list.
- A failed read refuses. Unknown is red, as in decision ci-unknown-is-red (an unknown read in CI is red).
- The refusal names the other PR, and the check with its link or the workflow that runs. It says to wait. The session that watches the other PR wakes when its run ends. A red run also posts the CI-done comment (rule git-ci-done-comment-wakes).
- No reason flag lifts this refusal in the tool.

Not counted:

- Drafts. CI skips them.
- The PR's own run.
- A completed check, or a pending check that is not required, on a head with no workflow run open.
- A PR on another base.
- The push run on main after a merge.
- A busy ready PR whose head contains this PR's head: the next batch, built on this one.

Limits:

- Pressing GitHub's own Merge button is not refused by a hook.
- A GraphQL merge or auto-merge, sent with `gh api graphql`, is not refused (read hooks/guard_merge.py).
- A forced push, a push of all branches, or a mirror push that writes main is not braked: these name no single head.
- A pull-list read that fails on a push to main stays an ask, as before.
- GitHub auto-merge fires later, so a batch that turns busy after auto-merge is on is missed.
- The merge tool's own refusal offers no `override`: nothing lifts a Stop there.
- A raw `gh api` merge path the guard cannot read as a number or a plain `$VAR` is not matched: `pulls/${PR:-1}/merge`, `pulls/$(…)/merge`, a backtick number, an absolute URL, and `-X=PUT`. Main allowed these too. A plain `$PR` or `$REPO` is matched and denied as unknown (read hooks/guard_merge.py).
- The legacy `repos/:owner/:repo/pulls/5/merge` form reads as a repo that cannot resolve, so it is denied as unknown: a false alarm, never a bypass.
- The variable-path refusal says to wait, but waiting never resolves `$PR`: name the pull request by its number.
- Each batch read has its own 25 s deadline, so two hung reads in one command add up to about 50 s, near the guard's 60 s hook timeout.
- For the rest, the rule binds the owner by the owner's own word.
- A required check with no entry and no workflow run on the other head does not count. So in the seconds after a PR goes ready, before GitHub creates its runs, a merge is not refused.
- A claim or heal commit at merge changes this PR's head. The running batch does not hold the new head, so the brake refuses again, and the claim is reverted. Build the next batch on this batch's head at ready, after its records step.

Routes the guard covers (lane batch-ci-merge-guard, after the Nov 8 incident): `gh pr merge`, the MCP merge tool, a raw `gh api -X PUT .../pulls/<n>/merge` (also `--method PUT`, and `-R`), the MCP `enable_pr_auto_merge`, and a `git push` that writes main. A push is refused when a ready PR on main is busy and its head does not hold the pushed head. An unreadable pushed head or compare counts as not held (unknown is red). With no busy PR the push keeps its ask. Each refusal names the busy PR and its run, offers the owner's typed `override`, and its Remedy sentence names no act.

Why the Nov 8 merges got through (#2352 at 19:19 CST and #2350 at 19:53 CST, during the run of #2361). Measured: `mcp__github__merge_pull_request` was in no guard matcher in `settings.json`, so the MCP route never reached the guard. Unmeasured: the form the local session used, because guard.log is not readable from the cloud. A raw API merge and a push to main had no batch brake in any case.

Why: batch 13's lanes, roadmap steps c182 and c187 (PRs #777 and #778), each conflicted with batch 12 (PR #779). A merge to main under a running batch run moves the base that run tests. This rule is roadmap step c195.

- Risk: named incident, batch 13 against batch 12, Oct 28. Landed 2026-10-28; overlapping batches 2026-11-02.
- Check: `merge/test_merge.py` classes BatchRunningReads and BatchBrake, and the `hooks/test_guard.py` cases named `merge-batch:` and `merge-route:`. The overlap cases replay PR #63 merging while PR #65 (head b8416ca, which contains #63's head 476f456c) runs.
- Cost: one batch read is one read of the open pull list. When another ready PR is on the base, it adds one read of the required checks (none with a pinned list). Each such PR adds three reads (check runs, commit statuses, workflow runs), and each busy one adds up to two compare reads. Per `--confirm`, two batch reads. Per preview, one. Per guarded merge call of a settled head, one, inside the guard's one read deadline. A raw API merge and auto-merge cost the same as a guarded merge call. A push that writes main adds one `git rev-parse` for the pushed head and one pull-list read. The `merge-route:` cost case pins the spawn count. When a busy PR blocks the push, one more compare read tests whether the pushed head equals main's tip. A push that moves nothing keeps its ask. That read runs inside the same deadline. A push to any other branch adds none. No process outlives the call, no file is written, no timer.

Kind: process
Home: merge/merge.py
