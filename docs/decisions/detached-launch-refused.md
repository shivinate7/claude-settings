# The guard refuses a detached launch

## The ruling

The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. It refuses these three shapes too:

- A bare `&` job in any segment, unless the command captures the pid with `$!`.
- `disown` in command position.
- The same shapes inside the script of `sh -c` or `bash -c`.

The remedy tells the agent to use `run_in_background`.

Passes: a wrapper that keeps its child in the foreground. `nohup cmd` with no trailing `&` waits for its child, so it detaches nothing, also inside `sh -c`. `setsid -w cmd` (or `--wait`) waits too. A `setsid` that `nohup` wraps is read the same way: `nohup setsid -w cmd` passes, and `nohup setsid cmd` and `nohup setsid -f cmd` are refused, because `nohup` hands on to its child. Still refused: every `&` background form (`nohup cmd &`), `setsid cmd` and `setsid -f cmd`. An unquoted `&` glued to a word (`cmd&`, `grep "x"&`, `tail&echo done`) ends that job, so it is refused. The words after it start a new command. A quoted `&`, `|&`, `&&`, `&>`, `>&2` and `2>&1` end no job (`amp_pieces` cuts the segment, `backgrounding_amp` reads it, shared with `check-tail`).

Measured against local transcripts (2026-09-24): 0 of 16571 Bash commands in 116 sessions ended
in a bare trailing `&`. Measured again (2026-09-26): over 13312 distinct commands in 118 sessions,
reading every segment refused 6 that the last-segment read allowed. All 6 held an `&` inside a
python heredoc body. So the guard drops every heredoc body before it reads.

Kind: process
Home: hooks/guard.py
