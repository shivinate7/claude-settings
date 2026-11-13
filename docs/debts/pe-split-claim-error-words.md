# A split pre-existing claim after an error word passes

**What.** The claim carried from the sentence before reads only fail, red and broken as that sentence's failure. The check's own failure list also holds error, regress, flake and break. "The build reported errors. It is pre-existing." and "There are 3 errors. They are pre-existing." pass. "The red banner shows. It is pre-existing." is refused, since red can be a colour.

**Where.** `lint/report_guard.py`, `PRIOR_FAIL_RE` and `_open_failure`, read by `_claims_pre_existing`.

**Decision.** `pre-existing-needs-main-run`, a pre-existing claim names a run on the base branch.

**Retire.** Closed when red cases in `lint/test_report_guard.py` refuse the two error-word lines, allow the red-banner line, and the green cases still pass.
