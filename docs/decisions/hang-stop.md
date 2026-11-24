# A CI or lane lint step stops only on a hang

Question: when may CI or lane lint stop a running step?

## The ruling

Owner ruling R2, 2026-11-23 10:49 CST, typed in the consultant's chat, as the consultant recorded it: "no arbitrary time limits, only hangs". "In CI or lint" is the consultant's gloss of the item it answered (item R2 of "CI, lint and merging"). The consultant reads the ruling as: a run is stopped only when it hangs.

Owner, 2026-11-23 21:21 CST: "Yeah R2 can get worked on now we've built a good amount since then that i trust you to tackle it". The consultant reads this as covering the hang stop, a standard way to resume, and cap sizing. That reading is the consultant's, not the owner's words.

Ruling: only on a hang. A hang is no new output byte and no CPU advance in any process under the step, for N seconds. This is the rule that decision `stall-watch` (the session stall watch) uses to report.

- Limit on every platform: a silent step that keeps starting short processes (a poll loop) is not stopped and falls back to its cap. On Linux, reaped children's CPU counts as work (`hooks/_nowindow.py` `tree_cpu`). On macOS, where that CPU cannot be read (no `/proc`), a process under the step that was not in the baseline sample also counts as work.
- A step that has finished is never a hang: `exited` is checked, and `hang_stop` checks again before it stops.
- Silence is measured on the monotonic clock, so a sleep or a clock change is not silence.
- N: 600 s for Linux push steps, the first value. It is 2 x the longest silent gap that does not end on a dot row (291.1 s, measured on the merge tool git-half fixture suite), rounded up. N is at least 300 s. CPU half unmeasured: logs cannot show CPU advance.
- One home: the wait loop of `bin/verdict`. Off unless the env var `VERDICT_HANG_SECONDS` is set. The five steps in Scope set it to 600. A value that is not a whole number turns the stop off and prints one line.
- Before a stop, it prints the process tree and the log tail. Then it ends the tree and prints one `HANG` line. In lane lint, a HANG reads unknown.
- Consultant's pick (08:38 CST Nov 24, 2026; the owner may reverse it): on a FAIL, `bin/verdict` keeps the last 30 hot lines and also every earlier line that starts FAIL, FAILED or ERROR (at most 300, each cut to 300 characters). Why: a wrapped CI step shows only this excerpt in the CI log, so every failing name must be in it.
- Exception, the consultant's pick (02:50 CST Nov 24, 2026; the owner may reverse it): a step whose log holds an `::error` line and then hangs reads FAIL in `bin/ci-job`, instead of unknown.
- Scope: lane lint steps, and five long CI steps, each run through `bin/verdict` with `VERDICT_HANG_SECONDS` 600 and no step cap: the three install checkout-detection shards (`checks-install-checkout` to `-3`), the install.sh checkout-detection suite in `shell-macos`, and the macOS guard fixture slice in `checks-macos`. Their job cap stays as the net. Other CI steps keep their job cap. Six short step caps (3 or 5 min) sit outside the scope and stay in force: the code-check tool install, the Windows PowerShell 5.1 bin EOL test, the record stamp engine suite (macOS), the Windows session-start freshness cases, the guard progress beat suite, and the record stamp engine suite in the second rest job.
- Consultant's reading of the 10:49 words: once the hang stop covers a step, that step's own time cap is removed in the same change; until then the cap stays. The owner has not ruled on this point in so many words.
- No stop on Windows until it has a CPU read. No stop on mutation steps yet.
- Job caps stay as the last net for a busy-loop hang, Windows and action steps. A net sits well above the measured run. It is never tightened to turn a slow healthy run red (owner, 2026-11-10, quoted at `ci-job-caps.md:7`). The consultant reads the 2026-11-23 words the same way; that reading is the consultant's, not the owner's words. Decision `ci-job-caps` (the CI job caps) holds the caps.
- Resume after a stop:
  - Lane lint: its pass cache keeps passed steps.
  - CI: the rerun of failed jobs that the merge tool already names.
  - Mutation verdicts: cached across run attempts. Not built.

State: decided. Built: the stop in `bin/verdict` (lane `verdict-hang-stop`), off unless `VERDICT_HANG_SECONDS` is set; lane `ci-job-hang-stop` (`bin/ci-job` reads a `HANG` line; pull request 3843, merged); and the five-step wrap (Scope above). Not built: lane `mutate-verdicts-cached-ci` (the mutation verdict cache), `code-caps-hang-stop`, and `hang-stop-poll-loop` (open, note `docs/notes/hang-stop-poll-loop.md`).

Measure, 2026-11-23: in the 50 newest push runs of `checks` on main, 4 jobs ended at the 30-minute step cap with no red test, and 0 at a job cap.

Read again at 21:43 CST from runner log timestamps: those 4 jobs (runs 45070046563, 45252280752, 45291804035, 45301573424) were slow, not hung. Their longest silent gap was 60.5 to 65.4 s, and 3 of the 4 had printed the suite's pass summary before the cap cut them. The stamps are per line, so they overstate silence on a pipe: a unittest dot row is stamped only at its newline. In 10 green push runs (150 jobs), the longest silent gap that does not end on a dot row is 291.1 s (merge tool git-half fixture suite). The longest that ends on a dot row is 549 s (Mutation CI report fixture suite), an artifact of line stamping. One schedule run (n=1): Windows 829.2 s, mutation 542.7 s, macOS 183.1 s.

Cost (rule `outcomes-mechanize-rules`; the log-size read is unmeasured):
- New long-lived process: none.
- Wake: min(the heartbeat, N / 4), at least 1 s. The heartbeat is `VERDICT_HEARTBEAT`, 120 s by default. At N = 600 the wake is 120 s. For N of 4 or less it is 1 s (test use only).
- Log-size read: one per wake.
- Process-table read: at most one per wake, only while the step is silent. It reads on the first silent wake, then once per N s of silence: at N = 600, one per 600 s. Pinned by `lint/test_verdict.py` `test_hang_stop_printing_child_makes_no_process_table_read` (no read while the child prints) and `test_hang_stop_silent_child_makes_a_process_table_read` (a read while silent).

Kind: process
Home: bin/verdict
Check: `lint/test_checks_step_scope.py` class `HangStopWrap`, `lint/test_verdict.py`
