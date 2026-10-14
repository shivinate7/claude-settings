# guard.log is read weekly

## The question

`hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. Who reads it,
and what does it say?

## The ruling, 2026-10-11

`lint/guard_log_report.py` reads it. It prints three tables: deny, ask and noted counts by
rule; denies per day; and every other row, such as `reverted`, verbatim. Run it at the start of
each audit session, and once a week:

```
python lint/guard_log_report.py --days 7
```

The session is the last field. A missing field or `-` means unknown session. The reader has
`--session <id>` and `--by-session`.

The STE gate and the Stop sweep (`lint/md_sweep.py`) write their own lines through `guard_logger`
in `lint/_transcript.py`. A `fixed` line means that a Markdown rewrite landed. Its rule is the
sorted STE codes, capped at 40 characters, or `STE-wording` when there are none. Its matched field
is `<basename> fixed=N`. A `deny` line means that a refusal was made, with matched field
`<basename> denied=N`. A `noted` line with rule `STE-fallback` means that the fixer timed out,
crashed, or skipped oversize text. Its matched field is `<basename> fallback=timeout|oversize|crash`.
A `noted` line with rule `STE-unchecked` means that the lint could not run. Its matched field is
`<basename> unchecked`. A Stop `deny` line names one blocked sweep run, with matched field
`<first basename> files=N`. A write with no fix, deny, fallback or unchecked outcome writes no
line. The reader counts `fixed` under noted. Its denies per day now include the STE denies and the
sweep blocks, and its by-rule table shows the STE rows as their own rows.

The table is the outcome meter for the two owner concerns: prompts the owner did not need,
and agents refused with no allowed path. A rule is judged by its row here, not by its test
count.

## The first table, this Windows machine, 30 days to 2026-10-11

Rules with a deny. The reader prints the rest.

| rule | deny | ask | noted |
|---|---|---|---|
| env-file | 766 | 0 | 0 |
| waiter | 464 | 0 | 0 |
| test-author-scope | 375 | 0 | 0 |
| silent-write | 290 | 0 | 0 |
| detached-launch | 206 | 0 | 0 |
| shared-tree | 146 | 26 | 127 |
| cite-by-id | 79 | 0 | 0 |
| builder-test-edit | 41 | 0 | 0 |
| live-stream | 41 | 0 | 0 |
| frozen-path | 39 | 0 | 0 |
| force-push | 16 | 15 | 0 |
| nine more rules | 54 | 0 | 0 |
| subagent-model-cap | 0 | 4 | 0 |

Denies per day peaked at 636 on 2026-10-10. The one `reverted` row is a `subagent-model-cap`
expiry on 2026-10-06.

What the matched text says:

- `env-file`, 766: 296 of them (39%) refused a loader flag behind a word the rule does not
  look through: `timeout` (160), `verdict` (78), and a word glued to a `(` (58). Counted by the
  command word the deny names; the log holds the word, not its arguments. The rule's own
  remedy names the `--env-file` form it then refuses. See deferred item env-file-wrappers.
- `waiter`, 464: every one `sleep` or `Start-Sleep`. Ruled in decision agents-wait-with-monitor.
- `silent-write`, 290: `-q` on a git write: `push` 215, `merge` 38, `pull` 17, `commit` 12,
  and 8 others. Right by rule `git-never-discard-output`. The cost is 290 retries. Unjudged:
  whether the rule earns it.
- `test-author-scope`, 375, and `detached-launch`, 206: unjudged.
- `shared-tree`, 26 asks in 30 days: about one a day. This is the count the per-file discard
  record (stash-push-is-clone-wide) called unmeasured.

## Named limits

- The log holds the matched text, not the outcome. It cannot say whether a deny was right. A
  hand-graded sample is the next measurement. None exists yet.
- Nothing runs the reader on a schedule. A session runs it by hand.
- One machine per log. The Mac's log (9,537 lines on 2026-10-11) is a second reading, not in
  this table.

## Holes, named

Debts: `guard-log-extra-ci` (an edit to the reader selects the Windows merge and guard suites), `guard-log-install-skew` (a six-field core and an old reader drop each other's lines), `guard-log-one-reader-gaps` (the one-reader test misses other split forms), `guard-log-session-id-fence` (a pipe or backtick in a session id breaks the table), `guard-log-tool-field-tab` (a tab in the tool field can add a seventh field), `guard-log-off-silent` (STE logging is disabled with no marker), `guard-log-lines-lost` (a guard.log line can be lost on Windows), `ste-rewrite-unchecked-lands` (an unchecked rewrite still lands), `ste-gate-closed-pipe-no-log` (a closed stdout pipe ends the STE gate with no log line), `guard-timeout-fails-open` (a stalled or slow guard lets the call through).

## What reopens it

A hand-graded sample, or a rule whose denies the table shows as mostly false.

Kind: process
Home: lint/guard_log_report.py
