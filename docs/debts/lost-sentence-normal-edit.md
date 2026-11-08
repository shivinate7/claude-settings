# Some normal note edits are refused as a lost sentence

**What.** The lost-sentence check refuses some normal note edits until a `Drops-lines` trailer names the note's slug as `- <slug>`. The refusal says how: it prints this trailer form. Refused normal edits include a renumbered `file.py:NNN` cite, a changed Decision id (refused when the note's other text lacks the old id's words; a label-only swap passes), and a corrected time or count. Example: `Until: 2026-11-22.` changed to `2026-12-06.`. A split is refused only when a part keeps the old slug or names it. A split with no such part, and no part that carries a clause of the old note, passes (debt `lost-sentence-rename-unpaired`, a renamed note's lost sentence passes). A split that keeps the old slug and moves a sentence to a new note is refused with nothing lost: `- split-old: A. B.` to `- split-old: A.` plus `- split-b: B.` refuses B. Likely in normal work: 41 of 1488 notes carry a file:line cite, and each such edit costs one trailer line.

**Where.** `lint/check_silent_undo.py`, `dropped_clauses` (flags the edit) and `lost_sentence_problem` (the refusal text).

**Decision.** `silent-undo-check-design` (the silent-undo check's design). Also `notes-merge-union` (debt notes merge by union), which the notes path rests on. Related: roadmap step `note-rewrite-keeps-claims` (a rewritten note keeps its claims).

**Retire.** Closed when `lint/test_check_silent_undo.py` has a case where a renumbered cite, or a corrected count, passes with no trailer, and a note that drops a sentence is still refused. Red on the current code, green after the fix.

Fix: none — one trailer line naming the slug costs less than a looser match that lets claims drop. Until: 2026-11-21.
