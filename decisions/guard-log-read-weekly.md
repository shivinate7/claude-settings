# guard.log is read daily, by a note

## The ruling

Owner, 2026-10-13. `hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. `lint/guard_log_report.py` reads it and prints three tables: deny, ask and noted counts by rule; denies per day; and every other row, such as `reverted`, verbatim. The session is the last field. A missing field or `-` means unknown session.

`hooks/daily_note.py` is a SessionStart hook under the `startup` matcher, not `resume`. The first start on a Central day runs the checks and writes the done-today stamp, `daily-note.stamp` in the config dir. A later start that day prints nothing. The note is silent unless a check fails. It prints one line per failed check, and each line names the reader by its absolute path.

The window is the days since the stamp, the stamp day through the day before today, at most 7 days. A day with no session start keeps its lines for the next start. With no stamp, the window is the day before today. The checks:

- a `crash` line in the window: a guard hook crashed.
- an `STE-fallback` line whose matched field ends `fallback=crash`.
- an `STE-unchecked` line: the lint could not run, so those writes are unknown.
- a guard.log that exists and cannot be read: unknown. A missing guard.log is not a failure.

The STE gate and the Stop sweep (`lint/md_sweep.py`) write their own lines through `guard_logger` in `lint/_transcript.py`: `fixed`, `deny`, and `noted` rows for `STE-fallback` and `STE-unchecked`. A write with no such outcome writes no line.

Reason: the table is the outcome meter for the two owner concerns, prompts the owner did not need and agents refused with no allowed path. Judge a rule by its row here, not by its test count.

Kind: process
Home: lint/guard_log_report.py
