# c46 lane 1: refuse a hand-made lane worktree

Cloud build thread brief. Build advisor, Oct 26, against claude-settings main 3f71d6b. Lane 2 is the
pilot, PR #577; this is lane 1 only. Full step text: briefs/c46-lanes-stay-in-their-trees.md.

## Incident and ruling

Oct 20: an orchestrator whose `isolation: 'worktree'` failed made lane trees by hand and spawned
agents without isolation; two agents wrote into the main clone. Owner ruling, Oct 21 (debt
agents-write-main-clone): block the workaround fully, and record which layer refused isolation.

## Task

1. Block: hooks/guard.py refuses the workaround, so a writing lane starts only through the tool's
   own isolation. Find the cheapest reliable predicate (an Agent or Task call with no isolation
   whose brief names a worktree path outside .claude/worktrees/, or `git worktree add` into a
   scratchpad from an orchestrator). Read the act, not a guess from location (decision
   predicate-is-the-act). Add rows to hooks/test_guard.py and mutants to hooks/mutate_guard.py.
2. Diagnose: when isolation is refused, the guard's existing refusal line names which layer
   refused (harness or guard) and its message.
3. Retire the debt per its Retire line.

## Failure classes

- False alarm: a read-only Explore spawn with no isolation, or a brief that only mentions a
  worktree path, must pass. A guard that cries wolf is spent.
- Bypass: other spellings of the same act (relative paths, Windows paths, PowerShell). Only forms
  Claude could write by mistake count (guard-guards-mistakes-only).
- Cloud note: claude-settings hooks are not installed here, so prove it with the guard's own test
  suite and mutation harness, not a live hook.

## Roles

Orchestrate: test-author, builder, fresh reviewer (it changes a guard). Base: main. PR stops at green.

## Report (25 lines max)

Done, Deviations, Input Needed, Next. The predicate chosen, red then green rows, mutants killed.
