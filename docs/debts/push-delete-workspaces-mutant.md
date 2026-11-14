# `_workspaces_off` in the push-delete guard has no mutant

- **What.** The `--no-workspaces` stop of the linked node_modules walk, `_workspaces_off`, has no entry in the guard mutation table. No mutant breaks it, so no test fails when it breaks. A guard change with no mutant can pass every test while the guard lets a push or delete through. Found in round 3 of PR #3169. The function is not on origin/main.
- **Where.** `hooks/guard_push_delete.py` (`_workspaces_off`, added by commit 96f5d8a2e1, which is not on origin/main). `hooks/mutate_guard.py` maps `hooks/guard_push_delete.py` to the `push-delete` suite (about line 3668). No mutant names `_workspaces_off`.
- **Decision.** `mutation-report-scores-suites` (the mutation report scores each suite on demand).
- **Retire.** A mutant for `_workspaces_off` in `hooks/mutate_guard.py`, with a case in `hooks/test_mutate_guard.py` (a new file) that fails when that mutant survives.
