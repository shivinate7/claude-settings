# A pre-existing cause noun passes the check

**What.** The pre-existing check no longer reads a cause noun (issue, problem, bug, defect) as a claim. "The test fails due to a pre-existing issue.", "CI is red, because of a pre-existing issue." and "A pre-existing issue in the parser breaks CI." pass with no run named. A lane can ship its own red this way, and the batch or main then goes red.

**Where.** `lint/report_guard.py`, `pre_existing_problem` and `_claims_pre_existing`. Rule `pre-existing-needs-main-run` shows the refusal for the forms it does read.

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on main (the Known limit). Coordinator ruling 2026-11-08 05:28 CST dropped the reading.

**Retire.** Read a cause noun named as a failure's cause, or as a failure verb's subject, as the claim, and let "Added error handling due to a pre-existing bug." and "The regression test for the pre-existing bug fails on the old code." pass. Closed when a red case in `lint/test_report_guard.py` refuses each cause form above with no run named, and the green cases still pass.

Fix: step:clause-parser-claims
