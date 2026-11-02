#!/usr/bin/env python3
"""At the first session start of each US Central day, prints one line for each failed check in the recent guard.log. Prints nothing when every check passes.

A once-a-day session-start note, silent unless a check fails (decision guard-log-read-weekly).

The first start on a Central day (America/Chicago, the rule in hooks/local_time.py) runs the checks
and writes the done-today stamp, <config dir>/daily-note.stamp, holding that day. A later start on the
same day prints nothing and writes nothing. The window is the days since the stamp: the stamp day
through the day before today, at most 7 days. With no stamp, or a stamp that is not before today,
the window is the day before today. A day with no session start keeps its lines for the next start.

Checks, each over the window. Each failure is one stdout line of at most 240 characters. The line
names the reader, lint/guard_log_report.py, by its absolute path beside this hook's folder, so the
path holds from any working folder.
- a `crash` line: a guard hook crashed.
- guard.log exists and cannot be read: unknown. A missing guard.log is not a failure.
There is no volume check: refusals grew with use, and a count check fired on 6 of 14 real days.
A line carries its UTC offset (an old line has none). Its day is the date of the reader-local `when`.

Seam: CLAUDE_DAILY_NOTE_NOW, an ISO-8601 instant with its UTC offset, in place of the clock.
Advisory, fail-open: any error prints one stderr line and exits 0.
"""
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in (HERE, os.path.join(HERE, "..", "lint")):
    if sub not in sys.path:
        sys.path.insert(0, sub)

MAX_WINDOW = 7    # days
READER = os.path.normpath(os.path.join(HERE, "..", "lint", "guard_log_report.py"))


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
    import guard_log_report as report  # the one reader of guard.log lines
    days = {day.isoformat() for day in window}
    span = str(window[0]) if len(window) == 1 else "%s to %s" % (window[0], window[-1])
    tail = "Read: python %s" % READER
    rows = [row for row in map(report.parse_line, lines) if row and row.when.date().isoformat() in days]
    out = []
    crashes = [r for r in rows if r.decision == "crash"]
    if crashes:
        out.append("%d guard crash line(s), %s: a guard hook crashed. %s" % (len(crashes), span, tail))
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
