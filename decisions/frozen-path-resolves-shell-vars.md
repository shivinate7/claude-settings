# Rule 7 resolves simple shell variables before it matches a write target

## The rule now

Before rule 7 (frozen-path) matches the target of a shell write, it resolves each
`VAR=value` and `export VAR=value` set earlier in the same command. Then `$VAR`,
`${VAR}` and their quoted forms read as the value. A write to the value under a
frozen directory is refused.

A variable that the command does not assign stays unresolved. Rule 7 allows it.

## The incident

2026-10-07T16:19Z, session 56ca874f in q_max. This command passed the guard:

    S="<scratchpad>"; D=~/.claude/state/handoff/<id>.handoff.md; cp "$S/handoff.md" "$D"

`state` is frozen. The static parse saw only `"$D"`. A direct Write to the same
path was denied by settings.json. The leftover file is stale: the session now
writes to `~/.claude/handoffs/`.

## Options weighed

- **Resolve simple assignments (chosen).** Refuses only when the resolved target
  is frozen. Ordinary commands that write to `$OUT` stay allowed.
- **Refuse any write to an unresolved variable when a frozen path is mentioned.**
  Rejected: it fires on `D=<frozen>; ...; cp a "$OUT"` and on reads that copy a
  frozen file out. A guard that cries wolf is spent.

## What stays open

Rule 7 is a fence, not a wall. It still misses a value built by command
substitution (`D=$(...)`), by `read`, or by an interpreter (`python -c`).
settings.json deny rules still refuse a direct Write or Edit. Unmeasured: how
often a session reaches a frozen path by those shapes.
