# Agents overwrite each other's scratchpad files

**What.** Agents in one session share a scratchpad folder, and one agent can overwrite a file that another agent wrote there. Unmeasured how often.

**Where.** `hooks/guard.py` and `hooks/guard_shared_tree.py`, the scratchpad-owner rule.

**Decision.** rule `roles-findings-are-debts-or-notes` (a known gap is a debt only if Claude is likely to hit it in normal work).

**Retire.** Closed when a case in `hooks/test_scratchpad_owner.py` refuses a write over another agent's file in the shared scratchpad.
