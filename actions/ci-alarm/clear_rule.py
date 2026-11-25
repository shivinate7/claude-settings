#!/usr/bin/env python3
"""The one home of the failed-run clear: does a run N of another event group clear a failed run R of the same workflow?

merge/merge.py (Host.base_state) loads this file (`load_clear_rule`) and calls `judge`; actions/ci-alarm/alarm.sh calls this file as a command (`--judge`), which calls `judge` too. One rule, two callers.

The judgment of main (`judge`, `judge_main`, `red_jobs`, `red_job_names`, `breaking_run`, `blames`): from one page of main's runs and the jobs of those it reads, which runs decide, which are red
and which job names are red. merge.py reads the page and words the verdict; this file holds the selection. `judge` fetches nothing: the caller passes `jobs_of` and `text_of`, each None on a failed read (merge.py reads through its API client, the `--judge` command through `gh_jobs` and `gh_text`).

The rule. N clears R when every job of R that "may run" in N has conclusion `success` in every N entry of that name. A job of R
is left out, and N need not have run it, when both hold: it is not red in R, and its job-level `if:` has a top-level `&&`
conjunct `github.event_name == 'X'` with X not N's event (a conjunct inside a parenthesized `&&` group counts), so it cannot run in N. Why: checks.yml gates `all-jobs-passed` and
`ci-done` on `pull_request`, so a push or schedule run always skips them, and a newer green push run never cleared a red nightly.
A job is kept (needed) when its test sits inside `||`, uses `!=`, its `if:` cannot be parsed, or its name maps to no job of the
workflow text. A red job (a completed job whose conclusion is not success, skipped, neutral or cancelled) is never left out.

Why this file reads the workflow text itself, and imports nothing from lint/ (lint/all_jobs_passed_rules.py `split_jobs`, `job_key`,
or lint/workflow_steps.py `job_block`): the action runs from a bare action path in other repos, with no checkout of this one, so only
the standard library and the files beside alarm.sh exist there. Those helpers also import lint/test_windows_split.py.

Two steps. Step one, `red_stays`, needs no workflow file: a red job of R missing from N or not passed in N is a certain red, and the
workflow is never read for it. Step two reads the workflow, once step one finds no certain red. `clears` runs both.

A job name maps to a job when exactly one job has it as `name:` or key. Two matches, or none, map to no job, and the job is kept. A plain
`if:` that goes on over later lines is read whole; a quoted one over several lines is not read, and the job is kept.

The empty-run rule (decision no-merge-onto-red-main). A push can run no suite: push-skip skips the whole run, or a docs-only push turns every
scope flag off. That run concludes `success` and must not hide an older red run of its group. A completed `success` run of the push
group (the events of events.json that share a group with `push`: push and workflow_dispatch) is EMPTY when no job of it concluded
`success` except the bookkeeping jobs `scope`, `push-skip` and `nightly-skip`. An empty run is a verdict only when it carries evidence: its `push-skip`
job is `success` and its `scope` job is `skipped`, which is the path where push-skip.py found the push tree equal to the head tree of a
pull request whose run passed (decision push-skip-on-proven-tree; checks.yml, jobs push-skip and scope). Only a `push` run carries evidence: a dispatch runs no
push-skip job. `empty_without_evidence` is that test; a caller walks past such a run to the group's newest run that is not, and when the
group has none keeps the newest run. A schedule run is left as it is.

The one command (alarm.sh makes this one call): clear_rule.py --judge RUNS_JSON --flows FLOWS_JSON --repo OWNER/REPO [--self NAME]. RUNS_JSON is the array that `gh run list --json workflowName,workflowDatabaseId,
databaseId,conclusion,createdAt,url,event,headSha,status,attempt` prints (in-flight runs included), FLOWS_JSON the workflow objects of the workflows API. This file reads the jobs of a run and a
workflow file itself, with `gh api`. It prints `green`, `red` or `unknown` on line one, then the red runs (`- workflow (conclusion): url`) or the reason it is unknown. Exit 0 on a verdict, 2 on an unreadable input or any other command line.
"""
import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys

