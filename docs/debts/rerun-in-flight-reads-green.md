# A re-run in flight hides a red main run

- **What.** A re-run puts the red run back in progress, and `Host.base_state` judges only completed runs. While the re-run goes, the group reads its older green run, or no run, as green. So `gh run rerun <id> --failed` followed at once by `merge <pr> --confirm` passes the red-main check onto a main that may still be red. The refusal now names that re-run, so Claude is likely to re-run and retry in one turn.
- **Where.** `merge/merge.py`, `Host.base_state` (the `status == "completed"` filter).
- **Decision.** no-merge-onto-red-main (no batch merges onto a red main).
- **Retire.** A run whose newest attempt is in progress on the base reads as pending or UNKNOWN, never green; a red test in `merge/test_merge.py` class `RedMainBrake` shows it. Delete this file in that PR.
