# The silent-undo refusal does not say where the trailer goes

**What waits.** `lint/check_silent_undo.py` (line 453) tells the reader to add the trailer
`Drops-lines: <path> -- <reason>` to a commit message. Git reads a trailer only from the last
paragraph of the message. A trailer above a blank line, with `Co-Authored-By` below it, is
ignored, and the check stays red with no reason given.

**Why it waits.** The orchestrator hit it once, on integration batch 4 on 2026-10-02, and fixed
the message by hand. The check is correct; only its hint is incomplete.

**What keeps it from being lost.** This file.

**Trigger.** When `lint/check_silent_undo.py` next changes, extend the hint. Say that the
trailer must sit in the last paragraph, beside any `Co-Authored-By` line. Add a test that a
trailer above a blank line is reported as ignored.
