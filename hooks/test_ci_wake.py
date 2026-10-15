#!/usr/bin/env python3
"""Cases for hooks/ci_wake.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_ci_wake.py

The hook is a PostToolUse command hook for the Bash and PowerShell tools, registered with
`asyncRewake: true`. Claude Code runs it in the background. Exit 2 wakes the session, and its
stderr shows as a system reminder. Every case runs the real hook as a subprocess, with the hook
JSON on stdin and its stdout and stderr written to files. No case imports the module.

Decision, from decision handoff-hooks-wave-2, part 3 (CI wake-up):
- Only `gh pr ready <N>` starts a watch. A `git push` in any form starts none, and makes no gh call.
- Each `gh pr ready` in one command gets its own watch, in one process. The hook prints one
  verdict line per PR, then exits 2 once.
- Text inside quotes, inside a heredoc body, or after an unquoted `#` is no command. A lone quote
  in earlier text does not hide a later `gh pr ready`. A `#` inside quotes is no comment.
- The watch has its own deadline. A run still pending at the deadline wakes with exit 2 and a
  "still running" line. It does not wait for the run to end.
- One watcher runs per PR. A second watcher for the same PR exits 0 with no output and no watch.
  A killed watcher, or a finished one, releases the PR.
- Any uncaught error exits 2 with one "unknown" line, never exit 1.

Verdict line, exit 2: `CI <green|red|cancelled> on <sha7>: <failing job names>`.
A cancelled run beside a run of the same name that ran, on the same head, reads as the ran one,
in either list order, completed or in progress (decision merge-needs-a-proven-head). A cancelled
run with no such twin reads cancelled.
Unreadable gh: gh not on PATH, exit non-zero, or output that is not JSON. For a `gh pr ready`
that could start a watch, exit 2 with one line `CI unknown on <sha>: <reason>`. Never a silent exit 0.

Seams under test (the builder must read these names):
- CI_WAKE_MODULE: the module under test (default hooks/ci_wake.py beside this file).
- CI_WAKE_LOCK_DIR: the folder that holds the per-PR watch locks. Each case sets its own.
- CI_WAKE_DEADLINE: the watch budget in seconds. Unset, the hook uses its own default.

The gh stub: a `gh` launcher in a temp folder, the only PATH entry for these cases, so no real gh
is ever reached. On Windows the launcher is `gh.cmd`, and a list-form subprocess call of "gh"
skips a .cmd stand-in (decision list-form-subprocess-ignores-a-path-shim-on-windows). So the hook
must find gh with shutil.which. The stub answers the --json forms of `pr view <N|branch>`,
`pr list --head B`, `run list --commit SHA`, `run view <id>` and `run watch <id>` from a JSON
fixture. It writes every call to its own file beside the log (one file per call, so parallel calls never share one). A run marked in_progress_until_watch stays in progress
until `run watch` names it. A run with hang_seconds: `run watch` first connects to the localhost
port in GH_STUB_READY_PORT, so a case can wait for the watch with one accept() and no polling.
Then the stub closes fds 0-2 and sleeps, which models a run still pending. Fixture mode "error"
makes every call fail with exit 1. Mode "garbage" makes every call print non-JSON with exit 0.

Scratch files live in one temp directory, removed at exit.
"""

import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
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

def logged_calls():
    return read_log(os.environ["GH_STUB_LOG"])

def view(r, watched, with_jobs):
    hidden = bool(r.get("in_progress_until_watch")) and str(r["databaseId"]) not in watched
    out = {"databaseId": r["databaseId"], "name": r["name"], "workflowName": r["workflowName"],
           "headSha": r["headSha"], "event": r["event"],
           "status": "in_progress" if hidden else r["status"],
           "conclusion": None if hidden else r["conclusion"]}
    if with_jobs:
        out["jobs"] = [] if hidden else r["jobs"]
    return out

def ready_ping():
    port = os.environ.get("GH_STUB_READY_PORT")
    if port:
        socket.create_connection(("127.0.0.1", int(port)), timeout=10).close()

def hang(seconds):
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    time.sleep(seconds)

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
        ready_ping()
        if r.get("hang_seconds"):
            hang(r["hang_seconds"])
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


def pr(number, draft=False, branch="hook-wave-2", sha=SHA):
    return {"number": number, "isDraft": draft, "headRefName": branch, "headRefOid": sha,
            "state": "OPEN", "url": "https://github.com/shivinate7/claude-settings/pull/%d" % number}


def job(name, conclusion):
    return {"name": name, "conclusion": conclusion, "status": "completed"}


def run(run_id, name, conclusion, jobs, in_progress_until_watch=False, sha=SHA,
        status="completed", hang=0):
    out = {"databaseId": run_id, "name": name, "workflowName": name, "headSha": sha,
           "event": "pull_request", "status": status, "conclusion": conclusion,
           "jobs": jobs, "in_progress_until_watch": in_progress_until_watch}
    if hang:
        out["hang_seconds"] = hang
    return out


def fixture(prs=(), runs=(), mode="ok"):
    return {"mode": mode, "prs": list(prs), "runs": list(runs)}


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def powershell(command):
    return {"tool_name": "PowerShell", "tool_input": {"command": command}}


READY = [pr(12)]
TWO_PRS = [pr(12), pr(13, branch="second-branch", sha=SHA_B)]
GREEN = run(901, "gates", "success", [job("lint", "success"), job("unit", "success")])
RED = run(902, "gates", "failure",
          [job("lint", "success"), job("unit", "failure"), job("e2e", "failure")])
