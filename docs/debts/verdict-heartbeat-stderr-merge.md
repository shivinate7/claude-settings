# The verdict heartbeat hides behind a redirect

**What.** `verdict` prints its heartbeat to stderr only. In a background Bash call, `verdict x 2>&1 | grep y`
and `verdict x 2>/dev/null` keep the line out of the job's output. The stall watch then reports a false STALL.

**Where.** `bin/verdict`, the heartbeat in `main`; `hooks/stall_watch.py`, `hook`.

**Decision.** stall-watch (the watcher of quiet background jobs).

**Retire.** The hook names a beat file next to its log and exports it to the job as `STALL_WATCH_BEAT`.
The watcher reads it with `--also`, and `verdict` appends each heartbeat to it. Cases 24a, 24b and 24d
of hooks/test_stall_watch.py, and test_heartbeat_also_appends_to_stall_watch_beat_file of
lint/test_verdict.py, go green.
