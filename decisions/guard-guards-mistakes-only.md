# Every guard, gate and check stops Claude's mistakes, not attacker-crafted forms

## The question

Must a guard, gate or check stop an act that only a deliberate attacker would write? This covers
the guard hooks (`hooks/guard*.py`), other gates, lints, CI checks and bin shims such as
`bin/rm`. An example is text hidden in a web page, file, issue or email that Claude reads and obeys
(prompt injection). The owner was asked this in plain words.

## Ruling

Owner ruling, 2026-10-17 09:07 CDT. The owner's word: "widen". Every guard, gate and check stops
Claude's mistakes, never an attacker.

- Every guard, gate and check protects against Claude's own mistakes. This includes guard hooks,
  other gates, lints, CI checks and bin shims such as `bin/rm`.
- None of them guards against an act that only a deliberate attacker would write.
- Never build a check that assumes that a nefarious actor is present.
- A bypass counts as a hole only if Claude could write it by mistake or from a misread task.
- A form whose only use is to evade the check is out of scope. It is not a hole.

Trigger: in review round 1 of lane ask-alone-bc, the form `export GIT_SSH_COMMAND='<cmd>' && <ask step>`
was found to ask where main denies. The owner ruled such crafted forms out of scope, with this exact
example in front of him.

## Why

A check reads Claude's own work. Each extra form it reads costs prompts, refusals and review
time on normal work. The owner gains fewer prompts and refusals, simpler rules and shorter reviews.

The owner accepts the loss. Hidden instructions could get a harmful act past a guard or other check, with
at most a prompt. Claude's own training is then the only defence against that.

Protected outcome: routine work runs without false stops, and the rules stay short.

## In scope and out of scope

Test a form by one question: could Claude write it by mistake or from a misread task, without
meaning to evade? If yes, it is in scope. If its only use is evasion, it is out of scope.

In scope (a hole):

- A routine wrapper round a denied step, such as `bash -c '<git write>'` or `x=$(<git write>)`.
- A python heredoc with an apostrophe in a comment, followed by a git write.
- ANSI-C quoting (`$'...'`) or an escape such as `\x2f` in a protected path. Debts
  `frozen-path-ansi-c-quote` and `ansi-c-escape-not-decoded` stay open.

Out of scope (not a hole):

- A PowerShell block with no space that sets `GIT_DIR` inside a group.
- The `export GIT_SSH_COMMAND='<cmd>' && <ask step>` form named under Trigger.

## Earlier cases this agrees with

- `builders-cannot-edit-tests`: the guard stops accidental test edits. A deliberate evasion goes to
  the reviewer. This ruling states the same stance for every guard, gate and check.
- `wsl-allow-list`: the list stops accidents, not a hostile test.

## Effect on other records

This ruling covers every guard, gate and check. For any of them, a safety hole counts
only when Claude could write the act by mistake or from a misread task. The rule
`roles-review-cap-three` (a change gets three review rounds) and `hold-unsafe-after-round-3` (net-value hold after round 3) say so.

Kind: process
Home: rule:roles-review-cap-three
