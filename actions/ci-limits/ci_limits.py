#!/usr/bin/env python3
"""Each CI job's time limit, read from the newest completed push runs on main (decision ci-job-caps, restart-plan R3).

    python3 actions/ci-limits/ci_limits.py --json     {job: minutes, "job/CI step": minutes, "deadlineMinutes": minutes}
    python3 actions/ci-limits/ci_limits.py --table    a markdown table, one row per job

The limit ends a hung job and nothing else, so it is generous: the slowest sample x 1.5, rounded up, at most 360.
A sample is a green job run, or a run the cap cut (cancelled, no failed CI step, minutes at or past the cap passed in,
the workflow's `timeout-minutes` on the base ref): a cut run counts as at least its limit, so its limit rises x 1.5 per cut
run up to 360 (owner, decision time-limits-end-hangs-only). A job that failed, or was cancelled before its cap by a newer
push, is no sample.
A new job (no green run yet) takes its nearest kind's limit x 1.5, else the largest old limit x 1.5. A new job cut at
its cap was misjudged and takes the largest. Every job limit is at least the median of the measured job limits (median_floor; an estimate is not measured),
so a job that runs for seconds is never cut at a minute. A job skipped in every run of the window never ran on main:
its limit is None (JSON null, table "not measured on main"), and it joins no median, estimate or deadline.
The deadline is the slowest green run's wall clock x 1.5, at least the largest job limit, new-job estimates included.
With no measured job and no green run it is 360, never 0.

Cost: one script run makes 1 + n `gh api` calls (n = 30 runs), plus one more per further 100 job rows of a run.
No timer, no file written. A read that fails gives every limit 360 and one warning line on stderr:
a hung job still ends, a good job is never cut.
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
CLAMP = 360  # GitHub-hosted jobs run at most 6 hours (docs.github.com/en/actions/reference/limits), so no limit is worth more
BASE_REF = "origin/main"  # the caps come from here, never from the checkout or a pull request tree
PER_PAGE = 100  # the jobs API's page size, its largest
NOT_MEASURED = "not measured on main"
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


def load_merge():
    global _merge
    if _merge is None:
        spec = importlib.util.spec_from_file_location("merge_for_ci_limits", os.path.join(ROOT, "merge", "merge.py"))
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)  # a failed load leaves nothing half-built to serve or to import
            raise
        _merge = module  # cached only once it is whole
    return _merge


def job_minutes(row):
    """Minutes a jobs-API row ran. merge/merge.py reads gh's camelCase fields, so this renames the API's snake_case ones."""
    return load_merge().job_minutes({"startedAt": row.get("started_at"), "completedAt": row.get("completed_at")})


def margin(minutes):
    """Minutes x 1.5, rounded up to a whole minute, at most CLAMP. Whole seconds in, so no float rounding decides a ceiling."""
    seconds = round(minutes * 60)
    return min(CLAMP, -(-seconds * MARGIN_NUM // (MARGIN_DEN * 60)))


def median_floor(values):
    """The median of the measured job limits (an estimate is not one), rounded up: no job's limit is below it. Derived each run, never stored. No values, no floor."""
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return 0
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2] + 1) // 2


def is_cut(job, minutes, cap):
    """Ended by its cap: cancelled, no CI step failed, and it ran at least as long as the cap passed in. A cancel from a newer push comes earlier."""
    return (job.get("conclusion") == "cancelled" and minutes >= cap
            and not any(s.get("conclusion") == "failure" for s in job.get("steps") or ()))


