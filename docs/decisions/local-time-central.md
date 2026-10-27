# Sessions speak times in US Central

## The ruling

Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. It says "21:40 CDT", never a
UTC time and never a 12-hour time.

`hooks/local_time.py` gives each session the current Central time as one line, for example `Local time: 2026-10-13 21:40 CDT (UTC-05:00)`.
In winter the line reads CST and UTC-06:00.

- `UserPromptSubmit` runs it on every prompt. `SubagentStart` runs it with `--agent`, which prints `hookSpecificOutput.additionalContext`
  JSON and never reads stdin.
- The hook codes the US rule: DST runs from the second Sunday of March to the first Sunday of November, at 02:00 local. It reads neither
  zoneinfo (Python on Windows often has no tz database) nor the machine zone.
- The hook is advisory. On an internal error it prints nothing to stdout, writes one `local_time:` line to stderr, and exits 0. It prints
  the time line before it reads stdin for feedback capture (`owner-feedback-inbox`).

Reason: sessions saw only UTC and answered in UTC, which shows the wrong date for the owner every evening.

Kind: process
Home: hooks/local_time.py
