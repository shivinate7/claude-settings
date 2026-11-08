# A rare "already red" form on the base passes the check

**What.** The pre-existing check reads "already red/failing" only with a base word it knows ("on main", "against main", "main is", "main branch", "main already", "before this change"). These pass with no run named: "Main's already red.", "The test is already failing for main.", "origin/main shows it already failing." A lane can ship its own red this way, and the batch or main then goes red.

**Where.** `lint/report_guard.py`, `BASE_WORD_RE` and `ALREADY_RE`, read in `_claims_pre_existing`. Rule `pre-existing-needs-main-run` shows the refusal for the forms it does read.

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on main (the Known limit).

**Retire.** Read "main's", "for main" and "origin/<branch> shows" as base words. Closed when a red case in `lint/test_report_guard.py` refuses each form above with no run named, and the green cases still pass.

Fix: step:clause-parser-claims
