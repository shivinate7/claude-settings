# A renamed note's lost sentence passes

**What.** The lost-sentence check pairs a removed note only with an added note under the same slug, or with one whose text names that slug. A note renamed, or folded into a note that never names the old slug, is a plain retire, so its lost sentences pass. Incident: commit 6c8b057cb (PR #2002, per the round-2 comment) renamed `find-time-pinned-donotfake-date` to `find-time-pinned-fake-overhide` and lost "The sleep scan reads fake timers the same way." The check still passes that commit (measured on this branch). Same family: a fold across two commits, and a rewrite inside a merge commit. Why open: pairing by shared topic words false-alarmed on a real retire (PR #2059, round 1).

**Where.** `lint/check_silent_undo.py`, `dropped_clauses` (the pairing rule) and `clauses` (the fragment join).

**Decision.** `notes-merge-union` (debt notes merge by union), which this check's notes path rests on. Roadmap step `note-rewrite-keeps-claims` (a rewritten note keeps its claims) carries the fix.

**Retire.** Closed when `lint/test_check_silent_undo.py` has a case where a note renamed to one that never names the old slug loses a sentence and is refused. A plain retire that loses no sentence must still pass. Red on the current code, green after the fix.
