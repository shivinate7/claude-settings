# The first pin move leaves the pin path absent for a moment

- **What.** The first move from a plain `<clone>-live` directory renames that directory to `<clone>-live-<commit>`. Then the link takes the name. Between the two renames `<clone>-live` is absent for milliseconds. Links in `~/.claude` that run through it dangle for that time. The header of `merge/install_from_main.sh` says the guard's load retry covers it. No check proves that, and other hooks have no retry.
- **Where.** The `git worktree move` step in `move_pin` in `merge/install_from_main.sh`, before `point_at`.
- **Decision.** `merge-reinstalls-from-main` (the first move; this is its named hole).
- **Retire.** A first move that never leaves `<clone>-live` absent. Check: a reader loop around a first move from a plain directory finds no absent path.
