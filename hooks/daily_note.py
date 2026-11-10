#!/usr/bin/env python3
"""At the first session start of each US Central day, prints one line for each failed check in the recent guard.log. Prints nothing when every check passes.

A once-a-day session-start note, silent unless a check fails (decision guard-log-read-weekly).

The first start on a Central day (America/Chicago, the rule in hooks/local_time.py) runs the checks
and writes the done-today stamp, <config dir>/daily-note.stamp, holding that day. A later start on the
same day prints nothing and writes nothing. The window is the days since the stamp: the stamp day
through the day before today, at most 7 days. With no stamp, or a stamp that is not before today,
the window is the day before today. A day with no session start keeps its lines for the next start.

Checks, each over the window. Each failure is one stdout line of 240 characters or fewer, unless
the short head plus the whole tail is longer. It ends with `Read:` and its reader by absolute path.
A line over 240 swaps its head for a short head, its count and what failed, such as
"3 guard crash line(s):". The short head and the `Read:` tail are never cut. The guard.log checks name
lint/guard_log_report.py, beside this hook's folder, so the path holds from any working folder.
- a `crash` line: a guard hook crashed.
- guard.log exists and cannot be read: unknown. A missing guard.log is not a failure.
- agent-end reap runs killed or crashed. The reader is the agent-end payload log,
  <config dir>/state/agent-end-payloads.jsonl (janitor/agent_end_reap.py `log`). A run counts when
  its run id's time (the part after the pid) falls on a window day, and it has a `started` row
  that no `done` row follows, or a row with an `error` key. A malformed row is skipped. A started
  row can also be a done row that `log()` dropped; the drops line below names that. A missing file
  is not a failure; an unreadable one is unknown.
- dropped payload-log rows. The reader is the drops file, <config dir>/state/agent-end-drops.jsonl
  (janitor/agent_end_reap.py `log`, which appends one JSON row, `at`, `run`, `error`, only when a
  write fails). A row counts when its `at` falls on a window day. A malformed row is skipped.
  A missing file is not a failure; an unreadable one is unknown.
- the daily sweep's error log, <config dir>/janitor/launchd-sweep.err.log
  (janitor/install_launchd.py `build_plist`), exists, is not empty, and was last written on a window
  day. The line names it and launchd-sweep.log, its stdout log. A missing file is not a failure.
The agent-end, drops and sweep checks read files already on disk, after the done-today stamp check: they
start no process and write nothing beyond the stamp. The drops file grows only on a failed write.
There is no volume check: refusals grow with use, so a count jump over a 7-day baseline
fires on ordinary days (debt note daily-note-no-volume-check).
A line carries its UTC offset (an old line has none). Its day is the date of the reader-local `when`.

Before the done-today stamp check, at every start, it also prints the one line of
precompact_handoff.cc_version_check(): the installed Claude Code changed a compaction fact the
handoff hooks rely on (docs/decisions/precompact-handoff.md, item 12). That check reads the binary
only when its path, size or mtime is new, so a normal start costs a cache read and one stat. It prints nothing
when the facts match, and it starts no process.

Seam: CLAUDE_DAILY_NOTE_NOW, an ISO-8601 instant with its UTC offset, in place of the clock.
Advisory, fail-open: any error prints one stderr line and exits 0.
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in (HERE, os.path.join(HERE, "..", "lint")):
    if sub not in sys.path:
        sys.path.insert(0, sub)

MAX_WINDOW = 7    # days
MAX_LINE = 240    # characters in one failure line
READER = os.path.normpath(os.path.join(HERE, "..", "lint", "guard_log_report.py"))


def central_day(at):
    """The Central calendar day of an aware instant. The one home of the DST rule is hooks/local_time.py."""
    import local_time
    return date.fromisoformat(re.search(r"\d{4}-\d\d-\d\d", local_time.line(lambda: at)).group())


def central_today():
    seam = os.environ.get("CLAUDE_DAILY_NOTE_NOW")
    return central_day(datetime.fromisoformat(seam) if seam else datetime.now(timezone.utc))


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
    span = span_of(window)
    tail = "Read: python %s" % READER
    rows = [row for row in map(report.parse_line, lines) if row and row.when.date().isoformat() in days]
    out = []
    crashes = [r for r in rows if r.decision == "crash"]
    if crashes:
        out.append(fit("%d guard crash line(s), %s: a guard hook crashed." % (len(crashes), span),
                       "%d guard crash line(s):" % len(crashes), tail))
    return out


def fit(head, short_head, tail):
    """One failure line: HEAD, then TAIL (the `Read:` part). When that passes MAX_LINE, SHORT_HEAD, the
    count and what failed, takes HEAD's place. Neither SHORT_HEAD nor TAIL is ever cut, so the line passes
    MAX_LINE only when those two are longer than it."""
    line = "%s %s" % (head, tail)
    return line if len(line) <= MAX_LINE else "%s %s" % (short_head, tail)


def span_of(window):
    return str(window[0]) if len(window) == 1 else "%s to %s" % (window[0], window[-1])


def run_day(run):
    """The Central day in an agent-end run id, "<pid>-<time_ns>". None when the id has no readable time."""
    try:
        return central_day(datetime.fromtimestamp(int(run.split("-", 1)[1]) / 1e9, timezone.utc))
    except (AttributeError, IndexError, ValueError, OverflowError, OSError):
        return None


def agent_end_failures(path, window):
    """One line when an agent-end reap run on a window day was killed or crashed, from the payload log
    at PATH. A run is one `run` id: its `started` row with no `done` row, or any row with `error`."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            rows = handle.readlines()
    except FileNotFoundError:
        return []
    except OSError as err:
        head = "agent-end payload log cannot be read (%s): its state is unknown." % type(err).__name__
        return [fit(head, head, "Read: " + path)]  # the short head keeps "unknown": a cut line must not read as clear
    days = set(window)
    runs = {}
    for text in rows:
        try:
            row = json.loads(text)
            run, state = row["run"], row.get("state")
            if not isinstance(run, str):
                continue
        except (ValueError, KeyError, AttributeError, TypeError):
            continue
        seen = runs.setdefault(run, {"started": False, "done": False, "bad": False})
        seen["started"] = seen["started"] or state == "started"
        seen["done"] = seen["done"] or state == "done"
        seen["bad"] = seen["bad"] or "error" in row
    bad = [run for run, seen in runs.items()
           if (seen["bad"] or (seen["started"] and not seen["done"])) and run_day(run) in days]
    if not bad:
        return []
    return [fit("%d agent-end reap run(s) killed or crashed, %s: servers may be left (or a done row "
                "that log() dropped, see the drops line)." % (len(bad), span_of(window)),
                "%d agent-end reap run(s) killed or crashed:" % len(bad), "Read: " + path)]


