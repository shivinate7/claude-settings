# A red daily on a shard that left the rollup is not surfaced to the next merge

- **What.** The 13 Windows shard jobs run on the daily schedule and on manual dispatch only. They are not in the `needs` of `all-jobs-passed`. A red daily on one of them is not surfaced to the next merge until the follow-up lane `red-main-reads-back-to-daily` lands. The red-main read in `merge/merge.py` reads only the newest 50 runs, and the rule that blames a red run never blames a schedule run.
- **Where.** `merge/merge.py` (`base_state`) and `actions/ci-alarm/clear_rule.py` (`blames()`). The shard jobs `checks-windows-guard-2` to `-5` and `checks-windows-merge-2` to `-10` in `.github/workflows/checks.yml`.
- **Decision.** `windows-prs-run-marked-tests` (the shards run daily only; owner, 2026-11-24 22:27 CST, the cut lands before this fix). Its gap is named in `push-skip-on-proven-tree` (Risk B and Risk C).
- **Retire.** The lane `red-main-reads-back-to-daily` lands: the red-main read looks back to the newest daily by its own query. A case in `merge/test_merge.py` (class `RedMainBrake`) holds a red daily shard and expects the next merge to name it.
- **Reported.** 2026-11-24 23:06 CST (lane `windows-prs-run-marked-tests`).
