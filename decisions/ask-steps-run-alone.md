# A step that needs the owner's answer runs alone

## Ruling

Owner ruling, 2026-10-14. An agent never chains a step that needs the owner's answer onto other
steps in one command. The guard rule `ask-alone` denies such a command. The same step alone
still asks.

Owner ruling, 2026-10-15 (12:00 CDT). Two harmless additions are no extra step. The command asks
once, as the step alone does. Only these named forms count:

- Before the step: a leading `cd X &&`, `Set-Location X;` or `export NAME=value &&`.
- After the step: `| tail -N`, `| head -N`, `| Out-Null`, `&& echo <text>`, or in PowerShell
  `; Write-Host <text>`.

Every other form stays a step: `; echo`, `| cat`, `; Write-Output`, `| tee`, `| sh`, `||`, the
aliases `sl`, `chdir` and `Push-Location`, and any segment with a redirect, a substitution or a
`&`. A reset after `Set-Location` is judged in the target folder, as after `cd`.

The steps that ask today: a worktree prune, a worktree discard, a forced push, and a shell write
to the model-cap settings. The deny names the kind of step, never the command text.

Kind: process
Home: hooks/guard.py

## Why

An agent chained `git worktree prune` onto a routine command. The whole command then waited on
the owner, for a step the owner would have skipped. A lone ask shows the owner one plain step.
