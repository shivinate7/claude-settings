# Start audit does not pin its held-model read

**What.** The start audit's Opus lane check reads two grants: a held model (the pass file) and a live timed override. Its one test pins the timed-override half only. No case sets a held Opus. So a mutant that drops that read passes every case.

**Where.** `lane_opus_without_grant` in `hooks/start_session_audit.py`, line 76. It calls `override._take_opus` and `override.timed_live`. Its test is `tests/guard/s38500-start-session-audit.py`, which pins the timed half in `audit_opus_lane_timed_override_silent`.

**Decision.** start-session-not-pretooluse (start_session is not judged at PreToolUse; the start check runs as a PostToolUse audit).

**Retire.** Add these cases to `tests/guard/s38500-start-session-audit.py` (the start audit section file), run through `lane_opus_without_grant`. `hooks/test_guard.py` (the guard test suite, which runs that folder's section files) runs them:

- Silent: Opus no-role, and general-purpose, each under a live held Opus (set by a plain ask such as `use opus for everything`; the keyword `opus 2h` is gone).
- Flagged: a builders-only held Opus, a once override, an expired timed override, and an unreadable timed override.
