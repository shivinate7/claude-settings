# main branch protection

## The ruling

`main` of shivinate7/claude-settings requires one check: `all-jobs-passed`, the job in
`.github/workflows/checks.yml` that runs the shared action `actions/all-jobs-passed`. Owner ruling,
2026-10-30 15:03 CDT (waiting-page item 87, the owner's waiting page): branch protection requires that one
check. The one-check ruling for every repo sits in record same-check-kinds (PR #877).
Owner ruling r (2026-11-11 16:43 CST) puts that check in a ruleset on `main`. See Built, not yet live, and Ruled, not yet built.
`.github/stamp.json` `merge.requiredChecks` is `"protection"`. The `merge` tool reads the check names
from `main`'s ruleset first, then from classic branch protection (see Built, not yet live). Changing a repo's protection is the owner's to do, unless a grant covers it (see the
temporary grant below).
Built-today lines in this record were not re-read by the edit of 2026-11-12 11:27 CST. No live setting was read.

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
- Today's classic protection includes admins (`enforce_admins`), so it binds the owner. Bypass, below, is ruled and built in
  `protect.py`'s form. It is not live.
- `protect.py` (project-ops, the script that sets a repo's `main` rule) builds the ruled ruleset: active, on the branch, `all-jobs-passed` as its one required check, deletion and non_fast_forward (force-push) blocked, and the Admin role as its one bypass actor, on pull requests only. It writes no classic protection. A new ruleset sends `strict_required_status_checks_policy` false, because the REST API requires the field. The ruling names no strict value, so that false is planned, not ruled. An update keeps the held ruleset's own strict value.
- Today, classic protection blocks force pushes and branch deletion. No repo has a ruleset yet (lane brief; not re-read by this edit).
- Today's protection holds the one required check. A new job goes in the `needs` of `all-jobs-passed`, not in
  the required set. Merge stops when a pinned `merge.requiredChecks` list in `stamp.json` differs from a non-empty list from the ruleset (or from classic protection, when the ruleset names no check), and names both sets. An empty or unreadable list does not stop it: the pinned list stays in force, and an unreadable one is said aloud, an unreadable ruleset included. It is not read as classic protection instead (`refuse_pinned_mismatch`, sweep row `pinned-mismatch`; roadmap step c189, the merge tool and branch protection work).
- The switch is one `protect.py` write, to a ruleset. Preview
  `python3 ~/.claude/skills/project-ops/scripts/protect.py --repo shivinate7/claude-settings --check all-jobs-passed`,
  then the same with `--confirm`. With no ruleset on the branch it POSTs one. With a ruleset that differs from the ruled form it PUTs that ruleset in place: its other rules, its conditions and its strict value stay. A ruleset already in the form is left alone. The preview names what differs, such as the checks the ruleset holds now.
  Classic protection pins app id 15368 (GitHub Actions) (last read 2026-11-03 19:19 CST: `checks` [{all-jobs-passed, 15368}]). The ruled ruleset body names only the check's context, with no `integration_id`, so it pins no app id. Whether GitHub pins one on its own is unmeasured. The classic write needed the
  shivinate7 login: `ssemwal-cdc` has push, not admin. A handed block (commands handed to the owner to run, decision `act-in-place`) opens with `gh auth switch -u shivinate7`. A cloud session acts as `shivinate7` with admin, but the auto-mode classifier refused its direct classic PATCH as a CI bypass. Whether it refuses the ruleset POST or PUT from `protect.py --confirm`, and whether a ruleset write needs admin, is unmeasured.
  The owner switched it on 2026-10-31 at 14:52 CDT (waiting-page item 101) with a direct call, not `protect.py`; the coordinator's read-back showed the one check and strict false.
- Before every merge, read the checks yourself and refuse on red. The `merge` tool reads its checks
  from the ruleset first, then from classic branch protection (see Built, not yet live).
- Owner ruling, 2026-10-28 (waiting-page item 33 a): a rename of required checks switches branch
  protection in the merge act. The owner switches it, then the batch merges at once.
- PR #2606, the grant text that adds the ruleset move, is a draft and not merged. Once it merges, a session on the owner's computer runs the move of `main` to the ruleset under the standing grant "Acts the cloud refuses". Until then that grant covers only classic protection.

Reason: agent rules alone did not stop red merges.

## Built, not yet live

Built in `ruleset_names` and `protection_names` (`merge/merge.py`), and in `main` and `ruled_body` (`skills/project-ops/scripts/protect.py`). This record merges with that code. Live is still classic protection only: no repo has a ruleset yet (lane brief; not re-read by this edit).

- Merge tool, owner ruling c (2026-11-11 19:49 CST, "c is prob best"). The merge tool reads `main`'s ruleset first (`ruleset_names`, one read of `rules/branches/<base>`). Classic protection is read second (`protection_names`), and only when the ruleset names no check. The owner chose c over the ruling that a repo changes to fit a shared tool, never the tool to fit a repo. The step lands before any sweep removes old protection.
  - A ruleset with no check rule, or no ruleset (an empty list), hands the names to classic protection.
  - Any failed ruleset read stops the merge, an HTTP 404 included. It does not fall back to classic protection (class `RulesetFirst`: `test_an_http_404_on_the_ruleset_read_stops_the_merge`, `test_a_failed_ruleset_read_stops_and_does_not_fall_back_to_the_classic_list`). With a pinned list, it does not stop the merge: `refuse_pinned_mismatch` says so aloud, and the pinned list stays in force.
- Protect script, owner ruling r (2026-11-11 16:43 CST) and its bypass (2026-11-11 16:49 CST, "yes with bypass"). `protect.py` writes the ruled form: active, on the named branch, `all-jobs-passed` as its one required check, deletion and non_fast_forward (force-push) blocked, and the Admin role as its one bypass actor, on pull requests only. On update it keeps the held ruleset's name, conditions, strict value and other rules.
  - Not set: no pull-request rule, no approval count, no strict policy of its own. Those are planned, not ruled.
  - The Admin role's actor id is 5 (`ADMIN_ROLE_ID`). UNKNOWN: not confirmed against a live ruleset. No ruleset exists on any repo yet. Verify when the sweep applies the first one.
- `merge.requiredChecks` stays `"protection"` in `.github/stamp.json`. That is the lane's pick, not an owner ruling. The merge tool names the ruleset's checks when it names any, and classic protection's only when it names none. So `"protection"` names one set, never both.

## Ruled, not yet built

- Owner ruling r (2026-11-11 16:43 CST): `main` moves to a ruleset that requires only `all-jobs-passed` and blocks deletion and force-push of `main`. Cause: a classic rule with many checks failed to save (owner, 16:39 CST). In the child-repo sweep (R44), a session on the owner's computer moves every repo's `main` to that ruleset. The form is built (see above). The sweep has not run.
- Bypass (owner, 16:49 CST, "yes with bypass", coordinator-relayed): the ruleset may let the repository admin
  role skip the checks on pull requests only. Under this ruling, admins are not bound by the checks there. Built in `protect.py`; not live.
- Planned form, not an owner ruling (step ruleset-pr-bypass, coordinator's plan): PR required; only `all-jobs-passed`; 0 approvals; not strict; no linear history; no signed commits. `strict` is planned false. That is not an owner ruling. Not built: `protect.py` sets no pull-request rule, no approval count, and no linear-history or signed-commit rule.
- Old-protection removal: a session on the owner's computer may remove old protection only after step
  merge-reads-ruleset has merged and the ruleset is on. PR #2606 (draft, not merged) carries the standing-grant text for it.
- Old-protection read: deleted once every repo has a ruleset.

Trigger: the first live ruleset on any repo (the sweep's first apply). Then read back the Admin role's actor id, the strict value and the bypass actor, and rewrite the lines marked Built, Today and Live. Old-protection removal fires the same rewrite.

Temporary grant (owner, 2026-10-30 15:37 CDT): "changing a repo's protection is generally mine to do, but i can and am granting you protection changes as a temporary grant". The ruling above is the default, and it holds without the grant. While the grant holds, the coordinator, and the batch runner it names, may make a branch-protection write in any of the owner's repos at merge time. The write must match the gold form: one required check, `all-jobs-passed`; `strict` false; `enforce_admins` true. The ruleset move takes the ruleset form under PR #2606's standing-grant text, the ruled successor for that move once it merges. Until then, the gold form does not fit the ruleset move. The grant holds until the owner withdraws it in chat. Then delete this paragraph.

Kind: process
Home: .github/stamp.json