PASS_OR_QUIET = ("success", "skipped", "neutral", "cancelled")  # a completed job with another conclusion is red
EVENT_TEST = re.compile(r"^github\.event_name\s*==\s*'([^']*)'$")
EVENT_TEST_REVERSED = re.compile(r"^'([^']*)'\s*==\s*github\.event_name$")
MATRIX_SUFFIX = re.compile(r"\s+\(.*\)$")
BOOKKEEPING = ("scope", "push-skip", "nightly-skip")  # the jobs of a push-group run that run no suite
EVENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")  # event -> group, the one home merge.py and alarm.sh read
CONCLUSION_BUCKET = {"success": "pass", "neutral": "skipping", "skipped": "skipping", "cancelled": "cancel"}  # a job's conclusion to its bucket; a job not completed is pending, any other conclusion is a fail
QUIET_BUCKETS = ("pass", "skipping", "pending")  # a bucket that is not red
TIMED_OUT = "timed out"  # the start of the bucket of a cancelled job that ran its full cap


def top_level_split(expr, op):
    """expr split at each `op` outside a single-quoted string and outside parentheses, or None when a quote or a paren is unbalanced.
    A doubled quote inside a string is an escaped quote, which the quote toggle reads as a close and a reopen."""
    parts, depth, quoted, start, i = [], 0, False, 0, 0
    while i < len(expr):
        ch = expr[i]
        if ch == "'":
            quoted = not quoted
        elif not quoted:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return None
            elif depth == 0 and expr.startswith(op, i):
                parts.append(expr[start:i])
                start = i + len(op)
                i += len(op)
                continue
        i += 1
    if quoted or depth:
        return None
    parts.append(expr[start:])
    return parts


def unwrap(expr):
    """expr without any pair of parentheses that wraps all of it, or None when it is unbalanced."""
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        inner = expr[1:-1]
        if top_level_split(inner, "\0") is None:  # the outer pair is not a matched pair, as in (a) && (b)
            break
        expr = inner.strip()
    return expr if top_level_split(expr, "\0") is not None else None


def other_event_only(expr, event):
    """True when the expression has a top-level `&&` conjunct `github.event_name == 'X'` with X not `event`: it is false in a run of `event`.
    False for everything else, including any expression with a top-level `||` and any expression this reader cannot parse."""
    expr = unwrap(expr or "")
    if not expr:
        return False
    ors = top_level_split(expr, "||")
    ands = top_level_split(expr, "&&")
    if ors is None or ands is None or len(ors) > 1:
        return False
    for part in ands:
        part = unwrap(part)
        if part is None:
            return False
        m = EVENT_TEST.match(part) or EVENT_TEST_REVERSED.match(part)
        if m and m.group(1).lower() != event.lower():
            return True
        if len(ands) > 1 and other_event_only(part, event):  # a parenthesized `&&` group is a conjunct of the whole: (A && B) && C
            return True
    return False


def strip_comment(value):
    """A YAML plain scalar without its trailing ` #` comment; a `#` inside a quoted string stays."""
    quote = None
    for i, ch in enumerate(value):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i].rstrip()
    return value.rstrip()


def closes_quote(value):
    """True when a value that starts with a quote ends that quote on the same line (a doubled single quote inside is an escaped quote)."""
    q = value[0]
    i = 1
    while i < len(value):
        if value[i] == q:
            if q == "'" and value[i + 1:i + 2] == "'":
                i += 2
                continue
            return value[i + 1:].strip() == "" or value[i + 1:].lstrip().startswith("#")
        if q == '"' and value[i] == "\\":
            i += 1
        i += 1
    return False


