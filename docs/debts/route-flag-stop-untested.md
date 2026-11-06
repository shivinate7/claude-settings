# No test feeds a refusal row with route_flag through Stop

**What.** No test feeds a refusal row that carries `route_flag` through the Stop read, so that path has no test.

**Where.** `lint/report_guard.py`, `refusal_route_flags` (:1194-1215) and its Stop call (:1537-1544), on the `prose-truth-falsifier-r3` branch.

**Decision.** `claims-carry-backing` (the claim-backing record, its falsifiers section).

**Retire.** A test writes a refusal row with `route_flag` and runs the Stop read, and checks that the flag is read. When that case is in the suite and green, the finding is closed.
