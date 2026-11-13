# The Retire-run reader misses the session link

- **What.** `lint/check_debt_retire.py` reads `Retire-run:` only from the PR body's last paragraph. That reader skips the "Generated with Claude Code" line, but not the session URL line after it. So a `Retire-run:` line above the footer is not read, and the merge tool refuses the first try. Batch 82e cost one retry (coordinator, 2026-11-11 19:57 CST).
- **Where.** `lint/check_debt_retire.py`, function `cites`. It reads the PR body through `last_paragraph` in `lint/check_silent_undo.py`.
- **Decision.** `debt-close-runs-retire` (a debt close runs its Retire check).
- **Retire.** A case in `lint/test_check_debt_retire.py` gives a PR body whose last paragraph is the session URL line, and asserts that the `Retire-run:` line above the footer is read. The fix makes that case pass: the reader also skips a trailing session URL line.
