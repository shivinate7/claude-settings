#!/usr/bin/env python3
"""Each CI job's time limit, read from the newest green runs on main (decision ci-job-caps, restart-plan R3).

    python3 actions/ci-limits/ci_limits.py --json     {job: minutes, "job/step": minutes, "deadlineMinutes": minutes}
    python3 actions/ci-limits/ci_limits.py --table    a markdown table, one row per job

The limit ends a hung job and nothing else, so it is generous: the slowest sample x 1.5, rounded up, at most 360.
A sample is a green job run, or a run the cap cut (cancelled, no failed step, minutes at or past the cap in force):
a cut run counts as at least its limit. A job that failed or was cancelled early is no sample.
A new job (no green run yet) takes its nearest kind's limit x 1.5, else the largest old limit x 1.5. A new job cut at
its cap was misjudged and takes the largest. The deadline is the slowest green run's wall clock x 1.5, at least the
largest job limit, new-job estimates included.

Cost: one `gh api` call for the run list and one per run (1 + n, n = 30), in one process. No timer, no file written.
A read that fails gives every limit 360 and one warning line on stderr: a hung job still ends, a good job is never cut.
Run it from a checkout of this repo: job_minutes is merge/merge.py's, the one reader of a job's minutes.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
WORKFLOW = "checks.yml"
WINDOW = 30
CLAMP = 360  # GitHub's own ceiling for a job's timeout-minutes
MARGIN_NUM, MARGIN_DEN = 3, 2  # x 1.5, kept as a ratio so the ceiling is exact in integer seconds
GREEN_OK = ("success", "skipped", "neutral")  # a run is green when no job did worse than these

# Kind of a job, by its name, for the nearest-kind estimate of a new job. The first match wins; no match is no kind.
KIND_PATTERNS = (("mutation", r"mutat"), ("lint", r"lint"), ("test", r"^(checks|shell|pointer)"))


def kind_of(name):
    for kind, pattern in KIND_PATTERNS:
        if re.search(pattern, name):
            return kind
    return None


_merge = None


def job_minutes(row):
    """Minutes a jobs-API row ran. merge/merge.py reads gh's camelCase fields, so this renames the API's snake_case ones."""
    global _merge
    if _merge is None:
        spec = importlib.util.spec_from_file_location("merge_for_ci_limits", os.path.join(ROOT, "merge", "merge.py"))
        _merge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_merge)
    return _merge.job_minutes({"startedAt": row.get("started_at"), "completedAt": row.get("completed_at")})


def margin(minutes):
    """Minutes x 1.5, rounded up to a whole minute, at most CLAMP. Whole seconds in, so no float rounding decides a ceiling."""
    seconds = round(minutes * 60)
    return min(CLAMP, -(-seconds * MARGIN_NUM // (MARGIN_DEN * 60)))


def is_cut(job, minutes, cap):
    """Ended by its cap: cancelled, no step failed, and it ran at least as long as the cap in force. A cancel from a newer push comes earlier."""
    return (job.get("conclusion") == "cancelled" and minutes >= cap
            and not any(s.get("conclusion") == "failure" for s in job.get("steps") or ()))


def analyse(jobs_by_run, caps, kinds, window):
    """-> (limits, misjudged). See job_limits."""
    kinds = {name: kind_of(name) for name in caps} if kinds is None else kinds
    samples, steps, green, cut = {}, {}, set(), set()
    for r in jobs_by_run[:window]:
        for job in r["jobs"]:
            name = job.get("name")
            minutes = job_minutes(job) if name in caps else None
            if minutes is None:
                continue
            if job.get("conclusion") == "success":
                green.add(name)
            elif is_cut(job, minutes, caps[name]):
                cut.add(name)
            else:
                continue
            samples.setdefault(name, []).append(minutes)
            for s in job.get("steps") or ():
                m = job_minutes(s)
                if s.get("conclusion") == "success" and m is not None:
                    steps.setdefault(name + "/" + s["name"], []).append(m)
    # A job with a green run is old, and its cut samples count. A new job's cut makes it misjudged instead.
    old = {name: margin(max(samples[name])) for name in caps if name in green}
    largest = max(old.values(), default=None)
    limits, misjudged = dict(old), []
    for name in caps:
        if name in green:
            continue
        misjudged_now = name in cut
        if misjudged_now:
            misjudged.append(name)
        same_kind = [v for n, v in old.items() if kinds.get(n) is not None and kinds.get(n) == kinds.get(name)]
        base = max(same_kind) if same_kind and not misjudged_now else largest
        limits[name] = CLAMP if base is None else min(CLAMP, -(-base * MARGIN_NUM // MARGIN_DEN))
    for key, values in steps.items():
        limits[key] = margin(max(values))
    return limits, misjudged


def job_limits(jobs_by_run, caps, kinds=None, window=30):
    """jobs_by_run: completed push runs on main, newest first, [{"run_id": int, "jobs": [jobs-API job, ...]}].
    caps: {job name: timeout-minutes in force}. kinds: {job name: kind}, else kind_of.
    -> ({job name: minutes, "job/step": minutes}, the job names cut at their estimate while still new)."""
    return analyse(jobs_by_run, caps, kinds, window)


def deadline_minutes(jobs_by_run, limits, window=30):
    """The slowest green run's wall clock x 1.5, at least the largest job limit in `limits` (job-level limits only), at most CLAMP."""
    deadline = max(limits.values(), default=0)
    for r in jobs_by_run[:window]:
        # One attempt is one wall clock: a re-run hours later must not stretch the run it replaced.
        attempts = {}
        for j in r["jobs"]:
            attempts.setdefault(j.get("run_attempt"), []).append(j)
        for jobs in attempts.values():
            timed = [j for j in jobs if job_minutes(j) is not None]
            if not timed or any(j.get("conclusion") not in GREEN_OK for j in jobs):
                continue
            # ISO timestamps in one format sort as text, so min and max need no parse.
            wall = job_minutes({"started_at": min(j["started_at"] for j in timed), "completed_at": max(j["completed_at"] for j in timed)})
            if wall is not None:
                deadline = max(deadline, margin(wall))
    return min(CLAMP, deadline)