def analyse(jobs_by_run, caps, kinds, window):
    """-> (limits, misjudged). See job_limits."""
    kinds = {name: kind_of(name) for name in caps} if kinds is None else kinds
    samples, steps, green, cut, seen, ran = {}, {}, set(), set(), set(), set()
    for r in jobs_by_run[:window]:
        for job in r["jobs"]:
            name = job.get("name")
            if name not in caps:
                continue
            seen.add(name)
            if job.get("conclusion") != "skipped":
                ran.add(name)
            minutes = job_minutes(job)
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
    not_measured = {name for name in caps if name in seen and name not in ran}
    raw, misjudged = dict(old), []
    for name in caps:
        if name in green or name in not_measured:
            continue
        misjudged_now = name in cut
        if misjudged_now:
            misjudged.append(name)
        same_kind = [v for n, v in old.items() if kinds.get(n) is not None and kinds.get(n) == kinds.get(name)]
        base = max(same_kind) if same_kind and not misjudged_now else largest
        raw[name] = CLAMP if base is None else min(CLAMP, -(-base * MARGIN_NUM // MARGIN_DEN))
    floor = median_floor(old.values())
    limits = {name: max(v, floor) for name, v in raw.items()}
    limits.update({name: None for name in not_measured})
    for key, values in steps.items():
        limits[key] = margin(max(values))
    return limits, misjudged


def job_limits(jobs_by_run, caps, kinds=None, window=30):
    """jobs_by_run: completed push runs on main, newest first, [{"run_id": int, "jobs": [jobs-API job, ...]}].
    caps: {job name: timeout-minutes in force}. kinds: {job name: kind}, else kind_of.
    -> ({job name: minutes, or None when the job never ran on main; "job/CI step": minutes},
        the job names cut at their estimate while still new)."""
    return analyse(jobs_by_run, caps, kinds, window)


def deadline_minutes(jobs_by_run, limits, window=30):
    """The slowest green run's wall clock x 1.5, at least the largest job limit in `limits` (job-level limits only), at most CLAMP."""
    deadline = max((v for v in limits.values() if v is not None), default=0)
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
    return min(CLAMP, deadline) if deadline else CLAMP  # no measured job and no green run: no data is never a 0 deadline


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
        shown = NOT_MEASURED if limits[name] is None else limits[name]
        rows.append("| %s | %s | %s |" % (name, shown, "misjudged: cut at its estimate while new" if name in misjudged else ""))
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


def run_jobs(api, run_id):
    """Every job row of a run, all attempts, a page of PER_PAGE at a time until total_count is read."""
    jobs, page = [], 1
    while True:
        got = api("repos/{owner}/{repo}/actions/runs/%d/jobs" % run_id, "filter=all", "per_page=%d" % PER_PAGE, "page=%d" % page)
        rows = got["jobs"]
        jobs += rows
        total = got.get("total_count")
        if not rows or (len(jobs) >= total if total is not None else len(rows) < PER_PAGE):
            return jobs
        page += 1


def fetch_runs(api=None, workflow=WORKFLOW, window=WINDOW):
    """The newest `window` completed push runs of `workflow` on main, with the jobs of every attempt (a cut attempt that a re-run
    replaced is a sample the latest attempt hides). One call for the list, one per run, one more per further PER_PAGE rows.
    `api(path, *fields)` returns the parsed JSON: gh_api, or a test's fake."""
    api = api or gh_api
    listed = api("repos/{owner}/{repo}/actions/workflows/%s/runs" % workflow,
                 "branch=main", "event=push", "status=completed", "per_page=%d" % window)["workflow_runs"]
    return [{"run_id": r["id"], "jobs": run_jobs(api, r["id"])} for r in listed[:window]]


def workflow_caps(ref=BASE_REF, root=ROOT):
    """The job caps on `ref`: merge/merge.py's own line scan (job_caps) of WORKFLOW as git shows it there, never the checkout's copy.
    base_job_caps reads every workflow file; this reads only the file whose runs are measured, so another workflow's jobs
    are not counted as new jobs here."""
    merge = load_merge()
    code, text = merge.git(root, "show", "%s:.github/workflows/%s" % (ref, WORKFLOW))
    if code:
        raise OSError("cannot read %s on %s: %s" % (WORKFLOW, ref, " ".join(str(text).split())))
    return merge.job_caps([text])


if __name__ == "__main__":
    try:
        base_caps = workflow_caps()
    except OSError as e:
        print("ci-limits: %s" % e, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1:], fetch_runs, base_caps))
