# Blame has no route after a lint cancel

**What.** A red lint cancels the batch run, and a cancelled run concludes `cancelled`. `merge --batch-build --blame` refuses a run that did not conclude `failure`, so no blame is stored and `merge --batch-drop` refuses. Before step lane-lint-once-fail-fast, a lint FAIL at `--ready` stored the blame itself.

**Where.** `merge/merge.py`, the `--blame` run check; `.github/workflows/checks.yml`, job `cancel-on-red-lint`.

**Decision.** `lanes-run-no-full-ci-job` (lint first, a red lint cancels the run) and `batch-freeze-lane-set` (a drop needs a stored blame). The owner picks between accepting a cancelled run whose cancel job named lint red, and dropping the cancel step.

**Retire.** The owner's pick lands in both decisions, and `merge/test_merge.py` holds a case that a lane red in the lint job can be dropped.
