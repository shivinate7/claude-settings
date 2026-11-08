# A number after a glossed plural item cite reads as an item

**What.** After a plural head with a gloss in parentheses, a comma joins the next number as an item. `items 46 (search pill), 2026-11-01 was the day` refuses on 2026. `items 46 (search pill), and 12 more` refuses on 12. A false alarm; the reason names the number.

**Where.** `lint/report_guard.py`, `ITEM_NEXT_RE` in `bare_item_cite`.

**Decision.** None; rule `speak-cite-id-plus-gloss` (an id carries a short name).

**Retire.** The tail joins a number only when no gloss sits between it and the head's last number, or when the number is followed by its own gloss or the reply's end. Closed when both inputs above pass and `items 46 (search pill) and 47` still refuses.
