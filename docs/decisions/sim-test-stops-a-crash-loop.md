# sim-test stops a simulator that crash-loops

## The rulings

While its tests run, `sim-test` stops a simulator whose SpringBoard crash-loops.

1. Watch. While its tests run, `sim-test` lists the crash folder every 2 seconds. The default folder is `~/Library/Logs/DiagnosticReports`. It counts new reports whose name starts with `SpringBoard`. Reports in the folder before the run do not count. A new report counts only when its text names this run's UDID, or names no `CoreSimulator/Devices/<UUID>` path at all, so a crash of another simulator never stops this run.
2. Stop. At 3 or more new reports within 30 seconds, `sim-test` stops `xcodebuild`. It shuts down the simulator only when `sim-test` booted it. It never shuts down a simulator it reused. It prints that it did so, and why: the count, the window and the UDID. Then it exits 1.
3. No process. It reads only during its own run. It starts no watcher process.
4. Cost: one folder listing every 2 seconds during a run. It writes no file.
5. Named limit: rule 1 reads on a timer. The rule `outcomes-mechanize-rules` allows monitoring reads on demand only, never on a timer. The step accepts this 2-second poll during sim-test's own run as its cost.
6. Unproven until a Mac run: the real folder and file name of a simulator SpringBoard crash report. Rule 1 assumes the default folder and the `SpringBoard` prefix.

Test: a fixture writes 3 crash reports within 30 seconds. `sim-test` then shuts down the simulator it booted, and exits 1 with the message. The test is red first.

Incidents:

- Reported 2026-11-01 19:02 CST, home repo: a simulator crash-looped for 7 minutes before anyone stopped it. The step estimate of about 10 seconds to stop it is unmeasured.

Basis: named incident, the home crash loop. Landed: 2026-11-02.

Kind: process
Home: bin/sim-test
