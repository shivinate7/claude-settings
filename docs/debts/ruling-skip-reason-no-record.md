# The ruling-skip refusal names no decision and no cite form

**What.** `RULING_REASON` names the rule `ruling-skip-check` and says "its time in parentheses". It names neither decision `questions-go-to-owner` (questions go to the owner), where the cite form lives, nor the literal form `under ruling item <N> <key> (<time>)`. Near-miss forms refuse again with the same generic text, "cites no item or decision with a time": `under ruling (item 284 a, 13:08 CST)` and `under ruling item 284 b, 13:08 CST`.

**Where.** `lint/report_guard.py`, `RULING_REASON`, and the "cites no item or decision with a time" text in `ruling_claims`.

**Decision.** `questions-go-to-owner`, questions go to the owner (its ruling-skip bullet, rule `ruling-skip-check`).

**Retire.** Closed when the refusal names decision `questions-go-to-owner`, gives the form `under ruling item <N> <key> (<time>)` with one example, and `lint/test_report_guard_ruling_skip.py` asserts both. The assertion goes red on the current text first.
