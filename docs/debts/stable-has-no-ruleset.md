# Stable has no ruleset

**What.** `stable` has no ruleset, so nothing blocks a delete or a force-push of it. Sessions install from it (plan R42 part 2). Main has a ruleset that blocks both (ruling r, the owner's Nov 11 ruling). `protect.py` sets that ruleset on a named branch (plan R45). Nothing in the repo names `stable` in a `protect.py` call.

**Where.** `skills/project-ops/scripts/protect.py`: `--branch` names the branch, default `main`. The `stable` branch has no protection at all (not read in this change).

**Decision.** `none`. Related: `main-branch-protection` (ruling r, the ruleset that blocks delete and force-push of main only).

**Retire.** Close after the live act: `protect.py --repo <owner>/<name> --branch stable --confirm`, then read the ruleset back. Runnable: `skills/project-ops/tests/test_scaffold.py` (class `Protect`) asserts the payload, deletion and force-push blocked, on main only. A `stable` case is still to add. Land before act 2.
