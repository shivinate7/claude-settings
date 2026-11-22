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

## A lane lint starts as a tracked task

- The mistake: starting a lane lint (`merge --lane-lint`, `bin/ci-job --lint`) detached from the harness. The shapes are a list ended by `&` (with or without `$!`, run by `python`, `bash` or `sh`), `nohup ... &`, `setsid` and `disown`. A kept pid passed the rule above, but it does not carry the lint's end to the session. The reason to refuse it is the Nov 20 incident below (commit 554adff467), not a ruling. This refusal of a kept pid departs from the `$!` allowance in the ruling section above and waits on the owner's ruling (asked 03:48 CST Nov 22). The tests now expect it refused.
- The harm: the harness tracks no task, so a FAIL wakes no one. Incident, Nov 20: the lane lint for PR 3723 started as `bash ... &` inside a foreground call. Its FAIL sat unseen for 52 minutes.
- The rule: the `detached-launch` rule refuses these calls with its own remedy, which says to start the lint with the tool's `run_in_background`. It is the same rule id, so the owner's typed override lifts it as it lifts the rule above. The reader is `detached_lint_hit` in `hooks/guard_stream.py`. It walks the call with `lint_start_hit` (the load brake's reader of a lint start), which reads each list and each `( ... )` group or `bash -c` script as the shell tokenizer cuts them. A name inside a comment, a quoted string or a heredoc body is no command, so it counts for nothing. The refusal text is `DETACHED_LINT_REASON`.
- Passes: the lint in the foreground, the lint with `run_in_background` and no `&`, `nohup` with no `&`, and `setsid -w`. The rule also refuses a lint that a `&` ends and a later `wait` joins, because the harness tracks neither the job nor its end. The wrong-refusal rate is unmeasured.
- Cost: it reads the call text again, inside the guard process that already runs for each Bash call. It starts no process and writes no file apart from the refusal log line. Section s43728 in `tests/guard/s43728-detached-lane-lint.py` pins the verdicts, and the load brake's own cases pin the shell-run forms. The cost is unmeasured: it is a guard verdict, not tracking.
- Reader: the session that started the lint reads the refusal and starts the lint again with `run_in_background`.

Kind: process
Home: hooks/guard.py
