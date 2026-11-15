# A bad session start is flagged, not refused

**What.** The model floor and handoff-unread no longer refuse a `start_session` call. A PostToolUse audit flags a bad start after the session exists, and the calling session must stop it with `interrupt_session` or `archive_session`. A caller that ignores the flag leaves a Haiku session running, or a session started from a brief written without the caller's handoff. The guard refused both before the call. For the model floor, the started session's own start check also flags a Haiku start (`hooks/start_check.py`, decision `start-checks-after-call`, the start checks run in the started session). A model can ignore that flag too. Whether the desktop app delivers it is unknown.

**Where.** `hooks/start_session_audit.py`, and the PostToolUse entry for `mcp__ccd_session__start_session` in `settings.json`. `hooks/start_check.py` for the model floor flag.

**Decision.** `start-session-not-pretooluse` (start_session is not judged at PreToolUse). `start-checks-after-call` (the start checks run in the started session).

**Retire.** The owner or the app makes a refusal before the start possible without the start card (anthropics/claude-code#103832 fixed, the public bug on that card), and the matcher lists `start_session` again. Closed when `lint/test_settings_matcher.py` allows that matcher, and a guard case refuses a Haiku start and an unread-handoff start before the call.
