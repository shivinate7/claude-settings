#!/usr/bin/env python3
"""Flags test cases that run far longer than the rest of their group. It reports only; it always exits 0.

    python3 lint/case_times_report.py [--dir FOLDER]

FOLDER holds the job row files (one JSONL file per job, written by testing/case_times/). With no --dir it
reads RUNNER_TEMP/case-times. Each row has suite, group, case, s, fixture_s, outcome.

Rows from every file are merged and grouped by (suite, group): the group is the suite file for unittest and
the family for the guard runner. A skipped case is left out of its group, since it did no work. A case is
flagged when its time (`s` plus `fixture_s`; a row with no `fixture_s` reads 0.0) is at least FLAG_RATIO times
its group's median time and at least FLAG_FLOOR_S seconds. A group under MIN_GROUP cases is not judged. The flags
print with the largest excess over the median first, each with the case's total, its `s` and its `fixture_s`.

It prints `read: <path>` for each row file it read, then `missing: <job>` for each job named in the env
CASE_TIMES_JOBS (comma-separated) that has no `<job>.jsonl` file.

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
    """(rows, paths of the files read) under `folder`. Raises ValueError with the file and line when a row cannot be read."""
    rows = []
    paths = []
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(root, name)
            paths.append(path)
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
                    fixture = row.get("fixture_s", 0.0)
                    if isinstance(fixture, bool) or not isinstance(fixture, (int, float)):
                        raise ValueError("%s line %d has a fixture_s that is not a number" % (path, number))
                    rows.append(row)
    if not paths:
        raise ValueError("no .jsonl row file under %s" % folder)
    if not rows:
        raise ValueError("the row files under %s hold no rows" % folder)
    return rows, paths


def missing_jobs(paths):
    """The jobs named in env CASE_TIMES_JOBS (comma-separated) that have no `<job>.jsonl` among `paths`."""
    have = {os.path.basename(path) for path in paths}
    named = [job.strip() for job in os.environ.get("CASE_TIMES_JOBS", "").split(",")]
    return [job for job in named if job and job + ".jsonl" not in have]


def case_s(row):
    """A case's whole time: its own `s` plus its fixture time."""
    return row["s"] + row.get("fixture_s", 0.0)


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
        median = statistics.median(case_s(row) for row in members)
        for row in members:
            total = case_s(row)
            if total >= FLAG_RATIO * median and total >= FLAG_FLOOR_S:
                found.append((total - median, median, row))
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
        rows, paths = read_rows(folder)
    except (OSError, ValueError) as error:
        print("unknown: could not read the case times: %s" % error)
        return 0
    for path in paths:
        print("read: %s" % path)
    for job in missing_jobs(paths):
        print("missing: %s" % job)
    found, judged = flagged(rows)
    print("%d cases read, %d groups judged (flag: at least %gx the group median and at least %g s)"
          % (len(rows), judged, FLAG_RATIO, FLAG_FLOOR_S))
    if not found:
        print("No case flagged.")
    for excess, median, row in found:
        total = case_s(row)
        print("%8.2f s  %5.1fx median %.3f s  (s %.2f + fixture_s %.2f)  %s  [%s]  %s"
              % (total, total / median if median else float("inf"), median, row["s"], row.get("fixture_s", 0.0),
                 row["case"], row["group"], row["suite"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