def read_limits(fetch, caps, kinds=None, window=30):
    """-> (limits with "deadlineMinutes", misjudged, warning lines). A failed fetch gives every limit CLAMP and one warning."""
    try:
        jobs_by_run = fetch()
    except Exception as e:  # any read failure: the limits must still come out
        why = " ".join(str(e).split()) or type(e).__name__
        limits = {name: CLAMP for name in caps}
        limits["deadlineMinutes"] = CLAMP
        return limits, [], ["ci-limits: cannot read the jobs API (%s). Every limit is %d minutes." % (why, CLAMP)]
    limits, misjudged = job_limits(jobs_by_run, caps, kinds, window)
    limits["deadlineMinutes"] = deadline_minutes(jobs_by_run, {n: limits[n] for n in caps}, window)
    return limits, misjudged, []


def table(limits, misjudged, caps):
    rows = ["| Job | Limit (minutes) | Note |", "| --- | --- | --- |"]
    for name in sorted(caps):
        rows.append("| %s | %d | %s |" % (name, limits[name], "misjudged: cut at its estimate while new" if name in misjudged else ""))
    rows.append("| deadlineMinutes | %d | the merge deadline |" % limits["deadlineMinutes"])
    return "\n".join(rows) + "\n"


def main(argv, fetch, caps, kinds=None, out=None, err=None):
    out, err = out or sys.stdout, err or sys.stderr
    parser = argparse.ArgumentParser(prog="ci_limits.py")
    form = parser.add_mutually_exclusive_group(required=True)
    form.add_argument("--json", action="store_true")
    form.add_argument("--table", action="store_true")
    args = parser.parse_args(argv)
    limits, misjudged, warnings = read_limits(fetch, caps, kinds)
    for line in warnings:
        print(line, file=err)
    for name in misjudged:
        print("ci-limits: %s was cut at its estimate while new: misjudged, now the largest limit x 1.5." % name, file=err)
    if args.json:
        json.dump(limits, out, indent=2, sort_keys=True)
        out.write("\n")
    else:
        out.write(table(limits, misjudged, caps))
    return 0


def gh_api(path, *fields):
    cmd = ["gh", "api", path, "-X", "GET"]
    for f in fields:
        cmd += ["-f", f]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise OSError("gh api %s: %s" % (path, done.stderr.strip() or "exit %d" % done.returncode))
    return json.loads(done.stdout)


def fetch_runs():
    """The newest WINDOW completed push runs of WORKFLOW on main, with the jobs of every attempt (a cut attempt that a re-run
    replaced is a sample the latest attempt hides). One call for the list, one per run; a run holds at most 100 jobs per page."""
    listed = gh_api("repos/{owner}/{repo}/actions/workflows/%s/runs" % WORKFLOW,
                    "branch=main", "event=push", "status=completed", "per_page=%d" % WINDOW)["workflow_runs"]
    return [{"run_id": r["id"],
             "jobs": gh_api("repos/{owner}/{repo}/actions/runs/%d/jobs" % r["id"], "filter=all", "per_page=100")["jobs"]}
            for r in listed[:WINDOW]]


def workflow_caps():
    """The job caps in force: merge/merge.py's own line scan of the workflow file."""
    job_minutes({})  # loads merge/merge.py
    with open(os.path.join(ROOT, ".github", "workflows", WORKFLOW), encoding="utf-8") as f:
        return _merge.job_caps([f.read()])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], fetch_runs, workflow_caps()))
