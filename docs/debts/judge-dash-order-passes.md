# A past-ruling judge's own words reach a refusal

**What.** A past-ruling judge's own words reach a refusal on two paths, and no wording check runs on either. `session_wording`, which flags an order after an em dash or with no mark, has no production caller.

1. A reply that is not JSON. `parse_verdict` puts its first 120 characters into the error, and the Unvetted refusal carries that error.
2. An item-8 answer that names no listed id. `call_judge` refuses with its reason as written, under the call's rule, not the past-ruling rule.

**Where.** `hooks/decision_watch.py` `parse_verdict`, the 120-character cut. Path 1: `cannot_run` in `lint/report_guard.py`, called by `past_ruling_problem` on the Stop path; and `unvetted` in `hooks/call_judge.py`, on the chat and page path. Path 2: `main` in `hooks/call_judge.py`, where `past` is False and `refuse` gets the reason.

**Decision.** `guard-remedy-not-to-owner` (the past-ruling guard).

**Retire.** Retired when a test pins that neither path carries the judge's words to a refusal.
