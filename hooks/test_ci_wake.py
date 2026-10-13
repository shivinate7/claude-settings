#!/usr/bin/env python3
"""Cases for hooks/ci_wake.py. Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_ci_wake.py

The hook is a PostToolUse command hook for the Bash tool, registered with `asyncRewake: true`.
Claude Code runs it in the background. Exit 2 wakes the session, and its stderr (or stdout, when
stderr is empty) shows as a system reminder. Every case runs the real hook as a subprocess, with
the hook JSON on stdin. No case imports the module.

Seams under test:
- Input: PostToolUse JSON on stdin, `{"tool_name": "Bash", "tool_input": {"command": "..."}, "cwd": ...}`.
  Only tool_name Bash counts.
- Decision, from tool_input.command alone: a watch starts for `gh pr ready <N>`, and for a
  `git push` whose target branch has an open PR that is not a draft (`git push origin B` and
  `git push origin HEAD:B`, also inside a `&&` chain). Command text inside quotes is not a command.
  A push to a branch with only a draft PR, or with no PR, starts no watch. Any other command
  exits 0 with no output and makes no gh call.
- Watch: one read of the PR head, one list of the runs on that head, one blocking
  `gh run watch <id>` per run, then one read of each run's jobs. It never polls.
- Verdict: exit 2, and exactly one output line `CI <green|red|cancelled> on <sha7>: <failing job names>`.
  A cancelled run beside a run of the same name that ran, on the same head, reads as the ran one,
  in either list order, completed or in progress (decision merge-needs-a-proven-head). A cancelled
  run with no such twin reads cancelled.
- Unreadable gh: gh not on PATH, exit non-zero, or output that is not JSON. For a command that
  could start a watch, exit 2 with one line `CI unknown on <sha>: <reason>`. Never a silent exit 0.
  A branch with no PR is not unreadable: it is no watch.

The gh stub: a `gh` launcher in a temp folder, which is the only PATH entry for these cases, so
no real gh is ever reached. On Windows the launcher is `gh.cmd`. A list-form subprocess call of
"gh" skips a .cmd stand-in (decision list-form-subprocess-ignores-a-path-shim-on-windows), so the
hook must find gh with shutil.which. The stub answers the --json forms of `pr view <N|branch>`,
`pr list --head B`, `run list --commit SHA`, `run view <id>` and `run watch <id>` from a JSON
fixture. It appends every call to a log. A run marked in_progress_until_watch stays in progress
until `run watch` names it. Fixture mode "error" makes every call fail with exit 1. Mode
"garbage" makes every call print non-JSON with exit 0.

Environment: CI_WAKE_MODULE names the module under test (default hooks/ci_wake.py beside this
file). A mutation run points it at a copy with a defect in it.

Scratch files live in one temp directory, removed at exit.
"""

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# Absolute: each case runs the hook with its own temp folder as cwd, so a relative path breaks there.
MODULE = os.path.abspath(os.environ.get("CI_WAKE_MODULE") or os.path.join(HERE, "ci_wake.py"))
PY = sys.executable
TIMEOUT = 30  # seconds; a hook that hangs fails its case, it does not stall the run
SHA = "9f3c2a1b7d4e5f60718293a4b5c6d7e8f9012345"
SHA7 = SHA[:7]

TMP = tempfile.mkdtemp(prefix="ci-wake-test-")
atexit.register(shutil.rmtree, TMP, True)
BIN = os.path.join(TMP, "bin")
os.makedirs(BIN)

