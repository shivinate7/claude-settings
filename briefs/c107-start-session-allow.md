# c107 step 1: what pre-approves start_session on the Mac desktop app?

Local liaison, Oct 27, against claude-settings main d4e1b86b. Mac session, read-only: no settings
edit, no session start, no ask to the owner. Print no token, cookie or key.

hooks/guard.py never asks on mcp__ccd_session__start_session, so the accept the owner clicked most
likely comes from the desktop app.

1. List every permissions rule (allow, ask, deny, defaultMode) in ~/.claude/settings.json,
   ~/.claude/settings.local.json and any managed settings that names ccd_session or mcp__.
2. List the setting names (not values that look secret) in the Claude desktop app's config under
   ~/Library/Application Support/Claude/ that touch permissions, approvals, or sessions.
3. From the Claude Code docs (code.claude.com/docs, permissions page), say whether an allow rule
   `mcp__ccd_session__start_session` pre-approves an MCP tool in bypass mode, and whether the
   desktop app's own session-start prompt is outside settings.json.
4. Report in 10 lines: what exists today, the most likely pre-approval (a rule or a desktop
   setting), and what one owner click would prove it.
