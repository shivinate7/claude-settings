# A fork's step grants read main's record branch

**What.** In a fork, the Opus step-grant lookup reads the `record-branch` key from `origin/main`'s `.claude/layout-extras.json`. A fork's key sits on a branch that never reaches main, so the lookup falls back to `origin/roadmap`, main's record branch. No step there names the fork's lane unless someone writes one on purpose, so the check fails closed: the harm is a fork's Opus grant that never lifts. Only a checkout with no `origin/main` reads its own working copy of the extras file. There a lane could name a branch it pushed and lift its own grant, which main never did, but only by a deliberate edit, not a mistake. Likely risk in normal work in a fork. Unmeasured.

**Where.** `hooks/override.py`, `_step_ref`, read in `_take_step`.

**Decision.** `session-tiers` (a fork's own page and record branch: a fork names its record branch in the `record-branch` key).

**Retire.** `_step_ref` finds the fork's record branch from a source the lane cannot write, with or without `origin/main`. The check, in `hooks/test_guard.py`: a fork with `origin/main` present finds the grant on its own record branch. A lane-written extras file lifts nothing, both with `origin/main` (`gs_pushed_record_check`) and without it. Closing this flips the own-branch case in `gs_fork_check` to deny.
