# The Cost-pin check reads no line range as a file

**What.** `LINE_SUFFIX` drops only a trailing `:digits`. So `lint/stale_cites.py:228-253` keeps its `-253`, and the check does not read it as a file token. Its `:228` form is read. Decision records hold 37 `.py:N-M` range refs (grep, 2026-11-12), all in one record.

**Where.** `lint/check_cost_pins.py`, `LINE_SUFFIX` (line ~70).

**Decision.** `cost-line-pinned`, a Cost line backs each file and count it states.

**Retire.** Drop a trailing `:N-M` range as well as `:N` in `LINE_SUFFIX`. `lint/test_check_cost_pins.py` then flags an unpinned Cost sentence that names a `:N-M` range, and passes it once it is pinned or marked.
