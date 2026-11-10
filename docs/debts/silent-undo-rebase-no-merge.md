# A rebase onto main that revives a deleted note is not caught

**What.** `revived_notes` replays the branch's own commits and flags a note that a merge put back. A rebase onto main has no merge. The union driver runs as the deleting commit is replayed, and keeps the note inside that commit. The commit then lowers no count, so the check sees no deletion and passes. A branch rebased onto a main that edited the same note loses its deletion this way, so Claude hits it when it rebases a lane.

**Where.** `lint/check_silent_undo.py`, `revived_notes`: it reads each commit's file against its parent's, and only a lowered count is an event.

**Decision.** notes-merge-union (the notes file merges by union; `check_silent_undo` refuses a revived note).

**Retire.** A rebase that keeps a note the branch deleted is refused, or the deletion is read from the branch's original commits. A case in `lint/test_check_silent_undo.py` rebases a deleting branch onto a main that appended beside the note, and expects a finding.
