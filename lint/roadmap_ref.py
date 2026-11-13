#!/usr/bin/env python3
"""The one reader of origin/roadmap that fetches a stale ref before it judges. Standard library only.

    fresh_ref(repo_dir, now=None, fetch=None) -> str

Returns "" when the local ref origin/roadmap is fresh or was just fetched, else the note "read as of HH:MM TZ" (US
Central, 24 h, with the zone): the time of the last fetch. The ref is stale when the repo's FETCH_HEAD is missing or
older than MAX_AGE seconds. A stale ref gets one `git fetch` of the roadmap branch, bounded at FETCH_TIMEOUT seconds.
A fetch that fails, times out or has no origin gives the note and never raises: the caller reads the ref as it is.

Callers: lint/ruled_store.py (read_store) and hooks/feedback_guard.py (roadmap_candidates). Step
roadmap-ref-fresh-before-verdict. `fetch(repo_dir, timeout)` is the injected fetch of a test: it returns True when
the ref was fetched, and False or raises when not. No other file runs a fetch of the roadmap
(lint/test_roadmap_ref.py scans for one).

Cost: a fresh ref costs one stat of FETCH_HEAD, and no process. A repo whose `.git` is neither a folder nor a
`gitdir:` file adds one `git rev-parse` to find FETCH_HEAD. A stale ref adds one `git fetch`, up to FETCH_TIMEOUT
seconds. No file is written but the one git writes (FETCH_HEAD and the ref), no timer, no log.
"""
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# As in ruled_store: a caller that already put hooks/ on the path keeps its order.
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:
    sys.path.append(os.path.join(HERE, "..", "hooks"))
    import _nowindow  # noqa: E402
import local_time  # noqa: E402  the one home of US Central time

MAX_AGE = 60  # seconds a fetch keeps the ref fresh
FETCH_TIMEOUT = 2.0  # seconds one fetch may run
REF = "refs/remotes/origin/roadmap"
# A git start must read repo_dir, never an outer repo that a hook or CI step points at through these.
STRIPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")


def _env():
    env = {key: value for key, value in os.environ.items() if key not in STRIPPED}
    env["GIT_TERMINAL_PROMPT"] = "0"  # an offline or private origin fails the fetch; it never waits for a password
    return env


def _run_git(repo_dir, args, timeout):
    return _nowindow.run(["git", "-C", repo_dir] + list(args), capture_output=True, text=True, env=_env(),
                         timeout=timeout)


def fetch_roadmap(repo_dir, timeout):
    """The one fetch of the roadmap branch. True when git fetched it; False when git failed. A timeout raises.
    Git opens FETCH_HEAD before it connects, so a failed fetch would leave a fresh FETCH_HEAD and the next read would
    take an unfetched ref for a fresh one. A failed fetch puts FETCH_HEAD's mtime back, and FETCH_HEAD's mtime stays the
    time of the last good fetch."""
    path = _fetch_head(repo_dir)
    before = _mtime(path)
    fetched = False
    try:
        # "+" makes the refspec the default remote-tracking one: a rewritten roadmap branch still updates the ref.
        done = _run_git(repo_dir, ["fetch", "--quiet", "origin", "+roadmap:refs/remotes/origin/roadmap"], timeout)
        fetched = done.returncode == 0
        return fetched
    finally:
        if not fetched and path:
            _restore_mtime(path, before)


def _restore_mtime(path, before):
    try:
        if before is None:
            os.remove(path)
        elif _mtime(path) != before:
            os.utime(path, (before, before))
    except OSError:
        pass


def _fetch_head(repo_dir):
    """The path of repo_dir's FETCH_HEAD, read from `.git` with no process when `.git` is a folder or a `gitdir:` file."""
    dot_git = os.path.join(repo_dir, ".git")
    if os.path.isdir(dot_git):
        return os.path.join(dot_git, "FETCH_HEAD")
    try:
        with open(dot_git, encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("gitdir:"):
            return os.path.join(repo_dir, first[len("gitdir:"):].strip(), "FETCH_HEAD")
    except (OSError, UnicodeDecodeError):
        pass
    done = _run_git(repo_dir, ["rev-parse", "--git-path", "FETCH_HEAD"], FETCH_TIMEOUT)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    return os.path.join(repo_dir, done.stdout.strip())


def _mtime(path):
    try:
        return os.stat(path).st_mtime if path else None
    except OSError:
        return None


def _tip_time(repo_dir):
    """The commit time of the local roadmap ref: the best "as of" when no fetch ever wrote FETCH_HEAD. None when unreadable."""
    try:
        done = _run_git(repo_dir, ["log", "-1", "--format=%ct", REF], FETCH_TIMEOUT)
        return float(done.stdout.strip()) if done.returncode == 0 else None
    except (OSError, ValueError, _nowindow.subprocess.SubprocessError):
        return None


def _note(when):
    if when is None:
        return "read as of an unknown time"
    return "read as of " + local_time.central_hhmm(datetime.fromtimestamp(when, timezone.utc))


def fresh_ref(repo_dir, now=None, fetch=None):
    """"" when origin/roadmap in repo_dir is fresh or was just fetched, else "read as of HH:MM TZ". Never raises."""
    try:
        now = time.time() if now is None else now
        last = _mtime(_fetch_head(repo_dir))
        if last is not None and now - last <= MAX_AGE:
            return ""
        try:
            if (fetch or fetch_roadmap)(repo_dir, FETCH_TIMEOUT):
                return ""
        except Exception:  # a timeout, a missing git, an injected failure: the note says so
            pass
        return _note(last if last is not None else _tip_time(repo_dir))
    except Exception:
        return "read as of an unknown time"
