#!/usr/bin/env python3
"""Wake the session when CI ends on a PR it marked ready: after `gh pr ready <N>`, wait on that
head's runs and print one line with the result. Standard library only. See
decisions/handoff-hooks-wave-2.md, part 3.

PostToolUse hook for the Bash and PowerShell tools, registered with `asyncRewake: true`. Only
`gh pr ready <N>` starts a watch, and each one in a command gets its own, in this one process.
A push starts none. Per PR it reads the head once. It lists that head's runs until a run that
ran has ended (a skipped draft run is no run), waits on it, and prints one line:

    CI <green|red|cancelled> on <sha7>: <failing job names>
    CI unknown on <sha7 or PR>: <reason>        (also "still running" at the deadline)

Then it exits 2 once, which wakes the session. It prints nothing and exits 0 when no watch starts,
or when another watcher already holds every PR it would watch. Any error exits 2 with an unknown
line, never 1. It reads GitHub at most once per 30 s per run, and never loops on a red run.

Seams: CI_WAKE_DEADLINE, the watch budget in seconds (default DEFAULT_DEADLINE, under the hook
timeout in settings.json). CI_WAKE_LOCK_DIR, the folder of the per-PR lock files.
The cancelled-twin rule is merge.py's `Host.judge_runs`, loaded through guard_merge.merge_module.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# The sibling modules (guard_core, guard_env, guard_merge) load inside main(), so a failed import
# ends in an unknown line, never a traceback and exit 1.

DEFAULT_DEADLINE = 3300   # seconds; the hook timeout in settings.json is 3600
STATUS_PAUSE = 30         # seconds between two status reads of one run
READ_TIMEOUT = 60         # seconds for each gh read
PR_FIELDS = "number,isDraft,headRefName,headRefOid,state,url"
RUN_FIELDS = "databaseId,name,status,conclusion,workflowName,headSha,event"
GOOD = ("success", "skipped", "neutral")
REPO_FLAGS = ("-R", "--repo")
# A word-internal apostrophe (don't) opens no quote. Masked here, so split_segments does not read it as one.
APOSTROPHE = re.compile(r"(?<=[A-Za-z])'(?=[A-Za-z])")
HELD = []   # open lock files, kept until the process ends: the OS drops the locks then, kill included


class Unknown(Exception):
    """A read that could not run. The message is the reason."""


class NoPR(Exception):
    """The number names no pull request: no watch, not an unknown."""


def emit(lines):
    if not lines:
        return 0
    try:
        sys.stderr.buffer.write("".join(" ".join(x.split())[:300] + "\n" for x in lines).encode("utf-8", "replace"))
        sys.stderr.buffer.flush()
    except Exception:
        pass
    return 2


def gh(args, cwd, timeout=READ_TIMEOUT):
    """-> (rc, stdout, stderr). gh is found with shutil.which: a list-form call of a bare "gh"
    misses a .cmd launcher on Windows. A timeout kills gh and never waits on its pipes."""
    exe = shutil.which("gh")
    if exe is None:
        raise Unknown("gh is not on PATH")
    try:
        p = subprocess.Popen([exe, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=cwd)
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        raise Unknown("gh %s timed out" % " ".join(args[:2]))
    except OSError as e:
        raise Unknown("gh %s failed: %s" % (" ".join(args[:2]), type(e).__name__))
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def gh_json(args, cwd):
    rc, out, err = gh(args, cwd)
    if rc != 0:
        if "no pull requests found" in (out + err).lower():
            raise NoPR()
        raise Unknown("gh %s exited %d: %s" % (" ".join(args[:2]), rc, (err or out).strip()))
    try:
        return json.loads(out)
    except ValueError:
        raise Unknown("gh %s printed non-JSON" % " ".join(args[:2]))


def watch_run(run_id, cwd, deadline):
    """Read `gh run view <id> --json status` until the status is `completed` or the deadline
    passes. Reads are at least STATUS_PAUSE seconds apart, and the last pause ends at the
    deadline. No `gh run watch` (decision ci-wait-reads-run-status). A failed or non-JSON read
    raises Unknown."""
    while deadline - time.monotonic() > 0:  # at or past the deadline: no read, no pause
        if gh_json(["run", "view", str(run_id), "--json", "status"], cwd).get("status") == "completed":
            return
        left = deadline - time.monotonic()
        if left <= STATUS_PAUSE:  # the last pause is clamped to the deadline, and the wait ends there
            time.sleep(max(0, left))
            return
        time.sleep(STATUS_PAUSE)


def ready_call(rest):
    """-> (selector, repo) for the args of a `gh pr ready` call, else None."""
    if rest[:2] != ["pr", "ready"] or any(a in ("--undo", "-h", "--help") for a in rest):
        return None
    pos, repo, i = [], "", 2
    while i < len(rest):
        a = rest[i]
        if a in REPO_FLAGS and i + 1 < len(rest):
            repo, i = rest[i + 1], i + 1
        elif a.startswith("--repo="):
            repo = a[7:]
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    return (pos[0] if pos else ""), repo


def triggers(command, powershell):
    """-> [(selector, repo)], one per `gh pr ready` in the command. Reads the text only. A heredoc
    body, quoted text and text after `#` is no command (split_segments drops comments and keeps
    quotes whole); a lone apostrophe in a word opens no quote. A lone `&` ends a command too
    (guard_env's quote-aware split); the `&` of `2>&1` leaves the call whole."""
    import guard_core
    from guard_env import _ampersand_split
    from guard_merge import gh_call_of
    guard_core.POWERSHELL_CALL[0] = powershell
    text = APOSTROPHE.sub("\x01", guard_core.strip_heredoc_bodies(command))
    found = []
    for segment in (p for s in guard_core.split_segments(text) for p in _ampersand_split(s)):
        rest = gh_call_of(segment)
        call = ready_call(rest) if rest is not None else None
        if call:
            found.append(call)
    return found


def lock_pr(pr, lock_dir):
    """Take the one lock of this PR for the life of the process. False when another watcher holds it."""
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", str(pr.get("url") or pr["number"]))
    os.makedirs(lock_dir, exist_ok=True)
    fd = os.open(os.path.join(lock_dir, key + ".lock"), os.O_CREAT | os.O_RDWR)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    HELD.append(fd)
    return True


def wait_for(sha, cwd, deadline):
    """List the head's runs, watch each one (not a cancelled twin), then read each with its jobs.
    A run that ends skipped is no run: the draft PR's run skips, and the run of `gh pr ready`
    comes after it. While no run that ran is judged, list again, STATUS_PAUSE apart; the last
    pause ends at the deadline, with one list there. Once a run that ran is judged, return it:
    later runs are not waited on (debt ci-wake-lists-runs-once)."""
    list_args = ["run", "list", "--commit", sha, "--limit", "100", "--json", RUN_FIELDS]
    while True:
        runs = [r for r in gh_json(list_args, cwd) if r["conclusion"] != "skipped"]
        live = {r["name"] for r in runs if r["conclusion"] != "cancelled"}
        for r in runs:
            if r["conclusion"] == "cancelled" and r["name"] in live:
                continue   # a cancelled twin: judge_runs reads the run that ran
            watch_run(r["databaseId"], cwd, deadline)
        viewed = [gh_json(["run", "view", str(r["databaseId"]), "--json", "databaseId,name,status,conclusion,jobs"], cwd)
                  for r in runs]
        viewed = [r for r in viewed if r.get("conclusion") != "skipped"]   # it ended skipped: no run
        if viewed:
            return viewed
        left = deadline - time.monotonic()
        if left <= 0:
            raise Unknown("no run yet")
        time.sleep(min(STATUS_PAUSE, left))


def verdict(sha, runs):
    from guard_merge import merge_module
    merge = merge_module()
    if merge is None:
        raise Unknown("the merge tool (judge_runs) could not be loaded")
    red, pending = merge.Host.judge_runs(runs)
    if pending:
        raise Unknown("still running: " + ", ".join(pending))
    if not red:
        return "CI green on %s: no failing jobs" % sha[:7]
    names, cancelled = [], True
    for text in red:
        run = next((r for r in runs if text.startswith("workflow %s: " % r["name"])), None)
        if run is None:
            names.append(text)
            cancelled = False
            continue
        cancelled = cancelled and run["conclusion"] == "cancelled"
        jobs = [j["name"] for j in run.get("jobs") or [] if j.get("conclusion") not in GOOD]
        names.extend(jobs or ["workflow " + run["name"]])
    return "CI %s on %s: %s" % ("cancelled" if cancelled else "red", sha[:7], ", ".join(dict.fromkeys(names)))


def watch_pr(selector, repo, cwd, deadline, lock_dir):
    """-> one output line, or None when no watch starts."""
    ident = "PR" + selector if selector else "PR"
    try:
        extra = ["-R", repo] if repo else []
        pr = gh_json(["pr", "view", *([selector] if selector else []), *extra, "--json", PR_FIELDS], cwd)
        ident = pr["headRefOid"][:7]
        if pr.get("isDraft"):
            return None   # gh pr ready did not take: a draft runs no CI
        if not lock_pr(pr, lock_dir):
            return None
        return verdict(pr["headRefOid"], wait_for(pr["headRefOid"], cwd, deadline))
    except NoPR:
        return None
    except Unknown as e:
        return "CI unknown on %s: %s" % (ident, e)
    except Exception as e:
        return "CI unknown on %s: %s: %s" % (ident, type(e).__name__, e)


def main():
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = data["tool_input"]["command"]
    if "ready" not in command.lower():
        return 0   # no `gh pr ready` can hide here: no import, so a broken install wakes no `ls`
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and os.path.isdir(data["cwd"]) else None
    calls = triggers(command, data["tool_name"] == "PowerShell")
    if not calls:
        return 0
    try:
        budget = float(os.environ.get("CI_WAKE_DEADLINE") or DEFAULT_DEADLINE)
    except ValueError:
        budget = DEFAULT_DEADLINE
    deadline = time.monotonic() + budget
    lock_dir = os.environ.get("CI_WAKE_LOCK_DIR") or os.path.join(tempfile.gettempdir(), "ci-wake-locks")
    from guard_merge import merge_module
    merge_module()   # load once here, before the threads
    lines = [None] * len(calls)

    def work(i, selector, repo):
        lines[i] = watch_pr(selector, repo, cwd, deadline, lock_dir)

    threads = [threading.Thread(target=work, args=(i, *call), daemon=True) for i, call in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return emit([x for x in lines if x])


if __name__ == "__main__":
    try:
        code = main()
        if code:
            sys.stderr.flush()   # only after a write: a broken stderr must not wake a silent run
    except BaseException as e:   # never exit 1: an unread CI is an unknown, not a silent failure
        code = emit(["CI unknown on ?: %s: %s" % (type(e).__name__, e)])
    os._exit(code)   # a daemon thread or a killed gh child must not hold the process open
