#!/usr/bin/env python3
"""Cases for hooks/ci_wake.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_ci_wake.py

The hook is a PostToolUse command hook for the Bash and PowerShell tools, registered with
`asyncRewake: true`. Claude Code runs it in the background. Exit 2 wakes the session, and its
stderr shows as a system reminder. Every case but the `watch_run` cases runs the real hook as a
subprocess, with the hook JSON on stdin and its stdout and stderr written to files. The `watch_run`
cases import the module and swap its `gh`, `time`, `subprocess` and `shutil` for fakes: no gh runs
and no wait is real.

Decision ci-wait-reads-run-status, section "The CI wake-up":
- Only a ready call starts a watch: the shell `gh pr ready <N>`, or a GitHub MCP
  update_pull_request call with draft false. A `git push` in any form starts none, and makes no gh call.
- Each `gh pr ready` in one command gets its own watch, in one process. The hook prints one
  verdict line per PR, then exits 2 once.
- Text inside quotes, inside a heredoc body, or after an unquoted `#` is no command. A lone quote
  in earlier text does not hide a later `gh pr ready`. A `#` inside quotes is no comment.
- The watch has its own deadline. A run still pending at the deadline wakes with exit 2 and a
  "still running" line. It does not wait for the run to end.
- One watcher runs per PR. A second watcher for the same PR exits 0 with no output and no watch.
  A killed watcher, or a finished one, releases the PR.
- Any uncaught error exits 2 with one "unknown" line, never exit 1.

Decision ci-wait-reads-run-status ("CI waits read the run status"): the hook never runs
`gh run watch` (one watch made 131 API calls in 60 s). `watch_run` reads `gh api -i repos/<repo>/actions/runs/<id>`
at once (`gh run view` takes no -i, and the quota headers come on -i), then every 30 s for 4 minutes, then at growing gaps of 120 s at most, and returns when
the status is `completed` or when the deadline passes (55 minutes): its last pause ends at the
deadline, never past it. A call made at its deadline
or past it makes no read and returns at once. A failed or non-JSON read gets one retry after the
STATUS_PAUSE pause (decision ci-wait-reads-run-status). A second failed read raises Unknown, so the wake
line is `CI unknown`. A status that is not `completed` (in_progress, queued) means read again.

Verdict line, exit 2: `CI <green|red|cancelled> on <sha7>: <failing job names>`.
A cancelled run beside a run of the same name that ran, on the same head, reads as the ran one,
in either list order, completed or in progress (merge/merge.py Host.judge_runs). A cancelled
run with no such twin reads cancelled.
Unreadable gh: gh not on PATH, exit non-zero, or output that is not JSON. For a `gh pr ready`
that could start a watch, exit 2 with one line `CI unknown on <sha>: <reason>`. Never a silent exit 0.

Seams under test:
- CI_WAKE_MODULE: the module under test (default hooks/ci_wake.py beside this file).
- CI_WAKE_LOCK_DIR: the folder that holds the per-PR watch locks. Each case sets its own.
- CI_WAKE_DEADLINE: the watch budget in seconds. Unset, the hook uses its own default.
- `watch_run(run_id, cwd, deadline)` keeps its signature (deadline: a time.monotonic() value). It
  reads through the module's `gh()`, reads the clock with the module's `time.monotonic`, pauses
  with the module's `time.sleep`, and makes no direct `subprocess` call.
- `wait_for(sha, cwd, deadline)` keeps its signature (deadline: a time.monotonic() value). Its gh reads
  go through the module's `gh()`, it reads the clock with the module's `time.monotonic`, and it pauses
  with the module's `time.sleep`. The pace and deadline cases run it in process on a fake clock.
- `time.sleep` in the hook process: a case run through FAST_SLEEP_LAUNCHER caps it at 0.05 s, so the
  30 s status pause costs 0.05 s there. Every pause of the hook must go through `time.sleep`.

The gh stub: a `gh` launcher in a temp folder, the only PATH entry for these cases, so no real gh
is ever reached. On Windows the launcher is `gh.cmd`, and a list-form subprocess call of "gh"
skips a .cmd stand-in (decision list-form-subprocess-ignores-a-path-shim-on-windows). So the hook
must find gh with shutil.which. The stub answers `gh api repos/O/R/pulls/N` and
`gh api -X GET repos/O/R/pulls -F head=OWNER:BRANCH -f state=open` (it refuses any argument holding `&`) in the REST field names only (the cloud proxy
refuses GraphQL: every `gh pr ...` call and `gh api graphql` exit 1 with the proxy's 403 text), and the --json forms of `run list --commit SHA` and `run view <id>` from a JSON fixture. `run view`
prints only the fields `--json` names; `run view --json status` exits 1, since the status read is the api route
`gh api -i repos/O/R/actions/runs/<id>` (under -i a header block with a full quota). `run watch` exits 1: the hook must never run it. The stub
writes every call to its own file beside the log (one file per call, so parallel calls never share one).
A run marked in_progress_at_list reads in progress at `run list` and as its fixture says at
`run view`. A run with ping_on_status_read: its status read (the api route) first
connects to the localhost port in GH_STUB_READY_PORT, so a case can wait for that read with one
accept() and no polling. A run with fail_status_read: that read exits 1. A run with in_progress_reads N: its first N
reads of the run, by either route (`run view <id>` in any --json fields, or the status read), counted from the call log,
show it in progress with no conclusion, and later reads show the fixture: a run that ends only after N reads. A run with
early_status S shows S (such as queued) in place of in_progress for those N reads. A run with
appears_at_list N: `run list` leaves it out until the Nth `run list` call of the case (counted from the call
log, all PRs together). A run with unfinished_to_list N: `run list` shows it in progress, with no
conclusion, up to the Nth `run list` call, and as its fixture says after. Fixture mode "error"
makes every call fail with exit 1. Mode "garbage" makes every call print non-JSON with exit 0.
A prs, runs or workflows entry with a `repo` field answers only a call that reaches that repo: a call
with its own -R or --repo (any spelling gh takes), else a PR URL selector's repo, else GH_REPO, else the
fixture's `cwd_repo`. An entry with no
`repo` answers every call. `workflows` is the `gh workflow list` answer (one active `checks` workflow
when absent); without --all only active entries answer. The fixture key `workflow_list` ("error" or
"garbage") fails that one call and no other. The fixture key `list_error_from` N makes every `run list`
from the Nth call of the case on exit 1 (HTTP 403), so a re-list can be refused after a judged run.

Draft run, then the real run: `gh pr create --draft` makes a run
whose jobs all skip, and `gh pr ready` makes the real run seconds later. A hook that lists the head
once waits on the draft run, reads it as skipped, and prints "CI red ...: workflow checks"
(judge_runs' "skipped, no job ran") before the real run shows. The cases below use these rules:
- A run that ends skipped is no run, whether the list showed it skipped or in progress.
- While no run that ran has been judged, the hook lists the head again, at most once per 30 s
  (STATUS_PAUSE). It keeps listing until its deadline: the last pause ends at the deadline.
  No list comes after the deadline. A list made at the deadline after that pause is allowed.
- A head with no real run at the deadline wakes with `CI unknown`, never red or green.
- A real run that failed still reads red, with its own failing job names.
- After the first judged run, the hook re-lists the head once at once. A run visible at that re-list is
  judged too. Every later list is 30 s or more after the one before it, so a stream of new runs costs
  one list per 30 s.

Repo rules, each pinned by a case below:
- A GH_REPO set in the command (`export GH_REPO=o/r`, `$env:GH_REPO = ...`) names the repo of the hook's
  own gh calls, as a command prefix does.
- Every gh call of a watch passes the PR's repo as -R, the same one each time. A watch that reads runs
  from the folder's repo finds none, and says "no run yet" for a PR whose CI passed.
- A repo with no active workflow starts no watch: no output, exit 0, no run read. The hook asks
  `gh workflow list -R <repo>` for that.
- A repo with an active workflow and no run on the head still wakes "CI unknown on <sha7>: no run
  yet" at the deadline. That is the real alert.
- A failed `gh workflow list` read is not "no workflows": the watch runs as it does today.

Cloud route (ci-wake-mcp-ready): a GitHub MCP update_pull_request call with draft false marks a PR
ready. It starts a watch on the PR's own repo, from the owner and repo of tool_input. A call with no
draft field, or with draft true, starts none.

Scratch files live in one temp directory, removed at exit.
"""

import atexit
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
# Absolute: each case runs the hook with its own temp folder as cwd, so a relative path breaks there.
MODULE = os.path.abspath(os.environ.get("CI_WAKE_MODULE") or os.path.join(HERE, "ci_wake.py"))
PY = sys.executable
TIMEOUT = 30  # seconds; a hook that hangs fails its case, it does not stall the run
SHA = "9f3c2a1b7d4e5f60718293a4b5c6d7e8f9012345"
SHA7 = SHA[:7]
SHA_B = "1a2b3c4d5e6f708192a3b4c5d6e7f80910111213"  # the head of PR 13
SHA7_B = SHA_B[:7]

TMP = tempfile.mkdtemp(prefix="ci-wake-test-")
atexit.register(shutil.rmtree, TMP, True)
BIN = os.path.join(TMP, "bin")
os.makedirs(BIN)

