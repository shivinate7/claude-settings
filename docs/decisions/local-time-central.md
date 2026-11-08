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
  - Form: the header is the first non-blank line of a `mcp__claude-code-remote__send_message` message, after optional markdown lead characters. It starts with a label of one to four words, then `,`, `:` or a spaced dash (`-`, `—` or `–`), then the time. The time has an optional `YYYY-MM-DD`, a 1- or 2-digit hour, optional `:SS`, and CST or CDT in any letter case. Examples: `Coordinator, 13:28 CST: ...`, `Triage, 7:40 cst: ...` and `Now: 13:28 CST`. The guard judges that one stamp by its position. It guesses nothing from prose.
  - Verdict: deny when the zone name is wrong for the season, whatever the minutes (local_time's DST rule names the current zone, so `07:08 CDT` at 07:08 CST is refused). A dated stamp is refused when it is more than 1 minute ahead of the clock, with no upper limit. An undated stamp is refused only when it is 2 to 60 minutes ahead. It is read as a signed minute-of-day offset in [-720, 720), across midnight. One more than 60 minutes ahead is read as a quote from an earlier day, and passes. A stamp behind passes when its zone name is right (every incident was ahead; coordinator pick 2026-11-07 14:48 CST). The window and the wrong-zone refusal: lane pick 2026-11-08 07:14 CST. The refusal prints the real time.
  - Passes: every other stamp, such as a quoted owner-ruling time later on the header line, a stamp on a later line, or a message with no header. An override lifts it.
  - Steer: the refusal names two fixes. Re-stamp your own header with the printed time. Or, if the first line quotes someone else's time in header form, open the message with your own label first. The clock is cut to the minute before the compare, so a dated stamp and an undated one judge the same.
  - Known miss: a label of 5 or more words, a stale stamp behind the clock, and an undated stamp more than 60 minutes ahead. Also a sender's time in any other form, such as `13:40 CST, coordinator here`, and git commit messages. Commit messages have no incident.
  - Known false alarm, three cases, each costing one retry, and the refusal names the fix: (1) a quoted stamp in header form up to 60 minutes ahead, such as `Owner, 13:40 CST: ...` at 13:22 CST; open with your own label instead. (2) a first line that names a future time 2 to 60 minutes ahead, such as `ETA: 07:45 CST` or `PR 12 merged - 07:40 CST deadline`; move the time off the first line. (3) a dated quote from the other DST season, such as `Owner, 2026-10-30 16:20 CDT: grant` sent in winter, which the wrong-zone check refuses whatever the minutes; open with your own label instead.
  - Cost: one clock read per send_message, inside the guard process the PreToolUse matcher already starts. No transcript read, file, process or timer.
  - Tests: family `message-time-matches-clock` in `hooks/test_guard.py`.
