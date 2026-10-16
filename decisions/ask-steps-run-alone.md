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

Every other form stays a step: `; echo`, `| cat`, `; Write-Output`, `| tee`, `| sh`, `||`, and the
aliases `sl`, `chdir` and `Push-Location`. So does `cd -`. A segment with a redirect, a
substitution, a `&`, or an escaped quote (`\"`, `\'`) is a step too. A reset after `Set-Location`
is judged in the target folder, as after `cd`.

An inline interpreter script (a python, node, perl or ruby heredoc) is one step, and it asks once.
A chain around it still counts. A shell body (bash, sh, or a heredoc piped to a shell) counts each
line. A body with no closing line counts each line too. A deny in the body still wins. The rule
adds no safety hole that main lacks.

The steps that ask today: a worktree prune, a worktree discard, a forced push, and a shell write
to the model-cap settings. The deny names the kind of step, never the command text.

Kind: process
Home: hooks/guard.py

## Why

An agent chained `git worktree prune` onto a routine command. The whole command then waited on
the owner, for a step the owner would have skipped. A lone ask shows the owner one plain step.

## Holes, named

Review round 3 (Sonnet) found a positive net safety value, so the lane merges on green. Each open
finding is a limit below. Each one also has a debt in the debt store.

- Hole: `cd ~-`, `Set-Location -` and `Set-Location +` count as harmless leads. The guard does not
  know their target, so it judges the ask step in the folder the shell stands in. A shared-tree deny
  can become an ask. Debt: `ask-alone-reset-target-unknown`, the previous-folder forms.
- Over-deny, safe direction: `<`, `>` or `&` in quoted text, such as `echo "R&D"`, counts as a step.
  Debt: `ask-alone-echo-amp-overdeny`, the quoted operator characters.
- Over-deny: a trailing newline or `;` after a harmless tail stops the tail count. Debt:
  `ask-alone-empty-segment-denies`, the empty last segment.
- Over-deny: a quoted PowerShell path ending in a backslash, such as `Set-Location "C:\Program Files\"`,
  counts as a step. Debt: `ask-alone-ps-backslash-denies`, the PowerShell escape.
- Test gap: no row puts a quoted `#`, `/*` or a lone apostrophe inside a harmless tail. Probes pass
  today. Debt: `ask-alone-tail-test-gap`, the harmless-tail rows.
- Limit: tail arguments are not checked. `echo` and `Write-Host` take any arguments, and a `(...)`
  subexpression passes the text check. Debt: `ask-alone-tail-args-unchecked`.
- Over-deny: `sl`, `chdir` and `Push-Location` are not named leads, so a chain with them denies. The
  owner ruling of 2026-10-15 names only `Set-Location`. Debt: `ask-alone-sl-chdir-denies`, pending the
  owner's choice.
