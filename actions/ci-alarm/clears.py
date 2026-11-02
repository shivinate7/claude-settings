#!/usr/bin/env python3
"""The one home of the clearing rule of the red-main check (decision no-merge-onto-red-main). alarm.sh and
merge/merge.py `Host.base_state` both call it.

candidate(red, runs, groups): the runs that may clear the red run `red`. Runs are dicts with `id`, `wf` (the
workflow's identity: its file path or id), `event`, `status`, `conclusion` and `created_at` (ISO times compare as
text). `groups` maps an event to its group (actions/ci-alarm/events.json); an event not in it is never judged. Per
other group of the same workflow, the newest completed run is taken; it is a candidate when it succeeded and is
newer than `red` by creation time. That is the same-group rule: the newest completed run decides. A newer run that
is cancelled or red is its group's newest, so it is no candidate, and an older success behind it never stands in
for it. A run still going is skipped and clears nothing itself, so the newest completed run behind it decides.

clears(red_jobs, newer_jobs): a red run R is cleared by a candidate N when N ran every job R ran and each of them
has the conclusion `success`. Jobs are dicts with `name` and `conclusion`. R's job set is the names of R's jobs
whose conclusion is not `skipped`. An empty set clears nothing, so a startup_failure run with no job stays red.
Names are compared exactly. A name that N has twice needs every one of them to be `success`: a skipped, cancelled
or failed twin is not a pass. Extra jobs in N are fine. The caller reads the jobs.

Command line, every input a JSON file (one argv string holds 128 KB at most, and a job list can pass that):
  clears.py candidates RUNS_FILE GROUPS_FILE RED_ID   prints the id of each candidate, one a line
  clears.py clears RED_JOBS_FILE NEWER_JOBS_FILE      prints yes or no
A bad argument prints nothing on stdout and exits 2.
"""
import json
import sys


def candidate(red, runs, groups):
    group = groups.get(red.get("event"))
    if group is None or not red.get("created_at"):
        return []
    newest = {}
    for r in runs:
        g = groups.get(r.get("event"))
        if g is None or g == group or r.get("wf") != red.get("wf") or r.get("status") != "completed" or not r.get("created_at"):
            continue
        if g not in newest or r["created_at"] > newest[g]["created_at"]:
            newest[g] = r
    return [r for r in newest.values() if r.get("conclusion") == "success" and r["created_at"] > red["created_at"]]


def clears(red_jobs, newer_jobs):
    need = {j.get("name") for j in red_jobs if j.get("conclusion") != "skipped"}
    if not need:
        return False
    return all(
        (got := [j.get("conclusion") for j in newer_jobs if j.get("name") == name]) and all(c == "success" for c in got)
        for name in need
    )


def _load(path, kind):
    with open(path) as f:
        data = json.load(f)
    if kind == "dict" and not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object")
    if kind == "list" and not (isinstance(data, list) and all(isinstance(x, dict) for x in data)):
        raise ValueError(f"{path} must hold a JSON list of objects")
    return data


def main(argv):
    try:
        if len(argv) == 4 and argv[0] == "candidates":
            runs, groups = _load(argv[1], "list"), _load(argv[2], "dict")
            red = [r for r in runs if str(r.get("id")) == argv[3]]
            if len(red) != 1:
                raise ValueError(f"run {argv[3]} is not in {argv[1]} exactly once")
            print("".join(f"{r['id']}\n" for r in candidate(red[0], runs, groups)), end="")
        elif len(argv) == 3 and argv[0] == "clears":
            print("yes" if clears(_load(argv[1], "list"), _load(argv[2], "list")) else "no")
        else:
            raise ValueError("usage: clears.py candidates RUNS GROUPS RED_ID | clears.py clears RED_JOBS NEWER_JOBS")
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"clears.py: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
