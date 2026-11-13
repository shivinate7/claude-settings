# The cloud CI wake is unproven

- **What.** No live cloud run shows the CI-done wake firing after an MCP ready call. No live cloud run shows gh REST reads working in a cloud session. Without gh, the hook prints "CI unknown" with the reason "gh is not on PATH". Owner, 2026-11-11 11:55 CST (relayed): the cloud CI-done wake never fires.
- **Where.** `hooks/ci_wake.py`, and its PostToolUse row in `settings.json` for the MCP `update_pull_request` call.
- **Decision.** `ci-wait-reads-run-status` (the CI wait reads the run's status).
- **Retire.** One cloud session marks a draft PR ready through the MCP tool, and reads the wake line that follows. No runnable test shows this, so the Retire is prose. The closing PR cites the cloud run with `Retire-run:`.
