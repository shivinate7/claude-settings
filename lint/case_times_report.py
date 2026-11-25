#!/usr/bin/env python3
"""Flags test cases that run far longer than the rest of their group. It reports only; it always exits 0.

    python3 lint/case_times_report.py [--dir FOLDER]

FOLDER holds the job row files (one JSONL file per job, written by testing/case_times/). With no --dir it
reads RUNNER_TEMP/case-times. Each row has suite, group, case, s, fixture_s, outcome.

Rows from every file are merged and grouped by (suite, group): the group is the suite file for unittest and
the family for the guard runner. A skipped case is left out of its group, since it did no work. A case is
flagged when its `s` is at least FLAG_RATIO times its group's median and at least FLAG_FLOOR_S seconds. A group
under MIN_GROUP cases is not judged. The flags print with the largest excess over the median first.

When a read fails, or no row is found, it prints `unknown` and says why. It never prints "nothing flagged"
for a read that did not happen.

Known false flag: a module-level fixture that a unittest file builds lazily inside its first case lands on
that file's first case, so that case can be flagged.
"""
import argparse
import json
import os
import statistics
import sys

FLAG_RATIO = 10
FLAG_FLOOR_S = 1.0
MIN_GROUP = 5
KEYS = ("suite", "group", "case", "s", "outcome")


def read_rows(folder):
    """Every row under `folder`. Raises ValueError with the file and line when a row cannot be read."""
    rows = []
    found = False
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if not name.endswith(".jsonl"):
                continue
            found = True
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as f:
                for number, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        raise ValueError("%s line %d is not JSON" % (path, number))
                    if not isinstance(row, dict) or any(key not in row for key in KEYS) \
                            or isinstance(row["s"], bool) or not isinstance(row["s"], (int, float)):
                        raise ValueError("%s line %d is not a case row" % (path, number))
                    rows.append(row)
    if not found:
        raise ValueError("no .jsonl row file under %s" % folder)
    if not rows:
        raise ValueError("the row files under %s hold no rows" % folder)
    return rows


def flagged(rows):
    """(excess seconds, median, row) for each flagged case, largest excess first, plus the groups judged."""
    groups = {}
    for row in rows:
        if row["outcome"] != "skip":
            groups.setdefault((row["suite"], row["group"]), []).append(row)
    found = []
    judged = 0
    for members in groups.values():
        if len(members) < MIN_GROUP:
            continue
        judged += 1
        median = statistics.median(row["s"] for row in members)
        for row in members:
            if row["s"] >= FLAG_RATIO * median and row["s"] >= FLAG_FLOOR_S:
                found.append((row["s"] - median, median, row))
    found.sort(key=lambda item: -item[0])
    return found, judged


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", help="folder holding the job row files (default RUNNER_TEMP/case-times)")
    args = parser.parse_args(argv)
    folder = args.dir
    if folder is None:
        temp = os.environ.get("RUNNER_TEMP")
        if not temp:
            print("unknown: no --dir given and RUNNER_TEMP is not set")
            return 0
        folder = os.path.join(temp, "case-times")
    try:
        rows = read_rows(folder)
    except (OSError, ValueError) as error:
        print("unknown: could not read the case times: %s" % error)
        return 0
    found, judged = flagged(rows)
    print("%d cases read, %d groups judged (flag: at least %gx the group median and at least %g s)"
          % (len(rows), judged, FLAG_RATIO, FLAG_FLOOR_S))
    if not found:
        print("No case flagged.")
    for excess, median, row in found:
        print("%8.2f s  %5.1fx median %.3f s  %s  [%s]  %s"
              % (row["s"], row["s"] / median if median else float("inf"), median, row["case"], row["group"],
                 row["suite"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
