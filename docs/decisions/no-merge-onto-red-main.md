# No batch merges onto a red main

## The ruling

The red-main check: the merge tool refuses `merge <pr> --confirm` while the base branch's latest completed run has a red job. The preview prints the same verdict on its `<base> run:` line.

- Judged: per workflow file and per event group, on the base branch. The groups are in one file, `actions/ci-alarm/events.json`, which the CI alarm reads too. Its keys are the judged events. Its values are the groups. `push` and `workflow_dispatch` (`gh workflow run`, the tool's own remedy) form one group. `schedule` is its own group. For each file and group, the newest completed run decides. So a green push or dispatch run clears an older red push or dispatch run. A green push or dispatch run never hides a red schedule run. Only a newer schedule run clears a red schedule run. A green schedule run never hides a red push or dispatch run. Only a newer push or dispatch run clears that red run. A run of any other event, such as a Pages build, is not judged. A newer run still in progress waits its turn. Runs are keyed by workflow file, not by name, so a rename inside the file keeps one verdict. A run whose workflow file is gone from the base is not judged, because no new run will ever replace it. One page of 50 runs is read. A group with no run on that page is not judged.
- Red: a job whose conclusion is `failure`, or any value GitHub adds later (`Host.classify`). A job cancelled at its cap (timed out), a cancelled job and a skipped job are not red.
- A run that did not succeed and has no red job: a timed-out job explains it, so it is not red. A cancelled run is UNKNOWN. It is never swapped for an older run: on the base, `judge_runs`'s twin rule would reach across commits. Any other conclusion is red, such as `startup_failure` from a broken workflow file that runs no job. The tool sees a failed run and no reason for it, so it treats the run as red.
- The refusal names each red job, the run id, its head and its URL.
- Unknown: a read of the workflow files, the runs or the jobs that fails is UNKNOWN, never green or red. Unknown refuses, as the silent-undo check does.
- The way out is `--base-red-ok "<reason>"`. It is a reason flag, like `--undo-check-unknown-ok`, not the owner's `override`. Claude can type it with no owner present. Use it for the batch that carries the fix, or when the owner accepts an unknown read. The tool prints the verdict and `--base-red-ok, reason: <reason>`. A blank reason lifts nothing.

Why: Oct 13 to 14, 14 main runs in a row were red, and batch merges kept landing on top. Main's latest run was not green for 311 of 366 hours. Each merge onto a red main hides the next defect and makes the repair lane longer (roadmap step c166, from plan c95-step2-escapes, option C's brake).

- Risk: named incident, the Oct 13 to 14 red episode. Landed 2026-10-28.
- The owner's `override` prompt does not reach this check. The override check has one home, `refuse()` in `hooks/guard_core.py`. The merge tool runs after the guard, and decision owner-override lists the `bin/merge` shim as outside every override. The tool also cannot tell a session's run from its agent's, and a one-act override must not reach an agent.
- Check: `merge/test_merge.py`, class `RedMainBrake` and `GhHalf.test_a_red_main_run_read_through_gh_refuses_the_merge`. The CI alarm's groups: `actions/ci-alarm/test_action.sh`.
- Cost: at each `--confirm` and each preview, one `git ls-tree` of the base, one `actions/runs` read (one page of 50), and one jobs read for each judged run that did not succeed. No process starts, no file written, no timer.

Kind: process
Home: merge/merge.py
