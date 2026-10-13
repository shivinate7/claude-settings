#!/usr/bin/env python3
"""UserPromptSubmit and SubagentStart hook: tell the session the time in US Central (America/Chicago).

Owner ruling 2026-10-13: sessions speak times in US Central, 24-hour clock. See decision
local-time-central. Prints one line, for example "Local time: 2026-10-13 21:40 CDT (UTC-05:00)".
Plain stdout is context for UserPromptSubmit. SubagentStart takes context only as JSON, so
`--subagent` prints `hookSpecificOutput` with `additionalContext` (Claude Code hooks reference).
The US rule is coded here, not read from zoneinfo: Windows Python often has no tz database.
Advisory, fail-open: any error prints one stderr line and exits 0. The hook never reads stdin.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

CST = timedelta(hours=-6)


def nth_sunday(year, month, n):
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    d += timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    return d


def line(clock=None):
    now = (clock or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
    # US rule since 2007: DST runs from 02:00 CST on the 2nd Sunday of March (08:00 UTC)
    # to 02:00 CDT on the 1st Sunday of November (07:00 UTC).
    start = nth_sunday(now.year, 3, 2).replace(hour=8)
    end = nth_sunday(now.year, 11, 1).replace(hour=7)
    dst = start <= now < end
    local = now + CST + (timedelta(hours=1) if dst else timedelta())
    name, off = ("CDT", "UTC-05:00") if dst else ("CST", "UTC-06:00")
    return "Local time: %s %s (%s)" % (local.strftime("%Y-%m-%d %H:%M"), name, off)


def main(argv):
    try:
        text = line()
        if "--subagent" in argv:
            text = json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                                      "additionalContext": text}})
        print(text)
    except Exception as e:  # advisory hook: fail open; one stderr line shows in --debug
        print("local_time: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
