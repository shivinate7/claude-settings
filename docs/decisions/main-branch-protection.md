# main branch protection

## The ruling

`main` of shivinate7/claude-settings requires one check: `all-jobs-passed`, the job in
`.github/workflows/checks.yml` that runs the shared action `actions/all-jobs-passed`. Owner ruling,
2026-10-30 15:03 CDT (waiting-page item 87, the owner's waiting page): branch protection requires that one
check. The one-check ruling for every repo sits in record same-check-kinds (PR #877).
Owner ruling r (2026-11-11 16:43 CST) puts that check in a ruleset on `main`. See Ruled, not yet built.
`.github/stamp.json` `merge.requiredChecks` is `"protection"`. Today the `merge` tool reads the check names
from branch protection. Changing a repo's protection is the owner's to do, unless a grant covers it (see the
temporary grant below).
Built-today lines in this record were not re-read by the edit of 2026-11-11 23:09 CST. No live setting was read.

- `all-jobs-passed` needs every job that runs on a pull request, except `ci-done`, which needs it. It fails
  when a needed job failed, was cancelled or was skipped. `lint/test_all_jobs_passed.py` goes red when such a
  job is missing from its `needs`.
- `all-jobs-passed` runs only on a pull request. The five Windows shard jobs run only off a pull request, so
  they are not in its `needs`. On main their own job results are the verdict.
- A job that a scope flag turns off skips its steps, not the job, so it ends green, not skipped. Cost: a
  pull request that turns every flag off starts 11 runners (6 Windows, 2 macOS, 3 Linux) that skip every
  step.
- A draft PR runs no CI: `scope` skips on a draft, and every other job skips with it.
- A merge needs a pull request and no approval.
- Today's classic protection has `strict` false (`strict` requires the branch to be up to date with main).
  GitHub merges a PR that lacks main's newest commit. The `merge` tool refuses it (`merge-needs-current-base`: a merge needs a green run on the current base). The refusal lifts only for a small base move (`small_base_move` in `merge/merge.py`; decision `merge-needs-current-base`). A small base move holds when main has no change since the merge base. Otherwise all four conditions must hold. Main's paths since the merge base share no path with the batch's (the records page aside). The merge of the head and main is clean. The scope turns no job on for main's paths. The lints and affected suites pass on that merge. If any one fails, the refusal says to merge main into the branch, push, and run again.
- Today's classic protection includes admins (`enforce_admins`), so it binds the owner. Ruled, not yet built:
  bypass, below, lets the repository admin role skip the checks on pull requests only.
- Today, a new repo's protection from project-ops `protect.py` (the script that sets branch protection) sets `strict` false, `enforce_admins` true, no review rule, no restrictions. Ruled, not yet built: `protect.py` sets a ruleset instead.
- Today, classic protection blocks force pushes and branch deletion. Whether `main` has a ruleset today is unmeasured by this edit.
- Today's protection holds the one required check. A new job goes in the `needs` of `all-jobs-passed`, not in
  the required set. Today `merge` stops when a pinned `merge.requiredChecks` list in `stamp.json` differs from a non-empty branch protection list, and names both sets. An empty or unreadable protection list does not stop it: the pinned list stays in force, and an unreadable one is said aloud (`refuse_pinned_mismatch`, sweep row `pinned-mismatch`; roadmap step c189, the merge tool and branch protection work).
- Today's switch changes only the required checks, through `protect.py`: preview
  `python3 ~/.claude/skills/project-ops/scripts/protect.py --repo shivinate7/claude-settings --check all-jobs-passed`,
  then the same with `--confirm`. On a branch with a check rule it PATCHes the check list only; `strict` stays.
  The protection pins app id 15368 (GitHub Actions) (last read 2026-11-03 19:19 CST: `checks` [{all-jobs-passed, 15368}]). `protect.py` sends `contexts` only, so it does not pin an app id. Whether a contexts-only PATCH keeps that pin is unmeasured. The write needs the
  shivinate7 login: `ssemwal-cdc` has push, not admin. A handed block (commands handed to the owner to run, decision `act-in-place`) opens with `gh auth switch -u shivinate7`. A cloud session acts as `shivinate7` with admin, but the auto-mode classifier refused its direct PATCH as a CI bypass. Whether it refuses `protect.py --confirm` is unmeasured.
  The owner switched it on 2026-10-31 at 14:52 CDT (waiting-page item 101) with a direct call, not `protect.py`; the coordinator's read-back showed the one check and strict false.
- Before every merge, read the checks yourself and refuse on red. Today the `merge` tool reads its checks
  from the branch protection only. Ruled to change; see Ruled, not yet built.
- Owner ruling, 2026-10-28 (waiting-page item 33 a): a rename of required checks switches branch
  protection in the merge act. The owner switches it, then the batch merges at once.
- PR #2606, the grant text that adds the ruleset move, is a draft and not merged. Once it merges, a session on the owner's computer runs the move of `main` to the ruleset under the standing grant "Acts the cloud refuses". Until then that grant covers only classic protection.

Reason: agent rules alone did not stop red merges.

## Ruled, not yet built

- Owner ruling r (2026-11-11 16:43 CST): `main` moves to a ruleset that requires only `all-jobs-passed` and blocks deletion and force-push of `main`. Cause: a classic rule with many checks failed to save (owner, 16:39 CST). In the child-repo sweep (R44), a session on the owner's computer moves every repo's `main` to that ruleset.
- Bypass (owner, 16:49 CST, "yes with bypass", coordinator-relayed): the ruleset may let the repository admin
  role skip the checks on pull requests only. Under this ruling, admins are not bound by the checks there.
- Planned form, not an owner ruling (step ruleset-pr-bypass, coordinator's plan): PR required; only `all-jobs-passed`; 0 approvals; not strict; no linear history; no signed commits. `strict` is planned false. That is not an owner ruling. Step merge-reads-ruleset's lane may still pick it.
- Step merge-reads-ruleset (the merge tool reads rulesets; owner ruling c, 19:49 CST Nov 11: "c is prob best").
  The merge tool reads `main`'s ruleset first and the old protection second. The owner chose c over the ruling that a
  repo changes to fit a shared tool, never the tool to fit a repo. The step lands before any sweep removes old protection.
- `protect.py` (`skills/project-ops/scripts/protect.py`) sets classic protection today. Ruled: it sets the ruleset.
- Old-protection removal: a session on the owner's computer may remove old protection only after step
  merge-reads-ruleset has merged and the ruleset is on. PR #2606 (draft, not merged) carries the standing-grant text for it.
- Old-protection read: deleted once every repo has a ruleset.
- `merge.requiredChecks` value after step merge-reads-ruleset: not ruled; step merge-reads-ruleset's lane picks it.

Trigger: the built-today lines above go stale when step merge-reads-ruleset merges or `main` gets a ruleset.
Rewrite them then.

Temporary grant (owner, 2026-10-30 15:37 CDT): "changing a repo's protection is generally mine to do, but i can and am granting you protection changes as a temporary grant". The ruling above is the default, and it holds without the grant. While the grant holds, the coordinator, and the batch runner it names, may make a branch-protection write in any of the owner's repos at merge time. The write must match the gold form: one required check, `all-jobs-passed`; `strict` false; `enforce_admins` true. The ruleset move takes the ruleset form under PR #2606's standing-grant text, the ruled successor for that move once it merges. Until then, the gold form does not fit the ruleset move. The grant holds until the owner withdraws it in chat. Then delete this paragraph.

Kind: process
Home: .github/stamp.json
