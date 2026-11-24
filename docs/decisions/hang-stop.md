# A CI or lane lint step stops only on a hang

Question: when may CI or lane lint stop a running step?

## The ruling

Owner ruling R2, 2026-11-23 10:49 CST, typed in the consultant's chat, as the consultant recorded it: "no arbitrary time limits, only hangs". "In CI or lint" is the consultant's gloss of the item it answered (item R2 of "CI, lint and merging"). The consultant reads the ruling as: a run is stopped only when it hangs.

Owner, 2026-11-23 21:21 CST: "Yeah R2 can get worked on now we've built a good amount since then that i trust you to tackle it". The consultant reads this as covering the hang stop, a standard way to resume, and cap sizing. That reading is the consultant's, not the owner's words.

Ruling: only on a hang. A hang is no new output byte and no CPU advance in any process under the step, for N seconds. This is the rule that decision `stall-watch` (the session stall watch) uses to report.

- Limit on every platform: a silent step that keeps starting short processes (a poll loop) is not stopped and falls back to its cap. On Linux, reaped children's CPU counts as work (`hooks/_nowindow.py` `tree_cpu`). On macOS, where that CPU cannot be read (no `/proc`), a process under the step that was not in the baseline sample also counts as work.
- macOS gap: `bin/verdict` `hang_check`, through the `_nowindow.reaped_readable()` branch, can read a hang when a child that used CPU has exited and the parent sleeps. A healthy suite quiet for N seconds in that shape would stop. No stretch of the five suites has that shape, by reading; unmeasured.
- A step that has finished is never a hang: `exited` is checked, and `hang_stop` checks again before it stops.
- Silence is measured on the monotonic clock, so a sleep or a clock change is not silence.
- N: 600 s, the first value, for the five wrapped steps. It is 2 x the longest silent gap that does not end on a dot row, rounded up. That gap, 291.1 s, is the longest of 150 jobs in 10 green push runs; it fell in the merge tool git-half fixture suite. The record gives no gap per wrapped step: unmeasured. The two macOS steps do not run on push. N is at least 300 s. CPU half unmeasured: logs cannot show CPU advance.
- One home: the wait loop of `bin/verdict`. Off unless the env var `VERDICT_HANG_SECONDS` is set. The five steps in Scope set it to 600. A value that is not a whole number turns the stop off and prints one line. The HANG line's words, its pattern (`HANG_LINE`), exit code 124 and the 600 s default (`HANG_SECONDS_DEFAULT`) have one home, `hooks/_nowindow.py`. `bin/verdict` prints the line; `bin/ci-job` and the merge tool read it.
- Without `VERDICT_FULL_LOG`, before a stop it prints the process tree and the log tail. Then it ends the tree and prints one `HANG` line. In `bin/ci-job` (pull request 3852) the HANG line is the step's verdict line: a `FAIL `, `PASS ` or `SKIP ` line the step logged does not count. A hang reads unknown, or FAIL under the exception below. Lane lint reads the same result, and no `--lint-unknown-ok` reason lifts a hang.
- Consultant's pick (08:38 CST Nov 24, 2026; the owner may reverse it): on a FAIL without `VERDICT_FULL_LOG`, `bin/verdict` keeps the last 30 hot lines and also every earlier line that starts FAIL, FAILED or ERROR (at most 300, each cut to 300 characters). Why: a local run shows only this excerpt, so every failing name must be in it.
- Exception, the consultant's pick (02:50 CST Nov 24, 2026; the owner may reverse it): a step whose log holds an `::error` line and then hangs reads FAIL in `bin/ci-job`, instead of unknown. An install failure or a failed line before the suite keeps it unknown.
- Scope: `bin/ci-job` gives 600 s to each step it runs through `bin/verdict` that sets no `VERDICT_HANG_SECONDS` of its own, except a step whose command text contains `mutate` (`hang_default`). Lane lint runs through `bin/ci-job`. CI runs its own steps, so the default does not reach them. The five long CI steps run through `bin/verdict` with `VERDICT_HANG_SECONDS` 600 and no step cap: the three install checkout-detection shards (`checks-install-checkout` to `-3`), the install.sh checkout-detection suite in `shell-macos`, and the macOS guard fixture slice in `checks-macos`. Their job cap stays as the net. Other CI steps keep their job cap. Six short step caps (3 or 5 min) sit outside the scope and stay in force: the code-check tool install, the Windows PowerShell 5.1 bin EOL test, the record stamp engine suite (macOS), the Windows session-start freshness cases, the guard progress beat suite, and the record stamp engine suite in the second rest job.
- Full log, consultant's pick (09:21 CST Nov 24, 2026; the owner may reverse it): the five steps set `VERDICT_FULL_LOG: "1"`. With it, a FAIL prints the verdict line, then the whole log. A HANG prints its line, then its process tree, then the whole log, since a log left on a CI runner has no reader. Without it (local runs), a FAIL prints the excerpt above, and a HANG prints its tree and log tail before its line.
- Consultant's reading of the 10:49 words: once the hang stop covers a step, that step's own time cap is removed in the same change; until then the cap stays. The owner has not ruled on this point in so many words.
- No stop on Windows until it has a CPU read. No stop on mutation steps: `lint/test_checks_step_scope.py` `test_no_mutation_step_runs_through_verdict_or_sets_the_hang_stop` pins it for CI, and `bin/ci-job` gives a step whose command text contains `mutate` no default. The Mutation CI report fixture suite is quiet for 462-615 s, past the 600 s default, in 10 of 10 runs; no check in the repo reads that measure.
- Job caps stay as the last net for a busy-loop hang, Windows and action steps. A net sits well above the measured run. It is never tightened to turn a slow healthy run red (owner, 2026-11-10, quoted in decision `ci-job-caps`). The consultant reads the 2026-11-23 words the same way; that reading is the consultant's, not the owner's words. Decision `ci-job-caps` (the CI job caps) holds the caps.
- Resume after a stop:
  - Lane lint: its pass cache keeps passed steps.
  - CI: the rerun of failed jobs that the merge tool already names.
  - Mutation verdicts: cached across run attempts. Not built.

