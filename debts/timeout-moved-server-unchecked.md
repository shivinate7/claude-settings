# Foreground server moved to background is unchecked

- **What.** A foreground server that the harness moves to background at its 120 s timeout is not checked. The `background-end` rule reads the call at start. A call that starts in the foreground has no `run_in_background`, so the rule does not see it.
- **Where.** `hooks/guard_stream.py`, the `background-end` rule.
- **Decision.** `background-needs-end-note` (a background server or watcher needs an `until:` note at start).
- **Retire.** Cover the 120 s timeout move, in the guard or in the Stop check. A test case for a foreground server that the harness moves to background is red before the change and green after it.
