# A ready mark by MCP or gh skips the ready checks

**What.** A ready mark by MCP `update_pull_request draft=false` or by `gh pr ready`, made without `merge <pr> --confirm` on the draft, skips `merge.readyChecks`. `READY_ROUTES` sends sessions to MCP or gh to mark ready, so Claude is likely to do this in normal work. The batch's CI run is the only backstop, and it costs a CI cycle.

**Where.** `merge/merge.py` (`draft_step`, `READY_ROUTES`). `.github/stamp.json` `merge.readyChecks` in the repo that declares it.

**Decision.** `lanes-run-no-full-ci-job` (a lane runs no full CI job; the ready checks).

**Retire.** Closed when a case in `merge/test_merge.py` shows a ready mark made outside the draft step is refused.
