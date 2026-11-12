# The branch sweep deletes the `stable` branch

**What.** The sweep's `PROTECTED` list holds `main`, `master` and `roadmap`, not `stable`. The plan moves a `stable` branch with green main, so its tip sits on main's history, and the sweep deletes any branch whose last commit is on main. The sweep runs on every push to main, so each main push deletes `stable`. Child CI and sessions install from that branch. Claude is likely to hit this in normal work for that reason. Whether the next green move recreates a deleted `stable` is unmeasured.

**Where.** `actions/branch-sweep/sweep.py`, `PROTECTED` and the docstring list of names never deleted. The sweep runs from `.github/workflows/branch-sweep.yml` on each push to main. The plan is R42 part 2 in `docs/plans/restart-plan.md`, which names the `stable` branch.

**Decision.** `cloud-branch-delete`, how cloud sessions delete branches (ruling g, owner, 15:19 CST Nov 11, under R45). The workflow deletes what the Oct 30 grant allows: a branch whose last commit is on main or on an archive branch.

**Retire.** Closed when a case in `lint/test_branch_sweep.py` shows a merged branch named `stable` is kept. The case must fail on the current `PROTECTED` before the fix. The fix adds `stable` to `PROTECTED` and to the docstring list.
