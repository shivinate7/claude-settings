# The Cost-pin check reads no past-tense work verb

**What.** `WORK_VERB` has no past tense, so a count after a past verb passes unflagged. "opened the list once", "checked ... twice" and "ran ... once" are not read as counts.

**Where.** `lint/check_cost_pins.py`, `WORK_VERB` (line ~77).

**Decision.** `cost-line-pinned`, a Cost line backs each file and count it states.

**Retire.** Add the past tense of each work verb to `WORK_VERB`. `lint/test_check_cost_pins.py` then flags an unpinned past-tense count, such as "opened the list once", and passes it once it is pinned or marked.
