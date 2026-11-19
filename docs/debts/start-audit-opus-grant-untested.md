# Start audit does not pin its Opus override read

**What.** The start audit's Opus lane check reads two grants: the Opus override file and a live timed override. Its one test pins the timed-override half only. No case sets an Opus override file. So a mutant that drops that read passes every case.

**Where.** `hooks/start_session_audit.py`, `lane_opus_without_grant`. It calls `override._take_opus` and `override.timed_live`. Its test is `tests/guard/s38500-start-session-audit.py`, which pins the timed half in `audit_opus_lane_timed_override_silent`. The Opus check is not on main. It is on open PR #3690 (head dd071c6067). Read this debt against that head until the PR merges.

**Decision.** start-session-not-pretooluse (start_session is not judged at PreToolUse; the start check runs as a PostToolUse audit).

**Retire.** Add these cases to `tests/guard/s38500-start-session-audit.py`, run through `lane_opus_without_grant`:

- Silent: Opus no-role, and general-purpose, each under a live `opus 2h` override.
- Flagged: a builders-only override, a once override, an expired timed override, and an unreadable timed override.
