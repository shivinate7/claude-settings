# A merge through the MCP tool checks no repo tag

**What.** `mcp__github__merge_pull_request` is judged by green checks only. It has no cs-repo or role check, so a runner can merge a repo its tags do not name through the MCP tool, though `merge N --confirm` is refused there. A runner that is refused on the shim can reach the same merge by the MCP route.

**Where.** `hooks/guard.py`, the `MERGE_TOOLS` clause (`merge_check`), beside `repo_proof_hit` in `hooks/guard_merge.py`.

**Decision.** merge-confirm-repo (a cloud merge acts only in a repo its own record names).

**Retire.** In a cloud session, the MCP merge tool is denied for an `owner/repo` that no cs-repo tag of the own newest get_session record names. It is allowed for one that a tag names. A case in `hooks/test_guard.py` shows both, with a record that lacks the tag and one that has it.
