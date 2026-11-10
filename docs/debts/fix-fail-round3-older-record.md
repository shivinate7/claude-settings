# A fix check round limit reads only the newest earlier record

**What.** `round_floor` refuses a second fix check only when the newest earlier record has a fix check FAIL that counts as round 3. An older record's counted round-3 fix FAIL can be bypassed. Records A (R1 FAIL, R2 PASS, fix FAIL), B (R1 FAIL, R2 PASS, R3 FAIL) and C (same rounds, fix PASS, Guard or check `yes`, net value positive) read C as done. The end state equals main's B then C under item 363 b, so it is not worse than main. Whether lanes post this shape is unmeasured.

**Where.** `merge/merge.py` `round_floor`, the early rule on `earlier[-1]`.

**Decision.** pr-review-record (the review record); hold-unsafe-after-round-3 (hold a guard or check change with negative net value after round 3).

**Retire.** Refuse a fix check when any earlier record's fix FAIL counted as round 3 or later, with a test case for records A, B and C. `merge/test_merge.py` shows it closed.
