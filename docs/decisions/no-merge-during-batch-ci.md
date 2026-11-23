# No merge while a batch's CI runs

## The ruling

State: live until the cutover (decision `all-repos-switch-together`). The per-lane target retires it, with the batches it governs. Until then the red-main check (decision `no-merge-onto-red-main`) does not replace it.

No one merges to main while a batch's CI runs, unless the running batch's head already contains the merging PR's head. That includes the owner (ruled Oct 28 at 13:36 CDT).

The owner's reading, Nov 1 20:54 CST: the rule keeps main from moving under a running batch. It does not forbid testing batch N+1 on top of batch N. A merge of N moves main to a tree that N+1's head already holds, so N+1's run still tests what lands.

- Mechanism: the merge guard (`merge-checks`, through `Host.batch_running`) refuses a merge outside the merge tool while another open, non-draft PR on the same base is busy. The refusal stands only when that PR's head does not contain this PR's head. The merge tool (`merge <pr> --confirm`) merges each lane on its own and holds no merge for another PR's CI. Owner ruling `own-896-897-glued-amp-b` (2026-11-16 13:30 CST) keeps the guard's refusal.
- Contains: both reads must pass.
  - The busy PR's head holds this head: GitHub's compare of this PR's head to the other head (`compare/<this>...<other>`) reads `ahead` or `identical`.
  - This head holds the base tip: GitHub's compare of the base to this head (`compare/<base>...<this>`) reads `ahead` or `identical`.
  - Either failed read refuses. The guard reads both only for a busy PR.
- What counts as busy (orchestrator ruling, Oct 28): its head has any workflow run not completed, or a required check or status reported and pending. A running workflow counts, required or not, because a required job can wait on another job: in checks.yml, `checks` needs `scope`, so `checks` has no row while `scope` runs. Runs and checks that merge.ignoreChecks names never count.
- The guard reads the other PRs only after this head is settled.
- Required names: the repo's pinned `merge.requiredChecks` list, else the ruleset or the branch protection. The guard's ruling (orchestrator, Oct 28): with none (HTTP 404), every reported pending check on the other ready PR counts. A protection read that fails any other way is unknown, and denies.
- A failed read refuses. Unknown is red, as in decision ci-unknown-is-red (an unknown read in CI is red).
- The refusal names the other PR, and the check with its link or the workflow that runs. It says to wait. `--express` keeps the brake and adds the prose-only entry rule (ruling R59 part 5, a ruled prose change skips the batch queue and runs only the checks that read its files; decision owner-override). The session that watches the other PR wakes when its run ends. A red run also posts the CI-done comment (rule git-ci-done-comment-wakes).
- No reason flag lifts this refusal.

Express lane:

- R55, merge-flow fixes take an express lane. It puts a fix ahead of every other lane.
- R67, drain first, puts a fix ahead of the drain too.
- R65, ready express lanes share one batch: express lanes ready at the same time merge together.
- If a batch is in CI when an express fix is ready, the batch runner cancels that run first. Rule git-no-merge-during-batch-ci still holds: no run is in progress at the merge.
- The list names kinds of fix. It is not a closed list of step slugs. Every fix that tracks or lands work takes the express lane. Kinds named so far: merge flow, CI fixes, lane-start and hand-in guards, lost-work sweep, the pick-to-page guard, and the ruling-challenge and deference fixes.
- A fix of one of these kinds takes the lane even when no list names its slug. The test is whether the fix tracks or lands work. Sheer new work does not take the express lane.
- This is not the `--express` flag above.

Reason: R67 part 4 (owner grant, 10:54 and 10:56 CST Nov 13). Owner, 10:54 CST: "my rulings are being read too strictly". Owner, 10:56 CST: "fast track all of those". R55's list is read by kind, not word by word.

Not counted:

- Drafts. CI skips them.
- The PR's own run.
- A completed check, or a pending check that is not required, on a head with no workflow run open.
- A PR on another base.
- The push run on main after a merge.
- A busy ready PR whose head contains this PR's head: the next batch, built on this one.

Limits:

- Pressing GitHub's own Merge button is not refused by a hook.
- A raw `gh api -X PUT .../pulls/<n>/merge` is not refused by a hook.
- The guard stops `gh pr merge`, `mcp__github__merge_pull_request`, `mcp__github__enable_pr_auto_merge`, and `mcp__ccd_pr__set_auto_merge` with `enabled` not false. The last two arm GitHub auto-merge. `mcp__ccd_pr__set_auto_merge` names its pull request by URL, so the guard reads the number and repo from it (`hooks/guard_merge.py` `merge_tool_target`). A URL that names no github.com pull request is refused, never read from the checkout. Turning it off merges nothing and is allowed (`hooks/guard_merge.py` `merge_tool_merges`). It judges all four on the same head read, at the moment of the call only. An armed auto-merge can fire on a later head, because the guard does not look again after a push. What GitHub does with an armed auto-merge after a push is unverified. For the rest, the rule binds the owner by the owner's own word.
- A required check with no entry and no workflow run on the other head does not count. So in the seconds after a PR goes ready, before GitHub creates its runs, a merge is not refused.

Why: batch 13's lanes, roadmap steps c182 and c187 (PRs #777 and #778), each conflicted with batch 12 (PR #779). A merge to main under a running batch run moves the base that run tests. This rule is roadmap step c195.

- Risk: named incident, batch 13 against batch 12, Oct 28. Landed 2026-10-28; overlapping batches 2026-11-02.
- Check: the `hooks/test_guard.py` cases named `merge-batch:`. The overlap cases replay PR #63 merging while PR #65 (head b8416ca, which contains #63's head 476f456c) runs.
- Cost: one batch read is one read of the open pull list (unmeasured). When another ready PR is on the base, it adds one read of the required checks (none with a pinned list) (unmeasured). Each such PR adds three reads (check runs, commit statuses, workflow runs), and each busy one adds up to two compare reads. Per guarded merge call of a settled head, one, inside the guard's one read deadline (unmeasured). No process starts, no file written, no timer.

Kind: process
Home: merge/merge.py
