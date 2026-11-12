# The role refusal lets an owner-started lane think it may merge anywhere

**What.** The merge-role refusal prints "A lane the owner started merges its own PR" with no scope. The lone-lane grant holds only in claude-settings. So a lane the owner started in another repo reads that line as leave to merge, and may retry. The same text prints on each such refusal. Found in review round 3 of pull request #2815 (the lone-lane route).

**Where.** `hooks/guard_merge.py`, `ROLE_REASON`, and `hooks/shared_names.py`, `OWNER_LANE_ASK`, the sentence both print. The refusal is the merge-role proof (guard rule `merge-role-proof`).

**Decision.** `standing-merge-grant` (the merge grant that names the lone-lane route), its Scope sub-bullet: a lone lane's scope is claude-settings only.

**Retire.** Add a case to the merge section of `tests/guard/s13406-merge.py`, which `hooks/test_guard.py` runs. The case is a lone-lane record in another repo that runs `merge --role batch-runner`. It expects a refusal whose text does not claim that the lane may merge its own PR without a scope. It is red while the text is unscoped.
