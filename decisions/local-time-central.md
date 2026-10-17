# Sessions speak times in US Central

## The ruling

Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. It says "21:40 CDT", never a UTC time and never a 12-hour time.

`hooks/local_time.py` gives each session the current Central time as one line, for example `Local time: 2026-10-13 21:40 CDT (UTC-05:00)`. In winter the line reads CST and UTC-06:00.

- `UserPromptSubmit` runs it on every prompt. Plain stdout is context for that event.
- `SubagentStart` runs it with `--subagent`. That event takes context only as `hookSpecificOutput.additionalContext`, so the flag prints that JSON. With `--subagent` it never reads stdin.
- The hook codes the US rule: DST runs from the second Sunday of March to the first Sunday of November, at 02:00 local. It reads neither zoneinfo (Python on Windows often has no tz database) nor the machine zone.
- The hook is advisory. On an internal error it prints nothing to stdout, writes one `local_time:` line to stderr, and exits 0. It prints the time line before it reads stdin for feedback capture (`owner-feedback-inbox`).

Why: sessions saw only UTC and answered in UTC, which shows the wrong date for the owner every evening.

Protected by `hooks/test_local_time.py` (hard-coded DST instants, a child with no tz database, a child with `TZ=Asia/Tokyo`, the hook run as a script), run in `gates`, `gates-macos` and `gates-windows-rest`.

## Holes, named

Debts: `local-time-hard-coded-dst` (the US DST rule is coded in the hook, and the zoneinfo upgrade is not built), `local-time-line-cost-unmeasured` (the token cost of one line per prompt is unmeasured).

Limits:

- Nothing forces the model to use the line.
- The time is fixed at prompt send, or at agent start.
- The hook reaches a machine only after `install.sh` copies it to `~/.claude/hooks`. Until then no line shows.

Kind: process
Home: hooks/local_time.py
