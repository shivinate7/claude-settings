# Red main does not run the replaced push run

**What.** The owner ruling (12:38 CST Nov 25 2026, option a) has two halves. The first is built: a push run on main that a newer push replaced is skipped. The second is not: when the newest main push run fails, nothing runs the run before it, the replaced run, to find the last green point. Any red main under the shared group hits this. A session runs the replaced run by hand.

**Where.** `merge/merge.py`. `replaced_note()` names the replaced commit and prints no `gh run rerun <id>`. The red-main walk that prints it (`base_state`, `main_run_verdict`) starts no run. The replaced runs come from `replaced_in_span` in `actions/ci-alarm/clear_rule.py`.

**Decision.** `test-strategy-reset`, the replaced-run half of the owner ruling (12:38 CST Nov 25 2026, option a).

**Retire.** When the newest main push run fails, the merge tool runs the replaced run to find the last green point. `merge/test_merge.py` gets a red case for it: a red newest push run, a replaced run above the green point, and a verdict that names the green point. The fix PR deletes this debt file.
