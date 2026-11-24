# A failed tool install reads FAIL, when it should read unknown

**What.** With pipx present and a tool not cached, a failed install (no network) reads the code check FAIL with 33 problems, "the tool could not install", where it should read unknown. Only a missing pipx or npx reads unknown today. So a ready run, or `bin/cheap-lints` on a machine with no cached tools and no route to the index (a cloud session's first run with a blocked index), reports a red tree where the environment is at fault.

**Where.** `actions/code-check/code_check.py`, `execute()`, writes "could not start" only when the command is missing. `could_not_start()` in the CI job runner `bin/ci-job` turns only those lines into unknown.

**Decision.** `lanes-run-no-full-ci-job`. The lane lint and the ready checks run this check through `bin/ci-job`, and a run that cannot start reads unknown.

**Retire.** `lint/test_ci_job.py` gets a red case: a code check whose install fails with no route to the index reads unknown, and names the tool. The fix PR deletes this file.
