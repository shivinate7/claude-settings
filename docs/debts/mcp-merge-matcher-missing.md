# The MCP merge refusal never runs, because the guard matcher lacks both tool names

**What.** `settings.json`'s first PreToolUse matcher (the guard) does not name `mcp__github__merge_pull_request` or `mcp__github__enable_pr_auto_merge`. The guard never receives those calls, so the cloud coordinator's refusal of both never runs. A coordinator can merge, or arm auto-merge, through the GitHub MCP tools. The guard's CI check on a bare merge never sees those calls either.

**Where.** `settings.json` (first PreToolUse matcher). `hooks/guard.py` (`COORDINATOR_MERGE_TOOLS`, `coordinator_scope_hit`).

**Decision.** `session-tiers` (tier guards: a coordinator stays in its tier, and a guard enforces it).

**Retire.** Add both tool names to that matcher, and add a case to `lint/test_settings_matcher.py` that fails when a tool in `COORDINATOR_MERGE_TOOLS` is not in the matcher. Check: that case, and a guard case showing the coordinator's MCP merge refused through the real matcher.
