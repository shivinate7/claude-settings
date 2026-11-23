#!/usr/bin/env python3
"""The idle red pull request rule (owner, 2026-11-23 10:54 CST): a non-draft pull request whose head is red, and whose newest
pull_request run is IDLE_SECONDS old or more, goes back to draft. A PR comment says why and how to return, and wakes its session.

Two callers, one judgement: `merge --draft-idle` (the janitor's daily job) sweeps every open pull request; the pre-ready run's
open-PR clash drafts an idle red PR that clashes with the one going ready, and then does not count it.

This module reads and writes only through the host it is given (merge.Host or a fake): open_pulls, head_state, runs, draft, post_comment.
It imports nothing from merge.py, which loads it. The caller passes `errors` (merge.Stop and the like) and `routes` (merge.DRAFT_ROUTES).

A failed read is unknown: that PR is left alone and the line says unknown. A failed list read drafts nothing.
Cost: one open-pulls read per sweep; per non-draft PR in the sweep one runs read and one head_state read (the host's head_state reads the same run list from its memo);
in the clash only a counted clash with a non-draft PR is read: head_state, and a runs read when it reads red. One draft call and one comment per drafted PR. No file is written, no timer, no process is kept.
A PR a person readies again with no push, that goes red and idle again, is drafted again and gets a second comment: no comment is read
to stop it, since that read would cost a call on every drafted PR. A new head always gets its own comment.
"""
import calendar
import time

IDLE_SECONDS = 2 * 3600  # the ruling's two hours since the newest pull_request run of the head
RULING = "owner, 2026-11-23 10:54 CST"
RUN_EVENT = "pull_request"  # the runs that age a head: a push-triggered or scheduled run is not the lane's own push
RED_PREFIX = "red: "
ISO = "%Y-%m-%dT%H:%M:%SZ"


def run_age(runs, now):
    """-> seconds since the newest run of the head, or None when no run has a readable createdAt (an age that cannot be read is unknown, never idle)."""
    times = []
    for r in runs:
        if r.get("event") != RUN_EVENT:
            continue
        try:
            times.append(calendar.timegm(time.strptime(r["createdAt"], ISO)))
        except (KeyError, TypeError, ValueError):
            return None
    return now - max(times) if times else None


def comment_body(n, sha, red, age):
    """-> the comment on drafted pull request n: the head, the red jobs, the hours idle, the ruling and the way back."""
    hours = int(age // 3600)
    return (f"Returned to draft: #{n} at head {sha} has been red and idle {hours} h (no push for {hours} h; the rule is "
            f"{IDLE_SECONDS // 3600} h, {RULING}).\n\nRed: {red}\n\n"
            f"To return it: fix the failing job, push, and run `merge {n} --ready`.")


def judge(host, n, row, now, errors, runs_first=False):
    """-> (verdict, detail, age) for open non-draft pull request n (REST row `row`): "idle" with the red names, "keep" with why it stays ready, or
    "unknown" with why a read could not say. `runs_first`: the sweep reads the head's runs before its state (one runs read for each PR it judges); the clash reads them only for a head that reads red. The host's base and branch are set to this PR's for the head_state read and put back."""
    sha = row["head"]["sha"]
    saved = (host.base, host.branch)
    host.base, host.branch = (row.get("base") or {}).get("ref") or saved[0], row["head"].get("ref") or saved[1]
    try:
        runs = host.runs(sha) if runs_first else None  # the host's head_state reads the same list from its memo
        state = host.head_state(n, sha)
        if state.startswith("unknown"):
            return "unknown", state, None
        if not state.startswith(RED_PREFIX):
            return "keep", state, None
        runs = host.runs(sha) if runs is None else runs
        if any(r.get("status") != "completed" for r in runs):  # head_state reads red beside a pending run; a run still going may yet turn the head
            return "keep", "a run is still going on the head", None
        age = run_age(runs, now)
    except errors as e:
        return "unknown", " ".join(str(e).split()), None
    finally:
        host.base, host.branch = saved
    if age is None:
        return "unknown", "no pull_request run with a readable time on the head", None
    return ("idle" if age >= IDLE_SECONDS else "keep"), state[len(RED_PREFIX):], age


def draft_one(host, n, row, now, say, errors, routes, runs_first=False):
    """Judge pull request n and draft it when it is idle red. -> "drafted", "route" (a cloud host: the route is printed, the comment is posted),
    "keep", or "unknown". A draft that failed, or a comment that failed, is unknown: the PR is named, nothing is retried."""
    verdict, detail, age = judge(host, n, row, now, errors, runs_first)
    if verdict == "unknown":
        say(f"merge: #{n} unknown, left as it is: {detail}")
        return "unknown"
    if verdict != "idle":
        return "keep"
    sha = row["head"]["sha"]
    try:
        ok, why = host.draft(n)
        if not ok and why != routes:
            say(f"merge: #{n} unknown, left as it is: the draft call failed: {' '.join(str(why).split())}")
            return "unknown"
        host.post_comment(n, comment_body(n, sha, detail, age))
    except errors as e:
        say(f"merge: #{n} unknown, posting its idle-red comment or its draft failed: {' '.join(str(e).split())}")
        return "unknown"
    if ok:
        say(f"merge: #{n} drafted: red and idle {int(age // 3600)} h at {sha[:9]} ({detail}); it has one comment that says how to return")
        return "drafted"
    say(f"merge: #{n} is red and idle {int(age // 3600)} h at {sha[:9]} ({detail}); this session cannot draft it, and its comment is posted. {routes}")
    return "route"


def sweep(host, now, say, errors, routes):
    """`merge --draft-idle`: draft each open non-draft PR that is idle red. -> the exit code: 0, or 1 when the open list could not be read.
    The summary line counts drafted, route printed, kept and unknown."""
    try:
        rows = host.open_pulls()
    except errors as e:
        say(f"merge: unknown (the open pull request list could not be read, so nothing is drafted: {' '.join(str(e).split())})")
        return 1
    counts = {"drafted": 0, "route": 0, "keep": 0, "unknown": 0}
    for row in sorted(rows, key=lambda r: r["number"]):
        if row.get("draft") is True:
            continue
        if row.get("draft") is not False:  # a row that does not say is unknown, never a PR to draft
            say(f"merge: #{row['number']} unknown, left as it is: the open-PR list does not say whether it is a draft")
            counts["unknown"] += 1
            continue
        counts[draft_one(host, row["number"], row, now, say, errors, routes, runs_first=True)] += 1
    say(f"merge: drafted {counts['drafted']} idle red pull request(s); route printed {counts['route']}, kept {counts['keep']}, unknown {counts['unknown']}")
    return 0
