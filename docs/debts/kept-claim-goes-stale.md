# A kept claim goes stale when main takes its number, and the rerun stop names no remedy

- **What.** A merge keeps its claim after a read that could not run. If another PR's merge then puts the same record number on main, the rerun's claim check fails and `do_claim` stops with "the claim was refused. Nothing is on origin". The old claim is on origin, so that text is wrong. The stop also names no remedy. The remedy is to revert the old claim commit, then rerun. Frequency unmeasured.
- **Where.** `merge/merge.py` `own_claim` and `do_claim`. `actions/stamp/stamp.mjs` `branchNumbered`, which fails a claimed number that the base's history holds, and `claim`, which refuses a tree with a problem.
- **Decision.** `standing-merge-grant` (the repo's merge grant). Its clause "Only a proven refusal reverts the claim" keeps the claim this debt is about.
- **Retire.** The rerun stop names the revert of the kept claim commit as its remedy, and it does not say "Nothing is on origin" when a claim is on origin. `merge/test_kept_claim.py` pins both, and fails until the fix lands.
