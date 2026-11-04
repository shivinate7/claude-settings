# guard.log is read daily, by a note

## The ruling

Owner, 2026-10-13. `hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. `lint/guard_log_report.py` reads it and prints three tables: deny, ask and noted counts by rule; denies per day; and every other row, such as `reverted`, verbatim. The session is the last field. A missing field or `-` means unknown session.

`hooks/daily_note.py` is a SessionStart hook under the `startup` matcher, not `resume`. The first start on a Central day runs the checks and writes the done-today stamp, `daily-note.stamp` in the config dir. A later start that day prints nothing. The note is silent unless a check fails. It prints one line per failed check, and each line names the reader by its absolute path.

The window is the days since the stamp, the stamp day through the day before today, at most 7 days. A day with no session start keeps its lines for the next start. With no stamp, the window is the day before today. The checks:

- a `crash` line in the window: a guard hook crashed.
- a guard.log that exists and cannot be read: unknown. A missing guard.log is not a failure.
- an agent-end reap run in the window that was killed or crashed. A run counts when its `started` row has no `done` row after it, or one of its rows has an `error`. The reader is the agent-end payload log, `state/agent-end-payloads.jsonl` under the config dir. The log keeps the last 200 rows. The note reads only those rows, so a run whose rows the cap cut prints nothing. A done row the log lost also fires the line (debt `agent-end-log-loses-row`, a row the log can lose on Windows).
- the daily sweep's error log, `janitor/launchd-sweep.err.log` under the config dir, is not empty and was last written in the window. The line names it and the stdout log, `launchd-sweep.log`. The person who follows the line reads that stdout log.

Reader: `hooks/daily_note.py`, for each file above. Each failed line names the file to read next. The output goes to the session that started.

Cost: one hook process per `startup`, the existing SessionStart hook. On the first start of a Central day the checks run: one read of guard.log, one read of the payload log (at most 200 rows), and one stat of the err log. The note writes only the stamp and starts no process of its own.

The STE write guard and the markdown sweep wrote `STE-fallback` and `STE-unchecked` lines. Both are removed (owner, 2026-10-22 10:10 CDT; `ste-guard-fixes-not-nags`), so no new line of either kind is written, and the two checks that read them are removed too. Old rows stay in guard.log and show in `lint/guard_log_report.py` like any other row.

Reason: the table is the outcome meter for the two owner concerns, prompts the owner did not need and agents refused with no allowed path. Judge a rule by its row here, not by its test count.

Kind: process
Home: lint/guard_log_report.py
