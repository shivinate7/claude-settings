# The guard refuses a detached launch

## The ruling

The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. It refuses these three shapes too:

- A bare `&` job in any segment, unless the command captures the pid with `$!`.
- `disown` in command position.
- The same shapes inside the script of `sh -c` or `bash -c`.

The remedy tells the agent to use `run_in_background`.

Measured against local transcripts (2026-09-24): 0 of 16571 Bash commands in 116 sessions ended
in a bare trailing `&`. Measured again (2026-09-26): over 13312 distinct commands in 118 sessions,
reading every segment refused 6 that the last-segment read allowed. All 6 held an `&` inside a
python heredoc body. So the guard drops every heredoc body before it reads.

Kind: process
Home: hooks/guard.py
