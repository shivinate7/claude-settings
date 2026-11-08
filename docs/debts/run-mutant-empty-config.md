# The mutant runner gives merge-role mutants no role file

- **What.** `run_mutant` gives each mutant a config folder (`cfg_<label>`) that is created empty. The merge tool reads its role from `CLAUDE_CONFIG_DIR/state/merge-role.json`, so the file is absent for every mutant, and a merge-role mutant cannot run.
- **Where.** `run_mutant` and `run_suite` in `hooks/mutate_guard.py`, and `role_path` in `merge/merge.py`.
- **Decision.** `mutation-report-scores-suites` (the one home of mutation testing, `hooks/mutate_guard.py` with `hooks/mutate_shared.py`).
- **Retire.** A merge-role mutant runs against a role file it is given, and `hooks/test_mutate_replay.py` holds the case.

- Fix: step:notes-reverify-flags
