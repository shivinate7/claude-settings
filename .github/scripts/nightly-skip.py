#!/usr/bin/env python3
"""The daily skip decision: it decides whether the daily scheduled run of checks.yml can skip (decision push-skip-on-proven-tree, owner
page item 880, 11:53 CST Nov 15). A push to main runs the Linux fast jobs only; the daily runs every other job.

Writes one line to $GITHUB_OUTPUT (stdout when unset): skip=true or skip=false. It exits 0 on every path, so the skip job is a
visible success and scope reads its output. skip=true only when ALL of these hold:
  (a) the newest completed schedule run of checks.yml, other than this run, succeeded, and no other schedule run is still going;
  (b) every push run of checks.yml on main created after that daily completed with success AND was proven by the push skip (its
      push-skip job succeeded and its scope job was skipped, so every Linux and slow job rode a PR run), and none is still going;
  (c) the newest push run of checks.yml on main has this run's head sha.
A push run that ran only the Linux fast jobs (scope ran) is unproven: the daily is the only run that covers the slow jobs for it.
Any read failure, a missing page, a red, cancelled or running daily, and no prior daily write skip=false and say "unknown" or the
reason. The push runs read must reach the green daily: a full page of push runs that ends newer than it hides the pushes after it.

It also prints `range: <green daily head>..<this head> (<N> merges)` to stdout and to $GITHUB_STEP_SUMMARY: N counts the push runs
created after the green daily (the newest successful daily other than this run). With none: `range: unknown (no green daily)`.

Input (env): REPO (owner/name), HEAD_SHA, GITHUB_RUN_ID (this run, whose own record never blocks), GH_TOKEN. RUNS_JSON is a stand-in
for the read: a JSON list of run records in the shape of the Actions runs API, with a `jobs` list (the jobs API's name, status and
conclusion) on each push run (lint/test_nightly_skip.py).
Cost per daily, no file kept, no process kept: one schedule runs read, one push runs read per 100 push runs back to the green daily
(usually one), and one jobs read per push run after it, newest first, stopping at the first push run that is not proven.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

WORKFLOW = ".github/workflows/checks.yml"
API = "https://api.github.com"
PAGE = 100  # the runs page size
MAX_RUN_PAGES = 5  # push run pages read at most; a daily this far behind runs everything
MAX_JOB_PAGES = 5
MAX_PUSH_RUNS = 100  # more merges than this since the green daily and the daily runs everything, rather than read their jobs


class Unknown(Exception):
    """The runs read could not be judged: the script says skip=false."""


def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_checks(run):
    return str(run.get("path") or "").split("@")[0] == WORKFLOW


def created(run):
    return str(run.get("created_at") or "")


def runs_page(base, query, token):
    try:
        body = api_get(base + "?" + urllib.parse.urlencode(query), token)
    except Exception as ex:  # any read error (URLError, a cut-off http.client.IncompleteRead, bad JSON) is an unknown state
        raise Unknown("the runs read failed (%s: %s)" % (type(ex).__name__, ex))
    page = body.get("workflow_runs") if isinstance(body, dict) else None
    if not isinstance(page, list):
        raise Unknown("the runs read has no workflow_runs list")
    return page


def is_push(run):
    return is_checks(run) and run.get("event") == "push" and run.get("head_branch") == "main"


def green_daily(runs, self_id):
    """The newest successful completed schedule run of checks.yml other than this run, or None."""
    done = [r for r in runs if is_checks(r) and r.get("event") == "schedule" and r.get("status") == "completed" and r.get("id") != self_id]
    ok = [r for r in done if r.get("conclusion") == "success"]
    return max(ok, key=created) if ok else None


def read_live(env):
    """(runs, jobs_reader) from the API: main's schedule runs, then the push runs back to the green daily, one page at a time. Raises
    Unknown when a read fails or the pages do not reach the green daily within MAX_RUN_PAGES."""
    token, repo = env.get("GH_TOKEN"), env.get("REPO")
    if not token or not repo:
        raise Unknown("no RUNS_JSON and no GH_TOKEN or REPO to read runs with")
    if not env.get("GITHUB_RUN_ID"):
        raise Unknown("no GITHUB_RUN_ID, so this run's own record cannot be told from another daily")
    base = "%s/repos/%s/actions/workflows/%s/runs" % (API, repo, os.path.basename(WORKFLOW))
    runs = runs_page(base, {"event": "schedule", "branch": "main", "per_page": str(PAGE)}, token)
    daily = green_daily(runs, int_or_none(env.get("GITHUB_RUN_ID")))
    if daily is not None:
        for number in range(1, MAX_RUN_PAGES + 1):
            page = runs_page(base, {"event": "push", "branch": "main", "per_page": str(PAGE), "page": str(number)}, token)
            runs += page
            if len(page) < PAGE or any(created(r) < created(daily) for r in page):
                break
    # A full last page that never reached the daily is left as read: decide() sees a full page that ends newer than the daily.

    def jobs_reader(run):
        jobs = []
        for number in range(1, MAX_JOB_PAGES + 1):
            url = "%s/repos/%s/actions/runs/%s/jobs?per_page=%d&page=%d" % (API, repo, run.get("id"), PAGE, number)
            try:
                body = api_get(url, token)
            except Exception as ex:  # any read error is an unknown state, as in runs_page
                raise Unknown("the jobs read of run %s failed (%s: %s)" % (run.get("id"), type(ex).__name__, ex))
            page = body.get("jobs") if isinstance(body, dict) else None
            if not isinstance(page, list):
                raise Unknown("the jobs read of run %s has no jobs list" % run.get("id"))
            jobs += page
            if len(page) < PAGE:
                return jobs
        raise Unknown("the jobs of run %s run past %d pages" % (run.get("id"), MAX_JOB_PAGES))

    return runs, jobs_reader


def int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_runs(env):
    """(runs, jobs_reader): the stand-in when RUNS_JSON is set (jobs_reader is None, so a push run counts only by its own `jobs`),
    else the live read. Raises Unknown on anything that is not a list of records."""
    raw = env.get("RUNS_JSON")
    if raw is None:
        return read_live(env)
    try:
        runs = json.loads(raw)
    except ValueError as ex:
        raise Unknown("RUNS_JSON is not JSON (%s)" % ex)
    if not isinstance(runs, list):
        raise Unknown("RUNS_JSON is not a list of runs")
    return runs, None


def check_shape(runs, head):
    if not all(isinstance(r, dict) for r in runs):
        raise Unknown("a run record is not an object")
    if not head:
        raise Unknown("no HEAD_SHA, so main's head cannot be judged")


def proven(run, jobs_reader):
    """True when the push run's jobs show the push skip: push-skip succeeded and scope was skipped. A run whose jobs were not read is
    unproven."""
    jobs = run.get("jobs")
    if jobs is None and jobs_reader is not None:
        jobs = jobs_reader(run)
    if not isinstance(jobs, list):
        return False
    state = {j.get("name"): j.get("conclusion") for j in jobs if isinstance(j, dict) and j.get("status") == "completed"}
    return state.get("push-skip") == "success" and state.get("scope") == "skipped"


def range_line(runs, head, self_id):
    """The range line: the green daily's head to this head, and the push runs created after that daily."""
    daily = green_daily(runs, self_id)
    if daily is None:
        return "range: unknown (no green daily)"
    merges = [r for r in runs if is_push(r) and created(r) > created(daily)]
    return "range: %s..%s (%d merges)" % (daily.get("head_sha"), head, len(merges))


