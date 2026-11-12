"""The one home of a `git fetch` that deepens or completes a clone: bin/ci-job, actions/code-check and lint/stale_cites.py call it.
Standard library only. It starts one git process per call and writes nothing but what git itself fetches."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)


def is_shallow(top):
    done = _nowindow.run(["git", "rev-parse", "--is-shallow-repository"], cwd=top, capture_output=True, text=True)
    return done.returncode == 0 and done.stdout.strip() == "true"


def fetch(top, refs=(), unshallow=False, timeout=None):
    """One `git fetch [--unshallow] <remote> [refs...]` in top. The remote is origin, else the first remote.
    Returns (ok, message): message is "" when ok, else the first stderr line that starts `fatal:` or `error:`, else
    the whole short stderr, or why no fetch ran."""
    remotes = (_nowindow.run(["git", "remote"], cwd=top, capture_output=True, text=True).stdout or "").split()
    if not remotes:
        return False, "no remote to fetch from"
    remote = "origin" if "origin" in remotes else remotes[0]
    cmd = ["git", "fetch", *(["--unshallow"] if unshallow else []), remote, *refs]
    try:
        done = _nowindow.run(cmd, cwd=top, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    if done.returncode == 0:
        return True, ""
    return False, failure_message(done.stderr, done.returncode)


def failure_message(stderr, returncode):
    """The line that says why git failed: git's last line is often a hint ("and the repository exists.")."""
    lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
    if not lines:
        return "exit %d, no message" % returncode
    for line in lines:
        if line.startswith(("fatal:", "error:")):
            return line
    return " ".join(lines)
