# A bad session start is flagged, not refused

**What.** Handoff-unread no longer refuses a `start_session` call. A PostToolUse audit flags a bad start after the session exists, and the calling session must stop it with `interrupt_session` or `archive_session`. A caller that ignores the flag leaves a session started from a brief written without the caller's handoff. The guard refused it before the call. A Haiku start is not flagged: the owner's model name lifts the floor (owner, 2026-11-18 19:03 CST, decision `agent-model-cap`), and a started session cannot read that word.

**Where.** `hooks/start_session_audit.py`, and the PostToolUse entry for `mcp__ccd_session__start_session` in `settings.json`.

**Decision.** `start-session-not-pretooluse` (start_session is not judged at PreToolUse). `start-checks-after-call` (the start checks run in the started session).

**Retire.** The owner or the app makes a refusal before the start possible without the start card (anthropics/claude-code#103832 fixed, the public bug on that card), and the matcher lists `start_session` again. Closed when `lint/test_settings_matcher.py` allows that matcher, and a guard case refuses an unread-handoff start before the call.