def scalar(value, rest):
    """A job-level scalar: `value` is the text after `key:` on its line, `rest` the lines after it. Handles a plain, a quoted, and a
    block (`|` or `>`) scalar. A `${{ ... }}` wrapper is removed. None when the value is a form this reader does not handle."""
    value = value.strip()
    if re.match(r"^[|>][+-]?\d*[ \t]*(#.*)?$", value):
        body = []
        for line in rest:
            if line.strip() and len(line) - len(line.lstrip(" ")) <= 4:
                break
            body.append(line.strip())
        value = " ".join(x for x in body if x)
    else:
        if value[:1] in ("'", '"') and not closes_quote(value):
            return None  # a quoted scalar over several lines: not read, so the job stays needed
        parts = [strip_comment(value)]
        for line in rest:  # a plain scalar goes on over each later line indented deeper than the key
            if not line.strip():
                continue
            if len(line) - len(line.lstrip(" ")) <= 4:
                break
            if not line.strip().startswith("#"):
                parts.append(strip_comment(line.strip()))
        value = " ".join(x for x in parts if x)
    for q in ("'", '"'):
        if len(value) >= 2 and value[0] == q and value[-1] == q and q not in value[1:-1].replace(q * 2, ""):
            value = value[1:-1].replace(q * 2, q) if q == "'" else value[1:-1]
    value = value.strip()
    if value.startswith("${{"):
        if not value.endswith("}}") or "${{" in value[3:]:
            return None
        value = value[3:-2].strip()
    elif "${{" in value:
        return None
    return value


def parse_jobs(text):
    """{job key: {"name": its name: or None, "if": its job-level if: expression, None when it has none, False when unreadable}} of a workflow text."""
    lines = text.replace("\r\n", "\n").split("\n")
    jobs, key, in_jobs = {}, None, False
    for i, line in enumerate(lines):
        if re.match(r"^\S", line) and not line.startswith("#"):
            in_jobs = bool(re.match(r"^jobs:[ \t]*(#.*)?$", line))
            key = None
            continue
        if not in_jobs:
            continue
        m = re.match(r"^  (?:([\w.-]+)|\"([^\"]*)\"|'([^']*)'):[ \t]*(#.*)?$", line)
        if m:
            key = m.group(1) or m.group(2) or m.group(3)
            jobs[key] = {"name": None, "if": None}
            continue
        m = re.match(r"^    (name|if):[ \t]*(.*)$", line)
        if m and key is not None:
            got = scalar(m.group(2), lines[i + 1:])
            if m.group(1) == "name":
                jobs[key]["name"] = got if got and "${{" not in got else None
            else:
                jobs[key]["if"] = got if got is not None else False
    return jobs


def job_for(name, jobs):
    """The job of the workflow a run's job name belongs to: the one job whose name: or key is the name; a matrix suffix ` (...)` is
    dropped and the same try made. None when no job maps, and None when more than one job does (the name is ambiguous)."""
    for candidate in (name, MATRIX_SUFFIX.sub("", name)):
        keys = [key for key, job in jobs.items() if job["name"] == candidate or key == candidate]
        if len(keys) > 1:
            return None
        if keys:
            return jobs[keys[0]]
    return None


def is_red(job):
    return job.get("status") == "completed" and job.get("conclusion") not in PASS_OR_QUIET


def concluded(name, jobs, want):
    """True when `jobs` has the job name and every entry of that name is completed with conclusion `want`."""
    got = [j.get("conclusion") if j.get("status") == "completed" else None for j in jobs if j["name"] == name]
    return bool(got) and all(c == want for c in got)


def passed_in(name, n_jobs):
    """True when N has the job name and every entry of that name is a success."""
    return concluded(name, n_jobs, "success")


def rule_events():
    """The events the empty-run rule judges: those of events.json in the same group as `push`."""
    events = base_events()
    return sorted(e for e, group in events.items() if group == events["push"])


