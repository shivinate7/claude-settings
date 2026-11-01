#!/usr/bin/env python3
"""Reads ~/.claude/guard.log: one tab-separated line per guard verdict, written by
hooks/guard_core.py record(). Nobody read it, so a rule that never fires, or fires too often, went unseen.
Prints per-rule deny/ask/noted counts (a `fixed` rewrite line, written by the removed STE guard, counts as noted; an `override`
line, a refusal an owner override lifted, adds an override column), denies per day,
other verdicts verbatim, bad-line count.
--days all reads the whole log. --all-rules lists every rule id the guard and the other guards can emit
(rule_audit.emitted_rule_ids, the one home), 0 counts included, with the date of each rule's
first line in the whole log, whatever --days says, or "never". A line of any decision counts as
fired; a combined STE line (`STE007,STE008`) credits each code; an id only the log holds keeps its row,
and so does every whole STE code with a first line in the log (no hook writes one now).
A line ends in the hook's session_id as a sixth field; a five-field line, or "-", is "unknown
session". --session <id> keeps one session's lines. --by-session adds counts per session.
A line starts with its time and UTC offset (2026-11-01T12:00:00+05:00). `Row.when` is that instant as
a naive time on the reading machine's clock; `Row.at` is the aware instant. A line from before the offset
was written has no zone: `when` is its naked time and `at` is None, never assumed Central.
--between START END (aware ISO 8601 times) prints the rows whose `at` falls in [START, END], and the
count of old lines that could fall in it under some zone, for the batch pace read (window()).
--rule narrows --between to one rule id (the pace read uses load-brake)."""
import argparse
import os
import re
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

# One home for the placeholder: hooks/guard_core.py. lint/ and hooks/ land side by side, in the
# repo and under ~/.claude, so the hop holds in both places (lint/report_guard.py does the same).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
from guard_core import LOG_CUT_MARK, SESSION_LOG_PLACEHOLDER  # noqa: E402

COUNTED = ("deny", "ask", "noted")
OVERRIDE = "override"  # a refusal an owner override lifted: counted, and a key only when present
FIRST = "first line"  # the --all-rules column: YYYY-MM-DD of the rule's first line in the whole log, or "never"
COMBINED = re.compile(r"STE\d+(,STE\d+)+")  # one id the removed STE guard wrote for several codes found at once
UNKNOWN = "unknown session"
BY_SESSION_ROWS = 200
Row = namedtuple("Row", "line when tool decision rule matched session at", defaults=(None,))
MAX_ZONE_HOURS = 14  # the widest UTC offset in use is +14:00, the narrowest -12:00
COMBINED_CODE = re.compile(r"STE\d+")
WHOLE_CODE = re.compile(r"STE\d{3}")  # a whole STE code: STE and three digits


def codes(rule):
    """The STE codes one combined rule id names, or [] for any other id. The guard's logger cuts a long
    id and ends it LOG_CUT_MARK; the last piece of a cut id may be a partial code, so it counts only
    when it is a whole code."""
    if not rule.endswith(LOG_CUT_MARK):
        return rule.split(",") if COMBINED.fullmatch(rule) else []
    parts = rule[:-len(LOG_CUT_MARK)].split(",")
    if len(parts) < 2 or not all(COMBINED_CODE.fullmatch(p) for p in parts[:-1]):
        return []
    return [p for p in parts if WHOLE_CODE.fullmatch(p)]


def parse_line(raw):
    """Return the Row for one guard.log line, or None when it is unreadable.

    The one reader of guard.log lines. Both shapes: five tab fields, or six with the session last.
    The time is ISO 8601, with a UTC offset or without. `at` is the aware instant for an offset
    time, None for an old one; `when` is naive reader-local: an offset line is
    converted to the reader's clock, an old line keeps its wall time as written.
    `session` is field 6 alone, or UNKNOWN for a five-field line, an empty field or the
    placeholder. A tab beyond field 6 stays in `matched`, never in `session`. Unreadable: fewer
    than four fields, or a bad timestamp.
    """
    line = raw.rstrip("\r\n")
    parts = line.split("\t")
    try:
        if len(parts) < 4:
            raise ValueError
        when = datetime.fromisoformat(parts[0])
    except ValueError:
        return None
    parts += [""] * (6 - len(parts))
    session = parts[5] if parts[5] not in ("", SESSION_LOG_PLACEHOLDER) else UNKNOWN
    matched = "\t".join([parts[4]] + parts[6:])
    at = None
    if when.tzinfo is not None:
        at = when
        when = when.astimezone().replace(tzinfo=None)
    return Row(line, when, parts[1], parts[2], parts[3], matched, session, at)


def window(lines, start, end, rule=None):
    """Return (rows whose `at` is in [start, end], unknown_count). `start` and `end` are aware.

    An old line has no zone, so it is never a row. It counts as unknown when its naked time, read as
    wall time against the bounds' UTC wall time, is within MAX_ZONE_HOURS of the window: some zone
    could put it inside. `rule` keeps one rule id; a line of another rule counts nowhere.
    """
    rows, unknown = [], 0
    low = start.astimezone(timezone.utc).replace(tzinfo=None) - timedelta(hours=MAX_ZONE_HOURS)
    high = end.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(hours=MAX_ZONE_HOURS)
    for raw in lines:
        row = parse_line(raw)
        if row is None or (rule is not None and row.rule != rule):
            continue
        if row.at is not None:
            if start <= row.at <= end:
                rows.append(row)
        elif low <= row.when <= high:
            unknown += 1
    return rows, unknown


