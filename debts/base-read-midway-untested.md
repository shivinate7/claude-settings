# The midway unreadable base read has no test

- **What.** If a later verify cannot run, `read_default_base` returns unknown. No test covers that path, only the first verify.
- **Where.** `hooks/guard_core.py`, `read_default_base`.
- **Decision.** `default-branch-read-order` (the order that reads a repo's default branch).
- **Retire.** A push case and a sweep case mock a failed later verify and assert the safe result.
