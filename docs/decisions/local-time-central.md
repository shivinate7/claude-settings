# Sessions speak times in US Central

## The ruling

Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. It says "21:40 CDT", never a
UTC time and never a 12-hour time.
Every clock time the session gives the owner names its zone, each time, not once per message (owner, 2026-11-02 13:10 CST).

`hooks/local_time.py` gives each session the current Central time as one line, for example `Local time: 2026-10-13 21:40 CDT (UTC-05:00)`.
In winter the line reads CST and UTC-06:00.

- `UserPromptSubmit` runs it on every prompt. `SubagentStart` runs it with `--agent`, which prints `hookSpecificOutput.additionalContext`
  JSON and never reads stdin.
- The hook codes the US rule: DST runs from the second Sunday of March to the first Sunday of November, at 02:00 local. It reads neither
  zoneinfo (Python on Windows often has no tz database) nor the machine zone.
- The hook is advisory. On an internal error it prints nothing to stdout, writes one `local_time:` line to stderr, and exits 0. It prints
  the time line before it reads stdin to save the owner's message (`owner-feedback-inbox`).

Reason: sessions saw only UTC and answered in UTC, which shows the wrong date for the owner every evening.

Kind: process
Home: hooks/local_time.py

## A message's own time matches the clock

- **Message time matches clock** (rule `message-time-matches-clock`, guard rule that denies a send_message whose header time is off the clock). Risk kind: incident. Incident: on 2026-11-07 the claude-settings coordinator stamped its send_message headers 10 to 25 minutes ahead of the clock, twice ("13:40 CST" sent at 13:22 CST, "13:50 CST" at 13:26 CST). A lane caught it. Harm: wrong times mislead triage's records, owner-ruling times and age-based checks.
  - Form: the header is the first non-blank line of a `mcp__claude-code-remote__send_message` message, after optional markdown lead characters. It starts `<label>, HH:MM CST` or `<label>: HH:MM CST` (CDT in summer), with a label of one to three words and an optional `YYYY-MM-DD` before the time, such as `Coordinator, 13:28 CST: ...` or `Now: 13:28 CST`. The guard judges that one stamp by its position. It guesses nothing from prose.
  - Verdict: deny when the header stamp is more than 1 minute ahead of the clock; a stamp behind passes (a kept old value is always behind; every incident was ahead; coordinator pick 2026-11-07 14:48 CST). The stamp's zone sets its offset, so `15:22 CDT` at 13:22 CST is 60 minutes ahead. A stamp with no date is compared by minute of day, across midnight, as a signed offset in [-720, 720). The refusal prints the real time.
  - Written times (step `stamp-check-page-and-roadmap`). Incident: on 2026-11-07 triage 6 wrote page item 364 with `added` `2026-11-07T20:16:00Z` at 20:14Z, and roadmap step `updatedAt` values ahead of the clock. The same limit judges an ISO-8601 instant with an offset in three places: `added` in an ArtifactData write (set, update, each batch write) to collection `items`; `updatedAt` in a Write or Edit to `roadmap/data/steps/<name>.json`; and a literal double-quoted `updatedAt` value in a Bash command. Both sides are cut to the whole minute. The refusal prints the time in Central and in ISO form.
  - Passes: every other stamp, such as a quoted owner-ruling time later on the header line, a stamp on a later line, or a message with no header. Also a time in prose (`note`, `why`), another field or collection, a value with no offset, and `updatedAt=$T` from a shell variable. An override lifts it.
  - Steer: the refusal names two fixes. Re-stamp your own header with the printed time. Or, if the first line quotes someone else's time in header form, open the message with your own label first. The clock is cut to the minute before the compare, so a dated stamp and an undated one judge the same.
  - Known miss: a stale stamp behind the clock, a sender's time in any other form, such as `13:40 CST, coordinator here`, commit messages (no incident), other page time fields such as `replied` and `ruled` (no incident), and a single-quoted `updatedAt` literal in a shell command.
  - Known false alarm: a message that opens with a quoted stamp in header form, such as `Owner, 16:36 CST: ...`. Open with your own label instead.
  - Cost: one clock read per send_message, and per ArtifactData, Write, Edit or Bash call that carries a judged value, inside the guard process the PreToolUse matcher already starts. No transcript read, file, process or timer.
  - Tests: family `message-time-matches-clock` in `hooks/test_guard.py`.
