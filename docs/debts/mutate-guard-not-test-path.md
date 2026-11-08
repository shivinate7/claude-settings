# Builders can change existing mutation test entries

- **What.** A builder may add mutants to `hooks/mutate_guard.py`, but may not remove or change an existing entry, or a name in `AUTHOR_MUTATION_TESTS`. A re-anchor changes an entry, so the test-author makes it (coordinator ruling, 2026-11-07 20:35 CST). Today `is_test_rel` does not count the file as a test path, and the `AUTHOR_MUTATION_TESTS` exemption is deliberate in code. The decision `builders-cannot-edit-tests` names no such exception. PR #1676 had 4 builder commits that edited the file (the finding's count, not re-checked).
- **Where.** `is_test_rel` and `AUTHOR_MUTATION_TESTS` in `hooks/guard.py`.
- **Decision.** `builders-cannot-edit-tests` (a builder must not delete, skip or rewrite a test).
- **Retire.** PR #1675 merges, and a case in `hooks/test_guard.py` shows a builder's change to an existing entry refuses.

- Fix: PR #1675
