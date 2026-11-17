# The Cost-pin check reads no singular "time" noun

**What.** `COST_NOUN` has `times` but not `time`, so a count before the singular noun passes unflagged. "reads the list one time" is not read as a count.

**Where.** `lint/check_cost_pins.py`, `COST_NOUN` (lines ~79-80).

**Decision.** `cost-line-pinned`, a Cost line backs each file and count it states.

**Retire.** Add the singular `time` to `COST_NOUN`. `lint/test_check_cost_pins.py` then flags an unpinned "reads the list one time" and passes it once it is pinned or marked.
