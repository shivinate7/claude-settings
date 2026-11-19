# A two-agent merge of main trips the silent-undo lane check

**What.** A builder cannot edit tests and a test-author cannot edit product code. So when both merge main into one lane, one merge commit can hold an old line for one step, and the silent-undo check reads it as a dropped line. The lane lint then fails until a commit adds a `Drops-lines:` trailer. Mistake: Claude merges main in two steps, one per agent. Harm: a lint fail, then one extra trailer commit and a lint rerun. Seen once, on PR 3415 (lane rebase-wave-1c, 2026-11-15): the test-author's merge held the old `lint/check_debt_retire.py`, and the lane added `Drops-lines: lint/check_debt_retire.py` at head 163ae2541. This is the lane's report. It was not run again here, and no cause in the check's code is named.

**Where.** `lint/check_silent_undo.py`, the lost-lines check on a merge commit (`lost_lines`).

**Decision.** `silent-undo-check-design` (the silent-undo check and its remedy).

**Retire.** The lane merge flow adds the trailer itself, or the check reads a merge by its first parent. A case in `lint/test_check_silent_undo.py` builds a merge whose second agent re-adds an old line and expects no finding.
