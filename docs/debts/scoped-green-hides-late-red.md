# A late red that a newer scoped green hides

- **What.** A full push run that was unfinished when a newer scoped run started, and that the scoped run passed over, can go red later from a cause with no diff (a flake, a time-pinned test, an unmapped file). The newer scoped run is green and the newest run, so main reads green and `stable` has moved. Only the daily run catches it.
- **Where.** `actions/push-skip/push-skip.py`, `proven_base` (the walk passes over an unfinished run). `merge/merge.py:1954-1957` (the red-main read takes the newest run per group). `actions/ci-alarm/alarm.sh` and `actions/stable-mover/run.sh` (both judge the newest run).
- **Decision.** `push-skip-on-proven-tree` (a push skips on a proven tree).
- **Retire.** A separate decision either makes the red-main read, the alarm and the `stable` mover require the passed-over run's red job to have gone green since, or stops the walk at an unfinished run again. The closing check is `merge/test_merge.py`.
