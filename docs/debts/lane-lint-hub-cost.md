# Lane lint runs most suites for a widely imported module

**What.** A change to a widely imported module makes lane lint pick most of the suites, and each picked CI step runs whole. A change to `hooks/_nowindow.py` picks 94 suites, 82 of them in the checks job. A change to `hooks/guard.py` picks 62. The time per suite is unmeasured. The run can run past `LINT_SECONDS` (1200 s) and end as unknown. That fails safe, but it can block a lane that edits such a module. The base-move proof (`small_base_move`) pays the same cost under the merge lock. Claude is likely to hit this, since lanes often edit `hooks/guard.py`.

**Where.** `hooks/mutate_guard.py` (`--lint-suites`, and `suites_for_paths` with `chain`), `bin/ci-job` (`--lint` runs each picked suite step whole), and `merge/merge.py` (`LINT_SECONDS`, `small_base_move`).

**Decision.** `lanes-run-no-full-ci-job` (a lane runs only the suites its change touches, never a whole CI job).

**Retire.** None yet. The proposed step `lane-lint-hub-cost`, for triage, would close this with a runnable test. Until then a close needs a cited run (`debt-close-runs-retire`: the merge tool runs the Retire check at close).

Fix: none — no fix is built, and the time per suite is unmeasured, so a fix cannot be sized yet. A step is proposed to triage as `lane-lint-hub-cost`. Until: 2026-11-21 (coordinator ruling 04:13 CST Nov 8).
