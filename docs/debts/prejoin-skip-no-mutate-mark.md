# A pre-join skip can run with no mutation run

**What.** The batch runner's pre-join lint skips the mutation run when a hand-off lint PASS names the live head. That PASS carries the same text from an older merge tool copy, which ran no mutation test. A head handed off before this change lands can therefore skip the run with none ever made for it. CI on the batch head is the only backstop.

**Where.** `hand_off_pass` and `lint_body` in `merge/merge.py`, read by the pre-join branch of `lane_lint`.

**Decision.** lanes-run-no-full-ci-job (a lane runs no full CI job, and the lint runs the mutation test shards on a touched head).

**Retire.** Closed when a hand-off PASS comment records that its lint ran the mutation test, and the pre-join skip requires that mark. A case in `merge/test_lane_lint.py` shows a PASS without the mark no longer skips the run.
