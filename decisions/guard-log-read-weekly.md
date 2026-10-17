# guard.log is read daily, by a note

## The ruling

Owner, 2026-10-13. `hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. `lint/guard_log_report.py` reads it. It prints three tables: deny, ask and noted counts by rule; denies per day; and every other row, such as `reverted`, verbatim. For detail, run `python lint/guard_log_report.py --days 7`. The reader has `--session <id>` and `--by-session`. The session is the last field. A missing field or `-` means unknown session.

`hooks/daily_note.py` is a SessionStart hook under the `startup` matcher. The first start on a Central day runs the checks and writes the done-today stamp, `daily-note.stamp` in the config dir. A later start that day prints nothing. The note is silent unless a check fails. It prints one line per failed check, and each line names the reader by its absolute path, built from the hook's own folder.

The window is the days since the stamp, the stamp day through the day before today, at most 7 days. A day with no session start keeps its lines for the next start. With no stamp, the window is the day before today. The checks:

- a `crash` line in the window: a guard hook crashed.
- an `STE-fallback` line whose matched field ends `fallback=crash`.
- an `STE-unchecked` line: the lint could not run, so those writes are unknown.
- a guard.log that exists and cannot be read: unknown. A missing guard.log is not a failure.

The STE gate and the Stop sweep (`lint/md_sweep.py`) write their own lines through `guard_logger` in `lint/_transcript.py`:

- `fixed`: a Markdown rewrite landed. The rule is the sorted STE codes, capped at 40 characters, or `STE-wording` when there are none. Matched field: `<basename> fixed=N`. The reader counts `fixed` under noted.
- `deny`: a refusal. Matched field: `<basename> denied=N`. A Stop `deny` line names one blocked sweep run: `<first basename> files=N`.
- `noted` with rule `STE-fallback`: the fixer timed out, crashed, or skipped oversize text. Matched field: `<basename> fallback=timeout|oversize|crash`.
- `noted` with rule `STE-unchecked`: the lint could not run. Matched field: `<basename> unchecked`.
- A write with no fix, deny, fallback or unchecked outcome writes no line.

Why: the table is the outcome meter for the two owner concerns, prompts the owner did not need and agents refused with no allowed path. Judge a rule by its row here, not by its test count.

## Holes, named

Debts: `guard-timeout-fails-open` (a stalled or slow guard lets the call through).

Limits:

- The log holds the matched text, not the outcome. It cannot say whether a deny was right. A hand-graded sample is the next measurement, and none exists. Reopen on a sample, or a rule whose denies the table shows as mostly false.
- The note reads only the failures above. A rule that never fires, or fires for the wrong reason, shows only in the reader's tables, read by hand.
- The note has no volume check. A count jump over a 7-day baseline fired on 6 of 14 real days from growth in use alone.
- The note runs on `startup`, not on `resume`.
- One machine per log. A count is a lower bound: it counts verdicts, not harm or false alarms.
- Unjudged: whether `silent-write` (git `-q`), `test-author-scope` and `detached-launch` earn their denies.

Kind: process
Home: lint/guard_log_report.py
