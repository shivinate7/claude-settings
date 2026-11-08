# SendMessage never goes to a cloud session

## The ruling

Rule `sendmessage-session-id` in `hooks/guard.py` refuses a `SendMessage` call whose `to` is a string that starts `session_`. Layer: the lane that built it, brief from its coordinator, 2026-11-08 CST.

- The mistake: a lane called `SendMessage` with `to` set to a `session_...` id. `SendMessage` addresses in-process agents and local teammates by name. It reaches no cloud session.
- The harm: the hand-off goes missing with no error, so the receiving session never hears it and the sender believes it did.
- A hit: `tool_name` is `SendMessage` and `to` is a string that starts `session_`. The match is on the start of the value, so a name with `session_` mid-name passes.
- Passes: an agent name, `@parent`, an empty, missing or non-string `to`, and the `mcp__claude-code-remote__send_message` tool, whatever its `session_id`.
- Steer: the reason names `mcp__claude-code-remote__send_message` and its `session_id` argument.
- An owner override lifts it (`owner-override`). A form that only an attacker would write is not read (`guard-guards-mistakes-only`).
- Matcher: `settings.json` adds `SendMessage` to the guard's PreToolUse matcher. The separate `SendMessage` matcher for the state judge is unchanged.
- Cost: one guard process start per `SendMessage` call, from the PreToolUse matcher. A string prefix test, no file read, no log beyond the refusal's own.

Protected by the `sendmessage-session-id` cases in `hooks/test_guard.py` and `test_guard_matcher_covers_sendmessage` in `lint/test_settings_matcher.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
