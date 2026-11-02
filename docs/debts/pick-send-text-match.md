# Pick send must match its text exactly

**What.** The Stop pick check matches a send to a pick by the item id, or by the first 60 characters of the pick's first line. It does no markup normalization. A send that strips `**` or rewords the line does not clear the pick, so the check blocks once. The block names the item id. One resend that carries it clears the block.

**Where.** `lint/report_guard.py`, function `carries`.

**Decision.** questions-go-to-owner (questions go to the owner), section "Chat first, then the page".

**Retire.** `carries` strips Markdown emphasis and quote marks before it matches. The check: a red-then-green case in the guard tests, for a pick whose first line is wrapped in `**`.
