# A coordinator's REST merge through gh api is not read

**What.** Guard rule `coordinator-scope` refuses `gh pr merge`, `merge --confirm` and the host's merge tools. `gh api repos/o/r/pulls/N/merge -X PUT` merges the same pull request and passes for a coordinator.

**Where.** `hooks/guard_merge.py` (`merge_call_of`) reads only the `pr merge` words of `gh`. `hooks/guard.py` (`coordinator_act_hit`) calls it.

**Decision.** `session-tiers`, tiers and their guards (section "Spawns and merges"). Risk kind: unmeasured. No coordinator has been seen to write this form.

**Retire.** Read `gh api` with a path that ends in `/pulls/<N>/merge` and a write method, and refuse it for a coordinator. Add cases that go red on the old guard for `-X PUT` and `--method PUT`, and a pass case for a `GET` of the same path.
