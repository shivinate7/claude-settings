#!/usr/bin/env python3
"""Cost: one model call per scored (rev, file) group, run on demand, with no timer and no log. It measures the merge-time
prose judge against lint/route_claims_labelled.json, writes no file, and exits 0 whatever it finds.

    python3 lint/prove_route_judge.py [--labelled PATH] [--max-calls N]

Run it in the git repo that holds the rows' revs. Each file is read at its row's rev through git, never from the working
tree, and so is each cited backing file. The prompt is merge.prose_judge_prompt's, the call is decision_watch.invoke_model,
and the reply is parsed there by parse_verdict.

Labels: TRUE rows hold. STALE, PARTLY_STALE and HALF rows are stale-family rows. UNKNOWN and HISTORY rows, and a row with
a null rev, are skipped, and a group of skipped rows makes no call. A line span such as "16-20" is one row, judged under
its first line number. Only the verdict "stale" is scored: a false alarm is a TRUE row judged stale, a hit is a
stale-family row judged stale. The verdict "unbacked" is counted in its own field, out of all scored rows, and is neither.

A row the model could not judge is UNKNOWN, never a pass: a failed call, a malformed reply, a line the reply leaves out,
a file or line missing at the rev, or a group past --max-calls. It stays in its label's denominator and in neither
numerator. When a call failed, or its reply was not JSON, the unknown field carries the first line of that error text.

The one output line:
    false alarms A/B (P%), hits C/D, unbacked E/F, unknown G, skipped H
or, with a failed call, `unknown 17 (model error: <first line of the error>)`.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
for folder in ("lint", "hooks", "merge"):
    sys.path.insert(0, os.path.join(ROOT, folder))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import decision_watch  # noqa: E402  invoke_model and LINE_VERDICTS: the one model caller (hooks/decision_watch.py)
import merge  # noqa: E402  prose_judge_prompt and readable_verdicts: the one home of the judge (merge/merge.py)
import stale_cites  # noqa: E402  paren_cites, cite_kind, backing_path: the one home of a cite (lint/stale_cites.py)

HOLDS = ("TRUE",)
FLAGGED = ("STALE", "PARTLY_STALE", "HALF")
SPAN = re.compile(r"(\d+)(?:-(\d+))?")


def git_out(*args):
    """git's stdout as bytes, or None when git fails: the repo is the child's cwd."""
    run = _nowindow.run(["git", *args], capture_output=True)
    return run.stdout if run.returncode == 0 else None


def read_at(rev, path):
    """The text of `path` in the commit `rev`, or None when it is absent, a symlink, outside the tree, or not a plain file."""
    if not path or path.startswith("/") or ".." in path.split("/"):
        return None
    entry = git_out("ls-tree", "-z", rev, "--", path)
    if not entry:
        return None
    meta, _, _ = entry.rstrip(b"\0").partition(b"\t")
    mode, kind, sha = (meta.decode("ascii", "replace").split() + ["", "", ""])[:3]
    if kind != "blob" or mode == "120000":
        return None
    blob = git_out("cat-file", "blob", sha)
    return None if blob is None else blob.decode("utf-8", "replace")


def reader_at(rev):
    """A `read` for merge.prose_judge_prompt that fetches a backing file at `rev`; the tree argument is unused."""
    return lambda _wt, backing: read_at(rev, backing)


def judged(rows, text):
    """({first line: [row]}, {first line: (text, cites)}, unreadable rows) for one group's scored rows at `text`'s rev."""
    lines = text.replace("\r\n", "\n").split("\n")
    by_row, by_line, unreadable = {}, {}, []
    for r in rows:
        span = SPAN.fullmatch(str(r["line"]).strip())
        first = int(span.group(1)) if span else 0
        last = int(span.group(2) or first) if span else 0
        if not span or first < 1 or last < first or last > len(lines):
            unreadable.append(r)
            continue
        line = lines[first - 1] if last == first else " ".join(x.strip() for x in lines[first - 1:last])
        cites = [c for c in stale_cites.paren_cites(line) if stale_cites.backing_path(*stale_cites.cite_kind(c))]
        by_row.setdefault(first, []).append(r)
        by_line[first] = (line, cites)
    return by_row, by_line, unreadable


def judge_group(rev, path, rows):
    """-> ({id(row): the verdict word, or None for UNKNOWN}, the first line of the call's error or None) for one (rev, file)
    group, with one model call."""
    out = {id(r): None for r in rows}
    text = read_at(rev, path)
    if text is None:
        return out, None
    by_row, by_line, _ = judged(rows, text)
    if not by_line:
        return out, None
    prompt = merge.prose_judge_prompt(os.getcwd(), path, by_line, read=reader_at(rev))
    try:
        verdict, error = decision_watch.invoke_model(prompt, shape=decision_watch.LINE_VERDICTS)
    except Exception as exc:
        return out, (str(exc).splitlines() or [type(exc).__name__])[0]
    entries = merge.readable_verdicts(verdict) if verdict is not None else None
    if entries is None:
        return out, (str(error).splitlines() or [None])[0] if error else None
    said = {e["line"]: e["verdict"] for e in entries}
    for number, group in by_row.items():
        for r in group:
            out[id(r)] = said.get(number)
    return out, None


def score(rows, max_calls):
    """The verdict line for the labelled `rows`."""
    scored = [r for r in rows if r["label"] in HOLDS + FLAGGED and r.get("rev")]
    skipped = len(rows) - len(scored)
    groups = {}
    for r in scored:
        groups.setdefault((r["rev"], r["file"]), []).append(r)
    said, first_error = {}, None
    for calls, ((rev, path), group) in enumerate(groups.items()):
        if max_calls is not None and calls >= max_calls:
            said.update({id(r): None for r in group})
            continue
        verdicts, error = judge_group(rev, path, group)
        said.update(verdicts)
        first_error = first_error or error
    holds = [r for r in scored if r["label"] in HOLDS]
    flagged = [r for r in scored if r["label"] in FLAGGED]
    alarms = sum(1 for r in holds if said[id(r)] == "stale")
    hits = sum(1 for r in flagged if said[id(r)] == "stale")
    unbacked = sum(1 for r in scored if said[id(r)] == "unbacked")
    unknown = sum(1 for r in scored if said[id(r)] is None)
    unknown_text = "%d (model error: %s)" % (unknown, first_error) if unknown and first_error else str(unknown)
    rate = "%.1f%%" % (100.0 * alarms / len(holds)) if holds else "n/a"
    return "false alarms %d/%d (%s), hits %d/%d, unbacked %d/%d, unknown %s, skipped %d" % (
        alarms, len(holds), rate, hits, len(flagged), unbacked, len(scored), unknown_text, skipped)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure the merge-time prose judge against the labelled route claims.")
    parser.add_argument("--labelled", default=os.path.join(HERE, "route_claims_labelled.json"))
    parser.add_argument("--max-calls", type=int, default=None, help="stop after this many (rev, file) groups; the rest are UNKNOWN")
    args = parser.parse_args(argv)
    with open(args.labelled, encoding="utf-8") as f:
        rows = json.load(f)
    print(score(rows, args.max_calls))
    return 0


if __name__ == "__main__":
    sys.exit(main())
