# A choice phrase exempts the whole hand-off line

**What.** "your call" exempts the whole "Why yours" line, so a false "can't" on that line passes with no cite. Layer (b) covers it.

**Where.** `lint/report_guard.py`, the CHOICE_RE exemption (:1284-1287), read by `hand_off_problem`.

**Decision.** `claims-carry-backing` (the claim-backing record, its part (v) hand-off check).

**Retire.** Layer (b), `hooks/reply_judge.py`, lands and judges the cite on a line that has a choice phrase and a capability verb. A test feeds a "your call" line with a false "can't" and no cite, and expects a refusal.
