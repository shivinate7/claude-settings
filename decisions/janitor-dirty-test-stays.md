# The janitor's dirty test stays as it is

## The question

Should the janitor's dirty test ignore untracked tool junk, so that more dirty worktrees are reaped?

## The ruling

Owner word, 2026-10-13 15:56 CDT: option A.

- Skip the junk-pattern change. The janitor's dirty test stays as it is.
- Re-measure `q_max` after the lane `worktree-hook-paths` merges.
- Reaping dirty trees stays closed. The restore-point rule (purge-keeps-younger-restore-ref) does not reopen it.

## Why

- This clone shows 1 dirty tree of 108. That tree is live work.
- Most `q_max` leftovers come from false refusals in the `q_max` worktree-remove hook, not from dirt.
- Preview on 2026-10-13, no deletes: git lists 214 linked worktrees, and 156 sit in `q_max`. The preview would reap 51 trees.
- The dirty test counts 17 dirty trees. None is dirty only by line endings or ignored files. Line-ending noise does not cause the false dirty. Untracked tool junk may.

## Open

- Unmeasured: the `q_max` count after the lane `worktree-hook-paths` merges.

Kind: process
Home: janitor/sweep.py
