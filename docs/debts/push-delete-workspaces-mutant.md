# `_workspaces_off` in the push-delete guard has no mutant

- **What.** The `--no-workspaces` stop of the linked node_modules walk, `_workspaces_off`, has no entry in the guard mutation table. No mutant breaks it, so no test fails when it breaks. A guard change with no mutant can pass every test while the guard lets a push or delete through. Found in round 3 of PR #3169. The function is not on origin/main.
- **Where.** `hooks/guard_push_delete.py` line 1572 (`_workspaces_off`, added by commit 96f5d8a2e1, which is not on origin/main; it is on the PR #3169 head). `hooks/mutate_guard.py` maps `hooks/guard_push_delete.py` to the `push-delete` suite (line 3626 on that head). No mutant names `_workspaces_off`.
- **Decision.** `guard-linked-node-modules` (refuse an install or recursive delete through a linked node_modules).
- **Retire.** A mutant for `_workspaces_off` in `hooks/mutate_guard.py`, killed by a push-delete shard in `tests/guard/`, run through `hooks/test_guard.py`, which loads the shards.
