# Lane lint passes over a far shell or Node suite until CI runs

**What.** A shell or Node suite that a change breaks is still passed over by lane lint when the change touches neither the suite nor a path it names. Lane lint prints a `not run` line for it, not unknown, until CI runs. Claude meets it on any code change that merges on a lint PASS before its CI run ends.

**Where.** `bin/ci-job`, the `not run` line for a scope-gated suite (`flag_suite`, `reached_suites`).

**Decision.** `lanes-run-no-full-ci-job`, which sets the narrow unknown rule for such suites.

**Retire.** `lint/test_ci_job.py`, a case red first on the current code: a change that breaks a shell suite it does not touch makes lane lint run that suite or read unknown, never print only `not run`. The case goes green when it does.
