# Stable has no ruleset

**What.** `stable` has no ruleset, so nothing blocks a delete or a force-push of it. Sessions install from it (plan R42 part 2). Main has a ruleset that blocks both (ruling r, the owner's Nov 11 ruling). The plan says `protect.py`, which sets classic protection today, will set the ruleset (R45).

**Where.** `skills/project-ops/scripts/protect.py`, which has no ruleset path. The `stable` branch has no protection at all.

**Decision.** `none`. Related: `main-branch-protection` (ruling r, the ruleset that blocks delete and force-push of main only).

**Retire.** `protect.py` sets a ruleset on `stable` with the deletion and non-fast-forward rules. Check: `skills/project-ops/tests/test_protect.py` asserts that payload. Red before `protect.py` can build it, green after. Depends on act 0 (`protect.py` ruleset support). Land before act 2.
