#!/usr/bin/env python3
"""SessionStart hook (startup): the once-a-day note. It reads guard.log and prints one line per failed check, and nothing when every check passes. Standard library only.

Owner ruling 2026-10-13: a once-a-day session-start note, silent unless a check fails. It replaces the
weekly read of guard.log by hand. See decision guard-log-read-weekly.

The first start on a Central day (America/Chicago, the rule in hooks/local_time.py) runs the checks
and writes the done-today stamp, <config dir>/daily-note.stamp, holding that day. A later start on the
same day prints nothing and writes nothing. The window is the days since the stamp: the stamp day
through the day before today, at most 7 days. With no stamp, or a stamp that is not before today,
the window is the day before today. A day with no session start keeps its lines for the next start.

Checks, each over the window. Each failure is one stdout line of at most 240 characters. The line
names lint/guard_log_report.py, the reader to run for the detail.
- a `crash` line: a guard hook crashed.
- an `STE-fallback` line whose matched field ends fallback=crash.
- an `STE-unchecked` line: the lint could not run, so those writes are unknown, not clear.
- a rule whose denies on one day of the window reach DENY_FLOOR and exceed DENY_FACTOR times the
  daily mean of the 7 days before that day. The line names the rule.
- guard.log exists and cannot be read: unknown. A missing guard.log is not a failure.
A line's day is the date its timestamp is written with: guard.log holds Central wall time.

Seam: CLAUDE_DAILY_NOTE_NOW, an ISO-8601 instant with its UTC offset, in place of the clock.
Advisory, fail-open: any error prints one stderr line and exits 0.
"""
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in (HERE, os.path.join(HERE, "..", "lint")):
    if sub not in sys.path:
        sys.path.insert(0, sub)

MAX_WINDOW = 7    # days
DENY_FLOOR = 25   # denies in one day, below which a rule never fails
DENY_FACTOR = 3   # ponytail: fixed factor on a 7-day mean; tune from the reader's tables if it cries wolf
READER = "lint/guard_log_report.py"


def central_today():
    """The Central calendar day now. The one home of the DST rule is hooks/local_time.py."""
    import local_time
    seam = os.environ.get("CLAUDE_DAILY_NOTE_NOW")
    clock = (lambda: datetime.fromisoformat(seam)) if seam else (lambda: datetime.now(timezone.utc))
    return date.fromisoformat(re.search(r"\d{4}-\d\d-\d\d", local_time.line(clock)).group())


def read_stamp(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return date.fromisoformat(handle.read().strip())
    except (OSError, ValueError):
        return None


def failures(lines, window):
    """One line per failed check over the window, a list of consecutive days."""
    import guard_log_report as report
    days = {day.isoformat() for day in window}
    span = str(window[0]) if len(window) == 1 else "%s to %s" % (window[0], window[-1])
    tail = "Read: python %s --days %d" % (READER, len(window) + 1)
    rows = [row for row in map(report.parse_line, lines) if row and row.when.date().isoformat() in days]
    out = []
    crashes = [r for r in rows if r.decision == "crash"]
    if crashes:
        out.append("%d guard crash line(s) in guard.log, %s: a guard hook crashed. %s" % (len(crashes), span, tail))
    fallbacks = [r for r in rows if r.rule == "STE-fallback" and r.matched.endswith("fallback=crash")]
    if fallbacks:
        out.append("%d STE-fallback line(s) ended fallback=crash, %s: the STE fixer crashed. %s"
                   % (len(fallbacks), span, tail))
    unchecked = [r for r in rows if r.rule == "STE-unchecked"]
    if unchecked:
        out.append("%d STE-unchecked line(s), %s: the lint could not run, so those writes are unknown. %s"
                   % (len(unchecked), span, tail))

    def by_rule(end, count):  # the reader's tally: the `count` days up to and including `end`
        return report.summarize(lines, count, datetime.combine(end, time()))["by_rule"]

    for day in window:
        base = by_rule(day - timedelta(days=1), 7)
        for rule, tally in sorted(by_rule(day, 1).items()):
            deny = tally["deny"]
            if deny >= DENY_FLOOR and deny > DENY_FACTOR * base.get(rule, {"deny": 0})["deny"] / 7:
                out.append("Rule %s denied %d times on %s, over its 7-day baseline. %s"
                           % (rule[:60], deny, day, tail))
    return out


def main():
    try:
        config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
        stamp_path = os.path.join(config, "daily-note.stamp")
        today = central_today()
        stamp = read_stamp(stamp_path)
        if stamp == today:
            return 0
        start = stamp if stamp and stamp < today else today - timedelta(days=1)
        start = max(start, today - timedelta(days=MAX_WINDOW))
        window = [start + timedelta(days=i) for i in range((today - start).days)]
        out = []
        try:
            with open(os.path.join(config, "guard.log"), encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            out = failures(lines, window)
        except FileNotFoundError:
            pass
        except OSError as err:
            out = ["guard.log cannot be read (%s): its state is unknown. Read: python %s"
                   % (type(err).__name__, READER)]
        os.makedirs(config, exist_ok=True)
        with open(stamp_path, "w", encoding="utf-8") as handle:
            handle.write(today.isoformat() + "\n")
        for line in out:
            print(line[:240])
    except Exception as err:  # advisory hook: fail open; one stderr line shows in --debug
        print("daily_note: %s" % str(err).replace("\n", " "), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
