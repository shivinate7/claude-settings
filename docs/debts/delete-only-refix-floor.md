# A delete-only re-fix record now needs round 2 or a fix PASS

**What.** Decision `pr-review-record` says a `delete-only` change with Guard or check `no` and a round 1 FAIL reads done. The lane then fixes the defect and posts a new record for the new head. Rule G1 (a failed round stays failed, PR 1440) makes a later `Round 1: PASS` record read open. A lane that follows the old text gets an open line and no clear next step. The same applies to R1 PARTIAL, then R1 PASS, and to a same-round design re-read PASS. Whether lanes post these shapes is unmeasured. Found by review round 3 of PR 1440, 2026-11-07.

**Where.** `docs/decisions/pr-review-record.md`, the limit on delete-only changes. `merge/merge.py` `round_floor`, and the plain write's open-FAIL floor in `floor_problem`, which refuses the re-fix record with "run round 2".

**Decision.** pr-review-record (the review record).

**Retire.** Rewrite the delete-only limit to say the re-fix record carries a Fix check PASS on the fix diff, or exempt a delete-only round 1 from the floor. Add a test that pins the chosen path.
