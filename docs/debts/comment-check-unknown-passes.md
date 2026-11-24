# A comment-check unknown reads the Code check PASS

**What.** When the comment check exits 2, for example because `--base` names a ref that does not exist, `code_check.py` prints "comment check: unknown" and adds no failure. The Code check then reads PASS and exits 0, so an unread diff passes.

**Where.** `actions/code-check/code_check.py`, `comment_check()` at :50-52. An exit 2 returns only the hit rows, and an empty list passes. Checked: `comment_check` on a missing ref printed the unknown line and returned `[]`.

**Decision.** `lanes-run-no-full-ci-job` (the Code check is a ready check; an unread check reads unknown, not pass).

**Retire.** `actions/code-check/test_action.py` gets a red case: a comment check that exits 2 makes the Code check unknown or FAIL, never PASS.
