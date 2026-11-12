# The guard probe reports three false alarms

**What.** The guard probe reports three false alarms. A quoted "GitHub" in a `python -c` body is read as git. `../cfg/` text in a `python -c` body is flagged. A read-only probe that names a frozen path after a mutating word is flagged. Unmeasured how often.

**Where.** `hooks/probe.py`, which runs the guard rules in `hooks/guard.py`.

**Decision.** cull-guard-wrong-refusals (the guard cull), which lists these gaps.

**Retire.** Closed when each of the three cases in `hooks/test_probe.py` is allowed.
