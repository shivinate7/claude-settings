# A fork's step grants read main's record branch

**What.** In a fork, the Opus step-grant lookup reads the `record-branch` key from `origin/main`'s `.claude/layout-extras.json`. A fork's key sits on a branch that never reaches main, so the lookup falls back to `origin/roadmap`, main's record branch. A fork lane's override check can therefore read the wrong steps. Reading the key from the lane's own working copy is not the cure: a lane could then name a branch it pushed and grant itself Opus. Likely risk in normal work in a fork. Unmeasured.

**Where.** `hooks/override.py`, `_step_ref`, read in `_take_step`.

**Decision.** `session-tiers` (a fork's own page and record branch: a fork names its record branch in the `record-branch` key).

**Retire.** `_step_ref` finds the fork's record branch from a source the lane cannot write, and a fork's grant is found there. The check: a test with `origin/main` present runs `_take_step` in a fork and finds the grant on the fork's record branch, while a lane-written extras file still lifts nothing (`gs_pushed_record_check`).
