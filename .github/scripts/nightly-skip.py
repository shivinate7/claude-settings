#!/usr/bin/env python3
"""The nightly skip decision: it decides whether the 03:17 scheduled run of checks.yml can skip (R61, decision test-strategy-reset).

Writes one line to $GITHUB_OUTPUT (stdout when unset): skip=true or skip=false. It exits 0 on every path, so the skip job
is a visible success and scope reads its output.

skip=true only when BOTH hold:
  1. main's head (HEAD_SHA) has a completed, successful push run of checks.yml on main;
  2. the newest completed schedule run of checks.yml (by created_at) is successful. A skipped nightly concludes success only
     when the nightly before it was green, so a skipped run never supersedes a red one: the newest completed run decides.
Any read failure writes skip=false and says "unknown": an unknown state runs everything, never skips.

Input (env): REPO (owner/name), HEAD_SHA, GH_TOKEN. RUNS_JSON is a stand-in for the read: a JSON list of run records in the
shape of the Actions runs API (lint/test_nightly_skip.py). Cost: two runs reads per nightly, no file, no process kept.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

WORKFLOW = ".github/workflows/checks.yml"
API = "https://api.github.com"


class Unknown(Exception):
    """The runs read could not be judged: the script says skip=false."""


def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_runs(env):
    """The run records: the stand-in when RUNS_JSON is set, else main's push runs at the head and the newest completed
    schedule runs of checks.yml. Raises Unknown on anything that is not a list of records."""
    raw = env.get("RUNS_JSON")
    if raw is not None:
        try:
            runs = json.loads(raw)
        except ValueError as ex:
            raise Unknown("RUNS_JSON is not JSON (%s)" % ex)
        if not isinstance(runs, list):
            raise Unknown("RUNS_JSON is not a list of runs")
        return runs
    token, repo, head = env.get("GH_TOKEN"), env.get("REPO"), env.get("HEAD_SHA")
    if not token or not repo:
        raise Unknown("no RUNS_JSON and no GH_TOKEN or REPO to read runs with")
    base = "%s/repos/%s/actions/workflows/%s/runs" % (API, repo, os.path.basename(WORKFLOW))
    queries = [{"event": "push", "branch": "main", "head_sha": head, "status": "completed", "per_page": "100"},
               {"event": "schedule", "status": "completed", "per_page": "100"}]
    runs = []
    for q in queries:
        try:
            body = api_get(base + "?" + urllib.parse.urlencode(q), token)
        except (urllib.error.URLError, OSError, ValueError) as ex:
            raise Unknown("the runs read failed (%s)" % ex)
        page = body.get("workflow_runs") if isinstance(body, dict) else None
        if not isinstance(page, list):
            raise Unknown("the runs read has no workflow_runs list")
        runs += page
    return runs


def is_checks(run):
    return str(run.get("path") or "").split("@")[0] == WORKFLOW


def decide(runs, head):
    """True when the nightly can skip. `runs` is a list of run records."""
    if not all(isinstance(r, dict) for r in runs):
        raise Unknown("a run record is not an object")
    if not head:
        raise Unknown("no HEAD_SHA, so main's head cannot be judged")
    pushed = any(is_checks(r) and r.get("event") == "push" and r.get("head_branch") == "main" and r.get("head_sha") == head
                 and r.get("status") == "completed" and r.get("conclusion") == "success" for r in runs)
    done = [r for r in runs if is_checks(r) and r.get("event") == "schedule" and r.get("status") == "completed"]
    if not done:
        return False
    newest = max(done, key=lambda r: str(r.get("created_at") or ""))
    return pushed and newest.get("conclusion") == "success"


def main(env=None):
    env = os.environ if env is None else env
    try:
        skip = decide(read_runs(env), env.get("HEAD_SHA"))
        print("nightly-skip: skip=%s" % str(skip).lower())
    except Unknown as ex:
        skip = False
        print("nightly-skip: unknown (%s), so the nightly runs everything" % ex)
    line = "skip=%s\n" % str(skip).lower()
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        sys.stdout.write(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
