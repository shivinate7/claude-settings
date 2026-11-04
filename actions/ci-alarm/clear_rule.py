#!/usr/bin/env python3
"""The one home of the failed-run clear: does a run N of another event group clear a failed run R of the same workflow?

merge/merge.py (Host.base_state) imports `clears`; actions/ci-alarm/alarm.sh calls this file as a command. One rule, two callers.

The rule. N clears R when every job of R that "may run" in N has conclusion `success` in every N entry of that name. A job of R
is left out, and N need not have run it, when both hold: it is not red in R, and its job-level `if:` has a top-level `&&`
conjunct `github.event_name == 'X'` with X not N's event, so it cannot run in N. Why: checks.yml gates `all-jobs-passed` and
`ci-done` on `pull_request`, so a push or schedule run always skips them, and a newer green push run never cleared a red nightly.
A job is kept (needed) when its test sits inside `||`, uses `!=`, its `if:` cannot be parsed, or its name maps to no job of the
workflow text. A red job (a completed job whose conclusion is not success, skipped, neutral or cancelled) is never left out.

Why this file reads the workflow text itself, and imports nothing from lint/ (lint/all_jobs_passed_rules.py `split_jobs`, `job_key`,
or lint/workflow_steps.py `job_block`): the action runs from a bare action path in other repos, with no checkout of this one, so only
the standard library and the files beside alarm.sh exist there. Those helpers also import lint/test_windows_split.py.

Command (alarm.sh): clear_rule.py --event EVENT --workflow FILE R_JOBS_JSON N_JOBS_JSON. Each jobs file is a JSON array of job objects
from the jobs API. Exit 0 when N clears R, 1 when it does not, 2 on an unreadable input.
"""
import argparse
import json
import re
import sys

PASS_OR_QUIET = ("success", "skipped", "neutral", "cancelled")  # a completed job with another conclusion is red
EVENT_TEST = re.compile(r"^github\.event_name\s*==\s*'([^']*)'$")
EVENT_TEST_REVERSED = re.compile(r"^'([^']*)'\s*==\s*github\.event_name$")
MATRIX_SUFFIX = re.compile(r"\s+\(.*\)$")


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
        value = strip_comment(value)
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
    """The job of the workflow a run's job name belongs to: a job whose name: is the name, else the job key; a matrix suffix ` (...)`
    is dropped and the same two tries made. None when no job maps."""
    for candidate in (name, MATRIX_SUFFIX.sub("", name)):
        for key, job in jobs.items():
            if job["name"] == candidate:
                return job
        if candidate in jobs:
            return jobs[candidate]
    return None


def is_red(job):
    return job.get("status") == "completed" and job.get("conclusion") not in PASS_OR_QUIET


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
    """True when N, a run of `n_event` of the same workflow as R, clears R's red jobs. `text` is the workflow file at N's head. An R with
    no jobs is never cleared. Callers check the run-level conditions (newer, newest of its group, success, another group)."""
    if not r_jobs:
        return False
    theirs = {}
    for j in n_jobs:
        theirs.setdefault(j["name"], []).append(j.get("conclusion") if j.get("status") == "completed" else None)
    return all(theirs.get(x) and all(c == "success" for c in theirs[x]) for x in needed_names(r_jobs, n_event, text))


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--event", required=True)
    p.add_argument("--workflow", required=True)
    p.add_argument("r_jobs")
    p.add_argument("n_jobs")
    a = p.parse_args(argv)
    try:
        with open(a.r_jobs, encoding="utf-8") as f:
            r_jobs = json.load(f)
        with open(a.n_jobs, encoding="utf-8") as f:
            n_jobs = json.load(f)
        with open(a.workflow, encoding="utf-8") as f:
            text = f.read()
        return 0 if clears(r_jobs, n_jobs, a.event, text) else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"clear_rule: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
