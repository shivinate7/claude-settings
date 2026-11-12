# The hand-off verb list misses natural capability forms

**What.** A capability line in these words passes with no cite: "do not have access", "no permission", "not able to", "only the owner can", "cant", "can not".

**Where.** `lint/report_guard.py`, CAPABILITY_RE (:1280-1283), read by `hand_off_problem`.

**Decision.** `claims-carry-backing` (the claim-backing record, its part (v) hand-off check).

**Retire.** A test feeds each form above as a "Why yours" capability line with no cite, and expects a refusal. The test passes.
