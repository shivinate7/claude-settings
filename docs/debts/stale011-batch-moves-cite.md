# A batch move breaks a line cite on the integration head

**What.** A line cite that is right on its lane's head fails the stale-cite check (STALE011, `anchor_drift`) on the integration head when another lane in the same batch moves the cited code. The batch run then goes red until the cite is re-pointed. The flag is true on the merged tree, so it is no false alarm. Measure: round 3 of PR #2196 (branch `cite-range-symbol-match`) found it in 4 of the 12 latest main merge ranges (reviewer read, 2026-11-08). An earlier count put it at 5 of 80 past batch merges (round 3, no date). Example: `read_backing` was at line 2459 of `merge/merge.py` at lane commit 4555647b6, and at line 2525 at merge 335a6974a.

**Where.** lint/stale_cites.py `anchor_drift`.

**Decision.** record-cites-live-code (a claim about code cites a live code name).

**Retire.** Cite the code by symbol, `(file.py name)`, not by line. A case in `lint/test_stale_cites.py` shows a symbol cite stays green after its code moves within a batch. No such case exists yet.
