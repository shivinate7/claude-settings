# Rule 7 resolves shell variables before it matches a write target

## The ruling

Before rule 7 (frozen-path) matches the target of a shell write, it reads the command left to right and keeps a table of variable assignments:

- POSIX `VAR=value`, also after `(`, `{`, `then`, `do`, `else`, and after `export`, `declare`, `typeset`, `readonly` or `local`, several names at once.
- PowerShell `$VAR = value`.
- The last assignment wins. `unset` clears. A value it cannot resolve clears the older one.
- `$HOME` reads as `~`, also where the guard runs with no `HOME` set.

Each `$VAR` or `${VAR}` reads as its value at that point. Inside single quotes nothing expands. A write whose resolved target is frozen is refused. A variable with no known value at its use stays unresolved, and rule 7 allows it.

Why this option: it refuses only when the resolved target is frozen, so ordinary commands that write to `$OUT` stay allowed. Refusing any write to an unresolved variable when a frozen path is mentioned was rejected. It fires on `D=<frozen>; ...; cat "$D" > "$OUT"`, a read that writes nowhere frozen, and a guard that cries wolf is spent.

## Limits

Rule 7 is a fence, not a wall. `settings.json` deny rules still refuse a direct Write or Edit. It still misses:

- a value built by `$(...)`, backticks, `read`, `${D:-x}`, a loop variable or `eval`;
- a write by an interpreter (`python -c`);
- a variable set in another tool call;
- a value built from another env var, as `D="$CLAUDE_CONFIG_DIR/state/x"`, which the owner chose to leave open (2026-10-07);
- a PowerShell `$env:D` assignment.

Known false alarm, accepted by the owner: the token match is loose. Text like `echo D=<frozen>`, a commit message, a URL or a heredoc body counts as an assignment, and a later write to `"$D"` is then refused. A `cp` with a frozen source is refused, as before (`MUTATING_COMMAND` over-blocks `cp` and `mv` on purpose).

Unmeasured: how often a session reaches a frozen path by the open shapes.

Kind: process
Home: hooks/guard.py
