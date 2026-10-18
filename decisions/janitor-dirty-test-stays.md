# The janitor's dirty test stays as it is

## The ruling

Owner word, 2026-10-13 15:56 CDT: option A.

- The janitor's dirty test stays as it is. No junk-pattern change.
- Re-measure `q_max` after the lane `worktree-hook-paths` merges. Unmeasured until then.
- Reaping dirty trees stays closed. The restore-point rule does not reopen it.

Why: the dirty trees in this clone are live work. Most `q_max` leftovers come from false refusals in its worktree-remove hook, not from dirt.

Kind: process
Home: janitor/sweep.py
