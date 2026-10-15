# The guard hooks stop Claude's mistakes, not attacker-crafted forms

## The question

Must the guard hooks (`hooks/guard*.py`) stop a command that only a deliberate attacker would
write? An example is text hidden in a web page, file, issue or email that Claude reads and obeys
(prompt injection). The owner was asked this in plain words.

## Ruling

Owner ruling, 2026-10-15 15:47 CDT. The owner's answer: "Guard against Claude's mistakes only."

- The guard hooks protect against Claude's own mistakes.
- The guard hooks do not guard against a command that only a deliberate attacker would write.
- A bypass counts as a hole only if Claude could write it by mistake or from a misread task.
- A form whose only use is to evade the guard is out of scope. It is not a hole.

Trigger: in review round 1 of lane ask-alone-bc, the form `export GIT_SSH_COMMAND='<cmd>' && <ask step>`
was found to ask where main denies. The owner ruled such crafted forms out of scope.

## Why

The guard checks Claude's own work. Each extra form it reads costs prompts, refusals and review
time on normal work. The owner gains fewer prompts and refusals, simpler rules and shorter reviews.

The owner accepts the loss. Hidden instructions could get a harmful command past the guard, with
at most a prompt. Claude's own training is then the only defence against that.

Protected outcome: routine work runs without false stops, and the rules stay short.

## In scope and out of scope

Test a form by one question: could Claude write it by mistake or from a misread task, without
meaning to evade? If yes, it is in scope. If its only use is evasion, it is out of scope.

In scope (a hole):

- A routine wrapper round a denied step, such as `bash -c '<git write>'` or `x=$(<git write>)`.
- A python heredoc with an apostrophe in a comment, followed by a git write.

Out of scope (not a hole):

- An escape that spells a protected path, such as `\x2f`, or a `$'...'` quoted protected path.
- A PowerShell block with no space that sets `GIT_DIR` inside a group.
- The `export GIT_SSH_COMMAND='<cmd>' && <ask step>` form named under Trigger.

## Earlier cases this agrees with

- `builders-cannot-edit-tests`: the guard stops accidental test edits. A deliberate evasion goes to
  the reviewer. This ruling states the same stance for every guard hook.
- `wsl-allow-list`: the list stops accidents, not a hostile test.

## Effect on other records

This ruling narrows the word "safety hole" in `hold-unsafe-after-round-3` (the hold rule for a
change's net safety value). Under this ruling a hole counts only when Claude could write the act by
mistake or from a misread task. That record still uses the wider definition. It is not yet rewritten.

Kind: process
Home: rule:roles-review-cap-three
