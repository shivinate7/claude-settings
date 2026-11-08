# A renamed note's lost sentence can still pass

**What.** The lost-sentence check pairs a removed note with an added note in three cases. The slug is the same. The added text names the old slug (a fold). Or a new slug carries a clause of it, held at `PAIR_HELD` (0.75). That last pair is a rename. A removed note with no pair is a plain retire, and no finding. These forms still pass:
- A rename that rewords every clause below `PAIR_HELD`.
- A fold into an existing note that does not name the removed note. An existing slug never pairs as a rename.
- A fold across two commits that names the old slug in the later commit only.
- A rewrite inside a merge commit. The replay reads non-merge commits only.
- A clause that an unrelated note line in the same commit holds at `HELD`, on the words the two share. Words that a tenth of head's note lines carry do not count (`generic_words`). Commit baf4d61d7 lost "no check ties the 90% n/a share" and passes. `restates-na-by-copied-anchors`, added in that commit, holds 90, n and share.

Incident closed: commit 6c8b057cb (PR #2002) renamed `find-time-pinned-donotfake-date` to `find-time-pinned-fake-overhide` and lost "The sleep scan reads fake timers the same way."; the check now refuses it. A looser pair stays out. Pairing by shared topic words, a shared `Decision:` tag or a slug prefix false-alarmed on a real retire (PR #2059, round 1).

**Where.** `lint/check_silent_undo.py`: `dropped_clauses` (the pairing rule), `renamed_to` (the text pair), `dropped_in_pair` and `held` (the clause hold), `generic_words`.

**Decision.** `notes-merge-union` (debt notes merge by union), which this check's notes path rests on. Roadmap step `note-rewrite-keeps-claims` (a rewritten note keeps its claims) cites the incident.

Fix: pair a fold across commits by the old slug, as the one-commit fold does. Leave the reworded rename and the merge-commit rewrite open until one is met in real work.

**Retire.** Closed when `lint/test_check_silent_undo.py` has a case where a note folded across two commits, naming the old slug only in the later commit, loses a sentence and is refused. A plain retire that loses no sentence must still pass. Red on the current code, green after the fix. The other forms above stay open until one is met in real work.
