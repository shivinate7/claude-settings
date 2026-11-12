# The red-main walk has no test for head-group order

- **What.** No test pins that `base_state` walks the push and dispatch group (the head group) first. A mutant that sorts runs by age alone keeps all 105 `RedMainBrake` cases green. When a first-red nightly run is newer than a first-red push run, the gap matters. The refusal then names the nightly's re-run id, not the push run's. Harm: one wasted re-run, no wrong revert. Likelihood in normal work: low. A nightly red over a push red is the case PR #2889 (blame each red group's breaking run) targets.
- **Where.** `merge/merge.py`, `base_state` (the sort that puts the head group first). `merge/test_merge.py`, class `RedMainBrake`.
- **Decision.** `no-merge-onto-red-main` (no batch merges onto a red main). It is the closest decision. It does not name this gap.
- **Retire.** A new case in `merge/test_merge.py`, class `RedMainBrake`. It fails under an age-only sort and passes on the current code. It sets a first-red nightly run newer than a first-red push run. It asserts that the refusal names the push run's re-run id.
