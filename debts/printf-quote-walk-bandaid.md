# The printf quote case is a bandaid, not a cause fix

- **What.** `discards_output` cuts each `$( )` out of the segment, reads the rest again, and fails closed when the cut is too deep. Its docstring names this "a bandaid". The cause stays. `walk_quotes` reads a quote inside `$( )` as the outer string's own. Example: `-m "$(printf '"')" >/dev/null`. The cut catches the redirect, and the walk does not. The same walk feeds `split_segments` and `unquoted_at`, so they share the cause.
- **Where.** `discards_output` in `hooks/guard.py` (the bandaid, line 439); `walk_quotes` in `hooks/guard_core.py` (the cause, line 179).
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `walk_quotes` opens a nested reading inside `$( )` and backticks. The cut and reread in `discards_output` are deleted. A guard test denies the printf form with the cut removed, and it goes red on the current walk first.
