#!/usr/bin/env python3
"""The one reader of origin/roadmap that fetches a stale ref before it judges. Standard library only.

    fresh_ref(repo_dir, now=None, fetch=None) -> str

Returns "" when the local ref origin/roadmap is fresh or was just fetched, else a note that starts "read as of". The
ref is fresh only when the repo's FETCH_HEAD holds a `branch 'roadmap' of` line (git writes one per fetched branch, so
a fetch of main says nothing about the roadmap), its mtime is within MAX_AGE seconds, and its sha is the tip of the
local ref. A plain `git fetch origin roadmap` in a single-branch clone writes the line and leaves the ref where it was,
so a line that names another commit is stale, and so is a line with no local ref to compare. Anything else is stale
too, and a stale ref gets one `git fetch` of the roadmap branch, bounded at FETCH_TIMEOUT seconds. A fetch that fails,
times out or has no origin gives the note and never raises: the caller reads the ref as it is.

The note is "read as of HH:MM TZ" (US Central, 24 h, with the zone) when the time is known: the time of the last
roadmap fetch (FETCH_HEAD's mtime), else the commit time of the local ref's tip. It is "read as of an unknown time"
when neither is known: the fetch timed out and no roadmap fetch is on record (the tip read is skipped, so a hung git
costs one wait, not two), the ref cannot be read, or git finds no repository in repo_dir (then no fetch starts).
There is no note when there is nothing to be stale about: the local ref does not resolve, no roadmap fetch is on
record, and the fetch says there is no roadmap to fetch (the repo has no remote `origin`, or origin has no `roadmap`
branch: fetch_roadmap returns NO_ROADMAP). An origin that cannot be reached could hold one, so it keeps the note.

Callers: lint/ruled_store.py (read_store), hooks/feedback_guard.py (roadmap_candidates), hooks/sendmessage_state.py
(read_rulings), hooks/override.py (the step grant) and hooks/question_form.py (_read_steps). Step
roadmap-ref-fresh-before-verdict. `fetch(repo_dir, timeout)` is the injected fetch of a test: it returns True when
the ref was fetched, NO_ROADMAP when origin holds no roadmap to fetch, and False or raises when not. No other file in lint/
or hooks/ runs a fetch of the roadmap (lint/test_roadmap_ref.py scans those two folders for one). merge/merge.py also
fetches the roadmap (fetch_branch), outside this helper and outside that scan.

The fetch runs in its own process group, and a timeout kills the whole group, so a transport helper that git started
does not outlive the wait. It reads no stdin, and it never prompts: GIT_TERMINAL_PROMPT=0, GIT_ASKPASS=true and, unless
the caller set GIT_SSH_COMMAND, ssh in BatchMode. Git runs with LC_ALL=C, so the fetch's error text matches
NOTHING_TO_FETCH in any locale.

Cost: a ref with no fresh roadmap line costs one stat and one small read of FETCH_HEAD, and no other process. A fresh
roadmap line adds one `git rev-parse` of the ref's tip, so a fresh ref costs one git start. A repo whose `.git` is
neither a folder nor a `gitdir:` file adds one `git rev-parse` to find FETCH_HEAD. A stale ref adds one `git fetch`,
up to FETCH_TIMEOUT seconds, and, after a failure that was not a timeout and with no fresh roadmap line on record, one
`git log` of the ref's tip. No file is written but the ones git writes (FETCH_HEAD and the ref), no timer, no log.
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
NO_ROADMAP = "no roadmap on origin"  # fetch_roadmap's answer when there is nothing to fetch
# What git (LC_ALL=C) prints when a fetch has nothing to fetch: no remote named origin, or no roadmap branch on it.
NOTHING_TO_FETCH = ("'origin' does not appear to be a git repository", "couldn't find remote ref")
# A git start must read repo_dir, never an outer repo that a hook or CI step points at through these.
STRIPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")


def _env():
    env = {key: value for key, value in os.environ.items() if key not in STRIPPED}
    env["GIT_TERMINAL_PROMPT"] = "0"  # an offline or private origin fails the fetch; it never waits for a password
    env["GIT_ASKPASS"] = "true"  # the no-op program: a credential helper that would ask gets an empty answer
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")  # ssh fails at once instead of asking for a passphrase
    env["LC_ALL"] = "C"  # git's error text in English, so NOTHING_TO_FETCH matches in any locale
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
    """(exit code, stderr text) of argv run in its own process group, stdin /dev/null. A timeout kills the group and
    raises subprocess.TimeoutExpired."""
    group = {"start_new_session": True} if os.name == "posix" else {}
    proc = _nowindow.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(),
                           **group)
    try:
        _out, err = proc.communicate(timeout=timeout)
        return proc.returncode, (err or b"").decode("utf-8", "replace")
    finally:
        if proc.poll() is None:
            _kill_group(proc)


def fetch_roadmap(repo_dir, timeout):
    """The one fetch of the roadmap branch. True when git fetched it; NO_ROADMAP when git says there is nothing to
    fetch (NOTHING_TO_FETCH); False when git failed otherwise. A timeout raises.
    Git truncates FETCH_HEAD before it connects, so a failed fetch would leave an empty one, fresh by mtime. A failed
    or timed-out fetch puts FETCH_HEAD back as it was, so it keeps the time and the branches of the last good fetch."""
    path = _fetch_head(repo_dir)
    before = _snapshot(path)
    fetched = False
    try:
        # "+" makes the refspec the default remote-tracking one: a rewritten roadmap branch still updates the ref.
        code, err = _run_group(["git", "-C", repo_dir, "fetch", "--quiet", "origin",
                                "+roadmap:refs/remotes/origin/roadmap"], timeout)
        fetched = code == 0
        if not fetched and any(text in err for text in NOTHING_TO_FETCH):
            return NO_ROADMAP
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


def _roadmap_fetch(path):
    """(mtime, sha) of FETCH_HEAD's roadmap line, or None: a missing file and a fetch of other branches alone say
    nothing about the roadmap ref."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if ROADMAP_LINE in line:
                    return os.stat(path).st_mtime, line.split("\t", 1)[0].strip()
    except (OSError, TypeError):
        pass
    return None


def _ref_tip(repo_dir):
    """The sha the local roadmap ref names, or None when it does not resolve or git cannot be read."""
    try:
        done = _run_git(repo_dir, ["rev-parse", "--verify", "--quiet", REF], FETCH_TIMEOUT)
        return done.stdout.strip() or None if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
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
        line = _roadmap_fetch(head)
        last = line[0] if line else None
        if line and now - last <= MAX_AGE:
            if line[1] == _ref_tip(repo_dir):
                return ""
            last = None  # the line is recent, but the ref is not at it: only the ref's own commit time says how old it is
        timed_out = nothing = False
        try:
            fetched = (fetch or fetch_roadmap)(repo_dir, FETCH_TIMEOUT)
            nothing = fetched == NO_ROADMAP
            if fetched and not nothing:
                return ""
        except subprocess.TimeoutExpired:
            timed_out = True
        except Exception:  # a missing git, an injected failure: the note says so
            pass
        if last is None and not timed_out:
            last = _tip_time(repo_dir)
            if last is None and nothing:
                return ""  # no ref, no roadmap fetch on record, and origin holds none: nothing to be stale about
        return _note(last)
    except Exception:
        return UNKNOWN
