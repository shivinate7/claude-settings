# A push to main skips its checks when a passing PR run already covered its tree

## The ruling

Owner, item 729 a (relayed by the coordinator, 2026-11-13 12:29 CST), extended by ruling `own-769-a-narrowed-pr-push` (owner, 16:03 CST, "main skips the whole run after a passing PR run"): the `push-skip` job skips a push to main in one case. The pushed commit's tree equals the head tree of a merged PR that the commit belongs to, and that PR's run passed. The PR is a `batch-*` integration PR or a single lane PR. In a passing run, `all-jobs-passed` and every suite job succeeded. A suite step that scope skipped (a narrowed run) does not stop the skip.

- The decision's one home is the shared action `actions/push-skip` (`push-skip.py` beside its `action.yml`). `checks.yml` calls it, and child repos pin it by SHA. The suite jobs are read from the calling repo's own workflow (the jobs its `all-jobs-passed` needs, minus the bookkeeping jobs), through `lint/all_jobs_passed_rules.py` from the action's own checkout. A pin carries its readers.
- Skip: the tree of a `batch-*` head whose ready run passed every suite job. Or the tree of a merged lone-lane head whose newest `checks.yml` run is a completed, green pull request run: every suite job and `all-jobs-passed` succeeded. Skipped steps inside a succeeded job are no gap.
- Run everything: a direct push, an admin merge with no green run, a tree mismatch, and a red, draft, cancelled, in-progress, other-head or other-workflow run. Any read error or unknown state runs everything and says "unknown". A `schedule` or `workflow_dispatch` run never skips (the action reads `EVENT`).
- The 03:17 nightly skips when main's head has a green push run and the newest schedule run is green (`nightly-skip`), so it is no sure re-run of a suite that a narrowed PR run left out. A suite the change did not touch is not run on main until a later change touches it or a nightly runs in full. A direct push still runs every suite.
- Ruling 176 b (owner, 2026-11-12 21:45 CST) kept the push suites until this repo changes the red-main check. This record is that change.

How the red-main check still sees a test-red main (`no-merge-onto-red-main`):

- A skipped push run reads green only because a tested-green tree is on main. The run it rests on passed on that exact tree, with the suites its diff touched.
- A red PR run, a direct push, an admin merge, a tree mismatch and a read error all run the full suites on the push. A red suite then makes the push run red, and the check refuses merges.
- A skipped push run clears no red nightly. It has `push-skip` success and `scope` skipped, with every suite job skipped, and a skipped job is no pass. Test: `merge/test_merge.py`, class `RedMainBrake`, `test_a_red_nightly_stays_red_under_a_newer_push_run_that_the_proven_skip_skipped`.

Why: every merge to main re-ran suites that a passing PR run had passed on the same tree, which cost Windows and macOS minutes and delayed the next merge. A tree equal to a tested-green tree has no new behaviour to test.

- Risk: accepted (owner reading of 16:03 CST). A red from an untouched suite shows only on a later change that touches it, since a narrowed PR run does not run it and main skips.
- Risk: `stable.yml` moves `stable` on any green push run of main, and a skipped push run is one. After a narrowed PR run, `stable` can advance with no suite run on main. The proven PR run is the accepted evidence.
- Risk: a skipped push run is a green push run, so `nightly-skip` may count it. It rests on a passing PR run of the same tree, so the nightly skips on a tree that run proved.
- Risk: accepted (coordinator, 16:37 CST Nov 13, reviewer-recommended). A skipped push run reads as evidence for the red-main check after a narrowed PR run too. So a revert whose PR run scoped out the broken suite can clear a red main. That suite is never re-run. A revert usually touches the broken paths, so the suite usually runs. Filed as note `push-skip-narrowed-clears-red-main`.
- Risk: a PR run re-run after a push cannot change that push's decision. The push reads the newest run at push time.

Check: `lint/test_push_skip.py` (the decision, the event refusal, the caller workflow read, the wiring), `merge/test_merge.py` class `RedMainBrake`, `actions/ci-alarm/test_clear_rule.py`.

Cost (unmeasured): a push makes a PR list read and a workflow file read. Each batch head adds a commit read and a check-runs read. A lone-lane head with the push's tree adds a commit read, a runs read and a jobs read (unmeasured). No file written, no process kept.

Kind: process
Home: actions/push-skip/push-skip.py
