# A negation clears only the verb right after it

**What.** `Do not edit or delete hooks/test_guard.py` and `Never edit, delete or rewrite X` ask at spawn, because the negation clears only the next verb. Fence lines like these are routine in briefs.

**Where.** `hooks/guard.py`, `_message_edit_verb`.

**Decision.** message-role-scope (what a message or brief edits).

**Retire.** A negation carries across a verb list joined by `or` and commas. A case in `hooks/test_guard.py` passes both briefs and still asks on `Do not read, but edit X`.
