# A past-ruling judge's own words reach a refusal

**What.** When the judge names no listed id, its reason is replaced by code-written text only if the answer marks item 8: an `item` of 8, `"8"` or 8.0, or, with no `item` from 1 to 8, a reason that opens with `8.`, `8:`, `8)` or `Item 8`. Any other refusal that names no listed id, such as an item-8 answer with neither mark, carries the judge's reason as written, under the call's rule. `session_wording`, which flags an order after an em dash or with no mark, has no production caller.

**Where.** `main` in `hooks/call_judge.py`: when `past` is False and `past_ruling_item` is False, `refuse` gets the judge's `reason`. `past_ruling_item` reads the `item` field when `item_mark` finds one from 1 to 8, else the reason's opener (`PAST_ITEM_REASON`).

**Harm.** A model reply's words reach the session as the refusal text. Refusals of form items 1 to 7 keep the judge's reason by design (`form_refusal`, `hooks/call_judge.py`).

**Decision.** `guard-remedy-not-to-owner` (the past-ruling guard).

**Retire.** Retired when a test pins that an item-8 answer with neither mark holds none of the judge's words. `case_item_eight_without_a_listed_id_holds_no_judge_words` in `hooks/test_call_judge.py` uses `"item": 8`, so it does not reach this path.
