# A pre-existing claim with its ref in a later clause passes the check

**What.** The check carries a failure word from an earlier clause only when the later clause starts with the ref. "The lint fails, and it does on 32b5f8b8e too." and "The test fails, as it does on 32b5f8b8e too." pass. Both should refuse. A claim split across sentences also passes: "One job failed. It is pre-existing." Debt `pe-claims-in-other-words-pass` does not name either form.

**Where.** `lint/report_guard.py`, `_claims_pre_existing`, the carry branch at line 831 (`FAIL_REF_RE.match`).

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on the base branch.

**Retire.** Closed when red cases in `lint/test_report_guard.py` refuse the two "fails ... too" lines and the split claim with no run named, and the green cases still pass.
