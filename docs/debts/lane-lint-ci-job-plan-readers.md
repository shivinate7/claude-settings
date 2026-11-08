# Lane lint misses merge/test_merge.py for a bin/ci-job change

**What.** `merge/test_merge.py` runs the real `bin/ci-job` and reads its `--plan` lines through `merge/merge.py` `lint_steps`, which the `CI_JOB` constant names. A diff that changes only `bin/ci-job` does not pick that suite. The selector follows only tracked `.py` modules. It matches a non-`.py` file only when a suite names that path itself. So lane lint does not run the suite, and only batch CI catches a break. This happened once in this lane: a change to `bin/ci-job`'s plan wording broke `SmallBaseMove`. Claude is likely to hit this whenever a lane changes the plan output of `bin/ci-job`.

**Where.** `merge/test_merge.py` (`SmallBaseMove`), `merge/merge.py` (`lint_steps`, `CI_JOB`), `bin/ci-job` (`--plan`), and `hooks/mutate_guard.py` (`suites_for_paths` with `chain`, the selector).

**Decision.** `lanes-run-no-full-ci-job` (a lane runs only the suites its change touches, never a whole CI job).

**Retire.** None yet. Until a runnable test exists, a close needs a cited run (`debt-close-runs-retire`: the merge tool runs the Retire check at close).

Fix: none — picking `merge/test_merge.py` for a `bin/ci-job` change adds about 677 s (one idle run), which pushes lane lint past its 1200 s limit (`LINT_SECONDS`). The proposed step `lane-lint-hub-cost` (triage of lane lint's run time) is where a fix gets sized. Until: 2026-11-21
