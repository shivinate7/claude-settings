# Lane lint never picks a folder-scan suite for a new file

**What.** Lane lint picks a `lint/test_*.py` suite only through the selector. These suites scan a whole folder, so a new file there is not picked: `lint/test_ci_job.py` `RunBodiesOfWorkflows` reads every `.github/workflows/*.yml` but is picked only for `checks.yml`; `lint/test_check_agent_models.py` reads `agents/*.md`; `lint/test_rule_audit.py` reads `hooks/*.py`; `lint/test_guard_log_report.py` and `lint/test_check_landed_dirs.py` read `hooks/guard*.py`. Example: a new `run: |-` step in `.github/workflows/impeccable-sync.yml` went red first in batch CI, found by review round 2 of PR #2120 (the tree-scan change). Claude is likely to hit it when it adds a workflow, an agent or a hook.

**Where.** `suites_for_paths` in `hooks/mutate_guard.py`.

**Decision.** `lanes-run-no-full-ci-job`, lane lint runs the picked suites and not the full CI job.

**Retire.** The selector picks each folder-scan suite for a path in its folder. Proof: `hooks/test_mutate_guard_folder_scans.py`, a file the fix adds. It is red on the current code and green after the fix.

Fix: none queued. Until: 2026-11-22
