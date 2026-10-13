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

Review ended at the three-round cap with no blocker open. The guard no longer crashes when
`guard_core` lacks `set_log_session` (a blocker found in round 1): same verdict and exit code,
no traceback.

- **Reader edit selects extra CI.** An edit to `lint/guard_log_report.py` selects
  `gates_windows_merge` and the `guard` suite, as well as `code`. Neither reads guard.log, so
  the cost is CI time. It ships for the macOS and Windows runs of the `decision_watch` tests,
  which `gates_macos` and `gates_windows_rest` give. Those two also select on this edit.
- **Install skew.** A new `hooks/guard_core.py` writes six fields. An old
  `hooks/decision_watch.py` (main, before this PR) skips every line whose field count is not
  five, so it drops every unread note. `install.sh` lands both files from one source, so only
  a partial copy, such as a Windows file copy, can split them.
- **One-reader test gaps.** `OneReaderTests` flags only a literal `.split("\t")` call in
  `hooks/*.py` and `lint/*.py` files that name guard.log. A `partition`, `re.split`, `csv`, a
  split on a variable, or a reader in `merge/`, `janitor/` or `bin/` passes. Risk is low. The
  test names its one allowed fallback (`gate-hooks-fail-closed`: an unread note must not vanish).
- **Session name read by `globals()`.** `record` in `hooks/guard_core.py` reads
  `_log_session` with `globals().get`. The module always defines that name, so the absent
  branch cannot run in production. A stale `guard_core.py` runs its own old `record`, which
  writes five fields. Test `session_log_stale_core_case` proves the code path, not the real
  skew in the install hole above.
- **Pipe or backtick in a session id.** A `|` splits its cell in the `--by-session` table.
  Control characters are stripped, so an id cannot add a line. A backtick is not stripped, so
  it could close the fence in the verbatim `other` rows. The fault is display only: counts use
  the raw id.
- **Seven or more fields.** The reader reads `session` as field 6, and `matched` as field 5
  plus the later fields. The `decision_watch` fallback reads `matched` as field 5 only. The
  line gets a seventh field only through the `tool` field, which is not folded. Not every
  caller of `tool` was checked for a tab. `log_cut` folds tabs out of `matched`, and the
  session cell strips control characters.
- **Stalled disk.** The gate prints its answer before the log write. A log write that stalls can
  still delay process exit. The hook timeout then lets the call through, as the old lint timeout
  did.
- **Logging off with no marker.** A missing `hooks/guard_core.py`, or an older one without
  `set_log_session`, turns STE logging off. No marker line is written. The reader then prints
  empty tables, which read as no events.
- **Lines lost on Windows.** A plain append from many processes is not atomic on Windows.
  Measured: a line was lost in 1 round of 12, each round with 20 processes calling `record`. A
  lost line costs one count and never changes a verdict. `lint/test_gates.py` skips the exact-count
  test on Windows (test_19). Test_19b checks a range of 17 to 20 lines.
- **Rewrite, then failed lint.** The fixer rewrites the text, then the lint cannot run. The
  rewrite still lands. The log holds `STE-unchecked` and no `fixed` line.

## What reopens it

A hand-graded sample, or a rule whose denies the table shows as mostly false.

Kind: process
Home: lint/guard_log_report.py
