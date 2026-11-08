# A pre-existing claim in other words passes the check

**What.** The pre-existing check reads the word "pre-existing", "already red" and a failure on a ref "too". A claim in other words passes with no run named; none of the forms below is read. Forms: "was red before this change", "not from this change", "The same lint failure is on main." A lane can ship its own red this way, and the batch or main then goes red.

**Where.** `lint/report_guard.py`, `pre_existing_problem` and `_claims_pre_existing`. Rule `pre-existing-needs-main-run` shows the refusal for the forms it does read.

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on main (the Known limit).

**Retire.** Read a failure said to predate this change, in other words, as the claim and ask for the run on the base branch's tip. Closed when a red case in `lint/test_report_guard.py` refuses each form above with no run named, and the green cases still pass.

Fix: step:clause-parser-claims
