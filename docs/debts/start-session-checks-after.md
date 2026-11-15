# A bad session start is flagged, not refused

**What.** The model floor and handoff-unread no longer refuse a `start_session` call. A PostToolUse audit flags the bad start after the session exists, and the calling session must stop it with `interrupt_session` or `archive_session`. A caller that ignores the flag leaves a Haiku session running, or a session started from a brief written without the caller's handoff. The guard refused both before the call.

**Where.** `hooks/start_session_audit.py`, and the PostToolUse entry for `mcp__ccd_session__start_session` in `settings.json`.

**Decision.** `start-session-not-pretooluse` (start_session is not gated at PreToolUse).

**Retire.** The owner or the app makes a refusal before the start possible without the start card (anthropics/claude-code#103832 fixed), and the matcher lists `start_session` again. Closed when `lint/test_settings_matcher.py` allows that matcher and a guard case refuses a Haiku start before the call.
