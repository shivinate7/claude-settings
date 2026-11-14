# Progress check: the subject reset at a block start has no test

**What.** Deleting the subject reset in `progress_claim_problem` keeps all progress tests green. The Done/Next test passes through the owner-wait exemption alone, so no test pins the reset.

**Where.** `lint/report_guard.py`, `_progress_claim_lines` (the subject carried to a block start); `lint/test_report_guard_progress.py`.

**Decision.** progress-claims-cite-live-read (a progress claim cites a named live read).

**Retire.** Add a case with a non-owner wait in the Next block after a Done PR (for example `waiting on CI for the deploy`). The case fails once the reset is removed. Proof: `lint/test_report_guard_progress.py`.
