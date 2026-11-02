#!/usr/bin/env python3
"""The one home of the clearing rule of the red-main check (decision no-merge-onto-red-main). alarm.sh and
merge/merge.py `Host.base_state` both call it.

clears(red_jobs, newer_jobs): a red run R is cleared by a newer completed run N of another event group of the
same workflow file when N ran every job R ran and each of them has the conclusion `success`. Jobs are dicts with
`name` and `conclusion`. R's job set is the names of R's jobs whose conclusion is not `skipped`. An empty set
clears nothing, so a startup_failure run with no job stays red. Names are compared exactly. A name that N has
twice needs every one of them to be `success`: a skipped, cancelled or failed twin is not a pass. Extra jobs in N
are fine. The caller checks that N is completed, successful and newer than R, and reads the jobs.

  clears.py RED_JOBS_JSON NEWER_JOBS_JSON   prints yes or no; a bad argument prints nothing on stdout and exits 2
"""
import json
import sys


def clears(red_jobs, newer_jobs):
    need = {j.get("name") for j in red_jobs if j.get("conclusion") != "skipped"}
    if not need:
        return False
    return all(
        (got := [j.get("conclusion") for j in newer_jobs if j.get("name") == name]) and all(c == "success" for c in got)
        for name in need
    )


if __name__ == "__main__":
    try:
        red, newer = (json.loads(a) for a in sys.argv[1:])
        if not all(isinstance(x, list) and all(isinstance(j, dict) for j in x) for x in (red, newer)):
            raise ValueError("each argument must be a JSON list of job objects")
    except (ValueError, TypeError) as e:
        print(f"clears.py: need two JSON job lists: {e}", file=sys.stderr)
        sys.exit(2)
    print("yes" if clears(red, newer) else "no")
