# An empty commit's Drops-lines trailer is refused with no hint why

**What.** A lane answers a silent-undo lost-line finding with a `Drops-lines` trailer on an empty commit, one that changes no file. The check counts that trailer for nothing, by design (decision `silent-undo-check-design`), and the refusal repeats its remedy, "put the work back, or add the trailer ... to a commit message", with no word that the commit must change a file. Reproduced at this head: the empty commits fd108fc65 and df3ff85d4 (lane notes-fix-page) fail on `hooks/guard.py` against upstream 624dcc188. Measured across all branches since 2026-09-01: 634 of 25944 commits carry a `Drops-lines` trailer (2.4%). The share that are empty is unmeasured.

**Where.** `lint/check_silent_undo.py`: `allowed()` (line 162, the empty-commit rule at lines 165-166) and `fix_text()` (line 717, the remedy at line 723). `misplaced()` (line 188) hints only at a trailer git does not read, so it prints nothing here. `merge/merge.py` lines 345 and 354 print the remedy through `fix_text`.

**Decision.** `silent-undo-check-design` (one check catches a merge or branch that silently undoes earlier work). Its trailer rules say an empty commit's trailer excuses nothing.

**Retire.** The remedy says the commit must change a file, or the check prints a note for a trailer it ignores. A case in `lint/test_check_silent_undo.py` puts a `Drops-lines` trailer on an empty commit, expects the lost line refused, and expects the refusal text to name the file-change rule.
