# The GitHub auto-merge tool has no guard rule

- **What.** `mcp__github__enable_pr_auto_merge` has no guard rule, and no `PreToolUse` matcher in `settings.json` matches it (checked with `re.fullmatch` on main). A cloud session can arm a merge with no merge role.
- **Where.** `hooks/guard.py` and `hooks/guard_merge.py` (no rule names the tool), and the `PreToolUse` matchers in `settings.json`.
- **Decision.** `session-tiers` (which merge role each session tier holds).
- **Retire.** The guard refuses `mcp__github__enable_pr_auto_merge` in a session with no merge role, and `hooks/test_guard.py` holds the case.

- Fix: step:notes-reverify-flags
