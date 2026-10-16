# No guard branch reads the merge grep and log allow text

- **What.** Test rows allow `grep` and `git log` commands that name merge words. No branch in the guard reads that text, so no row can fail when the allow breaks. Lane merge-guard-b found it on 2026-10-15.
- **Where.** The merge-checks family in `hooks/test_guard.py`; the merge rule in `hooks/guard.py`.
- **Decision.** `test-strategy-reset` (each kept test names the real failure it catches).
- **Retire.** A text-scan mutant proves a row fails, or the rows go as tests of nothing.