State: decided. Built: the stop in `bin/verdict` (lane `verdict-hang-stop`), off unless `VERDICT_HANG_SECONDS` is set; lane `ci-job-hang-stop` (`bin/ci-job` reads a `HANG` line; pull request 3843, merged); the five-step wrap with its full-log switch (Scope above); and lane `code-caps-hang-stop` (the HANG line's one home, the 600 s default in `bin/ci-job`, the lane lint no-lift). Not built: lane `mutate-verdicts-cached-ci` (the mutation verdict cache), and note `hang-stop-poll-loop` (open).

Measure, 2026-11-23: in the 50 newest push runs of `checks` on main, 4 jobs ended at the 30-minute step cap with no red test, and 0 at a job cap.

Read again at 21:43 CST from runner log timestamps: those 4 jobs (runs 45070046563, 45252280752, 45291804035, 45301573424) were slow, not hung. Their longest silent gap was 60.5 to 65.4 s, and 3 of the 4 had printed the suite's pass summary before the cap cut them. The stamps are per line, so they overstate silence on a pipe: a unittest dot row is stamped only at its newline. In 10 green push runs (150 jobs), the longest silent gap that does not end on a dot row is 291.1 s (merge tool git-half fixture suite). The longest that ends on a dot row is 549 s (Mutation CI report fixture suite), an artifact of line stamping. One schedule run (n=1): Windows 829.2 s, mutation 542.7 s, macOS 183.1 s.

Cost (rule `outcomes-mechanize-rules`; the log-size read is unmeasured):
- New long-lived process: none.
- Wake: min(the heartbeat, N / 4), at least 1 s. The heartbeat is `VERDICT_HEARTBEAT`, 120 s by default. At N = 600 the wake is 120 s. For N of 4 or less it is 1 s (test use only).
- Log-size read: one per wake.
- Process-table read: at most one per wake, only while the step is silent. It reads on the first silent wake, then once per N s of silence: at N = 600, one per 600 s. Pinned by `lint/test_verdict.py` `test_hang_stop_printing_child_makes_no_process_table_read` (no read while the child prints) and `test_hang_stop_silent_child_makes_a_process_table_read` (a read while silent).

Kind: process
Home: bin/verdict
Check: `lint/test_checks_step_scope.py` class `HangStopWrap` (CI values, 600), `lint/test_ci_job.py` class `HangStopDefault` (the 600 default), `lint/test_verdict.py` classes `FullLog` and `HangLineOneHome`, `merge/test_lane_lint.py` `test_a_hang_in_lane_lint_is_not_lifted_by_an_unknown_reason`
