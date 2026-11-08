# Lane lint skips the whole-tree scan suites

**What.** Since PR #2017 (lane-lint suites picked), lane lint runs a `python3 lint/test_*.py` suite only when the selector picks it. Four suites scan every tracked file, not one module: `lint/test_no_window_spawn.py`, `lint/test_retired_names.py`, `lint/test_retired_repos.py`, and `lint/test_check_glossary.py`. No ordinary diff picks them. So a raw `subprocess.run` in product code, or a retired name in a doc, passes lane lint and goes red in batch CI, at the cost of one batch cycle and a lane drop. Claude is likely to hit it in normal work. Found by review round 3 of PR #2017, in a selector probe on `merge/merge.py`, `hooks/guard.py` and `docs/debts/notes.md`.

**Where.** `suites_for_paths` in `hooks/mutate_guard.py`, the one selector `bin/ci-job --lint` asks.

**Decision.** `lanes-run-no-full-ci-job`, lane lint runs the picked suites and not the full CI job.

**Retire.** The selector picks each whole-tree scan suite for any diff that touches a file it scans. Proof: a file the fix adds, named by path in this line, that runs the selector on such a diff and checks the suite is picked.

Fix: none queued; proposed to triage as roadmap step `lane-lint-cloud-time-limit`. Until: 2026-11-22.
