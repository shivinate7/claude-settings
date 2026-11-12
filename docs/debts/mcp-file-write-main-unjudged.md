# MCP file writes to main are not judged

- **What.** `settings.json` (line ~251) sends `mcp__github__create_or_update_file`, `mcp__github__push_files` and `mcp__github__delete_file` to `hooks/guard.py`, but no guard reads their `branch` input. A write to `main` through them passes the batch-running check (`merge/merge.py` `batch_running`) and every other guard. Whether GitHub refuses it depends on main's ruleset needing a pull request, unmeasured. Claude is likely to hit this: the matcher already sends these tools to the guard, so Claude may expect a judgment that does not happen. Found by reviewer round 1 of lane batch-ci-merge-guard, 2026-11-12.
- **Where.** `settings.json` matcher (line ~251); `hooks/guard.py` `judge`, which has no clause for these three tools.
- **Decision.** no-merge-during-batch-ci (nothing merges to main while a batch's integration CI run is in progress).
- **Retire.** `tests/guard/test_mcp_file_write_main.py` sends each of the three tools with `branch` set to `main` and asserts refused or asked, and sends one with a feature branch and asserts allowed. It is red today; the fix lane adds the guard branch and this test.
