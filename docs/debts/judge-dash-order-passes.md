# A past-ruling judge's own words reach a refusal

**What.** An item-8 answer that names no listed id, and carries neither an `item` field nor a reason that opens with 8, reaches a refusal as the judge wrote it, under the call's rule. `session_wording`, which flags an order after an em dash or with no mark, has no production caller.

**Where.** `main` in `hooks/call_judge.py`: when `past` is False and `past_ruling_item` is False, `refuse` gets the judge's `reason`. `past_ruling_item` reads the `item` field, or without one, the reason's opener (`PAST_ITEM_REASON`).

**Harm.** A model reply's words reach the session as the refusal text. Refusal text holds facts only, written by code (decision `guard-remedy-not-to-owner`, Build).

**Decision.** `guard-remedy-not-to-owner` (the past-ruling guard).

**Retire.** Retired when a test pins that an item-8 answer with neither mark holds none of the judge's words. `case_item_eight_without_a_listed_id_holds_no_judge_words` in `hooks/test_call_judge.py` uses `"item": 8`, so it does not reach this path.
