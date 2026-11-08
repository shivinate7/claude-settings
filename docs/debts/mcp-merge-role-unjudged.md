# The GitHub merge tool skips the merge-role check

- **What.** The merge-role check that PR #1742 adds to `gh pr merge` does not judge the GitHub MCP merge tool, `mcp__github__merge_pull_request`. On main no `PreToolUse` matcher in `settings.json` matches that tool (checked with `re.fullmatch` and `re.search`). PR #1665 (guard matcher) and PR #1687 (merge-checks deny plus the bare-merge ask) cover the matcher and the deny, and land with the PR #1601 stack. This debt is the role gap that remains after them.
- **Where.** `MERGE_TOOLS` in `hooks/guard_merge.py`, and the `PreToolUse` matchers in `settings.json`.
- **Decision.** `session-tiers` (which merge role each session tier holds).
- **Retire.** The guard refuses `mcp__github__merge_pull_request` in a session with no merge role, and `hooks/test_guard.py` holds the case.

- Fix: step:mcp-merge-role
