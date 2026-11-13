# A push to main skips its checks when a full PR run already passed its tree

## The ruling

Owner, item 729 a (relayed by the coordinator, 2026-11-13 12:29 CST): the `push-skip` job skips a push to main in one case. The pushed commit's tree equals the head tree of a merged PR that the commit belongs to, and that PR's run was full. The PR is a `batch-*` integration PR or a single lane PR. In a full run, `all-jobs-passed` and every suite job succeeded, and scope skipped no suite step.

- The decision's one home is the shared action `actions/push-skip` (`push-skip.py` beside its `action.yml`). `checks.yml` calls it, and child repos pin it by SHA. The suite jobs are read from the calling repo's own workflow (the jobs its `all-jobs-passed` needs, minus the bookkeeping jobs), through `lint/all_jobs_passed_rules.py` from the action's own checkout. A pin carries its readers.
- Skip: the tree of a `batch-*` head whose ready run passed every suite job. Or the tree of a merged lone-lane head whose newest `checks.yml` run is a completed, green pull request run. In that run, every suite job and `all-jobs-passed` succeeded and no suite step was skipped. The `mutation-report` job is exempt from the step rule: its steps skip by head ref (`batch-*` only), and on a push it reports nothing.
- Run everything: a direct push, an admin merge with no green run, a tree mismatch, and a red, draft, cancelled, in-progress, other-head or other-workflow run. Any read error or unknown state runs everything and says "unknown". A `schedule` or `workflow_dispatch` run never skips (the action reads `EVENT`).
- CI has no nightly (`test-strategy-reset`), so nothing else runs what a PR run scoped out. A lone-lane PR run narrows its suites by diff, so a push skips on it only when it narrowed nothing. A narrowed run is partial, and its push runs in full.
- Ruling 176 b (owner, 2026-11-12 21:45 CST) kept the push suites until this repo changes the red-main check. This record is that change.

How the red-main check still sees a test-red main (`no-merge-onto-red-main`):

- A skipped push run reads green only because a tested-green tree is on main. The run it rests on passed every suite on that exact tree.
- A red PR run, a direct push, an admin merge, a tree mismatch and a read error all run the full suites on the push. A red suite then makes the push run red, and the check refuses merges.
- A skipped push run clears no red nightly. It has `push-skip` success and `scope` skipped, with every suite job skipped, and a skipped job is no pass. Test: `merge/test_merge.py`, class `RedMainBrake`, `test_a_red_nightly_stays_red_under_a_newer_push_run_that_the_proven_skip_skipped`.

Why: every merge to main re-ran suites that a full PR run had passed on the same tree, which cost Windows and macOS minutes and delayed the next merge. A tree equal to a tested-green tree has no new behaviour to test.

- Risk: accepted. A suite step that the PR run skipped for a reason other than scope, such as a step with `if: failure()`, reads as narrowing, so its push runs in full. That is safe and may skip less than it could (unmeasured on a real run).
- Risk: none from the nightly. CI has no nightly (`test-strategy-reset`), so a skipped push run cannot make a nightly skip.
- Risk: a PR run re-run after a push cannot change that push's decision. The push reads the newest run at push time.

Check: `lint/test_push_skip.py` (the decision, the event refusal, the caller workflow read, the wiring), `merge/test_merge.py` class `RedMainBrake`, `actions/ci-alarm/test_clear_rule.py`.

Cost (unmeasured): a push makes a PR list read and a workflow file read. Each batch head adds a commit read and a check-runs read. A lone-lane head with the push's tree adds a commit read, a runs read and a jobs read (unmeasured). No file written, no process kept.

Kind: process
Home: actions/push-skip/push-skip.py
