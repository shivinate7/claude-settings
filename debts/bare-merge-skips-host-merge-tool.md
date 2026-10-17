# The bare-merge ask does not cover the host merge tool

- **What.** `mcp__github__merge_pull_request` merges bare in a merge-tool repo, and the bare-merge rule says nothing. Merge-checks still gates it.
- **Where.** The `MERGE_TOOLS` branch of `hooks/guard.py`, beside its `merge_gate` call.
- **Decision.** `bare-merge-asks` (a bare merge in a merge-tool repo asks).
- **Retire.** The host merge tool asks in a merge-tool repo, and a case in `hooks/test_guard.py` pins it.
