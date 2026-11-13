# Two-worktrees guard misses an unexpanded target

- **What.** A `cd` or `git -C` target the guard cannot expand, such as `"$(git rev-parse --show-toplevel)"`, `$REPO` or `"$(pwd)"`, names a folder that does not exist. The worktree list read then returns no worktrees, so `cd "$(git rev-parse --show-toplevel)" && git checkout -B x` passes while another worktree holds `x`.
- **Where.** `hooks/guard.py` rule 1b2 and `_absolute` in `hooks/guard_core.py`.
- **Decision.** `two-worktrees-one-branch` (two worktrees never hold one branch).
- **Retire.** A target that holds `$`, a backtick or `(` refuses or falls back to the cwd, with a red case for each idiom above.
