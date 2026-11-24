# A command that needs the owner's answer runs alone

## Ruling

An agent never chains a command that needs the owner's answer onto other commands in one shell call (owner, 2026-10-14). The guard rule `ask-alone` refuses such a call. The same command alone still asks. Only the model-cap settings write asks now. A refusal chained with other commands is not an ask-alone matter: it prints its own reason (decision `guards-never-ask`).

Owner, 2026-10-15 12:00 CDT: two harmless additions are no extra command, and the call asks once, as the command alone does. Only these named forms count:

- Before the command: a leading `cd X &&`, `Set-Location X;` or `export NAME=value &&`.
- After the command: `| tail -N`, `| head -N`, `| Out-Null`, `&& echo <text>`, or in PowerShell `; Write-Host <text>`.

Every other form stays a command: `; echo`, `| cat`, `; Write-Output`, `| tee`, `| sh`, `||`, and the aliases `sl`, `chdir` and `Push-Location`. So does `cd -`. A segment with a redirect, a substitution, a `&`, or an escaped quote (`\"`, `\'`) is a command too. A reset after `Set-Location` is judged in the target folder, as after `cd`.

Owner, 2026-10-14 22:25 CDT: an inline interpreter script (a python, node, perl or ruby heredoc) is one command, and it asks once. A chain around it still counts. A shell body (bash, sh, a heredoc piped to a shell) counts each line, as does a body with no closing line. A refusal in the body still wins. Owner, 22:27: no safety hole that main lacks.

The one command that asks: a shell write to the model-cap settings (rule `agent-model-cap`). The refusal names the kind of command, never its text. Worktree prune, worktree discard and forced push no longer ask (decision `guards-never-ask`).

Why: a chained `git worktree prune` once made the whole shell call wait on the owner for a command the owner would have skipped. A lone ask shows one plain command.

Kind: process
Home: hooks/guard.py
