# No test fails when a coordinator-scope MCP tool leaves the guard matcher

**What.** `settings.json`'s first PreToolUse matcher (the guard) now names the GitHub MCP merge tools (`COORDINATOR_MERGE_TOOLS`) and file-write tools (`COORDINATOR_MCP_WRITE_TOOLS`), so the cloud coordinator's refusals of them run. No test pins that: a later edit that drops a name from the matcher turns the refusals off with every test green.

**Where.** `settings.json` (first PreToolUse matcher). `hooks/guard.py` (`COORDINATOR_MERGE_TOOLS`, `COORDINATOR_MCP_WRITE_TOOLS`, `coordinator_scope_hit`).

**Decision.** `session-tiers` (tier guards: a coordinator stays in its tier, and a guard enforces it).

**Retire.** Add a case to `lint/test_settings_matcher.py` that fails when a tool in `COORDINATOR_MERGE_TOOLS` or `COORDINATOR_MCP_WRITE_TOOLS` is not in the matcher. Check: that case, and a guard case showing the coordinator's MCP merge or file write refused through the real matcher.
