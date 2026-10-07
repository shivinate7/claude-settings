# Rule 7 resolves shell variables before it matches a write target

## The rule now

Before rule 7 (frozen-path) matches the target of a shell write, it reads the
command left to right and keeps a table of variable assignments:

- POSIX `VAR=value`, also after `(`, `{`, `then`, `do`, `else`, and after
  `export`, `declare`, `typeset`, `readonly` or `local`, several names at once.
- PowerShell `$VAR = value`.
- The last assignment wins. `unset` clears. A value it cannot resolve clears the
  older one.
- `$HOME` reads as `~`, also where the guard runs with no `HOME` set.

Each `$VAR` or `${VAR}` reads as its value at that point in the command. Inside
single quotes nothing expands. A write whose resolved target is frozen is
refused.

A variable with no known value at its use stays unresolved. Rule 7 allows it.

## The incident

2026-10-07T16:19Z, session 56ca874f in q_max. This command passed the guard:

    S="<scratchpad>"; D=~/.claude/state/handoff/<id>.handoff.md; cp "$S/handoff.md" "$D"

`state` is frozen. The static parse saw only `"$D"`. A direct Write to the same
path was denied by settings.json. The owner deleted the leftover file.

## Options weighed

- **Resolve assignments in the command (chosen).** Refuses only when the
  resolved target is frozen. Ordinary commands that write to `$OUT` stay allowed.
- **Refuse any write to an unresolved variable when a frozen path is mentioned.**
  Rejected: it fires on `D=<frozen>; ...; cat "$D" > "$OUT"`, a read that
  writes nowhere frozen. A guard that cries wolf is spent.

## What stays open

Rule 7 is a fence, not a wall. It still misses some values:

- a value built by `$(...)`, backticks, `read`, `${D:-x}`, a loop variable or
  `eval`;
- a write by an interpreter (`python -c`);
- a variable set in another tool call;
- a value built from another env var, as `D="$CLAUDE_CONFIG_DIR/state/x"`, which
  the owner chose to leave open on 2026-10-07;
- a PowerShell `$env:D` assignment.

settings.json deny rules still refuse a direct Write or Edit. Unmeasured: how
often a session reaches a frozen path by those shapes.

## Known false alarms

The token match is loose. Text like `echo D=<frozen>`, a commit message, a URL,
or a heredoc body counts as an assignment. A later write to `"$D"` is then
refused.

Measured 2026-10-07 over 105,260 past Bash and PowerShell commands: the change
refused 2 more commands than main and allowed none that main refused. One was
the incident. One was a false alarm, a script that tests the guard and holds
`D=<frozen>` text in a here-string. The owner accepted that rate.

A `cp` with a frozen source is refused. The literal form was refused before this
change too: `MUTATING_COMMAND` over-blocks `cp` and `mv` on purpose.