def summarize(lines, days, now, session=None):
    if session == SESSION_LOG_PLACEHOLDER:
        session = UNKNOWN  # --session - names the lines whose session is unknown
    end = now.date()
    window = [] if days is None else [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    out = {"by_rule": {}, "per_day": dict.fromkeys(window, 0), "other": [], "unreadable": 0,
           "by_session": {}, "first": {}}
    for raw in lines:
        row = parse_line(raw)
        if row is None:
            out["unreadable"] += 1
            continue
        day = row.when.date().isoformat()
        for rule_id in [row.rule] + codes(row.rule):
            out["first"][rule_id] = min(day, out["first"].get(rule_id, day))
        if days is None:
            out["per_day"].setdefault(day, 0)
        elif day not in out["per_day"]:
            continue
        decision, rule, label = row.decision, row.rule, row.session
        if session is not None and label != session:
            continue
        if decision == "fixed":
            decision = "noted"  # an old STE guard rewrite line: counted as a note, its STE codes are its rule
        if decision not in COUNTED + (OVERRIDE,):
            out["other"].append(row.line)
            continue
        row = out["by_rule"].setdefault(rule, dict.fromkeys(COUNTED, 0))
        row[decision] = row.get(decision, 0) + 1
        by_rule = out["by_session"].setdefault(label, {})
        cell = by_rule.setdefault(rule, dict.fromkeys(COUNTED, 0))
        cell[decision] = cell.get(decision, 0) + 1
        if decision == "deny":
            out["per_day"][day] += 1
    return out


def all_rules(s, ids):
    """The per-rule rows with a row for every id in `ids` and a FIRST column. A combined STE id adds
    its counts to each code, and keeps its own row."""
    by_rule = {r: dict(c) for r, c in s["by_rule"].items()}
    for rule_id, c in s["by_rule"].items():
        for code in codes(rule_id):
            mine = by_rule.setdefault(code, dict.fromkeys(COUNTED, 0))
            for k, n in c.items():
                mine[k] = mine.get(k, 0) + n
    for rule_id in list(ids) + [r for r in s["first"] if WHOLE_CODE.fullmatch(r)]:
        by_rule.setdefault(rule_id, dict.fromkeys(COUNTED, 0))
    for rule_id, c in by_rule.items():
        c[FIRST] = s["first"].get(rule_id, "never")
    return by_rule


def render(s, by_session=False, ids=None):
    by_rule = s["by_rule"] if ids is None else all_rules(s, ids)
    rows = sorted(by_rule.items(), key=lambda kv: (-kv[1]["deny"], kv[0]))
    # The override column shows only once some pass lifted a refusal, so a log with no lifted act keeps the old columns.
    cols = COUNTED + ((OVERRIDE,) if any(OVERRIDE in c for _, c in rows) else ())
    rule_cols = cols + ((FIRST,) if ids is not None else ())

    def table(lead, items, cols=cols):
        head = lead + list(cols)
        out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        return out + ["| " + " | ".join(list(keys) + [str(c.get(k, 0)) for k in cols]) + " |"
                      for keys, c in items]

    out = table(["rule"], [((r,), c) for r, c in rows], rule_cols)
    if by_session:
        flat = [(label, r, c) for label, rules in s["by_session"].items() for r, c in rules.items()]
        flat.sort(key=lambda t: (-t[2]["deny"], t[0], t[1]))
        out += [""] + table(["session", "rule"], [((label, r), c) for label, r, c in flat[:BY_SESSION_ROWS]])
        if len(flat) > BY_SESSION_ROWS:
            out.append("... and %d more" % (len(flat) - BY_SESSION_ROWS))
    out += ["", "| day | denies |", "|---|---|"]
    out += ["| %s | %d |" % kv for kv in sorted(s["per_day"].items())]
    out += ["", "```"] + s["other"] + ["```", "", "unreadable: %d" % s["unreadable"]]
    return "\n".join(out)


def days_arg(text):
    if text == "all":
        return None
    try:
        days = int(text)
    except ValueError:
        days = 0
    if days < 1:
        raise argparse.ArgumentTypeError("--days takes a whole number of days, or the word all (got %r)" % text)
    return days


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    # Same dir as hooks/guard.py config_dir(); a copy, since importing guard is heavy.
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    ap.add_argument("--log", default=os.path.join(home, "guard.log"))
    ap.add_argument("--days", type=days_arg, default=7, help="a number of days, or all for the whole log")
    ap.add_argument("--all-rules", action="store_true",
                    help="list every rule id the guard and the other guards can emit, with its first-line date or never")
    ap.add_argument("--session", help="keep only this session's lines (exact id)")
    ap.add_argument("--by-session", action="store_true", help="add counts per session")
    ap.add_argument("--between", nargs=2, metavar=("START", "END"), type=datetime.fromisoformat,
                    help="print the rows inside this window (aware ISO 8601 times) and the old-line unknown count")
    ap.add_argument("--rule", help="with --between: keep one rule id")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # absent when stdout is redirected to StringIO
        sys.stdout.reconfigure(errors="replace")
    if args.between and any(t.tzinfo is None for t in args.between):
        ap.error("--between takes times with a UTC offset, such as 2026-11-01T16:55:00-06:00")
    ids = None
    if args.all_rules:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # `python -I` leaves the script folder off the path
        import rule_audit
        ids = rule_audit.emitted_rule_ids()
    try:
        with open(args.log, encoding="utf-8", errors="replace") as handle:
            if args.between:
                rows, unknown = window(handle, args.between[0], args.between[1], args.rule)
                print("\n".join(row.line for row in rows))
                print("unknown (old lines with no zone that could fall inside): %d" % unknown)
                return 0
            print(render(summarize(handle, args.days, datetime.now(), args.session), args.by_session, ids))
    except FileNotFoundError:
        print("unreadable: log not found")
    except OSError as err:
        print("unreadable: log not readable (%s)" % type(err).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
