# Some normal note edits are refused as a lost sentence

**What.** The lost-sentence check refuses some normal note edits until a `Drops-lines` trailer names the note's slug as `- <slug>`. The refusal says how: it prints this trailer form. Refused normal edits include a renumbered `file.py:NNN` cite, a corrected time or count, and a changed Decision id. Example: `Until: 2026-11-22.` changed to `2026-12-06.`. A Decision id change is refused: `(P5)` to `(P6)` is refused, since `P5` is a token with a digit. A label-only swap passes: `Decision:` changed to `Ruling:` with the id kept.

A split passes when every clause of the old note is held. A clause is held when the note's new text, or one note line the commit adds, has half of the clause's content words (`HELD`, 0.5). It also holds every token with a digit (a number or an id such as `P5`). So `- split-old: A. B.` to `- split-old: A.` plus `- split-b: B.` passes. It is refused when `split-b` holds B at a third of its words. A split is read only when a part keeps the old slug, names it, or carries a clause of the old note at `PAIR_HELD` under a new slug (debt `lost-sentence-rename-unpaired`). Otherwise it is a plain retire.

Refused by design, one trailer line each:
- A retire beside a sibling note that keeps one long sentence verbatim and drops another. It has the shape of incident 6c8b057cb (a rename that lost a sentence). The check cannot tell them apart.
- A retired slug re-added later with a sentence dropped. The re-add is judged as a rewrite.

Likely in normal work: 41 of 1495 notes carry a file:line cite, and each such edit costs one trailer line naming the slug.

**Where.** `lint/check_silent_undo.py`: `dropped_clauses` and `dropped_in_pair` (flag the edit), `held` (the clause test), `lost_sentence_problem` (the refusal text).

**Decision.** `silent-undo-check-design` (the silent-undo check's design). Also `notes-merge-union` (debt notes merge by union), which the notes path rests on. Related: roadmap step `note-rewrite-keeps-claims` (a rewritten note keeps its claims).

**Retire.** Closed when `lint/test_check_silent_undo.py` has a case where a renumbered cite, or a corrected count, passes with no trailer, and a note that drops a sentence is still refused. Red on the current code, green after the fix.

Fix: none — one trailer line naming the slug costs less than a looser match that lets claims drop. Until: 2026-11-21.
