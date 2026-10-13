#!/usr/bin/env python3
"""Reads ~/.claude/guard.log: one tab-separated line per guard verdict, written by
hooks/guard.py record(). Nobody read it, so a rule that never fires, or fires too often, went unseen.
Prints per-rule deny/ask/noted counts, denies per day, other verdicts verbatim, bad-line count.
A line ends in the hook's session_id as a sixth field; a five-field line, or "-", is "unknown
session". --session <id> keeps one session's lines. --by-session adds counts per session."""
import argparse
import os
import sys
from datetime import datetime, timedelta

COUNTED = ("deny", "ask", "noted")
UNKNOWN = "unknown session"


def summarize(lines, days, now, session=None):
    end = now.date()
    window = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    out = {"by_rule": {}, "per_day": dict.fromkeys(window, 0), "other": [], "unreadable": 0,
           "by_session": {}}
    for raw in lines:
        line = raw.rstrip("\r\n")
        parts = line.split("\t", 5)
        try:
            if len(parts) < 4:
                raise ValueError
            day = datetime.fromisoformat(parts[0]).date().isoformat()
        except ValueError:
            out["unreadable"] += 1
            continue
        if day not in out["per_day"]:
            continue
        decision, rule = parts[2], parts[3]
        label = parts[5] if len(parts) > 5 and parts[5] not in ("", "-") else UNKNOWN
        if session is not None and label != session:
            continue
        if decision not in COUNTED:
            out["other"].append(line)
            continue
        row = out["by_rule"].setdefault(rule, dict.fromkeys(COUNTED, 0))
        row[decision] += 1
        by_rule = out["by_session"].setdefault(label, {})
        by_rule.setdefault(rule, dict.fromkeys(COUNTED, 0))[decision] += 1
        if decision == "deny":
            out["per_day"][day] += 1
    return out


def render(s, by_session=False):
    rows = sorted(s["by_rule"].items(), key=lambda kv: (-kv[1]["deny"], kv[0]))
    out = ["| rule | deny | ask | noted |", "|---|---|---|---|"]
    out += ["| %s | %d | %d | %d |" % (r, c["deny"], c["ask"], c["noted"]) for r, c in rows]
    if by_session:
        out += ["", "| session | rule | deny | ask | noted |", "|---|---|---|---|---|"]
        for label, rules in sorted(s["by_session"].items()):
            out += ["| %s | %s | %d | %d | %d |" % (label, r, c["deny"], c["ask"], c["noted"])
                    for r, c in sorted(rules.items(), key=lambda kv: (-kv[1]["deny"], kv[0]))]
    out += ["", "| day | denies |", "|---|---|"]
    out += ["| %s | %d |" % kv for kv in sorted(s["per_day"].items())]
    out += ["", "```"] + s["other"] + ["```", "", "unreadable: %d" % s["unreadable"]]
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    # Same dir as hooks/guard.py config_dir(); a copy, since importing guard is heavy.
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    ap.add_argument("--log", default=os.path.join(home, "guard.log"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--session", help="keep only this session's lines (exact id)")
    ap.add_argument("--by-session", action="store_true", help="add counts per session")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # absent when stdout is redirected to StringIO
        sys.stdout.reconfigure(errors="replace")
    try:
        with open(args.log, encoding="utf-8", errors="replace") as handle:
            print(render(summarize(handle, args.days, datetime.now(), args.session), args.by_session))
    except FileNotFoundError:
        print("unreadable: log not found")
    except OSError as err:
        print("unreadable: log not readable (%s)" % type(err).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
