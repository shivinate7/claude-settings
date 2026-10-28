# No batch merges onto a red main

## The ruling

The merge tool refuses `merge <pr> --confirm` while the base branch's latest completed push run has a red job. The preview prints the same verdict on its `<base> run:` line.

- Judged: the newest completed push run on the base, per workflow. A newer run still in progress waits its turn. The pick is the twin rule of `Host.judge_runs` (`Host.newest_runs`): a skipped or cancelled run beside one that ran is dropped.
- Red: a job of that run whose conclusion is `failure`, or any value GitHub adds later (`Host.classify`). A job cancelled at its cap (timed out), a cancelled job and a skipped job are not red. A run that succeeded needs no jobs read.
- The refusal names each red job, the run id, its head and its URL.
- Unknown: a read of the runs or the jobs that fails is UNKNOWN, never green or red. Unknown refuses, as the silent-undo check does.
- The way out: `--base-red-ok "<reason>"`, for the batch that carries the fix, or when the owner accepts an unknown read. The tool prints the verdict and the reason. A blank reason lifts nothing.

Why: Oct 13 to 14, 14 main runs in a row were red, and batch merges kept landing on top. Main's latest run was not green for 311 of 366 hours. Each merge onto a red main hides the next defect and makes the repair lane longer (roadmap step c166, from plan c95-step2-escapes, option C's brake).

- Risk: named incident, the Oct 13 to 14 red episode. Landed 2026-10-28.
- The way out is a reason flag, not the owner's `override` prompt. The override check has one home, `refuse()` in `hooks/guard_core.py`. The merge tool runs after the guard's gate, and decision owner-override lists the `bin/merge` shim as outside every override. The tool also cannot tell a session's run from its agent's, and a one-act override must not reach an agent. The flag follows `--undo-check-unknown-ok`.
- Check: `merge/test_merge.py`, class `RedMainBrake` and `GhHalf.test_a_red_main_run_read_through_gh_refuses_the_merge`.
- Cost: at each `--confirm` and each preview, one `actions/runs` read (one page of 30), plus one jobs read for each newest run that did not succeed. No process starts, no file written, no timer.

Kind: process
Home: merge/merge.py
