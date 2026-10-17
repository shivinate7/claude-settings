# A step that needs the owner's answer runs alone

## Ruling

An agent never chains a step that needs the owner's answer onto other steps in one command (owner, 2026-10-14). The guard rule `ask-alone` denies such a command. The same step alone still asks.

Owner, 2026-10-15 12:00 CDT: two harmless additions are no extra step, and the command asks once, as the step alone does. Only these named forms count:

- Before the step: a leading `cd X &&`, `Set-Location X;` or `export NAME=value &&`.
- After the step: `| tail -N`, `| head -N`, `| Out-Null`, `&& echo <text>`, or in PowerShell `; Write-Host <text>`.

Every other form stays a step: `; echo`, `| cat`, `; Write-Output`, `| tee`, `| sh`, `||`, and the aliases `sl`, `chdir` and `Push-Location`. So does `cd -`. A segment with a redirect, a substitution, a `&`, or an escaped quote (`\"`, `\'`) is a step too. A reset after `Set-Location` is judged in the target folder, as after `cd`.

Owner, 2026-10-14 22:25 CDT: an inline interpreter script (a python, node, perl or ruby heredoc) is one step, and it asks once. A chain around it still counts. A shell body (bash, sh, a heredoc piped to a shell) counts each line, as does a body with no closing line. A deny in the body still wins. Owner, 22:27: no safety hole that main lacks.

The steps that ask: a worktree prune, a worktree discard, a forced push, and a shell write to the model-cap settings. The deny names the kind of step, never the command text.

Why: a chained `git worktree prune` made the whole command wait on the owner for a step the owner would have skipped. A lone ask shows one plain step.

Kind: process
Home: hooks/guard.py

## Holes, named

Debts: `split-reader-misses-cd-forms` (`cd ~-`, `Set-Location -` and `Set-Location +` count as harmless leads with an unknown target, so a shared-tree deny can become an ask). `ask-alone-tail-args-unchecked` (tail arguments are unchecked, so the lane turns a main deny into an ask). `ask-alone-echo-amp-overdeny` (`<`, `>` or `&` in quoted text counts as a step). `ask-alone-empty-segment-denies` (a trailing newline or `;` after a harmless tail stops the tail count). `ask-alone-ps-backslash-denies` (a quoted PowerShell path ending in a backslash counts as a step). `ask-alone-tail-test-gap` (no row puts a quoted `#`, `/*` or lone apostrophe in a harmless tail). `ask-alone-sl-chdir-denies` (`sl`, `chdir` and `Push-Location` are not named leads, pending the owner's choice).
