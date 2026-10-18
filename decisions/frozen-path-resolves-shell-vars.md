# Rule 7 resolves shell variables before it matches a write target

## The ruling

Before rule 7 (frozen-path) matches the target of a shell write, it reads the command left to right. It keeps a table of variable assignments: POSIX `VAR=value` (also after `export`, `declare`, `typeset`, `readonly` or `local`) and PowerShell `$VAR = value`.

- The last assignment wins. `unset` clears. A value it cannot resolve clears the older one.
- `$HOME` reads as `~`, also where the guard runs with no `HOME` set.

Each `$VAR` or `${VAR}` reads as its value at that point. Inside single quotes nothing expands. A write whose resolved target is frozen is refused. A variable with no known value at its use stays unresolved, and rule 7 allows it.

Why this option: it refuses only when the resolved target is frozen, so ordinary commands that write to `$OUT` stay allowed. Refusing any write to an unresolved variable when a frozen path is mentioned would fire on a read that writes nowhere frozen, and a guard that cries wolf is spent.

Rule 7 is a fence, not a wall. `settings.json` deny rules still refuse a direct Write or Edit. Owner, 2026-10-07: a value built from another env var, as `D="$CLAUDE_CONFIG_DIR/state/x"`, stays open. A `cp` with a frozen source is refused (`MUTATING_COMMAND` over-blocks `cp` and `mv` on purpose).

Kind: process
Home: hooks/guard_frozen.py