def decide(runs, head, self_id=None, jobs_reader=None):
    """(skip, reason) over a list of run records. `reason` says why a false is false."""
    check_shape(runs, head)
    schedules = [r for r in runs if is_checks(r) and r.get("event") == "schedule" and r.get("id") != self_id]
    if any(r.get("status") != "completed" for r in schedules):
        return False, "another daily is still running, which is unknown"
    done = [r for r in schedules if r.get("status") == "completed"]
    if not done:
        return False, "no daily has completed yet"
    newest = max(done, key=created)
    if newest.get("conclusion") != "success":
        return False, "the newest daily concluded '%s', not success" % newest.get("conclusion")
    pushes = [r for r in runs if is_push(r)]
    if len(pushes) >= PAGE and min(created(r) for r in pushes) > created(newest):
        raise Unknown("the push runs page is full and does not reach the green daily")
    since = sorted((r for r in pushes if created(r) > created(newest)), key=created, reverse=True)
    if not since:
        return False, "no push run since the green daily, so there is nothing to prove"
    if len(since) > MAX_PUSH_RUNS:
        raise Unknown("more than %d push runs since the green daily" % MAX_PUSH_RUNS)
    if max(pushes, key=created).get("head_sha") != head:
        return False, "the newest push run is not at this run's head"
    for r in since:
        if r.get("status") != "completed":
            return False, "push run %s is still running, which is unknown" % r.get("id")
        if r.get("conclusion") != "success":
            return False, "push run %s concluded '%s'" % (r.get("id"), r.get("conclusion"))
        if not proven(r, jobs_reader):
            return False, "push run %s is not proven by the push skip, so the slow legs never ran for it" % r.get("id")
    return True, "every push run since the green daily was proven by the push skip"


def emit(line, summary):
    print(line)
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def main(env=None):
    env = os.environ if env is None else env
    summary = env.get("GITHUB_STEP_SUMMARY")
    self_id = int_or_none(env.get("GITHUB_RUN_ID"))
    head = env.get("HEAD_SHA")
    try:
        runs, jobs_reader = read_runs(env)
        check_shape(runs, head)
        emit(range_line(runs, head, self_id), summary)
        skip, reason = decide(runs, head, self_id, jobs_reader)
        emit("nightly-skip: skip=%s (%s)" % (str(skip).lower(), reason), summary)
    except Unknown as ex:
        skip = False
        emit("nightly-skip: unknown (%s), so the daily runs everything" % ex, summary)
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
