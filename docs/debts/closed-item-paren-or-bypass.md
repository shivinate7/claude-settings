# Closed-item check passes a letter with a parenthetical

**What.** A closed waiting-page item, asked again in the house option form, passes the Input Needed check. The examples cite item 214, a closed waiting-page item. In `_LETTERS`, " (" ends a letter cite, and the "or" lookahead skips only spaces and marks, never a parenthetical's text. So `item 214: pick a (recommended) or b`, `item 214 a (keep it) or b (drop it)` and `item 214: pick a (default), b (alt)` all pass. "a (recommended)" is the usual option form, so Claude is likely to write it.

**Where.** `lint/report_guard.py`: function `closed_item_problem`, with its `_LETTERS` and `RULING_AFTER_RE` patterns. Both are in PR #2203 (the pull request that adds the closed-item check), not yet on main. Tests: `lint/test_report_guard_page_status.py`, also in PR #2203.

**Decision.** `hold-unsafe-after-round-3` (the net-value hold after round 3). Round 3 of PR #2203 merged at positive net value, so its open findings are filed here.

**Retire.** After a letter's parenthetical, look ahead for `or` or `, <letter>` before treating the cite as a ruling. Test: `lint/test_report_guard_page_status.py` blocks the three examples in What, and still passes `item 109 b (owner, 11-04 17:55 CST)`. Red on the current code, green after the fix.
