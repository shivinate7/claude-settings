# "Yet that" before a bare noun refuses a hedged claim

**What.** "That" before a bare noun reads as a subject, so "yet" ends the clause and the negator before it misses the claim. "I can't say yet that failures are pre-existing." and "I have not proven yet that main also fails on 32b5f8b8e." refuse. 7 of 14 variants refuse. This is a false alarm in normal prose.

**Where.** `lint/_clause.py`, `_opens_with_subject` (line 288), read by `lead_opens_clause` for "yet".

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on the base branch, and a negated claim is exempt.

**Retire.** Closed when red cases in `lint/test_report_guard.py` exempt both sentences above, and the green cases still pass.
