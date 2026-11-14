#!/usr/bin/env python3
"""Skip lane-touched-tests' macOS job while a `checks` run on an integration branch (batch-*) is queued or in progress (R58 point 3).

Reads MATRIX (the selector's matrix JSON) and ANY, drops the macos-latest entry when an integration PR run is busy, and writes
`matrix` and `any` to $GITHUB_OUTPUT. A run list that cannot be read is unknown: the matrix stays whole and the log says so.
Env: GH_TOKEN, REPO (to read the runs); RUNS_JSON stands in for the API answer in tests.
"""
import json
import os
import subprocess
import sys

BUSY = ("queued", "in_progress")


def runs_json():
    given = os.environ.get("RUNS_JSON")
    if given:
        return given
    out = []
    for status in BUSY:
        r = subprocess.run(["gh", "api", "-X", "GET", "repos/%s/actions/workflows/checks.yml/runs" % os.environ["REPO"],
                            "-f", "status=" + status, "-f", "per_page=100"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "gh api failed")
        out.extend(json.loads(r.stdout).get("workflow_runs", []))
    return json.dumps({"workflow_runs": out})


def batch_busy(text):
    return any(r.get("head_branch", "").startswith("batch-") and r.get("status") in BUSY
               for r in json.loads(text).get("workflow_runs", []))


def main():
    matrix = json.loads(os.environ["MATRIX"])
    any_ = os.environ.get("ANY", "false")
    try:
        busy = batch_busy(runs_json())
    except Exception as e:
        print("batch-macos-skip: integration PR run state unknown (%s); the macOS job is kept" % e)
        busy = False
    if busy:
        matrix = {"include": [e for e in matrix.get("include", []) if e.get("os") != "macos-latest"]}
        any_ = "true" if matrix["include"] else "false"
        print("batch-macos-skip: a batch checks run is in progress, so the macOS job is skipped")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("matrix=%s\nany=%s\n" % (json.dumps(matrix), any_))
    return 0


if __name__ == "__main__":
    sys.exit(main())
