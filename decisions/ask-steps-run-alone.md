# A step that needs the owner's answer runs alone

## Ruling

Owner ruling, 2026-10-14. An agent never chains a step that needs the owner's answer onto other
steps in one command. The guard rule `ask-alone` denies such a command. The same step alone
still asks. A move into a folder first (`cd X && <step>`, `Set-Location`, `export ...;`) is a
chain too, and the guard denies it.

The steps that ask today: a worktree prune, a worktree discard, a forced push, and a shell write
to the model-cap settings. The deny names the kind of step, never the command text.

- Owner, 2026-10-14 22:25 CDT: an interpreter heredoc (python, node, perl, ruby) counts as one step
  and asks once. A chain around it still counts. A shell heredoc still counts each line.

Kind: process
Home: hooks/guard.py

## Why

An agent chained `git worktree prune` onto a routine command. The whole command then waited on
the owner, for a step the owner would have skipped. A lone ask shows the owner one plain step.
