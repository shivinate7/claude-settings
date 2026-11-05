# A relayed grant finds no answer once its item is routed

**What.** "Route and close" deletes `answers/<id>` and closes the item when the owning session routes the answer. A receiving session that checks the page after that gets `not counted` from `page_grant.py`, so the relayed act is refused. This is the case of item 242 (joyous ruleset): its answer was gone at 07:58 CST on 2026-11-05. It fails closed, so it costs a re-ask, not safety.

**Where.** `skills/waiting-page/SKILL.md` "Route and close" steps 1 and 2; `skills/waiting-page/page_grant.py`.

**Decision.** relayed-grant-read-from-page (a relayed grant is read from the page, not from the relay).

**Retire.** The owning session keeps the item open and `answers/<id>` in place until the receiver reports the act done, then closes and deletes. This is a write-side change and waits for the owner. The check: a case in `skills/waiting-page/test_page_grant.py` or a SKILL.md fixture shows an item routed to a receiver still reads `counted` until the receiver's done report.
