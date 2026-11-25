# Lane lint passes over a far shell or Node suite until CI runs

**What.** A shell or Node suite that a change breaks is still passed over by lane lint when the change touches neither the suite nor a path it names. Until CI runs, lane lint prints a `not run` line for it and moves on, so the change still reads PASS. Claude meets it on any code change that merges on a lint PASS before its CI run ends. Measured 2026-11-24 on the owner's Mac, six cheap non-Python suites take about 104 s: opt-in CI template suites 53.6 s, record stamp engine 44.8 s, scanner trap lint 2.8 s, record stamp action 1.7 s, `bash -n install.sh`, and duo-fold (its own debt, `duo-fold-test-trips-rm-shim`). Five of them are listed in `merge.lintSuites`, so lane lint runs each one the change reaches (decision `lanes-run-no-full-ci-job`), unless its job runs on another OS. On Linux, the macOS step `Shell syntax check, install.sh` is not run: a change that reaches it prints one `unknown` line naming it, and lane lint reads unknown. A listed suite the change does not reach still prints `not run`, and duo-fold is not listed.

**Where.** `bin/ci-job`, the `not run` line for an owed suite (`owed_suites`, `tell_owed`, `reached_suites`).

**Decision.** `lanes-run-no-full-ci-job`, which sets the narrow unknown rule for such suites.

**Retire.** `lint/test_ci_job.py`, a case red first on the current code: a change that breaks a shell suite it does not touch makes lane lint run that suite or read unknown, never print only `not run`. The case goes green when it does.