RED_B = run(911, "gates", "failure", [job("unit", "failure")], sha=SHA_B)
CANCEL_903 = run(903, "gates", "cancelled", [job("unit", "cancelled")])
RAN_904 = run(904, "gates", "success", [job("unit", "success")])
CANCEL_905 = run(905, "gates", "cancelled", [job("unit", "cancelled")])
INPROG_906 = run(906, "gates", "success", [job("unit", "success")], in_progress_until_watch=True)
INPROG_907 = run(907, "codeql", "success", [job("scan", "success")], in_progress_until_watch=True)
PENDING = run(908, "gates", None, [], status="in_progress", hang=10)  # still running at 10 s
HOLD = run(909, "gates", "success", [job("unit", "success")], hang=15)  # a watch that stays live

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
           if k.upper() != "PATH" and not k.startswith("CI_WAKE_")}
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
    return [c[2] for c in res.calls if c[:2] == ["run", "watch"] and len(c) > 2]


def count(res, *prefix):
    return sum(1 for c in res.calls if c[:len(prefix)] == list(prefix))


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
    check("%s: no run watch" % label, watched(res) == [], why(res))


def expect_no_gh(label, res):
    check("%s: no gh call" % label, res.calls == [], why(res))


def expect_watch(label, res, ids):
    """One blocking watch per run, and the run list read once (no polling)."""
    check("%s: watches %s once each, runs listed once" % (label, ids),
          sorted(watched(res)) == sorted(ids) and count(res, "run", "list") <= 1, why(res))


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
    releases PR 12. The handshake is one accept() on a localhost port the stub connects to."""
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
        check("first watcher reached its blocking run watch (handshake within 20 s)", reached,
              "no connection from the stub")
        if reached:
            second = run_hook(bash("gh pr ready 12"), fixture(READY, [GREEN]), lock=lock)
            check("second watcher for PR 12 while the first is live: exit 0, no output",
                  second.rc == 0 and not second.hung and second.lines == [], why(second))
            check("second watcher for PR 12 while the first is live: no run watch, exits at once",
                  watched(second) == [] and second.elapsed < 5, why(second))
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
    skipped = run(910, "gates", "skipped", [job("unit", "skipped")])
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
    """stderr whose flush raises. The final flush sits outside the try today. It must end in a
    wake with an unknown line, not a crash."""
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
    check("gh pr ready 12 & gh pr ready 13: watches runs 901 and 911, one each",
          sorted(watched(res)) == ["901", "911"], why(res))
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

    # Two gh pr ready calls in one command: one process, one verdict line per PR, one wake.
    res = run_hook(bash("gh pr ready 12 && gh pr ready 13"), fixture(TWO_PRS, [GREEN, RED_B]))
    vs = verdicts_of(res)
    check("gh pr ready 12 && gh pr ready 13: one process, two CI lines, exit 2",
          res.rc == 2 and not res.hung and vs is not None and len(vs) == 2, why(res))
    check("gh pr ready 12 && gh pr ready 13: one line per PR (12 green on sha7, 13 red on sha7)",
          vs is not None and sorted((v[0], v[1]) for v in vs) == sorted([("green", SHA7), ("red", SHA7_B)]),
          why(res))
    check("gh pr ready 12 && gh pr ready 13: watches runs 901 and 911, one each",
          sorted(watched(res)) == ["901", "911"], why(res))
    check("gh pr ready 12 && gh pr ready 13: run list read at most twice",
          count(res, "run", "list") <= 2, why(res))

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

    res = run_hook(bash("git push origin hook-wave-2"), fixture([pr(12, draft=True)], [GREEN]))
    expect_silent("git push, only a draft PR", res)
    expect_no_watch("git push, only a draft PR", res)
    expect_no_gh("git push, only a draft PR", res)

    res = run_hook(bash("git push origin hook-wave-2"), fixture([pr(12, branch="other-branch")], [GREEN]))
    expect_silent("git push, no PR for this branch (a ready PR on another branch)", res)
    expect_no_watch("git push, no PR for this branch", res)
    expect_no_gh("git push, no PR for this branch", res)

    res = run_hook(bash("git push origin hook-wave-2"), fixture([], [GREEN]))
    expect_silent("git push, no PR at all", res)
    expect_no_watch("git push, no PR at all", res)
    expect_no_gh("git push, no PR at all", res)

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
    expect_silent("non-Bash, non-PowerShell tool carrying a trigger command", res)
    expect_no_watch("non-Bash, non-PowerShell tool carrying a trigger command", res)

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
          and sorted(watched(res)) == ["911"], why(res))

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

    res = run_hook(bash("gh pr ready 12"), fixture(READY, [INPROG_906, INPROG_907]))
    expect_verdict("two in-progress runs, both waited on", res, "green")
    expect_watch("two in-progress runs", res, ["906", "907"])

    # Own deadline: a run still pending at the deadline wakes with a still-running line.
    res = run_hook(bash("gh pr ready 12"), fixture(READY, [PENDING]), extra={"CI_WAKE_DEADLINE": "1"})
    v = verdict_of(res)
    check("deadline 1 s, run still pending: exit 2, one unknown line with sha7 and 'still running'",
          res.rc == 2 and not res.hung and v is not None and v[0] == "unknown" and v[1] == SHA7
          and "still running" in v[2], why(res))
    check("deadline 1 s, run still pending: wakes at its deadline, not when the run ends (under 6 s)",
          not res.hung and res.elapsed < 6, "elapsed=%.1f s; the run ends at 10 s" % res.elapsed)

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

    # Review round 2: skipped-only head, draft PR, import and flush errors, separators, low items.
    case_skipped_only_head_is_no_run_yet()
    case_draft_pr_starts_no_watch()
    case_import_error_wakes_unknown()
    case_final_flush_error_wakes_unknown()
    case_background_separator_starts_each_watch()
    case_lock_folder_unusable_wakes_unknown()

    print()
    print("%d checks, %d failed" % (COUNT[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
