# No test pins the suites to the lane's own files

**What.** `lane_suites` writes the base's selector over the lane's, asks it which suites to run, then `_restore_scripts` puts the lane's files back before any suite runs. No case in `merge/test_lane_lint.py` fails if that restore is dropped. Then the suites run with the base's copy of the selector in place. For the claude_settings profile the selector is `hooks/mutate_guard.py`, product code with its own tests (`hooks/test_mutate_ci.py`, the `--tests-for` cases). A dropped restore would pass a broken lane selector unseen. Claude hits this in any lane that changes the selector.

**Where.** `hooks/mutate_shared.py`: `_restore_scripts`, and the `finally` that calls it in `lane_suites`. `merge/test_lane_lint.py`: the `merge.laneTests` cases. None of them pins the restore.

**Decision.** `lanes-run-no-full-ci-job` (a lane runs only the suites its change touches, and its selector set paragraph).

**Retire.** A case in `merge/test_lane_lint.py` where the lane changes the selector, the base lists a suite that fails while the base's selector is in place, and the lane's head passes. Check: that case is red when `_restore_scripts` is removed from `lane_suites`, and green on the current code.
