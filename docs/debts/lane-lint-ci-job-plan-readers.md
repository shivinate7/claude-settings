# Lane lint misses merge/test_merge.py for a bin/ci-job change

**What.** Cause: job scope. `merge/test_merge.py` runs in CI job `checks-merge-install` (`.github/workflows/checks.yml`), not in `checks`. Lane lint runs only the `checks` job's steps, so it never runs that suite, whatever the selector picks. Picking it only adds its name to that job's `not run` line, at no cost. A break in a reader of `bin/ci-job`'s plan (`merge/merge.py` `lint_steps`, pinned by `merge/test_merge.py`) is caught only by batch CI until #1916 (lane lint covers other jobs) lands. This happened once in this lane: a change to `bin/ci-job`'s plan wording broke `SmallBaseMove`. Claude is likely to hit this whenever a lane changes the plan output of `bin/ci-job`.

**Where.** `merge/test_merge.py` (`SmallBaseMove`), `merge/merge.py` (`lint_steps`, `CI_JOB`), `bin/ci-job` (`--plan`), and `hooks/mutate_guard.py` (`suites_for_paths` with `chain`, the selector).

**Decision.** `lanes-run-no-full-ci-job` (a lane runs only the suites its change touches, never a whole CI job).

**Retire.** None yet. Until a runnable test exists, a close needs a cited run (`debt-close-runs-retire`: the merge tool runs the Retire check at close).

Fix: none — #1916 runs other Linux jobs' suites under their own limit; it waits for #1521. Until: 2026-11-21
