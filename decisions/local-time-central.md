# Sessions speak times in US Central

## The question

Which time zone does a session use when it tells the owner a time?

## The ruling

Owner, 2026-10-12: US Central (America/Chicago), DST-aware, 24-hour clock. A session says
"21:40 CDT", never a UTC time and never a 12-hour time.

`hooks/local_time.py` gives each session the current Central time. It prints one line, for
example `Local time: 2026-10-13 21:40 CDT (UTC-05:00)`. In winter the line reads CST and
UTC-06:00.

- `UserPromptSubmit` runs it on every prompt. Plain stdout is context for that event
  (Claude Code hooks reference, "Exit code 0").
- `SubagentStart` runs it with `--subagent`. That event takes context only as
  `hookSpecificOutput.additionalContext`, so the flag prints that JSON (hooks reference,
  "Add context for Claude").
- The hook codes the US rule: DST runs from the second Sunday of March to the first Sunday of
  November, at 02:00 local. It does not read zoneinfo, because Python on Windows often has no
  tz database. It does not read the machine zone either.
- The hook is advisory. On an internal error it prints nothing to stdout, writes one
  `local_time:` line to stderr, and exits 0. It prints the time line before it reads stdin
  for feedback capture (decision owner-feedback-inbox). With `--subagent` it never reads stdin.

## Why

Incident, found 2026-10-12: sessions saw only UTC, so they answered in UTC. A UTC answer
shows the wrong date for the owner every evening.

## What protects it

`hooks/test_local_time.py`: 26 checks. They cover nine hard-coded instants (both DST changes,
the repeated 01:30 hour, a UTC date that differs from the Central date), a child with no tz
database, a child with `TZ=Asia/Tokyo`, and the hook run as a script. CI steps in `gates`,
`gates-macos` and `gates-windows-rest`.

## Holes, named

- The rule is the US rule in force since 2007. If the US changes its DST dates, edit
  `hooks/local_time.py`. The upgrade is zoneinfo with this rule as the fallback.
- The line states a time. Nothing forces the model to use it. A session that ignores the
  line still answers in UTC.
- The time is fixed when the prompt is sent, or when the agent starts. A long run does not
  see it move.
- The hook reaches a machine only after `install.sh` copies it to `~/.claude/hooks`. Until
  then the wrapper exits 0 and no line shows.
- Unmeasured: the token cost of one line per prompt.

Kind: process
Home: hooks/local_time.py
