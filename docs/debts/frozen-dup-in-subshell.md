# A descriptor dup in a subshell is judged as a path

**What.** From a frozen working folder (the live pin `<clone>-live`, or `~/.claude/hooks`), the frozen-path rule still refuses `x=$(ls 2>&1)`, `(ls 2>&1)`, a backtick form, and `ls 2>&1&`. In each, the descriptor word is `&1)`, `&1` followed by a backtick, or `&1&`, so the descriptor check in `_shell_write_hit` misses it and the word is judged as a path. Same on main and on this PR.

**Where.** hooks/guard_frozen.py, `_DESCRIPTOR` and `_shell_write_hit`, rule frozen-path.

**Decision.** merge-reinstalls-from-main (ruling 1: no work runs in the pinned checkout).

**Retire.** Strip a trailing `)`, backtick or `&` before the descriptor match. A guard case allows `x=$(ls 2>&1)` from the pin, red before the fix and green after.