STUB_SRC = r'''
import json, os, sys

def flag(args, name):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a[len(name) + 1:]
    return None

def logged_calls():
    with open(os.environ["GH_STUB_LOG"], encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]

def view(r, watched, with_jobs):
    hidden = bool(r.get("in_progress_until_watch")) and str(r["databaseId"]) not in watched
    out = {"databaseId": r["databaseId"], "name": r["name"], "workflowName": r["workflowName"],
           "headSha": r["headSha"], "event": r["event"],
           "status": "in_progress" if hidden else r["status"],
           "conclusion": None if hidden else r["conclusion"]}
    if with_jobs:
        out["jobs"] = [] if hidden else r["jobs"]
    return out

def main(args):
    with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")
    with open(os.environ["GH_STUB_FIXTURE"], encoding="utf-8") as f:
        fx = json.load(f)
    if fx.get("mode") == "error":
        sys.stderr.write("HTTP 401: Bad credentials\n")
        return 1
    if fx.get("mode") == "garbage":
        sys.stdout.write("<html>not json</html>\n")
        return 0
    obj = args[0] if args else ""
    verb = args[1] if len(args) > 1 else ""
    key = args[2] if len(args) > 2 else ""
    watched = set(str(c[2]) for c in logged_calls() if c[:2] == ["run", "watch"] and len(c) > 2)
    if obj == "pr" and verb == "view":
        hits = [p for p in fx["prs"] if str(p["number"]) == key or p["headRefName"] == key]
        if not hits:
            sys.stderr.write("no pull requests found\n")
            return 1
        sys.stdout.write(json.dumps(hits[0]) + "\n")
        return 0
    if obj == "pr" and verb == "list":
        head = flag(args, "--head")
        hits = [p for p in fx["prs"] if head is None or p["headRefName"] == head]
        sys.stdout.write(json.dumps(hits) + "\n")
        return 0
    if obj == "run" and verb == "list":
        commit = flag(args, "--commit")
        hits = [r for r in fx["runs"] if commit is None or r["headSha"].startswith(commit)]
        sys.stdout.write(json.dumps([view(r, watched, False) for r in hits]) + "\n")
        return 0
    if obj == "run" and verb in ("view", "watch"):
        hits = [r for r in fx["runs"] if str(r["databaseId"]) == key]
        if not hits:
            sys.stderr.write("could not find any workflow run with id %s\n" % key)
            return 1
        r = hits[0]
        if verb == "view":
            sys.stdout.write(json.dumps(view(r, watched, True)) + "\n")
            return 0
        sys.stdout.write("Run %s (%s) completed with '%s'\n" % (r["name"], r["databaseId"], r["conclusion"]))
        return 0 if r["conclusion"] in ("success", "skipped", "neutral") else 1
    sys.stderr.write("stub gh: unsupported: %s\n" % " ".join(args))
    return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def write_stub():
    stub_py = os.path.join(TMP, "gh_stub.py")
    with open(stub_py, "w", encoding="utf-8") as f:
        f.write(STUB_SRC)
    launcher = os.path.join(BIN, "gh")
    with open(launcher, "w", encoding="utf-8", newline="\n") as f:
        f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (PY, stub_py))
    os.chmod(launcher, 0o755)
    with open(os.path.join(BIN, "gh.cmd"), "w", encoding="utf-8", newline="") as f:
        f.write('@echo off\r\n"%s" "%s" %%*\r\n' % (PY, stub_py))


write_stub()


def pr(number, draft=False, branch="hook-wave-2"):
    return {"number": number, "isDraft": draft, "headRefName": branch, "headRefOid": SHA,
            "state": "OPEN", "url": "https://github.com/shivinate7/claude-settings/pull/%d" % number}


def job(name, conclusion):
    return {"name": name, "conclusion": conclusion, "status": "completed"}


def run(run_id, name, conclusion, jobs, in_progress_until_watch=False):
    return {"databaseId": run_id, "name": name, "workflowName": name, "headSha": SHA,
            "event": "pull_request", "status": "completed", "conclusion": conclusion,
            "jobs": jobs, "in_progress_until_watch": in_progress_until_watch}


def fixture(prs=(), runs=(), mode="ok"):
    return {"mode": mode, "prs": list(prs), "runs": list(runs)}


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


READY = [pr(12)]
GREEN = run(901, "gates", "success", [job("lint", "success"), job("unit", "success")])
RED = run(902, "gates", "failure",
          [job("lint", "success"), job("unit", "failure"), job("e2e", "failure")])
CANCEL_903 = run(903, "gates", "cancelled", [job("unit", "cancelled")])
RAN_904 = run(904, "gates", "success", [job("unit", "success")])
CANCEL_905 = run(905, "gates", "cancelled", [job("unit", "cancelled")])
INPROG_906 = run(906, "gates", "success", [job("unit", "success")], in_progress_until_watch=True)
INPROG_907 = run(907, "codeql", "success", [job("scan", "success")], in_progress_until_watch=True)

FAILS = []
COUNT = [0]
LINE = re.compile(r"^CI (green|red|cancelled|unknown) on (\S+?): ?(.*)$")


def check(label, ok, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
        return
    FAILS.append(label)
    print("FAIL  %s  [%s]" % (label, detail) if detail else "FAIL  " + label)


class Result:
    def __init__(self, rc, out, err, calls, hung):
        self.rc, self.out, self.err, self.calls, self.hung = rc, out, err, calls, hung
        self.lines = [x for x in (out + "\n" + err).splitlines() if x.strip()]


def _text(x):
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else x


def read_calls(log):
    with open(log, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def run_hook(payload, scen, path="stub"):
    """Run the real hook once. path "stub": PATH is the stub folder only. path "missing": PATH is empty."""
    case = tempfile.mkdtemp(prefix="case-", dir=TMP)
    fixture_path = os.path.join(case, "fixture.json")
    log = os.path.join(case, "gh.log")
    with open(fixture_path, "w", encoding="utf-8") as f:
        json.dump(scen, f)
    open(log, "w").close()
    search = BIN
    if path == "missing":
        search = os.path.join(case, "empty")
        os.makedirs(search)
    # Drop every spelling of PATH first: on Windows os.environ keys are case-insensitive.
    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
    env.update(PATH=search, GH_STUB_FIXTURE=fixture_path, GH_STUB_LOG=log)
    payload = dict(payload)
    payload.setdefault("cwd", case)
    try:
        p = subprocess.run([PY, MODULE], input=json.dumps(payload), capture_output=True,
                           encoding="utf-8", errors="replace", env=env, cwd=case, timeout=TIMEOUT)
        return Result(p.returncode, p.stdout or "", p.stderr or "", read_calls(log), False)
    except subprocess.TimeoutExpired as e:
        return Result(None, _text(e.stdout), _text(e.stderr), read_calls(log), True)


def watched(res):
    return [c[2] for c in res.calls if c[:2] == ["run", "watch"] and len(c) > 2]


def count(res, *prefix):
    return sum(1 for c in res.calls if c[:len(prefix)] == list(prefix))


def verdict_of(res):
    """(verdict, sha, names) when the output is exactly one CI line, else None."""
    if len(res.lines) != 1:
        return None
    m = LINE.match(res.lines[0].strip())
    return (m.group(1), m.group(2), m.group(3).strip()) if m else None


def why(res):
    return "rc=%s hung=%s lines=%r calls=%d" % (res.rc, res.hung, " | ".join(res.lines[:2])[:160], len(res.calls))


def expect_verdict(label, res, verdict, names_in=(), names_out=()):
    v = verdict_of(res)
    sha_ok = verdict == "unknown" or (v is not None and v[1] == SHA7)
    check("%s: exit 2, one CI %s line" % (label, verdict),
          res.rc == 2 and not res.hung and v is not None and v[0] == verdict and sha_ok, why(res))
    for name in names_in:
        check("%s: line names %s" % (label, name), v is not None and name in v[2], why(res))
    for name in names_out:
        check("%s: line does not name %s" % (label, name), v is not None and name not in v[2], why(res))


def expect_silent(label, res):
    check("%s: exit 0, no output" % label, res.rc == 0 and not res.hung and res.lines == [], why(res))


def expect_no_watch(label, res):
    check("%s: no run watch" % label, watched(res) == [], why(res))


def expect_no_gh(label, res):
    check("%s: no gh call" % label, res.calls == [], why(res))


def expect_watch(label, res, ids):
    """One blocking watch per run, and the run list read once (no polling)."""
    check("%s: watches %s once each, runs listed once" % (label, ids),
          sorted(watched(res)) == sorted(ids) and count(res, "run", "list") <= 1, why(res))


def main():
    hook_exists = os.path.isfile(MODULE)
    check("module under test exists (missing module = red for this reason)", hook_exists, MODULE)

    # Watch starts.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]))
    expect_verdict("gh pr ready 12 (green)", res, "green")
    expect_watch("gh pr ready 12", res, ["901"])

    res = run_hook(bash("git push origin hook-wave-2"), fixture(READY, [GREEN]))
    expect_verdict("git push to ready PR (green)", res, "green")
    expect_watch("git push to ready PR", res, ["901"])

    res = run_hook(bash("git add -A && git commit -m ci && git push origin HEAD:hook-wave-2"),
                   fixture(READY, [GREEN]))
    expect_verdict("chained git push via HEAD:branch (green)", res, "green")
    expect_watch("chained git push via HEAD:branch", res, ["901"])

    # No watch.
    res = run_hook(bash("git push origin hook-wave-2"), fixture([pr(12, draft=True)], [GREEN]))
    expect_silent("git push, only a draft PR", res)
    expect_no_watch("git push, only a draft PR", res)

    res = run_hook(bash("git push origin hook-wave-2"), fixture([pr(12, branch="other-branch")], [GREEN]))
    expect_silent("git push, no PR for this branch (a ready PR on another branch)", res)
    expect_no_watch("git push, no PR for this branch", res)

    res = run_hook(bash("git push origin hook-wave-2"), fixture([], [GREEN]))
    expect_silent("git push, no PR at all", res)
    expect_no_watch("git push, no PR at all", res)

    res = run_hook(bash("ls -la"), fixture(READY, [GREEN]))
    expect_silent("ls -la", res)
    expect_no_gh("ls -la", res)

    res = run_hook(bash("git status"), fixture(READY, [GREEN]))
    expect_silent("git status", res)
    expect_no_gh("git status", res)

    res = run_hook(bash('git commit -m "note: gh pr ready 12 later"'), fixture(READY, [GREEN]))
    expect_silent("trigger text inside a quoted commit message", res)
    expect_no_watch("trigger text inside a quoted commit message", res)

    res = run_hook(bash('echo "git push origin hook-wave-2"'), fixture(READY, [GREEN]))
    expect_silent("trigger text inside a quoted echo", res)
    expect_no_watch("trigger text inside a quoted echo", res)

    res = run_hook({"tool_name": "Edit", "tool_input": {"command": "gh pr ready 12"}},
                   fixture(READY, [GREEN]))
    expect_silent("non-Bash tool carrying a trigger command", res)
    expect_no_watch("non-Bash tool carrying a trigger command", res)

    # Verdicts.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [RED]))
    expect_verdict("red run", res, "red", names_in=["unit", "e2e"], names_out=["lint"])

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [CANCEL_903, RAN_904]))
    expect_verdict("cancelled twin listed first beside a ran run", res, "green", names_out=["unit"])

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [RAN_904, CANCEL_903]))
    expect_verdict("cancelled twin listed second beside a ran run", res, "green", names_out=["unit"])

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [CANCEL_903, INPROG_906]))
    expect_verdict("cancelled twin beside an in-progress ran run", res, "green")
    expect_watch("cancelled twin beside an in-progress ran run", res, ["906"])

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [CANCEL_905]))
    expect_verdict("cancelled run with no twin", res, "cancelled")

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [INPROG_906, INPROG_907]))
    expect_verdict("two in-progress runs, both waited on", res, "green")
    expect_watch("two in-progress runs", res, ["906", "907"])

    # Unreadable gh: never a silent exit 0 for a command that could start a watch.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), path="missing")
    expect_verdict("gh not on PATH, gh pr ready", res, "unknown")
    expect_no_watch("gh not on PATH, gh pr ready", res)

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN], mode="error"))
    expect_verdict("gh exits non-zero, gh pr ready", res, "unknown")

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN], mode="garbage"))
    expect_verdict("gh prints non-JSON, gh pr ready", res, "unknown")

    res = run_hook(bash("git push origin hook-wave-2"), fixture(READY, [GREEN], mode="error"))
    expect_verdict("gh exits non-zero, git push", res, "unknown")

    res = run_hook(bash("ls -la"), fixture(READY, [GREEN]), path="missing")
    expect_silent("gh not on PATH, ls -la (no gh needed)", res)

    print()
    print("%d checks, %d failed" % (COUNT[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
