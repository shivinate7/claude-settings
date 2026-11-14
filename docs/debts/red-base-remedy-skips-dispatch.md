# The red-main refusal names the re-run, not the dispatch that clears main

**What.** When passed-over push runs sit above a failed run, the red-main refusal names the wrong remedy. Its headline says the latest completed run is red. A revert merged under `--base-red-ok` usually has its push run skipped on the proven tree. The check passes that run over, so main stays red. The refusal then names `gh run rerun <id> --failed`, which re-tests the old broken commit. If the re-run is red again, the refusal names a revert PR instead. The revert may already be merged, and its skipped run is passed over, so the verdict stays red. No refusal names the dispatch that clears it, `gh workflow run checks.yml --ref main`, for this case. The all-empty refusal names only `--base-red-ok`. The cost is a wrong remedy only, because `--base-red-ok "<reason>"` still lifts the refusal.

**Where.** `merge/merge.py`, `Host.base_state` (writes the detail) and `red_base` (builds the remedy from it), with the cue constants `RERUN_REMEDY`, `FIRST_RED_RERUN` and `BREAKING_MERGE`.

**Decision.** `no-merge-onto-red-main` (no batch merges onto a red main, the red-main check). The owner's ruling `own-812-a-judge-suite-runs` (owner page item 812 a, 2026-11-13 23:38 CST) sets which runs the check judges. `push-skip-on-proven-tree` (a push skips its checks when a passing PR run covered its tree) names the dispatch only for the UNKNOWN steady state.

**Retire.** The refusal names `gh workflow run checks.yml --ref main` when passed-over runs sit above the verdict, and when the push group is all-empty. Cases in `merge/test_merge.py`, class `RedMainBrake`, assert both.

Open question for the owner: do merges resume when the revert merges (target ruling `own-745-b-resume-at-revert`, 2026-11-13 13:20 CST), or wait for a full dispatch run, as the live check does?