def drops_failures(path, window):
    """One line when log() dropped a payload-log row on a window day, from the drops file at PATH.
    A row counts when its `at` (the log's time format, with a UTC offset) falls on a window day."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            rows = handle.readlines()
    except FileNotFoundError:
        return []
    except OSError as err:
        return [fit("agent-end drops file cannot be read (%s): its state is unknown." % type(err).__name__,
                    "agent-end drops file cannot be read (%s):" % type(err).__name__, "Read: " + path)]
    days = set(window)
    count = 0
    for text in rows:
        try:
            when = datetime.strptime(json.loads(text)["at"], "%Y-%m-%dT%H:%M:%S%z")
            day = central_day(when)
        except (ValueError, KeyError, TypeError, OverflowError, OSError):  # OverflowError: `at` near year 9999
            continue
        if day in days:
            count += 1
    if not count:
        return []
    return [fit("%d agent-end payload-log row(s) dropped, %s: log() could not write them." % (count, span_of(window)),
                "%d agent-end payload-log row(s) dropped:" % count, "Read: " + path)]


def sweep_error_failures(err_path, out_path, window):
    """One line when the daily sweep's error log exists, is not empty and was last written on a window day."""
    try:
        info = os.stat(err_path)
    except FileNotFoundError:
        return []
    except OSError as err:
        return [fit("launchd-sweep.err.log cannot be read (%s): its state is unknown." % type(err).__name__,
                    "launchd-sweep.err.log cannot be read (%s):" % type(err).__name__,
                    "Read: tail %s; stdout: %s" % (err_path, out_path))]
    day = central_day(datetime.fromtimestamp(info.st_mtime, timezone.utc))
    if info.st_size <= 0 or day not in set(window):
        return []
    return [fit("daily sweep wrote errors (%d bytes, %s)." % (info.st_size, day),
                "daily sweep errors (%d bytes):" % info.st_size,
                "Read: tail %s; stdout: %s" % (err_path, out_path))]


def main():
    try:
        from shared_names import config_dir  # the one home of the config dir; inside the try, so a lone copy exits 0
        config = config_dir()
        stamp_path = os.path.join(config, "daily-note.stamp")
        today = central_today()
        try:
            import precompact_handoff
            line = precompact_handoff.cc_version_check()
            if line:
                print(line[:240])
        except Exception as err:  # fail open: the guard.log checks below still run
            print("daily_note: cc_version_check: %s" % str(err).replace("\n", " "), file=sys.stderr)
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
            head = "guard.log cannot be read (%s): its state is unknown." % type(err).__name__
            out = [fit(head, head, "Read: python %s" % READER)]  # the short head keeps "unknown"
        out += agent_end_failures(os.path.join(config, "state", "agent-end-payloads.jsonl"), window)
        out += drops_failures(os.path.join(config, "state", "agent-end-drops.jsonl"), window)
        out += sweep_error_failures(os.path.join(config, "janitor", "launchd-sweep.err.log"),
                                    os.path.join(config, "janitor", "launchd-sweep.log"), window)
        os.makedirs(config, exist_ok=True)
        with open(stamp_path, "w", encoding="utf-8") as handle:
            handle.write(today.isoformat() + "\n")
        for line in out:
            print(line)
    except Exception as err:  # advisory hook: fail open; one stderr line shows in --debug
        print("daily_note: %s" % str(err).replace("\n", " "), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