STUB_SRC = r'''
import json, os, socket, sys, time

def flag(args, name):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a[len(name) + 1:]
    return None

def is_repo_flag(a):
    """True for one argv token that names a repo: -R or --repo (the value is the next token), or a token
    that carries its value, as -Ro/r, -R=o/r and --repo=o/r do."""
    return a in ("-R", "--repo") or a.startswith("--repo=") or (a.startswith("-R") and not a.startswith("--"))

def strip_repo(args):
    """The words of one gh call without its repo flag and value, so the verb, the id and the key read the
    same wherever the flag sits. log_call keeps the raw argv: the -R check reads that."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in ("-R", "--repo"):
            skip = True
        elif not is_repo_flag(a):
            out.append(a)
    return out

def api_repo(args):
    """The repo in the path of a `gh api repos/OWNER/REPO/...` call, else None. A {owner}/{repo} placeholder
    names none: gh fills it from the folder."""
    plain = strip_repo(args)
    path = next((a for a in plain[1:] if a.startswith("repos/")), "") if plain[:1] == ["api"] else ""
    parts = path.split("/")
    if len(parts) > 2 and parts[0] == "repos" and "{" not in parts[1] + parts[2]:
        return parts[1] + "/" + parts[2].split("?")[0]
    return None

def repo_of(args):
    """The repo a gh call names with its own flag, in any spelling gh takes, or None."""
    if api_repo(args):
        return api_repo(args)
    for i, a in enumerate(args):
        if a in ("-R", "--repo"):
            if i + 1 < len(args):
                return args[i + 1]
        elif a.startswith("--repo="):
            return a[len("--repo="):]
        elif a.startswith("-R") and not a.startswith("--"):
            return a[3:] if a.startswith("-R=") else a[2:]
    return None

def call_repo(args, fx):
    """The repo a gh call reaches, as gh picks it: its own -R or --repo or the repo in its api path,
    else GH_REPO, else the folder's repo (the fixture's cwd_repo)."""
    named = repo_of(args)
    if named:
        return named
    return os.environ.get("GH_REPO") or fx.get("cwd_repo", "")

def here(entry, args, fx):
    """True when a gh call reaches a fixture entry. An entry with no repo is in every repo."""
    if entry.get("repo") is None:
        return True
    return entry["repo"] == call_repo(args, fx)

DEFAULT_WORKFLOWS = [{"id": 1, "name": "checks", "path": ".github/workflows/checks.yml", "state": "active"}]

_SEQ = [0]

def call_files(base):
    """The finished call files of one log, oldest first. The name starts with the time, zero padded."""
    folder, name = os.path.split(base)
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if n.startswith(name + ".") and n.endswith(".json"))

def log_call(args):
    """One call, one file. The line is written under a .part name and renamed once whole, so a
    reader never sees half of one. A shared append lost lines when two processes wrote at once on
    Windows (CI run 38484705402 lost 2 of 8 calls)."""
    base = os.environ["GH_STUB_LOG"]
    while True:
        _SEQ[0] += 1
        stem = "%s.%020d.%d.%d" % (base, time.time_ns(), os.getpid(), _SEQ[0])
        try:
            fd = os.open(stem + ".part", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError:
            continue
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")
    for _ in range(100):
        try:
            os.replace(stem + ".part", stem + ".json")
            return
        except PermissionError:   # Windows: a scanner may hold the new file for a moment
            time.sleep(0.02)
    raise OSError("gh stub: could not finish the call file " + stem)

def read_log(base):
    out = []
    for path in call_files(base):
        with open(path, encoding="utf-8") as f:
            out.append(json.loads(f.read()))
    return out

def view(r, listed, n=1):
    """One run as `gh --json` prints it. listed: the `run list` form, which has no jobs; n: the
    number of that `run list` call. A run marked in_progress_at_list reads in progress there, and as
    its fixture says at `run view`. So does a run with unfinished_to_list >= n."""
    hidden = listed and (bool(r.get("in_progress_at_list")) or n <= r.get("unfinished_to_list", 0))
    out = {"databaseId": r["databaseId"], "name": r["name"], "workflowName": r["workflowName"],
           "headSha": r["headSha"], "event": r["event"],
           "status": "in_progress" if hidden else r["status"],
           "conclusion": None if hidden else r["conclusion"]}
    if not listed:
        out["jobs"] = r["jobs"]
    return out

def run_read_id(args):
    """The run id of one read of a run: `run view <id>`, or the status read `api [-i] repos/O/R/actions/runs/<id>`.
    Else None. The -R of a call is not read: strip_repo drops it."""
    plain = strip_repo(args)
    if plain[:2] == ["run", "view"] and len(plain) > 2:
        return plain[2]
    path = next((a for a in plain[1:] if a.startswith("repos/")), "") if plain[:1] == ["api"] else ""
    parts = path.split("/")
    return parts[5] if len(parts) == 6 and parts[3:5] == ["actions", "runs"] else None

def views_of(key):
    """How many reads of run <key> the log holds, by either route, this one too (log_call ran first). Each gh
    call is a new process, so the log is the only count that outlives one."""
    return sum(1 for a in read_log(os.environ["GH_STUB_LOG"]) if run_read_id(a) == key)

def lists_of():
    """How many `run list` calls the log holds, this one too, as views_of counts."""
    return sum(1 for a in read_log(os.environ["GH_STUB_LOG"]) if strip_repo(a)[:2] == ["run", "list"])

def ready_ping():
    port = os.environ.get("GH_STUB_READY_PORT")
    if port:
        socket.create_connection(("127.0.0.1", int(port)), timeout=10).close()

def rest_pr(p):
    """One fixture PR as the REST pulls API prints it: REST names only, no GraphQL name."""
    return {"number": p["number"], "draft": p["isDraft"], "state": p["state"].lower(),
            "html_url": p["url"], "head": {"ref": p["headRefName"], "sha": p["headRefOid"]},
            "merged": False, "merged_at": None}

def rest(path, full, args, fx):
    """The pulls endpoints: `repos/O/R/pulls/N`, and `repos/O/R/pulls` with fields head=OWNER:BRANCH, state=open."""
    parts = path.split("/")
    if len(parts) < 4 or parts[0] != "repos" or parts[3] != "pulls":
        sys.stderr.write("stub gh: unsupported api path: %s\n" % full)
        return 1
    mine = [p for p in fx["prs"] if here(p, args, fx)]
    if len(parts) == 5:
        hits = [p for p in mine if str(p["number"]) == parts[4]]
        if not hits:
            sys.stdout.write('{"message":"Not Found","status":"404"}\n')
            sys.stderr.write("gh: Not Found (HTTP 404)\n")
            return 1
        sys.stdout.write(json.dumps(rest_pr(hits[0])) + "\n")
        return 0
    query = {}
    for i, a in enumerate(args):
        if a in ("-f", "-F") and i + 1 < len(args) and "=" in args[i + 1]:
            k, v = args[i + 1].split("=", 1)
            query[k] = v
    head = query.get("head", "")
    owner, _, branch = head.partition(":")
    # a {owner} placeholder is the folder's owner; the stub holds one repo per entry
    want = [p for p in mine if p["headRefName"] == branch and query.get("state") == "open"
            and p["state"] == "OPEN" and (owner.startswith("{") or not call_repo(args, fx)
                                    or owner == call_repo(args, fx).split("/")[0])]
    sys.stdout.write(json.dumps([rest_pr(p) for p in want]) + "\n")
    return 0

def header_block():
    """The header block `gh api -i` prints before a body: a full quota, its reset an hour on, so no wait."""
    return ("HTTP/2.0 200 OK\nContent-Type: application/json; charset=utf-8\nX-RateLimit-Limit: 5000\n"
            "X-RateLimit-Remaining: 5000\nX-RateLimit-Reset: %d\n\n" % (int(time.time()) + 3600))

def run_api(parts, args, fx):
    """`gh api [-i] repos/O/R/actions/runs/<id>`: the status read of one run, answered as its fixture answers
    `run view`. Under -i the reply starts with the header block the quota is read from."""
    hits = [r for r in fx["runs"] if here(r, args, fx) and str(r["databaseId"]) == parts[5]]
    if not hits:
        sys.stdout.write('{"message":"Not Found","status":"404"}\n')
        sys.stderr.write("gh: Not Found (HTTP 404)\n")
        return 1
    r = hits[0]
    if r.get("fail_status_read"):
        sys.stderr.write("HTTP 502: Bad Gateway\n")
        return 1
    if r.get("ping_on_status_read"):
        ready_ping()
    if views_of(parts[5]) <= r.get("in_progress_reads", 0):
        r = dict(r, status=r.get("early_status", "in_progress"), conclusion=None)
    sys.stdout.write((header_block() if "-i" in args else "") + json.dumps(view(r, False)) + "\n")
    return 0

def main(args):
    log_call(args)
    with open(os.environ["GH_STUB_FIXTURE"], encoding="utf-8") as f:
        fx = json.load(f)
    if fx.get("mode") == "error":
        sys.stderr.write("HTTP 401: Bad credentials\n")
        return 1
    if fx.get("mode") == "garbage":
        sys.stdout.write("<html>not json</html>\n")
        return 0
    amp = [a for a in args if "&" in a]
    if amp:  # cmd.exe behind a .cmd launcher reads `&` as a command separator
        sys.stderr.write("'state' is not recognized as an internal or external command: %r\n" % amp)
        return 1
    plain = strip_repo(args)
    obj = plain[0] if plain else ""
    verb = plain[1] if len(plain) > 1 else ""
    key = plain[2] if len(plain) > 2 else ""
    if obj == "pr" or (obj == "api" and verb == "graphql"):
        # The cloud proxy refuses every GraphQL call: `gh pr view|list|checks|status` and `gh api graphql`.
        sys.stderr.write("GitHub GraphQL is not available from Claude Code sessions; use the REST API (HTTP 403)\n")
        return 1
    if obj == "api":
        words, skip = [], False
        for a in plain[1:]:
            if skip:
                skip = False
            elif a in ("-X", "-f", "-F", "--hostname"):
                skip = True
            elif not a.startswith("-"):
                words.append(a)
        path = words[0] if words else ""
        parts = path.split("/")
        if len(parts) == 6 and parts[3:5] == ["actions", "runs"]:
            return run_api(parts, args, fx)
        return rest(path, path, args, fx)
    if obj == "run" and verb == "list":
        commit = flag(args, "--commit")
        n = lists_of()
        if fx.get("list_error_from") and n >= fx["list_error_from"]:   # the lists from that call on are refused
            sys.stderr.write("HTTP 403: Forbidden\n")
            return 1
        hits = [r for r in fx["runs"] if here(r, args, fx) and (commit is None or r["headSha"].startswith(commit))
                and r.get("appears_at_list", 1) <= n]
        sys.stdout.write(json.dumps([view(r, True, n) for r in hits]) + "\n")
        return 0
    if obj == "workflow" and verb == "list":
        if fx.get("workflow_list") == "error":
            sys.stderr.write("HTTP 401: Bad credentials\n")
            return 1
        if fx.get("workflow_list") == "garbage":
            sys.stdout.write("<html>not json</html>\n")
            return 0
        # gh lists the active workflows unless --all; the fixture's repo field is not gh's, so it is dropped
        wf = [{k: v for k, v in w.items() if k != "repo"} for w in fx.get("workflows", DEFAULT_WORKFLOWS)
              if here(w, args, fx) and ("--all" in args or w.get("state") == "active")]
        fields = flag(args, "--json")
        if fields:
            wf = [{k: v for k, v in w.items() if k in fields.split(",")} for w in wf]
        sys.stdout.write(json.dumps(wf) + "\n")
        return 0
    if obj == "run" and verb == "watch":
        sys.stderr.write("stub gh: the hook must not run `gh run watch`\n")
        return 1
    if obj == "run" and verb == "view":
        hits = [r for r in fx["runs"] if here(r, args, fx) and str(r["databaseId"]) == key]
        if not hits:
            sys.stderr.write("could not find any workflow run with id %s\n" % key)
            return 1
        r = hits[0]
        fields = flag(args, "--json")
        if fields == "status":   # the status read is the api route now: it carries the quota headers under -i
            sys.stderr.write("stub gh: the status read is gh api -i on the run, not run view\n")
            return 1
        if views_of(key) <= r.get("in_progress_reads", 0):
            r = dict(r, status=r.get("early_status", "in_progress"), conclusion=None)
        out = view(r, False)
        if fields:
            out = {k: v for k, v in out.items() if k in fields.split(",")}
        sys.stdout.write(json.dumps(out) + "\n")
        return 0
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


def link_git():
    """The cases run with the stub folder as the only PATH entry, and the empty-selector read runs git.
    On Windows the launcher is git.cmd, as for gh."""
    real = shutil.which("git")
    with open(os.path.join(BIN, "git.cmd"), "w", encoding="utf-8", newline="") as f:
        f.write('@echo off\r\n"%s" %%*\r\n' % real)
    launcher = os.path.join(BIN, "git")
    with open(launcher, "w", encoding="utf-8", newline="\n") as f:
        f.write('#!/bin/sh\nexec "%s" "$@"\n' % real)
    os.chmod(launcher, 0o755)


write_stub()
link_git()
sys.path.insert(0, TMP)
import gh_stub as GH  # the stand-in's own log reader: one home for the call-file format


FLUSH_SRC = r'''
import runpy, sys

class FlakyFlush(object):
    """A stderr whose flush raises. Writes pass through, so the hook's own lines still arrive."""
    def __init__(self, real):
        self._real = real
        self.buffer = real.buffer

    def write(self, text):
        return self._real.write(text)

    def flush(self):
        raise OSError("stderr flush failed (test)")

sys.stderr = FlakyFlush(sys.stderr)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
FLUSH_LAUNCHER = os.path.join(TMP, "flaky_flush.py")
with open(FLUSH_LAUNCHER, "w", encoding="utf-8") as f:
    f.write(FLUSH_SRC)

