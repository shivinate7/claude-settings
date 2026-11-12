# The scratchpad commit rule refuses a -F file the agent wrote

**What.** The scratchpad commit rule refuses a `-F` message file that the agent wrote itself. The refusal is a false alarm. Unmeasured how often.

**Where.** `hooks/guard.py`, rule `scratchpad-commit-msg-owner`.

**Decision.** cull-guard-wrong-refusals (the guard cull), which lists this gap.

**Retire.** Closed when a case in `hooks/test_scratchpad_owner.py` allows a `-F` message file that the agent wrote itself.
