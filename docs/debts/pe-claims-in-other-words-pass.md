# A pre-existing claim in other words passes the check

**What.** The pre-existing check reads three word forms. A claim in other words passes with no run named. Forms: "was red before this change", "not from this change", "The same lint failure is on main." A lane can ship its own red this way, and the batch or main then goes red.

**Where.** `lint/report_guard.py`, `pre_existing_problem` and `_claims_pre_existing`. Rule `pre-existing-needs-main-run` shows the refusal for the forms it does read.

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on main (the Known limit).

**Retire.** Read a failure said to predate this change, in other words, as the claim and ask for the run on the base branch. The hash must be on the base and no older than the merge base (step `base-hash-on-base`). Closed when a red case in `lint/test_report_guard.py` refuses each form above with no run named, and the green cases still pass.
