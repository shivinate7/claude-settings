# A merge through the MCP tool checks no repo tag

**What.** `mcp__github__merge_pull_request` has one merge test, the `MERGE_TOOLS` clause in `judge` (read `hooks/guard.py` `judge`). It passes only when `merge_check` reads the head green (read `hooks/guard_merge.py` `merge_check`). It has no cs-repo or role check: `judge` calls `judge_shell` only for `SHELL_TOOLS` (read `hooks/guard_core.py` `SHELL_TOOLS`), and `judge_shell` (read `hooks/guard.py` `judge_shell`) runs `repo_proof_hit` and `role_proof_hit`. So a runner can merge a repo its tags do not name through the MCP tool, though `merge N --confirm` is refused on the Bash route (read `hooks/guard_merge.py` `repo_proof_hit`). A runner that the Bash route refuses can reach the same merge by the MCP route (read `hooks/guard.py` `judge`).

**Where.** `hooks/guard.py`, the `MERGE_TOOLS` clause (`merge_check`), beside `repo_proof_hit` in `hooks/guard_merge.py`.

**Decision.** The decision `merge-confirm-repo`: a cloud merge confirm acts only in a repo its own record names.

**Retire.** In a cloud session, the MCP merge tool is denied for an `owner/repo` that no cs-repo tag of the own newest get_session record names (read `hooks/guard_merge.py` `repo_proof_hit`, the Bash route's denial). It is allowed for one that a tag names (read `hooks/shared_names.py` `repo_tag_names`; decision `merge-confirm-repo`: a cloud merge confirm acts only in a repo its own record names). A case in `tests/guard/s29942-merge.py` `REPO_RULE` must show both, with a record that lacks the tag and one that has it.
