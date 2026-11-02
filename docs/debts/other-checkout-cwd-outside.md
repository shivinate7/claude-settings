# other-checkout passes a write when the cwd is in no checkout

**What.** `other_checkout_hit` returns `""` when the call's `cwd` is in no checkout of the clone. After a persisted `cd` into a scratchpad folder that sits outside any linked checkout, a write into the primary checkout passes.

**Where.** `hooks/guard.py`, `other_checkout_hit`, the `if not own: return ""` line.

**Decision.** `an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop (the `other-checkout` section).

**Retire.** Add a case in `worktree_home_cross_checkout_case` with `cwd=<scratchpad>` and a write whose target lands in the primary. The call is refused, and the case goes red on the old guard.
