# A fork's step grants read main's record branch

**What.** In a fork worktree, the Opus step-grant lookup reads `origin/roadmap`, main's record branch. It does not read the fork's own record branch, named by the `record-branch` key. A fork lane's override check can therefore read the wrong steps. Likely risk in normal work. Unmeasured.

**Where.** `hooks/override.py`, `STEP_REF` (`refs/remotes/origin/roadmap`) and `STEP_DIR`, both read in `_take_step`.

**Decision.** `session-tiers` (a fork's own page and record branch: a fork names its record branch in the `record-branch` key).

**Retire.** `_take_step` reads the record branch that `lint/layout.py` `record_branch()` gives for the worktree, not `STEP_REF`. The check: a test runs `_take_step` in a fork worktree and finds the grant on the fork's record branch, not on `origin/roadmap`.
