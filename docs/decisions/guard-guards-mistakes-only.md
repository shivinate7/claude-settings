# Every guard, gate and check stops Claude's mistakes, not attacker-crafted forms

## Ruling

Owner, 2026-10-17 09:07 CDT, "widen": every guard, gate and check stops Claude's mistakes, never an attacker. This covers guard hooks (`hooks/guard*.py`), other gates, lints, CI checks and bin shims such as `bin/rm`.

- None of them guards against an act that only a deliberate attacker would write. One example is text hidden in a web page, file, issue or email that Claude reads and obeys (prompt injection).
- Never build a check that assumes a nefarious actor is present (owner, 2026-10-17 09:05 CDT).
- A bypass counts as a hole only if Claude could write it by mistake or from a misread task. A form whose only use is to evade the check is out of scope.
- `roles-review-cap-three` (a change gets three review rounds) applies this to the safety-hole count.

Why: each extra form a check reads costs prompts, refusals and review time on normal work. The owner accepts that hidden instructions could get a harmful act past a check. A guard may still ask about it. A lint or CI check never asks. Claude's own training is then the only defence.

Test a form by one question: could Claude write it by mistake or from a misread task, without meaning to evade?

- In scope (a hole): a routine wrapper round a denied step, such as `bash -c '<git write>'` or `x=$(<git write>)`. A python heredoc with an apostrophe in a comment, followed by a git write. ANSI-C quoting (`$'...'`) or an escape such as `\x2f` in a protected path (both stay open).
- Out of scope (not a hole): a PowerShell block with no space that sets `GIT_DIR` inside a group. The form `export GIT_SSH_COMMAND='<cmd>' && <ask command>`.

Same stance: `builders-cannot-edit-tests` (the guard stops accidental test edits) and `wsl-allow-list` (the list stops accidents, not a hostile test).

Kind: process
Home: rule:roles-review-cap-three
