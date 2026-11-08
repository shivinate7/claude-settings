# Mutation test files count as builder files, not test paths

- **What.** `hooks/mutate_guard.py` is test config, but a builder may edit it, because `is_test_rel` does not count it as a test path. The exemption is deliberate in the code: `AUTHOR_MUTATION_TESTS` names the three mutation test files, and its comment says a builder keeps editing them. The decision names no such exception. PR #1676 has 4 builder commits that edit it (the finding's count, not re-checked).
- **Where.** `is_test_rel` and `AUTHOR_MUTATION_TESTS` in `hooks/guard.py`.
- **Decision.** `builders-cannot-edit-tests` (a builder must not delete, skip or rewrite a test).
- **Retire.** A builder's edit to `hooks/mutate_guard.py` refuses, and a case in `hooks/test_guard.py` holds it.

- Fix: step:notes-reverify-flags