def base_events():
    """events.json: event -> group, the runs of the base's own commits that main is judged on. The groups judge apart, except for the cross-group clears."""
    with open(EVENTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def empty_without_evidence(jobs, event):
    """True when a completed `success` run of `event` (a push-group event) ran no check and carries no evidence (the module docstring).
    Empty: no job but `scope`, `push-skip` and `nightly-skip` concluded success. Evidence: a `push` run whose push-skip job is success and scope job is skipped.
    Callers check the run-level conditions (the event is in rule_events, the run concluded success) before they read the jobs."""
    # One of two homes of "proven push" (push-skip success and scope skipped; also nightly-skip.py `proven`).
    # This file cannot import the others: it runs from a bare action path in other repos (module docstring), so only the standard library exists.
    if any(j.get("status") == "completed" and j.get("conclusion") == "success" and j["name"] not in BOOKKEEPING for j in jobs):
        return False
    return not (event == "push" and concluded("push-skip", jobs, "success") and concluded("scope", jobs, "skipped"))


def red_stays(r_jobs, n_jobs):
    """Step one, needs no workflow file: True when a red job of R is missing from N or not passed in N. Such a red is certain, whatever any
    job's `if:` says, so a caller that finds it never reads the workflow file."""
    return any(not passed_in(j["name"], n_jobs) for j in r_jobs if is_red(j))


def needed_names(r_jobs, n_event, text):
    """The job names of R that N must have passed: every name but those left out (see the module docstring)."""
    jobs = parse_jobs(text)
    names = {j["name"] for j in r_jobs}
    red = {j["name"] for j in r_jobs if is_red(j)}
    left_out = set()
    for name in names - red:
        job = job_for(name, jobs)
        if job and job["if"] and other_event_only(job["if"], n_event):
            left_out.add(name)
    return names - left_out


def clears(r_jobs, n_jobs, n_event, text):
    """True when N, a run of `n_event` of the same workflow as R, clears R's red jobs. `text` is the workflow file at N's head; step one
    (red_stays) runs first, and the text is read only for step two (needed_names). An R with no jobs is never cleared. Callers check the
    run-level conditions (newer, newest of its group, success, another group)."""
    if not r_jobs or red_stays(r_jobs, n_jobs):
        return False
    return all(passed_in(x, n_jobs) for x in needed_names(r_jobs, n_event, text))


def job_minutes(row):
    """Minutes a check row ran, from startedAt to completedAt. None when either is missing or the job has not finished (gh gives a pending one the zero time)."""
    try:
        a, b = (datetime.datetime.fromisoformat(row[k].replace("Z", "+00:00")) for k in ("startedAt", "completedAt"))
    except (KeyError, AttributeError, ValueError):
        return None
    return (b - a).total_seconds() / 60 if b > a else None


def run_row(r, link):
    """A check run, or an Actions job (the same fields), as the row `job_buckets` and merge.py's check reads judge."""
    bucket = "pending" if r["status"] != "completed" else CONCLUSION_BUCKET.get(r.get("conclusion"), "fail")
    return {"name": r["name"], "bucket": bucket, "link": link, "startedAt": r.get("started_at"), "completedAt": r.get("completed_at")}


def capped(bucket, cap, used):
    """`bucket` after the job's cap: a cancel that ran its full cap (`used` minutes, `cap` the job's timeout-minutes) is a timeout, which reads red apart from a test failure."""
    if cap and used is not None and bucket == "cancel" and used >= cap:
        return f"{TIMED_OUT} at its {cap}-minute cap; re-cap or split"
    return bucket


def job_buckets(jobs, caps):
    """-> {job name: [(bucket, link), ...]} of the jobs API rows `jobs`, each judged against its cap in `caps` ({job id or name: minutes})."""
    got = {}
    for j in jobs:
        d = run_row(j, j.get("html_url"))
        got.setdefault(d["name"], []).append((capped(d["bucket"], caps.get(d["name"]), job_minutes(d)), d.get("link") or ""))
    return got


def red_jobs(jobs, caps, ignore=()):
    """-> (got, red, names) for the jobs of one finished run: `got` is job_buckets; `red` the lines `name: bucket link` of its red jobs (a job in `ignore` has none; a job
    cancelled or timed out at its cap is not red); `names` the red jobs' names, sorted, ignored ones too. The one home of what makes a job of a main run red."""
    got = job_buckets(jobs, caps)
    steps = {k: v for k, rows in got.items() if (v := [x for x in rows if x[0] != "cancel" and not x[0].startswith(TIMED_OUT)])}
    red = [f"{k}: {b} {link}".strip() for k, rows in steps.items() if k not in ignore for b, link in rows if b not in QUIET_BUCKETS]
    return got, red, sorted(k for k, rows in steps.items() if any(b not in QUIET_BUCKETS for b, _ in rows))


def red_job_names(jobs, caps):
    """-> the names of the red jobs of one finished run, sorted (red_jobs, names)."""
    return red_jobs(jobs, caps)[2]


def blames(first):
    """True when the breaking run `first` names its commit as the breaking merge: red again on a re-run, and not a schedule run (a nightly tests the
    base's head at run time, not the commit that started it, so that commit is no suspect)."""
    return (first.get("run_attempt") or 1) > 1 and first["event"] != "schedule"


def breaking_run(judged, newest_red, events=None):
    """-> (run, going): the first red run with a green parent. `judged` is the runs of main newest first. From `newest_red`, walk the runs of its workflow file and event
    group, newest first, past every red run to the first green one; the oldest red run before it is the first red run with a green parent. A cancelled, skipped or neutral
    run proves nothing and is stepped over. (None, None) when no green parent is on the page (a lone red run, or a page red to its end);
    (None, run) when `run`, an older run still going (a re-run in flight), stops the walk: the run under it may be red or green, so no run is blamed."""
    events = events or base_events()
    key = (newest_red["path"], events[newest_red["event"]])
    first = None
    for r in judged[judged.index(newest_red):]:
        if (r["path"], events[r["event"]]) != key:
            continue
        if r["status"] != "completed":
            return None, r
        if r["conclusion"] == "success":
            break
        if r["conclusion"] not in ("skipped", "neutral", "cancelled"):
            first = r
    else:
        return None, None
    return first, None


Red = collections.namedtuple("Red", "run lines names")  # a red run: the run, its red jobs' lines (empty when it ended red with no red job), their names (empty then too)
Judgment = collections.namedtuple("Judgment", "verdict red cancelled unknown judged order blamed base_head")


class ReadFailed(Exception):
    """jobs_of or text_of returned None: a read failed, so the verdict is unknown."""


def judge(runs, flows, ignore, caps, jobs_of, text_of, detail=True):
    """-> a Judgment of main from one page of its runs (decision no-merge-onto-red-main, the red-main check; the one home of the selection that decides whether main is red).
    `runs` is the page of workflow runs newest first, `flows` the workflow paths on main, `ignore` the names left out (a workflow name, a job name), `caps` the jobs' timeout-minutes,
    and `jobs_of(run)` and `text_of(run)` the jobs of a run and the workflow file at its head, each None on a failed read. Each is read at most once.
    verdict: green, red or unknown. red: a Red per red run, newest first, one per file and group. cancelled: the cancelled runs with no red job that no run cleared. unknown: the re-runs in flight.
    judged: the runs the verdict is taken from, newest first. order: the red runs, the head group's first, each the start of a walk to its breaking run. blamed: the full head shas of the breaking merges.
    base_head: the head sha of the newest run on the page. A failed read gives unknown with nothing else.
    `detail=False` (the CI alarm, which names runs and no jobs, and passes no caps): a run that did not succeed and that no run could clear (`candidates`) is red with no jobs read.

    Judged: per workflow file in `flows` and per event group (events.json maps an event to its group; an event not in it is never judged), the newest completed run on main, or a re-run in
    flight (not completed, `run_attempt` above 1) when one is newer: it makes the verdict unknown, never green, since the older run under it is the one being re-run. A dispatch clears an older
    failed push (one group). A failed run R with at least one red job is cleared by a run N of the same file and another group only when N is newer than R, is the newest completed run of its
    own group, concluded success, and `clears` holds (the workflow file read at N's head: one read per such N, none for a cancelled R). So a green nightly that ran other jobs never clears a failed push,
    and a newer green push run clears a red nightly. An R with no red job is never cleared by that rule. N's jobs are read only when R has a red job or is cancelled with no red job, and such an N exists.
    A run that did not succeed with no red job: a timed-out job explains it; else a cancelled run R is unknown, never swapped for an older run, unless a run N clears it. R is then on a commit older
    than the base's head. N clears it when it is such a candidate on another head than R's, every job R ran (not skipped) is in N by exact name with every entry of that name success, and every job R
    skipped is in N. An R with no jobs stays unknown. Any other run that did not succeed is red (a broken workflow file runs no job).
    An empty run is no verdict (empty_without_evidence): the newest run of a group that is not empty is the group's verdict, so an older red run stays red; a page with no run of the group that is not
    empty keeps the newest run. A schedule run is judged as it is. A newest-first walk of the push group's green runs costs one jobs read each, down to the first that is not empty."""
    events = base_events()
    judged = [r for r in runs if (r["status"] == "completed" or (r.get("run_attempt") or 1) > 1)
              and r["event"] in events and r["name"] not in ignore and r["path"].split("@")[0] in flows]
    base_head = next((r.get("head_sha") for r in runs if r["event"] in events), None)  # the newest run on the page starts at the base's head
    jobs_read, texts = {}, {}

    def jobs(r):  # a run's jobs, read once
        if r["id"] not in jobs_read:
            if (got := jobs_of(r)) is None:
                raise ReadFailed
            jobs_read[r["id"]] = got
        return jobs_read[r["id"]]

    def text(n):  # the workflow file at n's head, read once
        key = (n["path"].split("@")[0], n.get("head_sha"))
        if key not in texts:
            if (got := text_of(n)) is None:
                raise ReadFailed
            texts[key] = got
        return texts[key]
    try:
        red, cancelled, unknown, red_runs = [], [], [], []
        rule = rule_events()

        def empty(r):  # a green run of the push group that ran no suite and carries no evidence: no verdict; one jobs read, cached
            return r["conclusion"] == "success" and r["event"] in rule and empty_without_evidence(jobs(r), r["event"])
        newest, settled = {}, set()  # per (file, group): the newest run, but never an empty one while an older run of the group is not; with none, the newest run
        for r in judged:  # newest first
            key = (r["path"], events[r["event"]])
            if key in settled:
                continue
            newest.setdefault(key, r)
            if not empty(r):
                newest[key] = r
                settled.add(key)
        age = {r["id"]: i for i, r in enumerate(judged)}  # `judged` is newest first

        def candidates(r, cancelled=False):
            """The runs that may clear r, from `newest`: newer than r, the newest of their group, successful, of another group of r's file; with `cancelled`, also on another head than r's. No jobs are read."""
            return [n for n in newest.values()
                    if n["path"].split("@")[0] == r["path"].split("@")[0] and events[n["event"]] != events[r["event"]]
                    and age[n["id"]] < age[r["id"]] and n["conclusion"] == "success"
                    and not (cancelled and (not r.get("head_sha") or n.get("head_sha") == r["head_sha"]))]

        def cleared(r, cancelled=False):
            """True when a newer, newest-of-its-group, successful run of another group of r's file passed what r needs. Call it only for an r with a red job,
            or, with `cancelled`, for an r cancelled with no red job: the run must then also be on another head than r's, pass every job r ran
            (not skipped) and contain every job r skipped. A failed r is judged by red_stays first (no file read), then clears, with the workflow file at n's head.
            r's jobs are read only when a candidate exists."""
            cands = candidates(r, cancelled)
            if not cands or not jobs(r):
                return False
            names = {j["name"] for j in jobs(r)}
            need = {j["name"] for j in jobs(r) if j.get("conclusion") != "skipped"} if cancelled else names
            for n in cands:
                if not cancelled:
                    if red_stays(jobs(r), jobs(n)):
                        continue  # a certain red: no workflow read, so a failed read cannot turn it into unknown
                    if clears(jobs(r), jobs(n), n["event"], text(n)):
                        return True
                    continue
                theirs = {}
                for j in jobs(n):
                    theirs.setdefault(j["name"], []).append(j.get("conclusion") if j.get("status") == "completed" else None)
                if all(theirs.get(x) and all(c == "success" for c in theirs[x]) for x in need) and all(x in theirs for x in names):
                    return True
            return False
        for r in newest.values():
            if r["status"] != "completed":  # a re-run in flight: its jobs are mid-change, so none are read
                unknown.append(r)
                continue
            if r["conclusion"] in ("success", "skipped", "neutral"):
                continue
            if not detail and r["conclusion"] != "cancelled" and not candidates(r):  # no run could clear it: red, and its jobs need no read
                red.append(Red(r, [], []))
                red_runs.append(r)
                continue
            got, lines, names = red_jobs(jobs(r), caps, ignore)
            if lines:
                if not cleared(r):
                    red.append(Red(r, lines, names))
                    red_runs.append(r)
            elif any(b.startswith(TIMED_OUT) for rows in got.values() for b, _ in rows):
                continue
            elif r["conclusion"] == "cancelled":
                if not cleared(r, cancelled=True):
                    cancelled.append(r)
            else:
                red.append(Red(r, [], []))
                red_runs.append(r)
        # One walk per red group (red_runs holds one run per file and group): a red nightly or a red run of another file never hides the
        # push run that broke the base. The head group (push, dispatch) goes first, so its breaking merge or re-run leads the detail.
        order = sorted(red_runs, key=lambda r: (events[r["event"]] != events["push"], age[r["id"]]))
        blamed = [first["head_sha"] for first in (breaking_run(judged, r, events)[0] for r in order) if first and first.get("head_sha") and blames(first)]  # full shas, as data
    except ReadFailed:
        return Judgment("unknown", [], [], [], judged, [], [], base_head)
    verdict = "red" if red else "unknown" if unknown or cancelled else "green"
    return Judgment(verdict, red, cancelled, unknown, judged, order, blamed, base_head)


def judge_main(runs, flows, ignore, caps, jobs_of, text_of):
    """-> (verdict, red) of `judge`: red is [(run id, red job names)] for each red run, newest first. The pair the red-main check and its tests compare."""
    j = judge(runs, flows, ignore, caps, jobs_of, text_of)
    return j.verdict, [(e.run["id"], e.names) for e in j.red]


ALARM_RED = ("failure", "timed_out", "startup_failure")  # the conclusions the alarm alarms on; any other conclusion outside PASS_OR_QUIET never does


def alarm_runs(rows, workflows, own):
    """-> the runs `judge` reads, newest first, from the rows of `gh run list` and the workflow objects of the workflows API (`own` is the alarm's own workflow name, left out).
    A run is kept only when its workflow is not deleted and has its file under .github/workflows (a Pages build has none) and its event is in events.json. A completed run whose
    conclusion is neither red nor in PASS_OR_QUIET (action_required, stale) is `neutral`: it never alarms, and it still speaks for its group. The rows' names become the API's."""
    paths = {w["id"]: w["path"] for w in workflows if w.get("state") != "deleted" and str(w.get("path", "")).startswith(".github/workflows/")}
    events = base_events()
    runs = []
    for r in sorted(rows, key=lambda row: row["createdAt"], reverse=True):
        if r["workflowName"] == own or r["workflowDatabaseId"] not in paths or r["event"] not in events:
            continue
        conclusion = r.get("conclusion")
        if r["status"] == "completed" and conclusion not in ALARM_RED + PASS_OR_QUIET:
            conclusion = "neutral"
        runs.append({"id": r["databaseId"], "name": r["workflowName"], "path": paths[r["workflowDatabaseId"]], "event": r["event"], "status": r["status"], "conclusion": conclusion,
                     "run_attempt": r.get("attempt") or 1, "head_sha": r.get("headSha"), "url": r.get("url")})
    return runs


def gh_api(args):
    """The stdout of `gh api ARGS`, or None when gh fails."""
    try:
        done = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def gh_jobs(repo, run_id):
    """The jobs of a run over every page, or None when a read fails or its answer is not a list of jobs."""
    out = gh_api([f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", "--paginate"])
    if out is None:
        return None
    docs, decoder, i = [], json.JSONDecoder(), 0
    while True:  # --paginate prints one JSON document per page
        while i < len(out) and out[i].isspace():
            i += 1
        if i >= len(out):
            break
        try:
            doc, i = decoder.raw_decode(out, i)
        except ValueError:
            return None
        docs.append(doc)
    if not docs or not all(isinstance(d, dict) and isinstance(d.get("jobs"), list) for d in docs):
        return None
    return [j for d in docs for j in d["jobs"]]


def gh_text(repo, path, ref):
    """The workflow file `path` at `ref`, or None when the read fails or the file is empty."""
    return gh_api([f"repos/{repo}/contents/{path}?ref={ref}", "-H", "Accept: application/vnd.github.raw+json"]) or None


def alarm_verdict(rows, workflows, repo, own):
    """-> (verdict, lines) for the CI alarm: `judge` over the rows of `gh run list` (alarm_runs). red: a line `- workflow (conclusion): url` per red run, newest first. unknown: one line,
    the reason: a re-run in flight (the older run under it is the one being re-run) or a failed read. green: the rest. A cancelled run with no red job is green, since a cancelled run never
    alarms (decision no-merge-onto-red-main); its jobs are not read, so a red job of it counts for nothing. The alarm has no job caps, so a job cancelled at its cap reads as a cancel."""
    runs = alarm_runs(rows, workflows, own)

    def jobs_of(r):
        return [] if r["conclusion"] == "cancelled" else gh_jobs(repo, r["id"])

    def text_of(n):
        return gh_text(repo, n["path"].split("@")[0], n.get("head_sha"))
    j = judge(runs, sorted({r["path"] for r in runs}), (), {}, jobs_of, text_of, detail=False)
    if j.red:
        return "red", [f"- {e.run['name']} ({e.run['conclusion']}): {e.run['url']}" for e in j.red]
    if j.unknown:
        return "unknown", ["; ".join(f"run {r['id']} of {r['name']} is being re-run (attempt {r['run_attempt']}, {r['status']}): {r['url']}" for r in j.unknown)]
    if j.verdict == "unknown" and not j.cancelled:  # a read gave None: never a green
        return "unknown", ["a read of the jobs of a run or of a workflow file failed"]
    return "green", []


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--judge", metavar="RUNS_JSON", help="print the alarm's verdict from the file of runs (needs --flows and --repo)")
    p.add_argument("--flows", metavar="FLOWS_JSON")
    p.add_argument("--repo")
    p.add_argument("--self", dest="own", default="", help="the alarm's own workflow name, left out of the runs")
    a = p.parse_args(argv)
    try:
        if a.judge:
            if not a.flows or not a.repo:
                raise ValueError("--judge needs --flows and --repo")
            with open(a.judge, encoding="utf-8") as f:
                rows = json.load(f)
            with open(a.flows, encoding="utf-8") as f:
                workflows = json.load(f)
            verdict, lines = alarm_verdict(rows, workflows, a.repo, a.own)
            print("\n".join([verdict, *lines]))
            return 0
        raise ValueError("--judge is the only command")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"clear_rule: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
