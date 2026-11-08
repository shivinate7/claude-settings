# A normal note edit is refused as a lost sentence

**What.** The lost-sentence check refuses normal note edits until a `Drops-lines` trailer names the note's slug as `- <slug>`. Refused normal edits include a renumbered `file.py:NNN` cite, a swapped Decision tag, and a corrected time or count. Example: `Until: 2026-11-22.` changed to `2026-12-06.`. A split note that does not name the old slug is refused too. Likely in normal work: 41 of 1489 notes carry a file:line cite, and each such edit costs one trailer line.

**Where.** `lint/check_silent_undo.py`, `dropped_clauses` (flags the edit) and `lost_sentence_problem` (the refusal text).

**Decision.** `silent-undo-check-design` (the silent-undo check's design). Also `notes-merge-union` (debt notes merge by union), which the notes path rests on. Related: roadmap step `note-rewrite-keeps-claims` (a rewritten note keeps its claims).

**Retire.** Closed when `lint/test_check_silent_undo.py` has a case where a renumbered cite, or a corrected count, passes with no trailer, and a note that drops a sentence is still refused. Red on the current code, green after the fix.
