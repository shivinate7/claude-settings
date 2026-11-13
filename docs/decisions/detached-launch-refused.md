# The guard refuses a detached launch

## The ruling

The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. It refuses these three shapes too:

- A bare `&` job in any segment, unless the command captures the pid with `$!`. The `&` may be spaced or glued to the word before it: `cmd&`, `grep "x"&` and `rm -rf ..&` are jobs, and the words after a glued `&` start a new command (`tail&echo done`).
- `disown` in command position.
- The same shapes inside the script of `sh -c` or `bash -c`.

The remedy tells the agent to use `run_in_background`.

Passes: a wrapper that keeps its child in the foreground. `nohup cmd` with no trailing `&` waits for its child, so it detaches nothing, also inside `sh -c`. `setsid -w cmd` (or `--wait`) waits too. A `setsid` that `nohup` wraps is read the same way: `nohup setsid -w cmd` passes, and `nohup setsid cmd` and `nohup setsid -f cmd` are refused, because `nohup` hands on to its child. Still refused: every `&` background form (`nohup cmd &`), `setsid cmd` and `setsid -f cmd`. The `&` is read from the raw text, one reader for this rule and `check-tail` (`backgrounding_amp` in `hooks/guard_core.py`), so a quoted `&` (`grep '&' file`) is no job. These end no job either: `&&`, `|&`, `&>`, `>&2` and `2>&1`, a `&` after a comment's `#`, a `&` inside a multi-line quote, a bitwise `&` in `$(( ))`, `(( ))` or `${ }`, and PowerShell's call operator (`(& $tool x)`, `{&$tool $_}`).

Measured against local transcripts (2026-09-24): 0 of 16571 Bash commands in 116 sessions ended
in a bare trailing `&`. Measured again (2026-09-26): over 13312 distinct commands in 118 sessions,
reading every segment refused 6 that the last-segment read allowed. All 6 held an `&` inside a
python heredoc body. So the guard drops every heredoc body before it reads.

Kind: process
Home: hooks/guard.py
