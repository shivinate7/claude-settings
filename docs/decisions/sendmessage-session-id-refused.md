# A SendMessage to a session_ id is refused

## The ruling

Rule `sendmessage-session-id` in `hooks/guard.py` refuses a `SendMessage` call whose `to` is a string that starts `session_`. Layer: the lane that built it, brief from its coordinator, 2026-11-08 CST.

- The mistake (incident, lane `lane-model-sonnet`, 2026-11-08 about 12:39 CST): the lane called `SendMessage` with `to` set to a `session_...` id. Auto mode refused the call. `SendMessage` addresses an agent by name, and a `session_...` id is not an agent name.
- The harm: the hand-off could go missing, so the receiving session never hears it and the sender may believe it did. Whether `SendMessage` would deliver to such an id is unmeasured. The tool's own text says a bare name that matches one live agent or session delivers directly, even in the cloud.
- A hit: `tool_name` is `SendMessage` and `to` is a string that starts `session_`. The match is on the start of the value, so a name with `session_` mid-name passes.
- Passes: an agent name, `@parent`, an empty, missing or non-string `to`, and the `mcp__claude-code-remote__send_message` tool, whatever its `session_id`.
- Steer: the reason names `mcp__claude-code-remote__send_message` and its `session_id` argument, the sure route.
- An owner override lifts it (`owner-override`). A form that only an attacker would write is not read (`guard-guards-mistakes-only`).
- Matcher: `settings.json` adds `SendMessage` to the guard's PreToolUse matcher. The separate `SendMessage` matcher for the state judge is unchanged.
- Cost: one guard process start per `SendMessage` call, from the PreToolUse matcher. The rule is a string prefix test. The new matcher also gives two existing reads a `SendMessage` call they did not see before. `session_home_keep` in `hooks/guard.py` reads a lane's record file when one resolves. `unread_handoff` in `hooks/reread_check.py` can refuse a main-session `SendMessage` after compaction. No file is written beyond the refusal's own log line.
- Not covered: a `cse_...` id (a lane's own id, from `CLAUDE_CODE_REMOTE_SESSION_ID`), a pasted claude.ai URL, and a `to` with a leading space pass. This is a note. It becomes a debt after a real incident.

Protected by the `sendmessage-session-id` cases in `hooks/test_guard.py` and `test_guard_matcher_covers_sendmessage` in `lint/test_settings_matcher.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
