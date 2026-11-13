#!/usr/bin/env python3
"""The one reader of origin/roadmap that fetches a stale ref before it judges. Standard library only.

    fresh_ref(repo_dir, now=None, fetch=None) -> str

Returns "" when the local ref origin/roadmap is fresh or was just fetched, else a note that starts "read as of". The
ref is fresh only when the repo's FETCH_HEAD holds a `branch 'roadmap' of` line (git writes one per fetched branch, so
a fetch of main says nothing about the roadmap) and its mtime is within MAX_AGE seconds. Anything else is stale, and a
stale ref gets one `git fetch` of the roadmap branch, bounded at FETCH_TIMEOUT seconds. A fetch that fails, times out
or has no origin gives the note and never raises: the caller reads the ref as it is.

The note is "read as of HH:MM TZ" (US Central, 24 h, with the zone) when the time is known: the time of the last
roadmap fetch (FETCH_HEAD's mtime), else the commit time of the local ref's tip. It is "read as of an unknown time"
when neither is known: the fetch timed out and no roadmap fetch is on record (the tip read is skipped, so a hung git
costs one wait, not two), the ref cannot be read, or git finds no repository in repo_dir (then no fetch starts).

Callers: lint/ruled_store.py (read_store), hooks/feedback_guard.py (roadmap_candidates), hooks/sendmessage_state.py
(read_rulings), hooks/override.py (the step grant) and hooks/question_form.py (_read_steps). Step
roadmap-ref-fresh-before-verdict. `fetch(repo_dir, timeout)` is the injected fetch of a test: it returns True when
the ref was fetched, and False or raises when not. No other file runs a fetch of the roadmap
(lint/test_roadmap_ref.py scans for one).

The fetch runs in its own process group, and a timeout kills the whole group, so a transport helper that git started
does not outlive the wait. It reads no stdin, and it never prompts: GIT_TERMINAL_PROMPT=0, GIT_ASKPASS=true and, unless
the caller set GIT_SSH_COMMAND, ssh in BatchMode.

Cost: a fresh ref costs one stat and one small read of FETCH_HEAD, and no process. A repo whose `.git` is neither a
folder nor a `gitdir:` file adds one `git rev-parse` to find FETCH_HEAD. A stale ref adds one `git fetch`, up to
FETCH_TIMEOUT seconds, and, after a failure that was not a timeout and with no roadmap fetch on record, one `git log`
of the ref's tip. No file is written but the ones git writes (FETCH_HEAD and the ref), no timer, no log.
"""
import os
import signal
import subprocess
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
ROADMAP_LINE = "branch 'roadmap' of"  # what git writes in FETCH_HEAD for a fetched roadmap branch
UNKNOWN = "read as of an unknown time"
# A git start must read repo_dir, never an outer repo that a hook or CI step points at through these.
STRIPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")


def _env():
    env = {key: value for key, value in os.environ.items() if key not in STRIPPED}
    env["GIT_TERMINAL_PROMPT"] = "0"  # an offline or private origin fails the fetch; it never waits for a password
    env["GIT_ASKPASS"] = "true"  # the no-op program: a credential helper that would ask gets an empty answer
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")  # ssh fails at once instead of asking for a passphrase
    return env


def _run_git(repo_dir, args, timeout):
    return _nowindow.run(["git", "-C", repo_dir] + list(args), capture_output=True, text=True, env=_env(),
                         stdin=subprocess.DEVNULL, timeout=timeout)


def _kill_group(proc):
    """Kills the fetch child and every process in its group (POSIX: the child leads its own session), then reaps it."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        proc.kill()
    except (OSError, ValueError):
        pass
    try:
        proc.communicate(timeout=1)
    except (subprocess.SubprocessError, OSError, ValueError):
        pass


def _run_group(argv, timeout):
    """The exit code of argv run in its own process group, stdin /dev/null. A timeout kills the group and raises
    subprocess.TimeoutExpired."""
    group = {"start_new_session": True} if os.name == "posix" else {}
    proc = _nowindow.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(),
                           **group)
    try:
        proc.communicate(timeout=timeout)
        return proc.returncode
    finally:
        if proc.poll() is None:
            _kill_group(proc)


def fetch_roadmap(repo_dir, timeout):
    """The one fetch of the roadmap branch. True when git fetched it; False when git failed. A timeout raises.
    Git truncates FETCH_HEAD before it connects, so a failed fetch would leave an empty one, fresh by mtime. A failed
    or timed-out fetch puts FETCH_HEAD back as it was, so it keeps the time and the branches of the last good fetch."""
    path = _fetch_head(repo_dir)
    before = _snapshot(path)
    fetched = False
    try:
        # "+" makes the refspec the default remote-tracking one: a rewritten roadmap branch still updates the ref.
        code = _run_group(["git", "-C", repo_dir, "fetch", "--quiet", "origin", "+roadmap:refs/remotes/origin/roadmap"],
                          timeout)
        fetched = code == 0
        return fetched
    finally:
        if not fetched and path:
            _restore(path, before)


def _snapshot(path):
    """(bytes, mtime) of FETCH_HEAD, or None when it is missing."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        return data, os.stat(path).st_mtime
    except (OSError, TypeError):
        return None


def _restore(path, before):
    try:
        if before is None:
            os.remove(path)
        else:
            with open(path, "wb") as f:
                f.write(before[0])
            os.utime(path, (before[1], before[1]))
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


def _roadmap_fetched_at(path):
    """FETCH_HEAD's mtime when it holds a roadmap line, else None: a missing file and a fetch of other branches alone
    say nothing about the roadmap ref."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            if ROADMAP_LINE not in f.read():
                return None
        return os.stat(path).st_mtime
    except (OSError, TypeError):
        return None


def _tip_time(repo_dir):
    """The commit time of the local roadmap ref: the best "as of" when no roadmap fetch is on record. None when unreadable."""
    try:
        done = _run_git(repo_dir, ["log", "-1", "--format=%ct", REF], FETCH_TIMEOUT)
        return float(done.stdout.strip()) if done.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _note(when):
    if when is None:
        return UNKNOWN
    return "read as of " + (local_time.central_hhmm(datetime.fromtimestamp(when, timezone.utc)) or "an unknown time")


def fresh_ref(repo_dir, now=None, fetch=None):
    """"" when origin/roadmap in repo_dir is fresh or was just fetched, else "read as of HH:MM TZ" or "read as of an
    unknown time". Never raises."""
    try:
        now = time.time() if now is None else now
        head = _fetch_head(repo_dir)
        if head is None:
            return UNKNOWN  # git finds no repository here, so there is no ref to fetch into
        last = _roadmap_fetched_at(head)
        if last is not None and now - last <= MAX_AGE:
            return ""
        timed_out = False
        try:
            if (fetch or fetch_roadmap)(repo_dir, FETCH_TIMEOUT):
                return ""
        except subprocess.TimeoutExpired:
            timed_out = True
        except Exception:  # a missing git, an injected failure: the note says so
            pass
        if last is None and not timed_out:
            last = _tip_time(repo_dir)
        return _note(last)
    except Exception:
        return UNKNOWN
