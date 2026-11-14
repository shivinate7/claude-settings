# A builder shell check has no mutant

**What.** A builder's after-call shell check, `judge_shell_write` in `hooks/guard.py`, has no mutant in `hooks/mutate_guard.py`, so a later edit could weaken it and only the suite would show it. CI runs only the listed mutants and does not flag the gap.

**Where.** `hooks/guard.py` (`judge_shell_write`, `unmerged_test_path`, `BUILDER_CONFLICT_STATES`), `hooks/mutate_guard.py` (the mutation test), and the family `builder-bash-test-write` in `tests/guard/s43500-builder-bash-test-write.py`.

**Decision.** `builders-cannot-edit-tests` (builders cannot edit tests).

**Retire.** A test-author adds one mutant for each break below. Each mutant must turn a named case red. Case labels in the family start `builder-bash-test-write:`. (1) The `judge_shell_write` dispatch: "a builder's script that adds tests/foo.py is refused at PostToolUse" and "a builder's PowerShell call that adds tests/foo.py is refused at PostToolUse". (2) The `not unmerged_test_path` clause: "a builder's call in a merge with a product conflict and an unmerged test path is refused, and names the merge-abort step", and the rebase and cherry-pick cases with an unmerged test path. (3) `"MERGE_HEAD" in states`: "a builder's call in a merge with a test conflict names the merge-abort step". (4) The `rebase-apply` entry of `BUILDER_CONFLICT_STATES`: "a builder call in a rebase (rebase-apply) that stops on a product conflict, with an incoming test, is allowed and logs builder-bash-test-write-merging, noted". Check: each mutant goes red under `hooks/mutate_guard.py`. A builder cannot make this change, since `hooks/mutate_guard.py` is test content.
