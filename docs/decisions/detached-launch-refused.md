# The guard refuses a detached launch

## The ruling

The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. It refuses these three shapes too:

- A bare `&` job in any segment, unless the command captures the pid with `$!`.
- `disown` in command position.
- The same shapes inside the script of `sh -c` or `bash -c`.

The remedy tells the agent to use `run_in_background`.

Passes: a wrapper that keeps its child in the foreground. `nohup cmd` with no trailing `&` waits for its child, so it detaches nothing, also inside `sh -c`. `setsid -w cmd` (or `--wait`) waits too. A `setsid` that `nohup` wraps is read the same way: `nohup setsid -w cmd` passes, and `nohup setsid cmd` and `nohup setsid -f cmd` are refused, because `nohup` hands on to its child. Still refused: every `&` background form (`nohup cmd &`), `setsid cmd` and `setsid -f cmd`. An unquoted `&` glued to a word (`cmd&`, `grep "x"&`, `tail&echo done`) ends that job, so it is refused. The words after it start a new command. A quoted `&`, `|&`, `&&`, `&>`, `>&2` and `2>&1` end no job (`amp_pieces` cuts the segment, `backgrounding_amp` reads it, shared with `check-tail`).

The glued `&` reader reads `build&echo done` as a job end, so a check cannot hide behind a backgrounded left part. It may refuse a valid command: an unquoted URL with `&` in it is refused as a detached launch (`curl x?a=1&b=2`), and a quoted URL is allowed. The wrong-refusal rate is unmeasured. The owner accepted this cost (owner ruling to keep the glued-`&` reader, own-716-b-keep-2156-glued-amp, 2026-11-15 11:57 CST). The remedy text for that refusal, `DETACHED_LAUNCH_REASON` in `hooks/guard_kill.py`, needs a separate fix (roadmap step `glued-amp-url-remedy`).

Measured against local transcripts (2026-09-24): 0 of 16571 Bash commands in 116 sessions ended
in a bare trailing `&`. Measured again (2026-09-26): over 13312 distinct commands in 118 sessions,
reading every segment refused 6 that the last-segment read allowed. All 6 held an `&` inside a
python heredoc body. So the guard drops every heredoc body before it reads.

Kind: process
Home: hooks/guard.py