FAST_SLEEP_SRC = r'''
import runpy, sys, time

_real_sleep = time.sleep
# A cap, not a no-op: the 30 s status pause costs 0.05 s, and a negative sleep still raises.
time.sleep = lambda seconds: _real_sleep(min(seconds, 0.05))
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
FAST_SLEEP_LAUNCHER = os.path.join(TMP, "fast_sleep.py")
with open(FAST_SLEEP_LAUNCHER, "w", encoding="utf-8") as f:
    f.write(FAST_SLEEP_SRC)


def pr(number, draft=False, branch="hook-wave-2", sha=SHA, repo=None):
    out = {"number": number, "isDraft": draft, "headRefName": branch, "headRefOid": sha,
           "state": "OPEN",
           "url": "https://github.com/%s/pull/%d" % (repo or "shivinate7/claude-settings", number)}
    if repo:
        out["repo"] = repo   # answers only a gh call that reaches this repo (the stub's here())
    return out


def job(name, conclusion):
    return {"name": name, "conclusion": conclusion, "status": "completed"}


def run(run_id, name, conclusion, jobs, in_progress_at_list=False, sha=SHA,
        status="completed", ping=False, fail_status=False, in_progress_reads=0,
        appears_at_list=1, unfinished_to_list=0, early_status=None):
    out = {"databaseId": run_id, "name": name, "workflowName": name, "headSha": sha,
           "event": "pull_request", "status": status, "conclusion": conclusion,
           "jobs": jobs, "in_progress_at_list": in_progress_at_list}
    if appears_at_list > 1:
        out["appears_at_list"] = appears_at_list
    if unfinished_to_list:
        out["unfinished_to_list"] = unfinished_to_list
    if ping:
        out["ping_on_status_read"] = True
    if fail_status:
        out["fail_status_read"] = True
    if in_progress_reads:
        out["in_progress_reads"] = in_progress_reads
    if early_status:
        out["early_status"] = early_status
    return out


def fixture(prs=(), runs=(), mode="ok", **extra):
    """extra: cwd_repo (the folder's repo, for a call with no -R), workflows, workflow_list (the failure switch)."""
    return dict({"mode": mode, "prs": list(prs), "runs": list(runs)}, **extra)


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def powershell(command):
    return {"tool_name": "PowerShell", "tool_input": {"command": command}}


READY = [pr(12)]
TWO_PRS = [pr(12), pr(13, branch="second-branch", sha=SHA_B)]
GREEN = run(901, "checks", "success", [job("lint", "success"), job("unit", "success")])
RED = run(902, "checks", "failure",
          [job("lint", "success"), job("unit", "failure"), job("e2e", "failure")])
RED_B = run(911, "checks", "failure", [job("unit", "failure")], sha=SHA_B)
CANCEL_903 = run(903, "checks", "cancelled", [job("unit", "cancelled")])
RAN_904 = run(904, "checks", "success", [job("unit", "success")])
CANCEL_905 = run(905, "checks", "cancelled", [job("unit", "cancelled")])
INPROG_906 = run(906, "checks", "success", [job("unit", "success")], in_progress_at_list=True)
LATE_906 = run(906, "checks", "success", [job("unit", "success")], in_progress_at_list=True,
               in_progress_reads=2)  # in progress for 2 reads of `run view`, completed at the 3rd
LATE_907 = run(907, "codeql", "success", [job("scan", "success")], in_progress_at_list=True,
               in_progress_reads=3)  # in progress for 3 reads, completed at the 4th
PENDING = run(908, "checks", None, [], status="in_progress")  # never ends: only the deadline wakes the hook
HOLD = run(909, "checks", None, [], status="in_progress", ping=True)  # a live watcher: its status read pings, then it pauses
BAD_STATUS = run(912, "checks", "success", [job("unit", "success")], fail_status=True)  # its status read exits 1
QUEUED_913 = run(913, "checks", "success", [job("unit", "success")], in_progress_reads=2,
                 early_status="queued")  # queued for 2 reads of `run view`, completed at the 3rd
# The draft PR's run: every job skipped. DRAFT_LIVE lists with no conclusion at the first list, and ends
# skipped. DRAFT_DONE lists skipped from the first list.
DRAFT_LIVE = run(920, "checks", "skipped", [job("unit", "skipped")], unfinished_to_list=1)
DRAFT_DONE = run(921, "checks", "skipped", [job("unit", "skipped")])


def late(run_id, appears, conclusion="success", jobs=None):
    """The real run of `gh pr ready`, which the lists before list number `appears` do not show. It
    lists in progress when it first shows, and its first status read is in progress too."""
    jobs = jobs or [job("lint", "success"), job("unit", "success")]
    return run(run_id, "checks", conclusion, jobs, appears_at_list=appears, unfinished_to_list=appears,
               in_progress_reads=1)


PUSH_FORMS = [
    "git push",
    "git push origin hook-wave-2",
    "git push -u origin hook-wave-2",
    "git push origin HEAD:hook-wave-2",
    "git push origin HEAD",
    "git push origin refs/heads/hook-wave-2",
    "git push --force-with-lease origin hook-wave-2",
    "git -C sub push origin hook-wave-2",
    "git add -A && git commit -m ci && git push origin HEAD:hook-wave-2",
]

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
    def __init__(self, rc, out, err, calls, hung, elapsed):
        self.rc, self.out, self.err, self.calls, self.hung = rc, out, err, calls, hung
        self.elapsed = elapsed
        self.lines = [x for x in (out + "\n" + err).splitlines() if x.strip()]


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def read_calls(log):
    return GH.read_log(log)


def new_case(scen):
    case = tempfile.mkdtemp(prefix="case-", dir=TMP)
    fixture_path = os.path.join(case, "fixture.json")
    log = os.path.join(case, "gh.log")
    with open(fixture_path, "w", encoding="utf-8") as f:
        json.dump(scen, f)
    return case, fixture_path, log


def base_env(search, fixture_path, log, lock, extra):
    # Drop every spelling of PATH first: on Windows os.environ keys are case-insensitive.
    # Drop CI_WAKE_* from the caller's shell too, so only the case sets the seams.
    env = {k: v for k, v in os.environ.items()
           if k.upper() != "PATH" and not k.startswith("CI_WAKE_") and k.upper() != "GH_REPO"}
    env.update(PATH=search, GH_STUB_FIXTURE=fixture_path, GH_STUB_LOG=log, CI_WAKE_LOCK_DIR=lock)
    env.update(extra or {})
    return env


def run_hook(payload, scen, path="stub", extra=None, lock=None, stdin=None, module=None,
             launcher=None):
    """Run the real hook once and wait for it. path "stub": PATH is the stub folder only.
    path "missing": PATH is empty. lock: the watch-lock folder (default: this case's folder).
    stdin: raw text for stdin, in place of the JSON of payload. module: a copy of the hook to
    run instead. launcher: a script that runs the module with a changed stderr, given the module."""
    case, fixture_path, log = new_case(scen)
    search = BIN
    if path == "missing":
        search = os.path.join(case, "empty")
        os.makedirs(search)
    env = base_env(search, fixture_path, log, lock or case, extra)
    payload = dict(payload or {})
    payload.setdefault("cwd", case)
    text = stdin if stdin is not None else json.dumps(payload)
    out_p, err_p = os.path.join(case, "out.txt"), os.path.join(case, "err.txt")
    start = time.monotonic()
    # Output goes to files, not pipes: a killed hook can leave a stub child that holds pipes open.
    with open(out_p, "w", encoding="utf-8") as fo, open(err_p, "w", encoding="utf-8") as fe:
        try:
            cmd = [PY, launcher, module or MODULE] if launcher else [PY, module or MODULE]
            p = subprocess.run(cmd, input=text, stdout=fo, stderr=fe, encoding="utf-8",
                               env=env, cwd=case, timeout=TIMEOUT)
            rc, hung = p.returncode, False
        except subprocess.TimeoutExpired:
            rc, hung = None, True
    elapsed = time.monotonic() - start
    return Result(rc, read_text(out_p), read_text(err_p), read_calls(log), hung, elapsed)


def start_watcher(payload, scen, extra=None):
    """Start the real hook and return without waiting. -> (process, lock folder)."""
    case, fixture_path, log = new_case(scen)
    env = base_env(BIN, fixture_path, log, case, extra)
    payload = dict(payload)
    payload.setdefault("cwd", case)
    proc = subprocess.Popen([PY, MODULE], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, env=env, cwd=case, encoding="utf-8")
    try:
        proc.stdin.write(json.dumps(payload))
        proc.stdin.close()
    except OSError:
        pass
    return proc, case


def watched(res):
    """The ids of the runs the hook waited on: one status read `gh api -i repos/O/R/actions/runs/<id>` each. The -R of
    a call is not compared: GH.strip_repo drops it, so the check reads the same wherever -R sits."""
    return [GH.run_read_id(c) for c in map(GH.strip_repo, res.calls) if c[:2] == ["api", "-i"] and GH.run_read_id(c)]


def run_reads(res):
    """Every read of one run, by either route: `run view <id>` and the status read. The -R of a call is not compared."""
    return [c for c in map(GH.strip_repo, res.calls) if GH.run_read_id(c)]


def run_watches(res):
    """Every `gh run watch` call. The decision ci-wait-reads-run-status allows none."""
    return [c for c in res.calls if GH.strip_repo(c)[:2] == ["run", "watch"]]


def count(res, *prefix):
    return sum(1 for c in res.calls if GH.strip_repo(c)[:len(prefix)] == list(prefix))


def verdict_of(res):
    """(verdict, sha, names) when the output is exactly one CI line, else None."""
    if len(res.lines) != 1:
        return None
    m = LINE.match(res.lines[0].strip())
    return (m.group(1), m.group(2), m.group(3).strip()) if m else None


def verdicts_of(res):
    """[(verdict, sha, names)] for every output line, or None when a line is not a CI line."""
    found = []
    for line in res.lines:
        m = LINE.match(line.strip())
        if not m:
            return None
        found.append((m.group(1), m.group(2), m.group(3).strip()))
    return found


def why(res):
    return "rc=%s hung=%s elapsed=%.1fs lines=%r calls=%d" % (
        res.rc, res.hung, res.elapsed, " | ".join(res.lines[:2])[:160], len(res.calls))


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
    check("%s: no wait on a run (no status read, no run watch)" % label,
          watched(res) == [] and run_watches(res) == [], why(res))


def expect_no_gh(label, res):
    check("%s: no gh call" % label, res.calls == [], why(res))


def expect_watch(label, res, ids):
    """The status reads, as ids: one read per run for a run that is completed at its first read, and
    one more id per read for a run still in progress (in_progress_reads). The run list is read at most
    twice (no polling): one list, then the at-once re-list after the first judged run. No `gh run watch`."""
    check("%s: status reads are %s, runs listed at most twice, no run watch" % (label, ids),
          sorted(watched(res)) == sorted(ids) and run_watches(res) == []
          and count(res, "run", "list") <= 2, why(res))


def guard_silent(label, command, scen=None, tool=bash):
    """A command that must start no watch and make no gh call."""
    res = run_hook(tool(command), scen or fixture(READY, [GREEN]))
    expect_silent(label, res)
    expect_no_gh(label, res)


def watch_pr12(label, command):
    """A command that must watch PR 12 once and wake with its green verdict."""
    res = run_hook(bash(command), fixture(READY, [GREEN]))
    expect_verdict(label, res, "green")
    expect_watch(label, res, ["901"])


def case_one_watcher_per_pr():
    """A live watcher holds PR 12. A second one exits at once. A killed or finished watcher
    releases PR 12. The handshake is one accept() on a localhost port the stub connects to, at the
    first watcher's first status read. The watcher then pauses 30 s with the lock held, and the
    case kills it."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(20)
    proc, lock = None, None
    try:
        proc, lock = start_watcher(bash("gh pr ready 12"), fixture(READY, [HOLD]),
                                   extra={"GH_STUB_READY_PORT": str(srv.getsockname()[1])})
        try:
            conn, _ = srv.accept()
            conn.close()
            reached = True
        except OSError:
            reached = False
        check("first watcher reached its first status read (handshake within 20 s)", reached,
              "no connection from the stub")
        if reached:
            second = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), lock=lock)
            check("second watcher for PR 12 while the first is live: exit 0, no output",
                  second.rc == 0 and not second.hung and second.lines == [], why(second))
            check("second watcher for PR 12 while the first is live: no wait on a run, exits at once",
                  watched(second) == [] and run_watches(second) == [] and second.elapsed < 5, why(second))
    finally:
        if proc is not None:
            proc.kill()
            proc.wait()
        srv.close()
    after_kill = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), lock=lock)
    expect_verdict("watcher after the first was killed (its lock is released)", after_kill, "green")
    after_end = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), lock=lock)
    expect_verdict("watcher after the previous one ended (lock released on exit)", after_end, "green")


def case_skipped_only_head_is_no_run_yet():
    """A head whose only run is skipped (a draft PR's skipped run) is no run yet: one pause,
    one re-list, then unknown "no run yet". It is never read as red."""
    skipped = run(910, "checks", "skipped", [job("unit", "skipped")])
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [skipped]), extra={"CI_WAKE_DEADLINE": "4"})
    expect_verdict("head whose only run is skipped", res, "unknown")
    v = verdict_of(res)
    check("head whose only run is skipped: the line says no run yet",
          v is not None and "no run yet" in v[2], why(res))
    check("head whose only run is skipped: run list read twice (one pause, then re-list)",
          count(res, "run", "list") == 2, why(res))


def case_draft_pr_starts_no_watch():
    """gh pr ready on a PR whose view says isDraft true starts no watch: silent, no run read."""
    res = run_hook(bash("gh pr ready 12"), fixture([pr(12, draft=True)], [GREEN]))
    expect_silent("gh pr ready 12, PR isDraft true", res)
    expect_no_watch("gh pr ready 12, PR isDraft true", res)
    check("gh pr ready 12, PR isDraft true: no run list read", count(res, "run", "list") == 0,
          why(res))


def case_import_error_wakes_unknown():
    """A copy of the hook with no guard_core.py beside it. An import error must end in one
    unknown line and exit 2, never a traceback and exit 1."""
    folder = tempfile.mkdtemp(prefix="ci-wake-solo-", dir=TMP)
    copy = os.path.join(folder, "ci_wake.py")
    shutil.copy(MODULE, copy)
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), module=copy)
    expect_verdict("import error: guard_core.py missing beside the hook", res, "unknown")


def case_final_flush_error_wakes_unknown():
    """stderr whose flush raises. The final flush must end in a wake with an unknown line, not a
    crash."""
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), launcher=FLUSH_LAUNCHER)
    unknown = []
    for line in res.lines:
        m = LINE.match(line.strip())
        if m and m.group(1) == "unknown":
            unknown.append(line)
    check("final flush raises: exit 2, not a crash", res.rc == 2 and not res.hung, why(res))
    check("final flush raises: no traceback on stderr", "Traceback" not in res.err, why(res))
    check("final flush raises: one CI unknown line", len(unknown) == 1, why(res))


def case_background_separator_starts_each_watch():
    """A single `&` separates commands too: each gh pr ready after it gets its own watch in the
    same process. The `2>&1` redirect is no separator (a guard for any fix)."""
    res = run_hook(bash("gh pr ready 12 & gh pr ready 13"), fixture(TWO_PRS, [GREEN, RED_B]))
    vs = verdicts_of(res)
    check("gh pr ready 12 & gh pr ready 13: one process, one CI line per PR (12 green, 13 red)",
          res.rc == 2 and not res.hung and vs is not None
          and sorted((v[0], v[1]) for v in vs) == sorted([("green", SHA7), ("red", SHA7_B)]),
          why(res))
    check("gh pr ready 12 & gh pr ready 13: reads the status of runs 901 and 911, one each, no run watch",
          sorted(watched(res)) == ["901", "911"] and run_watches(res) == [], why(res))
    watch_pr12("gh pr ready 12 2>&1: the redirect starts one watch", "gh pr ready 12 2>&1")
    # A single & inside quotes or after a comment opener is no separator (guards for the fix).
    guard_silent("single & inside double quotes is no separator", 'echo "a & gh pr ready 12"')
    guard_silent("single & inside single quotes is no separator", "echo 'a & gh pr ready 12'")
    guard_silent("single & after an unquoted # is comment text", "echo ok # a & gh pr ready 12")


def case_lock_folder_unusable_wakes_unknown():
    """The lock folder is a file. The OSError at the lock must end in one unknown line, no watch."""
    blocker = os.path.join(TMP, "lock-folder-is-a-file")
    with open(blocker, "w", encoding="utf-8") as f:
        f.write("not a folder\n")
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), lock=blocker)
    expect_verdict("lock folder is a file (OSError at the lock)", res, "unknown")
    expect_no_watch("lock folder is a file", res)


def case_draft_run_then_real_run():
    """The draft run skips, and the real run comes after it. The hook never reads red for the
    skipped run: it waits on the real run and reports that run's result. Rows marked (control) list
    the real run at the first list, so no second list is needed. FAST_SLEEP_LAUNCHER: the pauses
    between lists cost 0.05 s."""
    fast = dict(launcher=FAST_SLEEP_LAUNCHER)
    ready = bash("gh pr ready 12")
    res = run_hook(ready, fixture(READY, [DRAFT_DONE, GREEN]))
    expect_verdict("draft run listed skipped beside a real run (control)", res, "green")
    expect_watch("draft run listed skipped beside a real run (control)", res, ["901"])
    res = run_hook(ready, fixture(READY, [DRAFT_LIVE, INPROG_906]), **fast)
    expect_verdict("draft run running at the list, real run listed with it (control)", res, "green")
    # The first list shows only the draft run, still running. The real run lists second.
    label = "draft run running at the first list, real run listed second"
    res = run_hook(ready, fixture(READY, [DRAFT_LIVE, late(922, 2)]), **fast)
    expect_verdict(label, res, "green")
    check("%s: waited on the real run (922) and listed again" % label,
          "922" in watched(res) and count(res, "run", "list") >= 2, why(res))
    res = run_hook(ready, fixture(READY, [DRAFT_LIVE, late(922, 2, "failure", RED["jobs"])]), **fast)
    expect_verdict("draft run running at the first list, real run listed second and failed", res, "red",
                   names_in=["unit", "e2e"], names_out=["lint", "workflow"])


def case_real_run_listed_late():
    """The real run is not in the first lists. It shows at list 3, so a hook that lists twice and
    gives up ends in `CI unknown ... no run yet`. It lists again and judges the run it finds."""
    for label, runs in (("no run at the first two lists, the real run at the third", [late(923, 3)]),
                        ("draft run listed skipped, the real run at the third list",
                         [DRAFT_DONE, late(923, 3)])):
        res = run_hook(bash("gh pr ready 12"), fixture(READY, runs), launcher=FAST_SLEEP_LAUNCHER)
        expect_verdict(label, res, "green")
        check("%s: waited on the real run (923) after 3 lists" % label,
              "923" in watched(res) and count(res, "run", "list") >= 3, why(res))


def case_real_failed_run_beside_a_draft_run_is_red():
    """Control: a skipped draft run does not hide a real failure, so the verdict still reads from the real run."""
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [DRAFT_DONE, RED]))
    expect_verdict("draft run listed skipped beside a failed real run (control)", res, "red",
                   names_in=["unit", "e2e"], names_out=["lint", "workflow"])
    expect_watch("draft run listed skipped beside a failed real run (control)", res, ["902"])


def case_draft_run_ending_skipped_is_no_run_yet():
    """The draft run is still running at the first list and ends skipped, and no real run comes. A
    real clock and a 4 s deadline: it ends in `CI unknown`, near the deadline. Never red ("CI red
    ...: workflow checks"), never green. At most one list at the start and one at the deadline."""
    label = "head whose draft run ends skipped, no real run by the deadline"
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [DRAFT_LIVE]), extra={"CI_WAKE_DEADLINE": "4"})
    expect_verdict(label, res, "unknown")
    check("%s: wakes near its deadline (3.5 s to 15 s)" % label, 3.5 <= res.elapsed < 15, why(res))
    check("%s: run list read at most twice" % label, count(res, "run", "list") <= 2, why(res))


def case_run_visible_at_the_at_once_relist_is_judged():
    """The first real run is judged, and wait_for re-lists at once. A run visible at that re-list is judged
    too: a hook that returns after the first judged run never reads it, and says green while it goes on. The
    control lists both runs at the first list, and passes either way. The red row shows the second run (a
    different workflow name, so judge_runs keeps both) only at the second list, the at-once re-list after the
    first run has ended. FAST_SLEEP_LAUNCHER: the pauses cost 0.05 s."""
    fast = dict(launcher=FAST_SLEEP_LAUNCHER, extra={"CI_WAKE_DEADLINE": "15"})
    ready = bash("gh pr ready 12")
    together = run(932, "codeql", "failure", [job("scan", "failure")])
    later = run(932, "codeql", "failure", [job("scan", "failure")], appears_at_list=2,
                unfinished_to_list=2, in_progress_reads=1)
    res = run_hook(ready, fixture(READY, [GREEN, together]), **fast)
    label = "two real runs listed together, the second failed (control)"
    expect_verdict(label, res, "red", names_in=["scan"], names_out=["lint", "unit"])
    check("%s: reads the second run (932)" % label, "932" in watched(res), why(res))
    res = run_hook(ready, fixture(READY, [GREEN, later]), **fast)
    label = "second real run listed at the second list, after the first ended"
    check("%s: reads the second run (932) and lists again" % label,
          "932" in watched(res) and count(res, "run", "list") >= 2, why(res))
    expect_verdict(label, res, "red", names_in=["scan"], names_out=["lint", "unit"])


def case_the_at_once_relist_judges_the_newest_run_of_a_name():
    """The at-once re-list can show a newer run of the same name as a run already judged. judge_runs keeps the
    first run of each name in list order, which is newest first, so the newer run must be judged in place of the
    green one. Control: both runs listed at the first list, newest first, judge red. Red row: the newer run
    shows only at the re-list, after the green run was judged, and the verdict must still be red."""
    ok = run(100, "CI", "success", [job("lint", "success"), job("unit", "success")])
    late_fail = run(101, "CI", "failure", [job("unit", "failure")], appears_at_list=2,
                    unfinished_to_list=2, in_progress_reads=1)
    together = run(101, "CI", "failure", [job("unit", "failure")])
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [together, ok]), extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE},
                   launcher=FAST_SLEEP_LAUNCHER)
    expect_verdict("both CI runs listed at once, the newer one failed (control)", res, "red",
                   names_in=["unit"], names_out=["lint"])
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [late_fail, ok]), extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE},
                   launcher=FAST_SLEEP_LAUNCHER)
    label = "newer CI run shows only at the at-once re-list, after the green run was judged"
    check("%s: reads the newer run (101)" % label, "101" in watched(res), why(res))
    expect_verdict(label, res, "red")


def case_failed_re_list_keeps_the_judged_verdict():
    """A red run is judged, then the at-once re-list is refused (HTTP 403). The hook still says red with its failing
    jobs. A red line states a failure the hook read, and no run the refused list could have shown undoes it. A green
    line would claim the whole head passed, so a green run reads unknown instead (the case after this one).
    Control: the same run with no refusal."""
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [RED]), extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    expect_verdict("red run, no refusal (control)", res, "red", names_in=["unit", "e2e"], names_out=["lint"])
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [RED], list_error_from=2),
                   extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    label = "red run judged, then the at-once re-list is refused"
    check("%s: reads run 902 and lists twice" % label, "902" in watched(res) and count(res, "run", "list") == 2,
          why(res))
    expect_verdict(label, res, "red", names_in=["unit", "e2e"], names_out=["lint"])


def case_failed_re_list_after_a_green_run_is_unknown():
    """A green run is judged, and then the at-once re-list is refused (HTTP 403). The re-list could have shown a
    red or a still-running run, and a green line would say the whole head passed. So the verdict is `CI unknown`,
    as for any read that could not run. Control: the same green run with no refusal reads green."""
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    expect_verdict("green run, no refusal (control)", res, "green")
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN], list_error_from=2),
                   extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    label = "green run judged, then the at-once re-list is refused"
    check("%s: reads run 901 and lists twice" % label, "901" in watched(res) and count(res, "run", "list") == 2,
          why(res))
    expect_verdict(label, res, "unknown")


def case_green_run_judged_past_the_deadline_is_not_green():
    """A green run ends at the deadline, so its jobs read is at the deadline too: no time is left for the at-once
    re-list, and wait_for returns after the one judged run. A red run that shows only at a later list (codeql) is
    then unread, and a line that says CI green would hide it. The line must be unknown, or the re-list must run and
    find the red run. Scope first: the green run's jobs read is at the deadline, so the case reaches that branch.
    Control: a red run that ends at the deadline, with no later run, stays red with its failing jobs. The status
    reads are 30 s apart, so the last one is at 90 s and the run ends at the 100 s deadline."""
    budget = 100
    later_red = run(931, "codeql", "failure", [job("scan", "failure")], appears_at_list=2)
    label = "green run ends at the deadline, a red run shows only at a later list"
    raised, clock, calls, deadline = wait_for_on_fakes([GREEN, later_red], budget, ends_at={901: budget}, line=True)
    detail = wait_detail(raised, clock, calls, deadline) + " line=%r" % clock.line
    jobs_reads = [t for t, a in calls if a[:3] == ["run", "view", "901"] and "jobs" in " ".join(a)]
    check("%s: the green run's jobs read is at or past the deadline (scope)" % label,
          bool(jobs_reads) and jobs_reads[-1] >= deadline - 1e-6, detail)
    check("%s: the line is not CI green, the later run is unread" % label,
          not str(clock.line).startswith("CI green"), detail)

    label = "red run ends at the deadline, no later run (control)"
    raised, clock, calls, deadline = wait_for_on_fakes([RED], budget, ends_at={902: budget}, line=True)
    detail = wait_detail(raised, clock, calls, deadline) + " line=%r" % clock.line
    check("%s: the line is CI red, naming unit and e2e, not lint" % label,
          str(clock.line).startswith("CI red") and "unit" in clock.line and "e2e" in clock.line
          and "lint" not in clock.line, detail)


def refused_new_run():
    """A run that first shows at the at-once re-list, completed, whose jobs read is refused (HTTP 403)."""
    return dict(run(931, "codeql", "success", [job("scan", "success")], appears_at_list=2), refuse_jobs_read=True)


def case_refused_re_list_view_keeps_a_judged_red():
    """A red run is judged, then the at-once re-list finds a new run whose jobs read is refused (HTTP 403). The
    refused read cannot undo the judged red run: a red run stays red, whatever the list hid (wait_for's docstring).
    Before the deadline, and past it, where the re-list is the one list left. Scope first: the refused read is
    reached at the re-list. Control: the same refusal after a green run is unknown (the next case)."""
    for where, budget, ends_at in (("before the deadline", 3600, None), ("past the deadline", 100, {902: 100})):
        label = "red run judged %s, the re-list's new run has a refused jobs read" % where
        raised, clock, calls, deadline = wait_for_on_fakes([RED, refused_new_run()], budget, ends_at=ends_at, line=True)
        detail = wait_detail(raised, clock, calls, deadline) + " line=%r" % clock.line
        refused = [t for t, a in calls if a[:3] == ["run", "view", "931"] and "jobs" in " ".join(a)]
        check("%s: the new run's jobs read is reached (scope)" % label, bool(refused), detail)
        check("%s: the line is CI red, naming unit and e2e" % label,
              str(clock.line).startswith("CI red") and "unit" in clock.line and "e2e" in clock.line, detail)


def case_refused_re_list_view_after_a_green_run_is_unknown():
    """Control. A green run is judged, then the same refused read at the re-list. The unread list could hold a red
    or a running run, so the line is CI unknown, never CI green. Before the deadline, and past it."""
    for where, budget, ends_at in (("before the deadline", 3600, None), ("past the deadline", 100, {901: 100})):
        label = "green run judged %s, the re-list's new run has a refused jobs read (control)" % where
        raised, clock, calls, deadline = wait_for_on_fakes([GREEN, refused_new_run()], budget, ends_at=ends_at, line=True)
        detail = wait_detail(raised, clock, calls, deadline) + " line=%r" % clock.line
        refused = [t for t, a in calls if a[:3] == ["run", "view", "931"] and "jobs" in " ".join(a)]
        check("%s: the new run's jobs read is reached (scope)" % label, bool(refused), detail)
        check("%s: the line is CI unknown, never CI green" % label, str(clock.line).startswith("CI unknown"), detail)


def case_new_runs_on_every_list_are_paced_after_the_at_once_relist():
    """A stream: each list shows one more run that ended. wait_for re-lists once at once after the first
    judged run; from then on each list is 30 s or more after the one before it, so the stream costs one gh
    list per 30 s, not one per run at +0 s. Only the pace is checked: a run first shown after the re-list is
    not judged here."""
    stream = [run(940 + k, "checks", "success", [job("unit", "success")], appears_at_list=k + 1)
              for k in range(12)]
    raised, clock, calls, deadline = wait_for_on_fakes(stream, 3600)
    times = list_times(calls)
    detail = wait_detail(raised, clock, calls, deadline)
    check("stream of 12 runs, one per list: no exception", raised is None, detail)
    check("stream of 12 runs, one per list: lists are 30 s or more apart after the at-once re-list, "
          "%d lists" % len(times), lists_paced(calls, deadline, stream), detail)


# watch_run, in process, on fakes (decision ci-wait-reads-run-status). No gh runs and no wait is real.
STATUS_READ = ["api", "-i", "repos/{owner}/{repo}/actions/runs/7"]   # what watch_run sends with no repo named
T0 = 1000.0   # where the fake clock starts


class FakeTime:
    """The module's `time`. It moves only when the code sleeps. A loop that never ends fails
    after 400 sleeps, so it cannot hang the run."""

    def __init__(self):
        self.now, self.sleeps = T0, []

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        if len(self.sleeps) > 400:
            raise AssertionError("runaway wait: 400 sleeps")
        self.now += max(seconds, 0)


def status_reply(status):
    return (0, json.dumps({"status": status}) + "\n", "")


def header_block(headers):
    """What `gh api -i` prints before a body: the status line, the headers under GitHub's names, a blank line. The shape of
    merge/test_merge.py's gh_i, written out here because this file runs standalone and importing test_merge would set the git
    environment for every case in the process."""
    lines = ["HTTP/2.0 200 OK", "Content-Type: application/json; charset=utf-8", *(f"{k}: {v}" for k, v in headers.items())]
    return "\r\n".join(lines) + "\r\n\r\n"


def watch_run_on_fakes(replies, budget, quota=None):
    """Run watch_run(7, cwd, deadline) in process. The module's `gh` is scripted: one
    (rc, stdout, stderr) per call, the last repeats, or a function of the clock's time that
    returns one. Its `time` is the fake clock. Its `subprocess`
    and `shutil` are fakes that record a direct call (the old `gh run watch` path) and start nothing.
    budget: seconds from the clock's start to the deadline.
    quota: None, or a function of the clock's time giving the X-RateLimit headers a `gh api -i` call prints before its body
    (`gh run view` takes no -i, so a read without it carries no headers).
    -> (module, exception or None, clock, gh calls [(time, args)], direct subprocess calls)."""
    spec = importlib.util.spec_from_file_location("ci_wake_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    clock, calls, direct = FakeTime(), [], []

    def fake_gh(args, cwd, timeout=None):
        calls.append((clock.now, list(args)))
        if len(calls) > 400:
            raise AssertionError("runaway reads: 400 gh calls")
        if callable(replies):
            rc, out, err = replies(clock.now)
        else:
            rc, out, err = replies[min(len(calls), len(replies)) - 1]
        if quota is not None and "-i" in args:
            out = header_block(quota(clock.now)) + out
        return rc, out, err

    class Proc:
        returncode, args = 0, []

        def wait(self, timeout=None):
            return 0

        def communicate(self, *a, **kw):
            return b"", b""

        def poll(self):
            return 0

        def kill(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def popen(argv, *a, **kw):
        direct.append(list(argv)[1:])
        return Proc()

    def run_(argv, *a, **kw):
        popen(argv)
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"", args=argv)

    fake_subprocess = types.SimpleNamespace(Popen=popen, run=run_, DEVNULL=-3, PIPE=-1, STDOUT=-2,
                                            TimeoutExpired=subprocess.TimeoutExpired)
    fake_shutil = types.SimpleNamespace(which=lambda name, *a, **kw: "gh-fake")
    deadline = clock.now + budget
    with mock.patch.object(mod, "time", clock), mock.patch.object(mod, "gh", fake_gh), \
            mock.patch.object(mod, "subprocess", fake_subprocess), mock.patch.object(mod, "shutil", fake_shutil):
        try:
            mod.watch_run(7, os.getcwd(), deadline)
            raised = None
        except Exception as e:   # Unknown is the one the cases look for
            raised = e
    return mod, raised, clock, calls, direct


def read_times(calls):
    return [t for t, a in calls if a == STATUS_READ]


def spaced(times, gap=30):
    return all(b - a >= gap for a, b in zip(times, times[1:]))


def watch_detail(raised, clock, calls, direct):
    return "raised=%r gh=%r direct=%r sleeps=%r" % (raised, [" ".join(a) for _, a in calls], direct, clock.sleeps)


def case_watch_run_reads_the_status_until_completed():
    """in_progress, in_progress, completed: three reads of `gh api -i repos/{owner}/{repo}/actions/runs/7`, 30 s or more
    apart, the first before any pause, none after `completed`. Never `gh run watch`, direct or by gh()."""
    label = "watch_run, in_progress twice then completed"
    mod, raised, clock, calls, direct = watch_run_on_fakes(
        [status_reply("in_progress"), status_reply("in_progress"), status_reply("completed")], 3600)
    times, detail = read_times(calls), watch_detail(raised, clock, calls, direct)
    check("%s: returns, no exception" % label, raised is None, detail)
    check("%s: never starts `gh run watch`" % label,
          direct == [] and not any(a[:2] == ["run", "watch"] for _, a in calls), detail)
    check("%s: reads `gh api -i repos/{owner}/{repo}/actions/runs/7` three times, and makes no other gh call" % label,
          [a for _, a in calls] == [STATUS_READ] * 3, detail)
    check("%s: reads at least 30 s apart" % label, len(times) == 3 and spaced(times), detail)
    check("%s: the first read comes before any pause" % label, times[:1] == [T0], detail)


def case_watch_run_completed_at_the_first_read_does_not_pause():
    label = "watch_run, completed at the first read"
    mod, raised, clock, calls, direct = watch_run_on_fakes([status_reply("completed")], 3600)
    check("%s: one read, no pause, no exception, no `gh run watch`" % label,
          raised is None and [a for _, a in calls] == [STATUS_READ] and clock.sleeps == [] and direct == [],
          watch_detail(raised, clock, calls, direct))


def case_watch_run_returns_at_the_deadline():
    """The run never completes. watch_run returns, no exception, with its last pause ending at the
    deadline: not before it, not past it. Reads stay 30 s or more apart."""
    for budget in (100, 10):
        label = "watch_run, always in_progress, deadline in %d s" % budget
        mod, raised, clock, calls, direct = watch_run_on_fakes([status_reply("in_progress")], budget)
        times, detail = read_times(calls), watch_detail(raised, clock, calls, direct)
        check("%s: returns, no exception, no `gh run watch`" % label, raised is None and direct == [], detail)
        check("%s: returns at the deadline, not before it and not past it" % label,
              abs(clock.now - (T0 + budget)) < 1e-6, "%s now=%.1f" % (detail, clock.now - T0))
        check("%s: only status reads, at least 30 s apart" % label,
              len(times) >= 1 and len(times) == len(calls) and spaced(times), detail)
        if budget == 100:
            check("%s: keeps reading while the run is in progress (3 reads or more)" % label,
                  len(times) >= 3, detail)


def case_watch_run_at_or_past_the_deadline_reads_nothing():
    """A call made at its deadline (budget 0) or past it (budget below 0) makes no read and returns
    at once, though the run is in progress: the clock does not move, so no pause either."""
    for budget in (0, -30):
        label = "watch_run, always in_progress, deadline already passed (%d s)" % budget
        mod, raised, clock, calls, direct = watch_run_on_fakes([status_reply("in_progress")], budget)
        detail = watch_detail(raised, clock, calls, direct)
        check("%s: returns, no exception, no `gh run watch`" % label, raised is None and direct == [], detail)
        check("%s: makes no gh call, so no status read" % label, calls == [], detail)
        check("%s: returns at once, the clock does not move" % label, clock.now == T0, detail)


def case_watch_run_failed_read_is_unknown_after_one_retry():
    """A failed read, or one that is not JSON, is read once more after the 30 s pause. A second
    failed read ends the wait: Unknown, and no third read of that failure."""
    rows = (
        ("gh exits 1 at the first read", [(1, "", "HTTP 401: Bad credentials")], 2),
        ("gh prints non-JSON at the first read", [(0, "<html>not json</html>", "")], 2),
        ("gh exits 1 at the second read", [status_reply("in_progress"), (1, "", "HTTP 502: Bad Gateway")], 3),
    )
    for label, replies, reads in rows:
        mod, raised, clock, calls, direct = watch_run_on_fakes(replies, 3600)
        detail = watch_detail(raised, clock, calls, direct)
        check("watch_run, %s: raises Unknown" % label, isinstance(raised, mod.Unknown), detail)
        check("watch_run, %s: %d reads (one retry), no `gh run watch`" % (label, reads),
              len(calls) == reads and direct == [], detail)
        check("watch_run, %s: the retry comes 30 s or more after the failed read" % label,
              spaced(read_times(calls)), detail)


def case_watch_run_retries_a_failed_read_once_and_goes_on():
    """A failed read, then `completed`: the retry succeeds, so watch_run returns with no exception
    after two reads, 30 s apart. A failed read, then queued, then `completed`: it reads on."""
    rows = (
        ("failed then completed", [(1, "", "HTTP 502: Bad Gateway"), status_reply("completed")], 2),
        ("failed, queued, then completed",
         [(1, "", "HTTP 502: Bad Gateway"), status_reply("queued"), status_reply("completed")], 3),
    )
    for label, replies, reads in rows:
        mod, raised, clock, calls, direct = watch_run_on_fakes(replies, 3600)
        detail = watch_detail(raised, clock, calls, direct)
        check("watch_run, %s: returns, no exception, no `gh run watch`" % label,
              raised is None and direct == [], detail)
        check("watch_run, %s: %d status reads, 30 s or more apart" % (label, reads),
              [a for _, a in calls] == [STATUS_READ] * reads and spaced(read_times(calls)), detail)


def case_watch_run_reads_past_a_queued_status():
    """queued, queued, completed: three reads, 30 s or more apart, and a return after the third.
    `queued` is not `completed`, so the wait goes on."""
    mod, raised, clock, calls, direct = watch_run_on_fakes(
        [status_reply("queued"), status_reply("queued"), status_reply("completed")], 3600)
    detail = watch_detail(raised, clock, calls, direct)
    check("watch_run, queued twice then completed: returns, no exception", raised is None, detail)
    check("watch_run, queued twice then completed: three status reads, 30 s or more apart",
          [a for _, a in calls] == [STATUS_READ] * 3 and spaced(read_times(calls)), detail)


def case_watch_run_retry_never_reads_or_pauses_past_the_deadline():
    """A failed read with the deadline 10 s away: the retry pause ends at the deadline at the latest,
    and no gh call comes at or after it. Whether watch_run raises Unknown or returns is not pinned."""
    budget = 10
    mod, raised, clock, calls, direct = watch_run_on_fakes([(1, "", "HTTP 502: Bad Gateway")], budget)
    detail = watch_detail(raised, clock, calls, direct) + " now=%.1f" % (clock.now - T0)
    check("watch_run, failed read, deadline in %d s: the clock never passes the deadline" % budget,
          clock.now <= T0 + budget, detail)
    check("watch_run, failed read, deadline in %d s: no gh call at or after the deadline" % budget,
          all(t < T0 + budget for t, _ in calls) and len(calls) >= 1, detail)


# watch_run back-off: reads come 30 s apart up to and including the read at BACKOFF_FLAT s after the
# first read, then each gap grows, to BACKOFF_CAP s at most. The watch still ends at WATCH_BUDGET.
BACKOFF_FLAT = 240    # 4 min: nine reads, at 0, 30, ... 240 s
BACKOFF_CAP = 120     # s
WATCH_BUDGET = 3300   # 55 min, the hook's default budget
FLAT_READS = WATCH_BUDGET // 30   # the reads of a never-ending run at a flat 30 s gap


def never_ending_run(budget=WATCH_BUDGET):
    """-> (module, clock, gh calls, [read times as seconds after the first read], [gaps])."""
    mod, raised, clock, calls, direct = watch_run_on_fakes([status_reply("in_progress")], budget)
    rel = [round(t - T0, 6) for t in read_times(calls)]
    return mod, clock, calls, rel, [b - a for a, b in zip(rel, rel[1:])]


def case_watch_run_reads_30_s_apart_for_the_first_four_minutes():
    """The first nine reads sit at 0, 30, ... 240 s. The gap after the read at 240 s is longer
    than 30 s: the boundary is exact, and a flat 30 s gap forever fails the second check."""
    label = "watch_run, never completes, 55 min budget"
    mod, clock, calls, rel, gaps = never_ending_run()
    detail = "reads at %r" % rel[:14]
    check("%s: the first nine reads are 30 s apart, at 0 to 240 s" % label,
          rel[:9] == [30.0 * i for i in range(9)], detail)
    check("%s: the gap after the read at 240 s is longer than 30 s" % label,
          len(rel) > 9 and rel[9] - rel[8] > 30, detail)


def case_watch_run_gaps_grow_to_a_cap():
    label = "watch_run, never completes, 55 min budget"
    mod, clock, calls, rel, gaps = never_ending_run()
    detail = "distinct gaps %r in %d reads" % (sorted({round(g, 1) for g in gaps}), len(rel))
    check("%s: no gap is shorter than the one before it" % label, gaps == sorted(gaps), detail)
    check("%s: no gap is longer than %d s" % (label, BACKOFF_CAP), gaps != [] and max(gaps) <= BACKOFF_CAP + 1e-6, detail)
    check("%s: the gaps grow past 30 s, to 90 s or more" % label, gaps != [] and max(gaps) >= 90, detail)


def case_watch_run_back_off_keeps_the_deadline_and_cuts_the_reads():
    """The default budget stays 55 min. A never-ending run ends exactly at its deadline, with no read at
    or after it, in the flat phase (250) and in the growth phase (400, 1000, 3300). Over the 55 min the
    watch reads at most half as often as a flat 30 s gap does."""
    for budget in (250, 400, 1000, WATCH_BUDGET):
        label = "watch_run, never completes, deadline in %d s" % budget
        mod, clock, calls, rel, gaps = never_ending_run(budget)
        detail = "end=%.1f reads=%d last=%r" % (clock.now - T0, len(rel), rel[-3:])
        check("%s: ends at the deadline, not before it and not past it" % label,
              abs(clock.now - (T0 + budget)) < 1e-6, detail)
        check("%s: no read at or after the deadline" % label, all(t < budget for t in rel), detail)
    check("the hook's default budget is %d s (55 min)" % WATCH_BUDGET, mod.DEFAULT_DEADLINE == WATCH_BUDGET,
          "DEFAULT_DEADLINE=%r" % mod.DEFAULT_DEADLINE)
    check("watch_run, never completes, 55 min budget: at most %d reads (half of %d at a flat 30 s)"
          % (FLAT_READS // 2, FLAT_READS), len(rel) <= FLAT_READS // 2, "reads=%d" % len(rel))


def case_watch_run_completed_wakes_on_the_next_read():
    """The status turns `completed` at a moment between two reads: in the flat phase (5, 100), just
    after the read at 240 s (241), and deep in the growth phase (1000, 2500). The watch ends at the
    first read that sees it: on the schedule a never-ending run keeps, with no pause after that read,
    and no later than the gap that was running."""
    _, _, _, baseline, _ = never_ending_run()
    for flip in (5, 100, 241, 1000, 2500):
        label = "watch_run, completed %d s after the first read" % flip
        mod, raised, clock, calls, direct = watch_run_on_fakes(
            lambda now, flip=flip: status_reply("completed" if now - T0 >= flip else "in_progress"), WATCH_BUDGET)
        rel = [round(t - T0, 6) for t in read_times(calls)]
        detail = watch_detail(raised, clock, calls, direct) + " reads=%r" % rel[-3:]
        check("%s: returns, no exception" % label, raised is None, detail)
        check("%s: ends at the first read at or after the flip, with no pause after it" % label,
              rel != [] and rel[-1] >= flip and (len(rel) < 2 or rel[-2] < flip)
              and abs(clock.now - T0 - rel[-1]) < 1e-6, detail)
        check("%s: every read is on the schedule of a never-ending run" % label,
              rel == baseline[:len(rel)], detail)
        check("%s: wakes no later than %d s after the flip" % (label, BACKOFF_CAP),
              rel != [] and rel[-1] - flip <= BACKOFF_CAP, detail)


# The GitHub quota during a watch (step gh-quota-budget). The reset is 900 s after the first read, inside the 900 s rate cap,
# and the run completes 300 s after that reset. A quota read rides on a `gh api -i` call, so the watch sees the quota only through it.
QUOTA_RESET = T0 + 900
RUN_ENDS = T0 + 1200


def quota_empty_until(reset):
    """Remaining 0 until `reset` (the header block of a `gh api -i` read), then a full quota in the next window."""
    def quota(now):
        if now < reset:
            return {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(reset))}
        return {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "5000", "X-RateLimit-Reset": str(int(reset + 3600))}
    return quota


def quota_full(now):
    """A full quota (Remaining equal to Limit) in a window that resets an hour on."""
    return {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "5000", "X-RateLimit-Reset": str(int(T0 + 3600))}


def completes_at(ends):
    """The status: in_progress until `ends` on the fake clock, then completed."""
    return lambda now: status_reply("completed" if now >= ends else "in_progress")


def case_watch_run_makes_no_read_while_the_quota_is_low():
    """The quota reads empty until 900 s after the first read, and the run completes 300 s after that reset. While the quota is
    low the watch makes no status read: the first read is the only one before the reset."""
    label = "watch_run, quota empty until 900 s, run completes at 1200 s"
    mod, raised, clock, calls, direct = watch_run_on_fakes(completes_at(RUN_ENDS), WATCH_BUDGET, quota=quota_empty_until(QUOTA_RESET))
    detail = watch_detail(raised, clock, calls, direct)
    check("%s: returns, no exception" % label, raised is None, detail)
    check("%s: the watch ran past the reset" % label, clock.now >= QUOTA_RESET, detail)
    window = [round(t - T0, 6) for t, _ in calls if T0 < t < QUOTA_RESET]
    check("%s: no read while the quota was low" % label, window == [],
          "%d reads between the first read and the reset, at %r s after the first" % (len(window), window[:5]))


def case_watch_run_with_the_quota_full_keeps_its_cadence():  # control: green on main
    """The quota is full: the reads keep the schedule of a never-ending run, 30 s apart for the first four minutes."""
    label = "watch_run, quota full, run completes at 1200 s"
    mod, raised, clock, calls, direct = watch_run_on_fakes(completes_at(RUN_ENDS), WATCH_BUDGET, quota=quota_full)
    detail = watch_detail(raised, clock, calls, direct)
    times = [t for t, _ in calls]
    gaps = [round(b - a, 6) for a, b in zip(times, times[1:])]
    check("%s: returns, no exception" % label, raised is None, detail)
    check("%s: the first four gaps between reads are 30 s" % label, gaps[:4] == [30, 30, 30, 30], detail + " gaps=%r" % gaps[:6])


def case_watch_run_with_the_quota_unreadable_still_ends_at_its_deadline():  # control: green on main
    """The quota reads empty with no reset header, so no reset is known: the watch holds no wait past the rate cap, and
    it still ends at its deadline."""
    label = "watch_run, quota empty with no reset header, run never completes, 30 min budget"
    budget = 1800
    no_reset = lambda now: {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "0"}
    mod, raised, clock, calls, direct = watch_run_on_fakes(completes_at(10 ** 9), budget, quota=no_reset)
    detail = watch_detail(raised, clock, calls, direct)
    check("%s: returns, no exception" % label, raised is None, detail)
    check("%s: no wait past 900 s" % label, all(s <= 900 for s in clock.sleeps), detail)
    check("%s: no read past the deadline" % label, clock.now <= T0 + budget + 1e-6, detail)


# wait_for, in process, on fakes: the pace and the deadline of the run lists. The module's `gh` answers
# `run list` (by the number of the call, as the stub does), `run view` and the status read. Its `time` is the fake clock.
def wait_for_on_fakes(runs, budget, ends_at=None, line=False):
    """Run wait_for(SHA, cwd, deadline) in process. budget: seconds from the clock's start to the
    deadline. -> (exception or None, clock, gh calls [(time, args)], deadline). shutil is a fake with
    no gh, so a read that bypasses the module's `gh()` ends as Unknown and reaches no real gh.
    ends_at: {run id: seconds from the clock's start}. Until then such a run lists and reads in progress
    with no conclusion; from then on it reads as its fixture says. line: also set clock.result (what
    wait_for returned) and clock.line (the line the hook prints for it). A run with refuse_jobs_read: its
    `run view ... jobs` read exits 1 with HTTP 403. Its status read does not."""
    spec = importlib.util.spec_from_file_location("ci_wake_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    clock, calls = FakeTime(), []

    def as_of_clock(r, out):
        end = (ends_at or {}).get(r["databaseId"])
        if end is not None and clock.now - T0 < end:
            return dict(out, status="in_progress", conclusion=None)
        return out

    def fake_gh(args, cwd, timeout=None):
        calls.append((clock.now, list(args)))
        if len(calls) > 400:
            raise AssertionError("runaway reads: 400 gh calls")
        if args[:2] == ["run", "list"]:
            n = sum(1 for _, a in calls if a[:2] == ["run", "list"])
            shown = [as_of_clock(r, GH.view(r, True, n)) for r in runs if r.get("appears_at_list", 1) <= n]
            return 0, json.dumps(shown) + "\n", ""
        if args[:2] == ["run", "view"]:
            hits = [r for r in runs if str(r["databaseId"]) == args[2]]
            if hits:
                if hits[0].get("refuse_jobs_read") and "jobs" in " ".join(args):
                    return 1, "", "HTTP 403: Resource not accessible by integration"
                out = as_of_clock(hits[0], GH.view(hits[0], False))
                fields = args[args.index("--json") + 1].split(",") if "--json" in args else None
                return 0, json.dumps({k: v for k, v in out.items() if not fields or k in fields}) + "\n", ""
        run_id = GH.run_read_id(args)
        if args[:1] == ["api"] and run_id:   # the status read of watch_run, which wait_for makes for each run it judges
            hits = [r for r in runs if str(r["databaseId"]) == run_id]
            if hits:
                return 0, json.dumps(as_of_clock(hits[0], GH.view(hits[0], False))) + "\n", ""
        return 1, "", "stub gh: unsupported: %s" % " ".join(args)

    fake_shutil = types.SimpleNamespace(which=lambda name, *a, **kw: None)
    deadline = clock.now + budget
    clock.result, clock.line = None, None
    with mock.patch.object(mod, "time", clock), mock.patch.object(mod, "gh", fake_gh), \
            mock.patch.object(mod, "shutil", fake_shutil):
        try:
            clock.result = mod.wait_for(SHA, os.getcwd(), deadline)
            raised = None
        except Exception as e:
            raised = e
    if line:
        clock.line = verdict_line(mod, raised, clock.result)
    return raised, clock, calls, deadline


def verdict_line(mod, raised, result):
    """The line the hook prints for one outcome: "CI unknown" when wait_for raised, else the verdict of its runs."""
    if raised is not None:
        return "CI unknown: %s" % raised
    try:
        return mod.verdict(SHA, result)
    except mod.Unknown as e:
        return "CI unknown: %s" % e


def list_times(calls):
    return [t for t, a in calls if a[:2] == ["run", "list"]]


def judged_read(args, runs):
    """True for the jobs read (`run view <id> --json ...,jobs`) of a run that ran: the judgement that
    wait_for makes before it lists again."""
    if args[:2] != ["run", "view"] or "jobs" not in " ".join(args[3:]):
        return False
    hits = [r for r in runs if str(r["databaseId"]) == args[2]]
    return bool(hits) and hits[0]["conclusion"] not in (None, "skipped")


AT_ONCE = 1   # s: a list this close after a judged jobs read is the at-once re-list


def lists_paced(calls, deadline, runs, gap=30):
    """The pace of wait_for's lists. One list may come at once (within AT_ONCE s of a judged jobs read): the
    re-list after the first judged run, once per wait. That list is the reference for the next one. Every
    other list is `gap` s or more after the list before it. The list made at the deadline, after the last
    pause was cut short, is the one other exception."""
    last, judged_at, used, paced = None, None, False, True
    for t, a in calls:
        if judged_read(a, runs):
            judged_at = t
        elif a[:2] == ["run", "list"]:
            if not used and judged_at is not None and t - judged_at <= AT_ONCE:
                used = True
            elif last is not None and not (t - last >= gap or abs(t - deadline) < 1e-6):
                paced = False
            last, judged_at = t, None
    return paced


def wait_detail(raised, clock, calls, deadline):
    return "raised=%r lists_at=%r end=%.1f deadline=%.1f gh=%r" % (
        raised, [round(t - T0, 1) for t in list_times(calls)], clock.now - T0, deadline - T0,
        [" ".join(a[:3]) for _, a in calls])


def case_wait_for_lists_again_until_a_real_run_shows():
    """wait_for: the real run (922) shows at list 3, after a draft run listed skipped. wait_for lists
    again, 30 s or more apart, and reads that run. Main lists twice, 20 s apart, and gives up."""
    label = "wait_for, draft run skipped, real run at the third list"
    runs = [DRAFT_DONE, run(922, "checks", "success", [job("unit", "success")], appears_at_list=3)]
    raised, clock, calls, deadline = wait_for_on_fakes(runs, 3600)
    times, detail = list_times(calls), wait_detail(raised, clock, calls, deadline)
    check("%s: returns, no exception" % label, raised is None, detail)
    check("%s: lists 3 times or more, the first at once" % label, len(times) >= 3 and times[0] == T0, detail)
    check("%s: lists 30 s or more apart, but one re-list at once after the judged run" % label,
          lists_paced(calls, deadline, runs), detail)
    check("%s: reads the real run (922)" % label,
          any(a[:3] == ["run", "view", "922"] for _, a in calls), detail)


def case_wait_for_lists_until_the_deadline_and_no_further():
    """wait_for: only a skipped draft run, so no real run, ever. It keeps listing, 30 s or more apart,
    and its last pause ends at the deadline: no list after the deadline, no pause past it. A deadline
    10 s away (budget 10): the one pause is cut to 10 s, so the wait never outlasts the deadline."""
    for budget in (100, 10):
        label = "wait_for, only a skipped draft run, deadline in %d s" % budget
        raised, clock, calls, deadline = wait_for_on_fakes([DRAFT_DONE], budget)
        times, detail = list_times(calls), wait_detail(raised, clock, calls, deadline)
        check("%s: ends at the deadline, not before it and not past it" % label,
              abs(clock.now - deadline) < 1e-6, detail)
        check("%s: no list after the deadline" % label, all(t <= deadline + 1e-6 for t in times), detail)
        check("%s: lists 30 s or more apart (no judged run, so no re-list at once)" % label,
              lists_paced(calls, deadline, [DRAFT_DONE]), detail)
        if budget == 100:
            check("%s: keeps listing until the deadline (3 lists or more)" % label, len(times) >= 3, detail)


def case_wait_for_lists_back_off_like_the_status_reads():
    """A head with only a skipped draft run is listed until the deadline. The lists follow the schedule of
    the status reads (30 s apart to 240 s, then growing to 120 s at most) and are at most half as many
    as a flat 30 s gap makes. The one list made at the deadline is the only extra."""
    label = "wait_for, only a skipped draft run, 55 min budget"
    _, _, _, baseline, _ = never_ending_run()
    raised, clock, calls, deadline = wait_for_on_fakes([DRAFT_DONE], WATCH_BUDGET)
    rel = [round(t - T0, 6) for t in list_times(calls)]
    before = [t for t in rel if t < WATCH_BUDGET]
    gaps = [b - a for a, b in zip(before, before[1:])]
    detail = wait_detail(raised, clock, calls, deadline)[:300] + " distinct gaps %r" % sorted({round(g, 1) for g in gaps})
    check("%s: ends at the deadline, with no list after it" % label,
          abs(clock.now - deadline) < 1e-6 and all(t <= WATCH_BUDGET for t in rel), detail)
    check("%s: at most %d lists (half of %d at a flat 30 s)" % (label, FLAT_READS // 2, FLAT_READS),
          len(rel) <= FLAT_READS // 2, "lists=%d" % len(rel))
    check("%s: the lists come at the times of the status reads" % label,
          before == baseline[:len(before)] and len(before) >= 9, detail)
    check("%s: the gaps grow to 90 s or more, never past %d s" % (label, BACKOFF_CAP),
          gaps != [] and 90 <= max(gaps) <= BACKOFF_CAP + 1e-6, detail)


def case_lists_paced_takes_one_at_once_relist_per_wait():
    """The pace check itself, on fixed call lists (no gh, no clock). One list may come at once after a judged
    jobs read; a skipped read between the judged read and that list does not change it (probe: a judged,
    skipped, at-once order is no pace break). A second at-once list, or a list at once after the first, is
    a pace break."""
    listed = ["run", "list", "--commit", SHA]
    judged = ["run", "view", "930", "--json", "databaseId,name,status,conclusion,jobs"]
    skipped = ["run", "view", "931", "--json", "databaseId,name,status,conclusion,jobs"]
    probe_runs = [run(930, "checks", "success", [job("unit", "success")]),
                  run(931, "checks", "skipped", [job("unit", "skipped")])]
    rows = (
        ("judged, skipped, at-once list, then 30 s", True,
         [(0, listed), (30, listed), (30, judged), (30, skipped), (30, listed), (60, listed)]),
        ("at-once list after a judged read, then 30 s", True,
         [(0, listed), (0, judged), (0, listed), (30, listed)]),
        ("second at-once list after the first", False,
         [(0, listed), (0, judged), (0, listed), (0, judged), (0, listed)]),
        ("at-once list after the first one was used", False,
         [(0, listed), (30, listed), (30, judged), (30, listed), (30, judged), (30, listed)]),
        ("two lists 10 s apart", False, [(0, listed), (10, listed)]),
    )
    for label, want, calls in rows:
        got = lists_paced(calls, 3600, probe_runs)
        check("lists_paced, %s: %s" % (label, "paced" if want else "a pace break"), got == want,
              "got %r" % got)


# The watch names the PR's repo on every gh call and gives that repo's verdict. The rows put the PR in
# one repo and the session folder in another. A run read that drops -R searches the folder's repo, finds
# no run, and the hook says "no run yet" for a PR whose CI passed.
# Every case runs the real hook. The cases that wait to a deadline use CI_WAKE_DEADLINE 4, so a wrong
# answer ends in seconds. A verdict case uses 15 s: once the deadline has passed, watch_run makes no status
# read (by design), so a tight deadline under a slow stub start would drop the status-read check.
VERDICT_DEADLINE = "15"
REPO_APP = "shivinate7/home"            # the PR's repo
REPO_HOME = "shivinate7/home-archive"   # the folder's repo: no workflow files


def wf(state="active", repo=None):
    """One entry of `gh workflow list --json`, as the fixture holds it."""
    out = {"id": 1, "name": "checks", "path": ".github/workflows/checks.yml", "state": state}
    if repo:
        out["repo"] = repo
    return out


def in_repo(entry, repo):
    """A copy of a run fixture that exists only in repo."""
    return dict(entry, repo=repo)


def case_wrong_repo_every_gh_call_names_the_pr_repo():
    """The watch passes the PR's -R on every gh call, and its verdict is that repo's own. The folder's
    repo (cwd_repo) holds no run, so a call that drops -R reads nothing and the hook says "no run yet".
    The rows spell the flag both ways and cover a green and a red run."""
    rows = (
        ("--repo, green", "--repo", GREEN, "green", [], ["901"]),
        ("-R, green", "-R", GREEN, "green", [], ["901"]),
        ("--repo, red", "--repo", RED, "red", ["unit", "e2e"], ["902"]),
    )
    for name, spelling, ran, want, names, ids in rows:
        label = "wrong repo, %s" % name
        fx = fixture([pr(214, repo=REPO_APP)], [in_repo(ran, REPO_APP)], cwd_repo=REPO_HOME,
                     workflows=[wf(repo=REPO_APP)])
        res = run_hook(bash("gh pr ready 214 %s %s" % (spelling, REPO_APP)), fx,
                       extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
        expect_verdict(label, res, want, names_in=names)
        check("%s: every gh call passes -R %s" % (label, REPO_APP),
              bool(res.calls) and all(GH.repo_of(c) == REPO_APP for c in res.calls), why(res))
        expect_watch(label, res, ids)


def case_repo_without_ci_starts_no_watch():
    """A repo with no active workflow starts no watch: silent, exit 0, no run read. The rows: no repo
    flag (the incident form), no workflows, and only a disabled workflow. The --repo rows also check
    that the hook asked the PR's repo for its workflows."""
    rows = (
        ("no repo flag, no workflows", "gh pr ready 7", [], False),
        ("--repo, no workflows", "gh pr ready 7 --repo " + REPO_HOME, [], True),
        ("--repo, only a disabled workflow", "gh pr ready 7 --repo " + REPO_HOME,
         [wf(state="disabled_manually", repo=REPO_HOME)], True),
    )
    for name, command, workflows, asks in rows:
        label = "no CI, %s" % name
        fx = fixture([pr(7, repo=REPO_HOME)], [], cwd_repo=REPO_HOME, workflows=workflows)
        res = run_hook(bash(command), fx, extra={"CI_WAKE_DEADLINE": "4"})
        expect_silent(label, res)
        expect_no_watch(label, res)
        check("%s: no run list, run view or status read" % label,
              count(res, "run", "list") == 0 and count(res, "run", "view") == 0 and run_reads(res) == [], why(res))
        if asks:
            check("%s: workflow list reads -R %s" % (label, REPO_HOME),
                  any(GH.strip_repo(c)[:2] == ["workflow", "list"] and GH.repo_of(c) == REPO_HOME
                      for c in res.calls), why(res))


def case_workflows_but_no_run_on_head_still_says_no_run_yet():
    """Pins existing behaviour (a control). A repo with an active workflow and no run on the head is the
    real alert: the hook waits to its deadline and wakes "CI unknown on <sha7>: no run yet"."""
    fx = fixture([pr(214, repo=REPO_APP)], [], cwd_repo=REPO_APP, workflows=[wf(repo=REPO_APP)])
    res = run_hook(bash("gh pr ready 214 --repo " + REPO_APP), fx, extra={"CI_WAKE_DEADLINE": "4"})
    label = "workflows, no run on the head (control)"
    expect_verdict(label, res, "unknown")
    v = verdict_of(res)
    check("%s: the line says no run yet, on sha7" % label,
          v is not None and v[1] == SHA7 and "no run yet" in v[2], why(res))
    check("%s: wakes at its deadline (3.5 s to 15 s)" % label, 3.5 <= res.elapsed < 15, why(res))


def case_failed_workflow_read_is_not_no_workflows():
    """Pins existing behaviour (a control). A failed `gh workflow list` read is not "no workflows": the watch
    runs as it does today, so a red run still wakes the session with its failing jobs. Rows: exit 1, non-JSON."""
    for name, switch in (("exit 1", "error"), ("non-JSON", "garbage")):
        label = "workflow list %s, red run (control)" % name
        fx = fixture([pr(214, repo=REPO_APP)], [in_repo(RED, REPO_APP)], cwd_repo=REPO_APP,
                     workflows=[wf(repo=REPO_APP)], workflow_list=switch)
        res = run_hook(bash("gh pr ready 214 --repo " + REPO_APP), fx, extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
        expect_verdict(label, res, "red", names_in=["unit", "e2e"])
        expect_watch(label, res, ["902"])


# Selector forms that leave the repo out of the hook's own parse. The PR lives in REPO_APP, and the folder
# is REPO_HOME, which has no workflow. Each form must give the PR's verdict, and every gh call after the
# pr view must name REPO_APP with -R, taken from the PR's own url field.
URL_APP = "https://github.com/%s/pull/214" % REPO_APP


def after_pr_view(res):
    """The gh calls made after the watch's PR read (gh api), in order. [] when there is none."""
    idx = next((i for i, c in enumerate(res.calls) if GH.strip_repo(c)[:1] == ["api"]), None)
    return [] if idx is None else res.calls[idx + 1:]


def pins_pr_repo_after_pr_view(label, command):
    """Run the hook from the folder, with the PR in REPO_APP. The verdict must be the PR's green run. The
    gh calls after the pr view must include a workflow list and a run list, and each must carry -R REPO_APP."""
    fx = fixture([pr(214, repo=REPO_APP)], [in_repo(GREEN, REPO_APP)], cwd_repo=REPO_HOME,
                 workflows=[wf(repo=REPO_APP)])
    res = run_hook(bash(command), fx, extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    expect_verdict(label, res, "green")
    after = after_pr_view(res)
    kinds = [GH.strip_repo(c)[:2] for c in after]
    check("%s: after its pr view, the watch makes a workflow list and a run list" % label,
          ["workflow", "list"] in kinds and ["run", "list"] in kinds, why(res))
    check("%s: every gh call after pr view passes -R %s" % (label, REPO_APP),
          bool(after) and all(GH.repo_of(c) == REPO_APP for c in after), why(res))
    expect_watch(label, res, ["901"])


def case_url_selector_pins_pr_repo_on_later_calls():
    pins_pr_repo_after_pr_view("URL selector, no -R", "gh pr ready " + URL_APP)


def case_gh_repo_prefix_pins_pr_repo_on_later_calls():
    pins_pr_repo_after_pr_view("GH_REPO prefix", "GH_REPO=%s gh pr ready 214" % REPO_APP)


def case_attached_short_repo_flag_pins_pr_repo_on_later_calls():
    pins_pr_repo_after_pr_view("attached -R, -Ro/r", "gh pr ready 214 -R%s" % REPO_APP)


def case_equals_short_repo_flag_pins_pr_repo_on_later_calls():
    pins_pr_repo_after_pr_view("-R=o/r", "gh pr ready 214 -R=%s" % REPO_APP)


def case_folder_without_workflows_still_watches_the_pr_repo():
    """The folder's repo has no workflow and the PR's repo has one. The watch must still run, and report
    the PR repo's verdict. The run here is red, so an empty folder cannot pass for it."""
    fx = fixture([pr(214, repo=REPO_APP)], [in_repo(RED, REPO_APP)], cwd_repo=REPO_HOME,
                 workflows=[wf(repo=REPO_APP)])
    res = run_hook(bash("gh pr ready " + URL_APP), fx, extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    label = "folder without workflows, PR repo with a red run"
    expect_verdict(label, res, "red", names_in=["unit", "e2e"])
    expect_watch(label, res, ["902"])


def case_exported_gh_repo_names_the_pr_repo():
    """The hook reads GH_REPO only as a prefix of the `gh pr ready` command. `export GH_REPO=o/r` (bash) and
    `$env:GH_REPO = "o/r"` (PowerShell) set it for gh in the shell, not for the hook. The hook's own gh calls
    then go to the folder's repo, which holds no PR here, and it says nothing. Controls: the prefix form, and
    a GH_REPO already in the hook's own environment (gh reads it for every call). Both controls pass either way."""
    fx = fixture([pr(214, repo=REPO_APP)], [in_repo(GREEN, REPO_APP)], cwd_repo=REPO_HOME,
                 workflows=[wf(repo=REPO_APP)])
    rows = (
        ("GH_REPO prefix (control)", bash("GH_REPO=%s gh pr ready 214" % REPO_APP), {}),
        ("GH_REPO in the hook's environment (control)", bash("gh pr ready 214"), {"GH_REPO": REPO_APP}),
        ("export GH_REPO, bash", bash("export GH_REPO=%s && gh pr ready 214" % REPO_APP), {}),
        ("$env:GH_REPO, PowerShell", powershell('$env:GH_REPO = "%s"; gh pr ready 214' % REPO_APP), {}),
    )
    for label, payload, env in rows:
        res = run_hook(payload, fx, extra=dict({"CI_WAKE_DEADLINE": VERDICT_DEADLINE}, **env))
        check("%s: the watch reads run 901 in %s" % (label, REPO_APP), "901" in watched(res), why(res))
        expect_verdict(label, res, "green")


def case_gh_repo_values_the_hook_cannot_read_fall_back_to_the_folder():
    """A GH_REPO the hook cannot expand (`$repo`, `$REPO`, `$(x)`, a backtick) names no repo, so the hook's own
    gh calls go to the folder's repo, as with no GH_REPO. `$null` clears it, and so does `Remove-Item Env:GH_REPO`
    after a set. `unset OTHER` leaves GH_REPO set (control). The folder holds one open PR in the fallback rows, so a
    wrong repo finds nothing. Scope first (the PR read's path), then the verdict."""
    home = fixture([pr(214, repo=REPO_HOME)], [in_repo(GREEN, REPO_HOME)], cwd_repo=REPO_HOME,
                   workflows=[wf(repo=REPO_HOME)])
    app = fixture([pr(214, repo=REPO_APP)], [in_repo(GREEN, REPO_APP)], cwd_repo=REPO_HOME,
                  workflows=[wf(repo=REPO_APP)])
    folder, app_path = "repos/{owner}/{repo}/pulls/214", "repos/%s/pulls/214" % REPO_APP
    rows = (
        ("$env:GH_REPO = $repo", powershell('$env:GH_REPO = $repo; gh pr ready 214'), home, folder),
        ("export GH_REPO=$REPO", bash("export GH_REPO=$REPO && gh pr ready 214"), home, folder),
        ("export GH_REPO=$(x)", bash("export GH_REPO=$(x) && gh pr ready 214"), home, folder),
        ("export GH_REPO=`x`", bash("export GH_REPO=`x` && gh pr ready 214"), home, folder),
        ("$env:GH_REPO = $null", powershell('$env:GH_REPO = $null; gh pr ready 214'), home, folder),
        ("$env:GH_REPO set, then Remove-Item Env:GH_REPO",
         powershell('$env:GH_REPO = "%s"; Remove-Item Env:GH_REPO; gh pr ready 214' % REPO_APP), home, folder),
        ("export GH_REPO, then unset OTHER (control: stays set)",
         bash("export GH_REPO=%s && unset OTHER && gh pr ready 214" % REPO_APP), app, app_path),
    )
    for label, payload, fx, path in rows:
        res = run_hook(payload, fx, extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
        where = "the folder's repo" if path == folder else REPO_APP
        check("%s: the PR read goes to %s" % (label, where), api_reads(res)[:1] == [path],
              "%r; %s" % (api_reads(res), why(res)))
        expect_verdict(label, res, "green")
        expect_watch(label, res, ["901"])


def case_exported_gh_repo_is_cleared_by_unset_and_empty_export():
    """An exported GH_REPO lasts until the command clears it. `unset GH_REPO` and `export GH_REPO=` (empty)
    clear it, so the hook's own gh calls go to the folder's repo, which holds no PR here, and it says nothing.
    The PowerShell form `${env:GH_REPO} = "o/r"` sets it, as `$env:GH_REPO = ...` does."""
    fx = fixture([pr(214, repo=REPO_APP)], [in_repo(GREEN, REPO_APP)], cwd_repo=REPO_HOME,
                 workflows=[wf(repo=REPO_APP)])
    rows = (
        ("export GH_REPO, then unset GH_REPO", bash("export GH_REPO=%s && unset GH_REPO && gh pr ready 214"
                                                    % REPO_APP), "clear"),
        ("export GH_REPO, then export GH_REPO= (empty)", bash("export GH_REPO=%s && export GH_REPO= && gh pr ready 214"
                                                              % REPO_APP), "clear"),
        ("${env:GH_REPO} = o/r, PowerShell", powershell('${env:GH_REPO} = "%s"; gh pr ready 214' % REPO_APP), "set"),
    )
    for label, payload, want in rows:
        res = run_hook(payload, fx, extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
        if want == "clear":
            check("%s: the PR read names no repo (the folder's)" % label,
                  api_reads(res)[:1] == ["repos/{owner}/{repo}/pulls/214"], "%r; %s" % (api_reads(res), why(res)))
            expect_silent(label, res)
            expect_no_watch(label, res)
        else:
            check("%s: the PR read names %s" % (label, REPO_APP),
                  api_reads(res)[:1] == ["repos/%s/pulls/214" % REPO_APP], "%r; %s" % (api_reads(res), why(res)))
            expect_verdict(label, res, "green")
            expect_watch(label, res, ["901"])


def api_reads(res):
    """The words after `api` of every `gh api` call (path, then fields), in order."""
    return [" ".join(c[1:]) for c in map(GH.strip_repo, res.calls) if c[:1] == ["api"] and len(c) > 1]


def graphql_calls(res):
    """Every call the proxy refuses: any `gh pr ...` and `gh api graphql`."""
    return [c for c in map(GH.strip_repo, res.calls) if c[:1] == ["pr"] or c[:2] == ["api", "graphql"]]


def case_pr_read_is_rest_for_every_selector():
    """The PR read goes by `gh api repos/.../pulls`, never `gh pr view`: the cloud proxy refuses GraphQL.
    Rows: number, url, branch, branch with -R, and the empty selector (the folder's branch). The stub
    refuses GraphQL and answers REST names only, so a hook on the GraphQL path wakes unknown."""
    branch = "hook-wave-2"
    folder = tempfile.mkdtemp(prefix="repo-", dir=TMP)
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=folder, check=True)
    rows = (
        ("number", "gh pr ready 12", "repos/{owner}/{repo}/pulls/12"),
        ("url", "gh pr ready " + URL_APP, "repos/%s/pulls/214" % REPO_APP),
        ("branch", "gh pr ready " + branch, "-X GET repos/{owner}/{repo}/pulls -F head={owner}:%s -f state=open" % branch),
        ("branch with -R", "gh pr ready %s -R %s" % (branch, REPO_APP),
         "-X GET repos/%s/pulls -F head=%s:%s -f state=open" % (REPO_APP, REPO_APP.split("/")[0], branch)),
        ("empty selector", "gh pr ready", "-X GET repos/{owner}/{repo}/pulls -F head={owner}:%s -f state=open" % branch),
    )
    for name, command, path in rows:
        label = "REST read, %s selector" % name
        prs = [pr(214, repo=REPO_APP, branch=branch)] if "214" in path or "-R" in command else [pr(12, branch=branch)]
        fx = fixture(prs, [in_repo(GREEN, REPO_APP)] if "-R" in command or "214" in path else [GREEN],
                     cwd_repo=REPO_APP if "214" in path else "", workflows=[wf(repo=REPO_APP)] if "214" in path else None)
        if fx["workflows"] is None:
            del fx["workflows"]
        res = run_hook(dict(bash(command), cwd=folder), fx, extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
        expect_verdict(label, res, "green")
        check("%s: reads %s" % (label, path), api_reads(res)[:1] == [path], "%r; %s" % (api_reads(res), why(res)))
        check("%s: no gh pr call, no graphql" % label, graphql_calls(res) == [], why(res))
        expect_watch(label, res, ["901"])


def case_draft_and_missing_pr_start_no_watch_by_rest():
    """A draft PR (REST `draft` true) and a PR that does not exist (404, or an empty branch list) start no
    watch and print nothing, for each selector form."""
    branch = "hook-wave-2"
    folder = tempfile.mkdtemp(prefix="repo-", dir=TMP)
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=folder, check=True)
    for selector in ("12", branch, ""):
        command = "gh pr ready" + (" " + selector if selector else "")
        label = "REST draft PR, selector %r" % selector
        res = run_hook(dict(bash(command), cwd=folder), fixture([pr(12, draft=True, branch=branch)], [GREEN]))
        expect_silent(label, res)
        expect_no_watch(label, res)
        check("%s: read by gh api, no run list" % label,
              len(api_reads(res)) == 1 and count(res, "run", "list") == 0 and graphql_calls(res) == [], why(res))
    for selector in ("99", "no-such-branch", ""):
        command = "gh pr ready" + (" " + selector if selector else "")
        label = "REST no PR, selector %r" % selector
        res = run_hook(dict(bash(command), cwd=folder), fixture([pr(12, branch="other-branch")], [GREEN]))
        expect_silent(label, res)
        expect_no_watch(label, res)
        check("%s: read by gh api, no run list" % label,
              len(api_reads(res)) == 1 and count(res, "run", "list") == 0 and graphql_calls(res) == [], why(res))


def case_empty_selector_without_a_branch_is_unknown():
    """`gh pr ready` on a detached HEAD names no branch: unknown, never a guessed PR."""
    folder = tempfile.mkdtemp(prefix="repo-", dir=TMP)
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
    with open(os.path.join(folder, "f"), "w") as f:
        f.write("x")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "f"], cwd=folder, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=folder, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach"], cwd=folder, check=True)
    res = run_hook(dict(bash("gh pr ready"), cwd=folder), fixture(READY, [GREEN]))
    expect_verdict("empty selector on a detached HEAD", res, "unknown")
    check("empty selector on a detached HEAD: no PR read", api_reads(res) == [], why(res))


def case_hash_number_selector_reads_the_number_route():
    """read_pr must strip a `#` before it tests the selector for digits. Without that, a quoted "#12" takes
    the branch route (head=owner:#12), finds no PR, and starts no watch. The selector is quoted on purpose:
    an unquoted `#` starts a shell comment, so neither the hook nor gh sees a selector there. Each row checks
    the route first, then the verdict. `gh pr ready 12` is the control."""
    rows = (
        ("gh pr ready 12 (control)", "gh pr ready 12", READY, [GREEN], "repos/{owner}/{repo}/pulls/12"),
        ('gh pr ready "#12"', 'gh pr ready "#12"', READY, [GREEN], "repos/{owner}/{repo}/pulls/12"),
        ('gh pr ready "#12" -R o/r', 'gh pr ready "#12" -R %s' % REPO_APP, [pr(12, repo=REPO_APP)],
         [in_repo(GREEN, REPO_APP)], "repos/%s/pulls/12" % REPO_APP),
    )
    for label, command, prs, runs, path in rows:
        res = run_hook(bash(command), fixture(prs, runs), extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
        check("%s: reads the PR by number, %s" % (label, path), api_reads(res)[:1] == [path],
              "%r; %s" % (api_reads(res), why(res)))
        expect_verdict(label, res, "green")
        expect_watch(label, res, ["901"])


def load_module():
    spec = importlib.util.spec_from_file_location("ci_wake_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_read_pr_maps_rest_fields():
    """read_pr gives the watch the names it reads (number, isDraft, headRefName, headRefOid, state, url)
    from the REST names (number, draft, head.ref, head.sha, state + merged, html_url). A host-qualified repo
    reads with --hostname. In process, on a fake gh."""
    mod = load_module()
    rest_pr = {"number": 7, "draft": True, "state": "closed", "merged": True, "html_url": "https://github.com/o/r/pull/7",
               "head": {"ref": "topic", "sha": SHA}}
    seen = []

    def fake_gh(args, cwd, timeout=None):
        seen.append(args)
        return 0, json.dumps(rest_pr), ""

    with mock.patch.object(mod, "gh", fake_gh):
        got = mod.read_pr("7", "ghe.example.com/o/r", None)
    check("read_pr maps the REST names",
          got == {"number": 7, "isDraft": True, "headRefName": "topic", "headRefOid": SHA, "state": "MERGED",
                  "url": "https://github.com/o/r/pull/7"}, repr(got))
    check("read_pr: a host-qualified repo reads repos/o/r with --hostname",
          seen == [["api", "repos/o/r/pulls/7", "--hostname", "ghe.example.com"]], repr(seen))
    open_pr = dict(rest_pr, draft=False, state="open", merged=False)
    with mock.patch.object(mod, "gh", lambda a, c, timeout=None: (0, json.dumps([open_pr]), "")):
        got = mod.read_pr("topic", "o/r", None)
    check("read_pr: a branch list answers its first PR as OPEN, not a draft",
          got["state"] == "OPEN" and got["isDraft"] is False and got["headRefOid"] == SHA, repr(got))


MCP_READY = "mcp__github__update_pull_request"   # the cloud's ready route: draft false marks a PR ready


def mcp_update(pull, owner, repo, draft=None):
    """The PostToolUse payload of the GitHub MCP update call. draft None: the call sets no draft field.
    tool_input keys as hooks/guard.py reads them for this tool: owner, repo, pullNumber, draft."""
    args = {"owner": owner, "repo": repo, "pullNumber": pull}
    if draft is not None:
        args["draft"] = draft
    return {"tool_name": MCP_READY, "tool_input": args}


def case_mcp_ready_call_starts_the_watch():
    """The MCP update with draft false marks its PR ready. Its watch reads the PR's own repo (owner and
    repo of tool_input), not the folder's (cwd_repo), and each gh call names that repo. The shell
    `gh pr ready` on the same fixture is the green control: only the payload differs."""
    owner, name = REPO_APP.split("/")
    fx = fixture([pr(214, repo=REPO_APP)], [in_repo(GREEN, REPO_APP)], cwd_repo=REPO_HOME,
                 workflows=[wf(repo=REPO_APP)])
    control = run_hook(bash("gh pr ready 214 --repo %s" % REPO_APP), fx,
                       extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    expect_verdict("control: shell gh pr ready 214 --repo, green", control, "green")
    expect_watch("control: shell gh pr ready 214 --repo", control, ["901"])

    res = run_hook(mcp_update(214, owner, name, draft=False), fx,
                   extra={"CI_WAKE_DEADLINE": VERDICT_DEADLINE})
    expect_verdict("MCP update_pull_request, draft false, green", res, "green")
    expect_watch("MCP update_pull_request, draft false", res, ["901"])
    check("MCP update_pull_request, draft false: every gh call passes -R %s" % REPO_APP,
          bool(res.calls) and all(GH.repo_of(c) == REPO_APP for c in res.calls), why(res))


def case_mcp_update_that_does_not_mark_ready_starts_nothing():
    """An MCP update with no draft field, or with draft true, is no ready call: the hook exits 0 with no
    output and makes no gh call. The decision comes from tool_input alone."""
    for label, draft in (("no draft field", None), ("draft true", True)):
        res = run_hook(mcp_update(12, "shivinate7", "claude-settings", draft=draft), fixture(READY, [GREEN]))
        expect_silent("MCP update_pull_request, %s: starts nothing" % label, res)
        expect_no_gh("MCP update_pull_request, %s" % label, res)


def main():
    hook_exists = os.path.isfile(MODULE)
    check("module under test exists (missing module = red for this reason)", hook_exists, MODULE)

    # Watch starts: only gh pr ready.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]))
    expect_verdict("gh pr ready 12 (green)", res, "green")
    expect_watch("gh pr ready 12", res, ["901"])

    res = run_hook(powershell("gh pr ready 12"), fixture(READY, [GREEN]))
    expect_verdict("PowerShell tool, gh pr ready 12 (green)", res, "green")
    expect_watch("PowerShell tool, gh pr ready 12", res, ["901"])

    # The cloud's ready route (ci-wake-mcp-ready): an MCP update with draft false starts a watch; one
    # with no draft field, or draft true, starts none.
    case_mcp_ready_call_starts_the_watch()
    case_mcp_update_that_does_not_mark_ready_starts_nothing()

    # Two gh pr ready calls in one command: one process, one verdict line per PR, one wake.
    res = run_hook(bash("gh pr ready 12 && gh pr ready 13"), fixture(TWO_PRS, [GREEN, RED_B]))
    vs = verdicts_of(res)
    check("gh pr ready 12 && gh pr ready 13: one process, two CI lines, exit 2",
          res.rc == 2 and not res.hung and vs is not None and len(vs) == 2, why(res))
    check("gh pr ready 12 && gh pr ready 13: one line per PR (12 green on sha7, 13 red on sha7)",
          vs is not None and sorted((v[0], v[1]) for v in vs) == sorted([("green", SHA7), ("red", SHA7_B)]),
          why(res))
    check("gh pr ready 12 && gh pr ready 13: reads the status of runs 901 and 911, one each, no run watch",
          sorted(watched(res)) == ["901", "911"] and run_watches(res) == [], why(res))
    check("gh pr ready 12 && gh pr ready 13: run list read at most four times (one list and one re-list per PR)",
          count(res, "run", "list") <= 4, why(res))

    # A push starts no watch, in any form, and makes no gh call.
    for command in PUSH_FORMS:
        res = run_hook(bash(command), fixture(READY, [GREEN]))
        expect_silent("push starts no watch: %s" % command, res)
        expect_no_gh("push starts no watch: %s" % command, res)

    res = run_hook(powershell("git push origin hook-wave-2"), fixture(READY, [GREEN]))
    expect_silent("PowerShell push starts no watch", res)
    expect_no_gh("PowerShell push starts no watch", res)

    res = run_hook(bash("git push origin hook-wave-2 && gh pr ready 12"), fixture(READY, [GREEN]))
    expect_verdict("push, then gh pr ready 12: verdict for PR 12", res, "green")
    expect_watch("push, then gh pr ready 12: watches PR 12 only", res, ["901"])
    check("push, then gh pr ready 12: no pr list call (the push is not read)",
          count(res, "pr", "list") == 0, why(res))

    # No watch and no gh call. Each row: (row id, tool payload, the PRs the stub holds).
    # The row id prints on FAIL. Quoted, heredoc and comment spellings are checked below.
    NO_WATCH_ROWS = (
        ("git push, only a draft PR", bash("git push origin hook-wave-2"), [pr(12, draft=True)]),
        ("git push, no PR for this branch (a ready PR on another branch)",
         bash("git push origin hook-wave-2"), [pr(12, branch="other-branch")]),
        ("git push, no PR at all", bash("git push origin hook-wave-2"), []),
        ("ls -la", bash("ls -la"), READY),
        ("git status", bash("git status"), READY),
        ("trigger text inside a quoted commit message",
         bash('git commit -m "note: gh pr ready 12 later"'), READY),
        ("trigger text inside a quoted echo", bash('echo "git push origin hook-wave-2"'), READY),
        ("non-Bash, non-PowerShell tool carrying a trigger command",
         {"tool_name": "Edit", "tool_input": {"command": "gh pr ready 12"}}, READY),
    )
    for label, payload, prs in NO_WATCH_ROWS:
        res = run_hook(payload, fixture(prs, [GREEN]))
        expect_silent(label, res)
        expect_no_watch(label, res)
        expect_no_gh(label, res)

    # Quotes, heredoc bodies, comments. The record: none of these starts a watch.
    guard_silent("gh pr ready inside double quotes", 'echo "gh pr ready 12"')
    guard_silent("gh pr ready inside single quotes", "echo 'gh pr ready 12'")
    guard_silent("gh pr ready inside a heredoc body", "cat <<'EOF'\ngh pr ready 12\nEOF")
    guard_silent("gh pr ready inside a multi-line double-quoted string",
                 'echo "first line\ngh pr ready 12\nlast line"')
    guard_silent("gh pr ready after an unquoted #", "echo ok # gh pr ready 12")
    guard_silent("gh pr ready in a PowerShell here-string", "Write-Output @'\ngh pr ready 12\n'@",
                 tool=powershell)
    res = run_hook(bash("cat <<'EOF'\ngh pr ready 12\nEOF\ngh pr ready 13"), fixture(TWO_PRS, [GREEN, RED_B]))
    vs = verdicts_of(res)
    check("heredoc body ignored, gh pr ready 13 after the delimiter still watches",
          res.rc == 2 and vs is not None and [(v[0], v[1]) for v in vs] == [("red", SHA7_B)]
          and sorted(watched(res)) == ["911"] and run_watches(res) == [], why(res))

    # A lone quote, a # inside quotes, and a multi-line quote do not hide a later gh pr ready.
    watch_pr12("lone quote in earlier text: gh pr ready 12 still watches", "echo don't && gh pr ready 12")
    watch_pr12("# inside double quotes is no comment", 'echo "see #12" && gh pr ready 12')
    watch_pr12("comment openers inside single quotes", "echo '// /*' && gh pr ready 12")
    watch_pr12("multi-line quoted text, then gh pr ready 12 still watches",
               'echo "one\ntwo" && gh pr ready 12')
    watch_pr12("trailing # after a real trigger", "gh pr ready 12 # watch PR 12")

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

    # Two runs that end only after several reads (906 after 2, 907 after 3): each is read again until
    # it completes, 3 and 4 status reads. A hook that stops after one read gets 1 and 1, and a
    # "still running" line, because the stub shows the run in progress at the final read too.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [LATE_906, LATE_907]),
                   launcher=FAST_SLEEP_LAUNCHER)
    expect_verdict("two in-progress runs, both waited on until each completes", res, "green")
    expect_watch("two in-progress runs, both waited on until each completes", res,
                 ["906"] * 3 + ["907"] * 4)

    # Own deadline: a run still pending at the deadline wakes with a still-running line.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [PENDING]), extra={"CI_WAKE_DEADLINE": "1"})
    v = verdict_of(res)
    check("deadline 1 s, run still pending: exit 2, one unknown line with sha7 and 'still running'",
          res.rc == 2 and not res.hung and v is not None and v[0] == "unknown" and v[1] == SHA7
          and "still running" in v[2], why(res))
    check("deadline 1 s, run still pending: wakes at its deadline (under 6 s): the 30 s pause stops at the deadline",
          not res.hung and res.elapsed < 6, "elapsed=%.1f s; the run never ends" % res.elapsed)

    # Decision ci-wait-reads-run-status: a failed status read is retried once, then the wait ends as
    # unknown (decision ci-wait-reads-run-status). FAST_SLEEP_LAUNCHER: the retry pause costs 0.05 s.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [BAD_STATUS]), launcher=FAST_SLEEP_LAUNCHER)
    expect_verdict("status read exits 1", res, "unknown")
    check("status read exits 1: two status reads (one retry), no run watch",
          watched(res) == ["912", "912"] and run_watches(res) == [], why(res))

    # A run queued for two reads is read again until it completes: three status reads, then green.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [QUEUED_913]), launcher=FAST_SLEEP_LAUNCHER)
    expect_verdict("run queued for two reads, then completed", res, "green")
    expect_watch("run queued for two reads, then completed", res, ["913"] * 3)

    # One watcher per PR.
    case_one_watcher_per_pr()

    # Unreadable gh: never a silent exit 0 for a command that could start a watch.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), path="missing")
    expect_verdict("gh not on PATH, gh pr ready", res, "unknown")
    expect_no_watch("gh not on PATH, gh pr ready", res)

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN], mode="error"))
    expect_verdict("gh exits non-zero, gh pr ready", res, "unknown")

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN], mode="garbage"))
    expect_verdict("gh prints non-JSON, gh pr ready", res, "unknown")

    res = run_hook(bash("git push origin hook-wave-2"), fixture(READY, [GREEN], mode="error"))
    expect_silent("gh exits non-zero, git push: no watch, no read", res)
    expect_no_gh("gh exits non-zero, git push", res)

    res = run_hook(bash("ls -la"), fixture(READY, [GREEN]), path="missing")
    expect_silent("gh not on PATH, ls -la (no gh needed)", res)

    # Any uncaught error exits 2 with one unknown line, never exit 1.
    res = run_hook(None, fixture(READY, [GREEN]), stdin="[" * 200000)
    expect_verdict("uncaught error: nested JSON on stdin (RecursionError)", res, "unknown")

    res = run_hook({"tool_name": "Bash", "tool_input": "ls -la"}, fixture(READY, [GREEN]))
    expect_verdict("uncaught error: tool_input is not an object", res, "unknown")

    case_skipped_only_head_is_no_run_yet()
    case_draft_pr_starts_no_watch()
    case_import_error_wakes_unknown()
    case_final_flush_error_wakes_unknown()
    case_background_separator_starts_each_watch()
    case_lock_folder_unusable_wakes_unknown()

    # Decision ci-wait-reads-run-status: watch_run on fakes.
    case_watch_run_reads_the_status_until_completed()
    case_watch_run_completed_at_the_first_read_does_not_pause()
    case_watch_run_returns_at_the_deadline()
    case_watch_run_at_or_past_the_deadline_reads_nothing()
    case_watch_run_failed_read_is_unknown_after_one_retry()
    case_watch_run_retries_a_failed_read_once_and_goes_on()
    case_watch_run_reads_past_a_queued_status()
    case_watch_run_retry_never_reads_or_pauses_past_the_deadline()
    case_watch_run_reads_30_s_apart_for_the_first_four_minutes()
    case_watch_run_gaps_grow_to_a_cap()
    case_watch_run_back_off_keeps_the_deadline_and_cuts_the_reads()
    case_watch_run_completed_wakes_on_the_next_read()

    # The GitHub quota during a watch: no read while it is low, the cadence and the deadline kept while it is full or unreadable.
    case_watch_run_makes_no_read_while_the_quota_is_low()
    case_watch_run_with_the_quota_full_keeps_its_cadence()
    case_watch_run_with_the_quota_unreadable_still_ends_at_its_deadline()

    # A draft run that skips, then the real run.
    case_draft_run_then_real_run()
    case_real_run_listed_late()
    case_real_failed_run_beside_a_draft_run_is_red()
    case_draft_run_ending_skipped_is_no_run_yet()
    case_run_visible_at_the_at_once_relist_is_judged()
    case_the_at_once_relist_judges_the_newest_run_of_a_name()
    case_failed_re_list_keeps_the_judged_verdict()
    case_failed_re_list_after_a_green_run_is_unknown()
    case_green_run_judged_past_the_deadline_is_not_green()
    case_refused_re_list_view_keeps_a_judged_red()
    case_refused_re_list_view_after_a_green_run_is_unknown()
    case_new_runs_on_every_list_are_paced_after_the_at_once_relist()
    case_wait_for_lists_again_until_a_real_run_shows()
    case_wait_for_lists_until_the_deadline_and_no_further()
    case_wait_for_lists_back_off_like_the_status_reads()
    case_lists_paced_takes_one_at_once_relist_per_wait()

    # The repo flag, the no-CI repo, the real alert, and a failed workflow read.
    case_wrong_repo_every_gh_call_names_the_pr_repo()
    case_repo_without_ci_starts_no_watch()
    case_workflows_but_no_run_on_head_still_says_no_run_yet()
    case_failed_workflow_read_is_not_no_workflows()

    # Selector forms that leave the repo blank, and the folder without workflows.
    case_url_selector_pins_pr_repo_on_later_calls()
    case_gh_repo_prefix_pins_pr_repo_on_later_calls()
    case_attached_short_repo_flag_pins_pr_repo_on_later_calls()
    case_equals_short_repo_flag_pins_pr_repo_on_later_calls()
    case_folder_without_workflows_still_watches_the_pr_repo()
    case_exported_gh_repo_names_the_pr_repo()
    case_exported_gh_repo_is_cleared_by_unset_and_empty_export()
    case_gh_repo_values_the_hook_cannot_read_fall_back_to_the_folder()

    # The PR read is REST: the proxy refuses GraphQL.
    case_pr_read_is_rest_for_every_selector()
    case_draft_and_missing_pr_start_no_watch_by_rest()
    case_empty_selector_without_a_branch_is_unknown()
    case_read_pr_maps_rest_fields()
    case_hash_number_selector_reads_the_number_route()

    print()
    print("%d checks, %d failed" % (COUNT[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
