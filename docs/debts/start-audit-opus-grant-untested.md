# Start audit does not pin its Opus override read

**What.** The start audit's Opus lane check reads two grants: the Opus override file and a live timed override. Its one test pins the timed-override half only. No case sets an Opus override file. So a mutant that drops that read passes every case.

**Where.** `lane_opus_without_grant` in `hooks/start_session_audit.py`, line 76 on main. It calls `override._take_opus` and `override.timed_live`. Its test is `tests/guard/s38500-start-session-audit.py`, which pins the timed half in `audit_opus_lane_timed_override_silent`.

**Decision.** start-session-not-pretooluse (start_session is not judged at PreToolUse; the start check runs as a PostToolUse audit).

**Retire.** Add these cases to `tests/guard/s38500-start-session-audit.py` (the start audit section file), run through `lane_opus_without_grant`. `hooks/test_guard.py` (the guard test suite, which runs that folder's section files) runs them:

- Silent: Opus no-role, and general-purpose, each under a live `opus 2h` override.
- Flagged: a builders-only override, a once override, an expired timed override, and an unreadable timed override.
