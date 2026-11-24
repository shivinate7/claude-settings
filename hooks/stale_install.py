#!/usr/bin/env python3
"""UserPromptSubmit hook: reinstall the hooks when the local origin ref moved past the installed sha, and say so.

A cloud session copies hooks at start, so a hook merged later stays stale for the whole session. A prompt reads no
origin (decision stale-install-cost). It reads the install record that install.sh --cloud
writes (<config dir>/.claude-settings-install.json: ref, sha, source, installer) and compares it with the local
refs/remotes/origin/<record ref> of the record's source clone. A pin with no such ref reads local main, the commit
install_from_main.sh pins to then. It acts on one trigger only: the local ref names a
commit the record's sha does not cover (a session start, a resume or a fetch moved it). A commit the record's sha
already contains is no trigger. With no trigger a prompt prints nothing and runs no installer.
A record, a source or a local ref that cannot be read prints one "install freshness unknown (reason)" line and
installs nothing. Unknown is never reported as current.
- source on a branch (a checkout or a mirror): runs the recorded installer once (`install.sh --cloud`), then reads
  the record again. A record now at the target prints one line naming both 7-character shas. A record still at another
  sha prints "reinstall did not reach <target> (record at <sha>)", never "reinstalled". A second line follows when a
  changed path needs a new session to read it again: CLAUDE.md, output-styles/, and the settings.json keys model and
  effortLevel. An installer that exits non-zero prints "reinstall failed (exit N)" and is not retried for that head. An
  installer past its timeout gets SIGTERM, so install.sh's EXIT trap releases its lock, then SIGKILL after a short
  wait; it prints "reinstall failed (timed out after N s)".
- source on a detached HEAD, the live pin, that holds merge/install_from_main.sh: runs it once per new head and prints
  one line that states how many commits the pin is behind the ref it read, counted from local objects.
  A refresh runs once per head, whatever its outcome, and the head is marked once the refresh has ended. A later prompt
  on a head the record still does not cover prints "install still stale", and runs nothing. While another install holds
  the install lock (a fresh <config dir>/.claude-settings-install.lock), the pin refresh prints nothing, runs nothing and
  leaves the head unseen: a later prompt checks again. A refresh that timed out behind that lock acts the same.
- the clone the config dir's CLAUDE.md points at (an @path line), when its HEAD is behind its own local origin ref:
  one line that names the clone and its commits behind, once per new head.
A local session (CLAUDE_CODE_REMOTE not "true": a Mac or a Windows machine) acts on the live pin only. install.sh
writes a record only with --cloud, so a local session has none. With none, the hook finds the pin from where its own
file lives (<clone>-live, or the <clone>-live-<12 hex> worktree it links to) and treats the pin's HEAD as the record:
ref stable, sha the pin's HEAD. A hook that lives in no pin is silent and makes no git call. The pin refreshes by the
cloud pin's rules: once per new head, from the local origin/stable ref (or local main), through
merge/install_from_main.sh, which moves the pin and reinstalls (on Windows it hands off to install.ps1). A local
session never runs `install.sh --cloud`, and never reinstalls a source that is not a pin. A record that exists in a
local session is read as a cloud one is.
Once per head: the file <config dir>/.claude-settings-refresh-seen holds the last 20 heads a reinstall, a pin refresh
or a clone flag acted on.
The ref comes only from the record: the installer gets it as CLAUDE_SETTINGS_REF, replacing any value in the hook's
environment. The hook names no branch of its own, bar the pin's fallback (PIN_FALLBACK_BRANCH). The installer also gets a CS_HOOK_INPUT whose source no SessionStart
entry fires on, so install.sh runs no startup entry for a reinstall in a running session.

Cost: one python process start per prompt. Network calls per prompt: 0. Local reads per prompt:
the install record, the config dir's CLAUDE.md, and local git reads in a clone: at most 4 on a prompt with no trigger
(rev-parse of the ref, merge-base, and rev-parse and rev-list of the shared clone) and at most 8 on a trigger prompt
(those four, symbolic-ref, then rev-list twice for a pin, or diff and two show reads of settings.json for a reinstall;
a pin with no origin ref adds one rev-parse of local main). A local session with no record reads its pin: with no trigger it makes 2 git calls when the pin is current
(HEAD and origin/stable) and 4 when the pin is behind a head already seen (the pin has no shared clone). A local session
whose hook lives in no pin reads no git. A trigger adds one installer
run (the installer fetches; this hook does not) and, for a pin, one stat of the install lock (a read of it when fresh). Files written by this hook: the seen file, only when a reinstall, a
pin refresh or a clone flag acts on a new head. No timer, no long-lived process.
"""
import functools
import json
import os
import re
import signal
import subprocess
import sys
import time
try:
    import _nowindow  # the one home of a no-window child start; a flat hooks/ file
except ImportError:  # the helper lands a moment after the hook in an install; a hook never dies for it
    _nowindow = subprocess
try:
    from git_bash import find_git_bash  # the one home of "which bash on Windows" (hooks/git_bash.py)
except ImportError:  # same: a hook never dies for a helper that has not landed
    def find_git_bash():
        return None

from shared_names import LIVE_PIN_SUFFIX, PIN_SCRIPT, PIN_TREE  # the one home of the pin's names (hooks/shared_names.py); not guard_frozen, which is costly to import

RECORD_NAME = ".claude-settings-install.json"
SEEN_NAME = ".claude-settings-refresh-seen"
SEEN_KEEP = 20
SHORT = 7
# Seconds for one local git read.
GIT_TIMEOUT = 10
# Seconds for one installer run. CLAUDE_SETTINGS_REINSTALL_TIMEOUT replaces it. The hook's own limit in settings.json
# is 120. A turn also makes up to 8 local git reads of up to GIT_TIMEOUT each, and a stop takes TERM_GRACE. A git read
# takes milliseconds unless git hangs. The default leaves room for a typical turn. Hung reads on all 8 would pass the
# hook's limit, and the harness would end the advisory hook.
INSTALL_TIMEOUT = 60
# Seconds the installer gets to run its EXIT trap after SIGTERM, before SIGKILL.
TERM_GRACE = 5
# The hook input a reinstall passes. install.sh reads the session source from it, and no SessionStart entry
# fires on this one (the startup entries ran at session start).
INSTALL_HOOK_INPUT = '{"source":"stale-install"}'
# A running session reads these once. A new session must start to see a change.
RESTART_PATHS = ("CLAUDE.md", "output-styles/")
RESTART_SETTINGS_KEYS = ("model", "effortLevel")
PREFIX = "claude-settings: "
# The install lock the two installers take, and the age (seconds) past which they remove it as a dead run's. Copies of
# INSTALL_LOCK in install.sh and merge/install_from_main.sh (their `find -mmin +10`), their home: bash and Python share
# no source. The hook only reads it, to leave a refresh to the install that holds it.
LOCK_NAME = ".claude-settings-install.lock"
LOCK_MAX_AGE = 600
# The one branch the hook names: install_from_main.sh pins to local main when origin has no ref for the record's ref.
PIN_FALLBACK_BRANCH = "main"
# The branch a local session's pin follows. A copy of the default in merge/install_from_main.sh,
# REF="${CLAUDE_SETTINGS_REF:-stable}", its home: shell and Python share no source, so a change there is made here too.
PIN_REF = "stable"
SHARED_LINE = re.compile(r"@(.+)/CLAUDE\.md")


def unknown(reason):
    return PREFIX + "install freshness unknown (%s)" % reason


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def load_record():
    """(record, None), or (None, reason) when the record is absent, unreadable or lacks a field."""
    path = os.path.join(config_dir(), RECORD_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except OSError:
        return None, "no install record"
    except ValueError:
        return None, "install record unreadable"
    if not isinstance(record, dict):
        return None, "install record unreadable"
    for key in ("ref", "sha", "source", "installer"):
        if not isinstance(record.get(key), str) or not record[key]:
            return None, "install record has no %s" % key
    if not re.fullmatch(r"[0-9a-f]{40}", record["sha"]):
        return None, "install record sha is not a commit id"
    if record["ref"].startswith("-") or re.search(r"\s", record["ref"]):
        return None, "install record ref is not a branch name"
    return record, None


def install_timeout():
    try:
        value = float(os.environ.get("CLAUDE_SETTINGS_REINSTALL_TIMEOUT", ""))
    except ValueError:
        return INSTALL_TIMEOUT
    return value if value > 0 else INSTALL_TIMEOUT


def git_run(source, *args):
    """The finished git command in the clone, or None when it did not run. git -C follows a linked worktree to its
    common dir, so a pin's refs read like a clone's."""
    try:
        return _nowindow.run(["git", "-C", source, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_out(source, *args):
    """The text of one git command in the source clone, or None when it fails."""
    done = git_run(source, *args)
    return done.stdout if done is not None and done.returncode == 0 else None


def local_sha(source, rev):
    """The commit a local rev names in the clone, or None."""
    text = git_out(source, "rev-parse", "--verify", "-q", rev + "^{commit}")
    found = text.strip() if text else ""
    return found if re.fullmatch(r"[0-9a-f]{40}", found) else None


def covered(source, sha, installed):
    """True when `sha` is the installed commit or one of its ancestors. An object the clone lacks, or a failed read,
    is not covered."""
    if sha == installed:
        return True
    done = git_run(source, "merge-base", "--is-ancestor", sha, installed)
    return done is not None and done.returncode == 0


def commits_behind(source, base, tip):
    """How many commits `tip` has that `base` lacks, from local objects, or None."""
    text = git_out(source, "rev-list", "--count", "%s..%s" % (base, tip))
    return int(text) if text and text.strip().isdigit() else None


def plural(count):
    return "%d commit%s" % (count, "" if count == 1 else "s")


def load_seen():
    try:
        with open(os.path.join(config_dir(), SEEN_NAME), encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except OSError:
        return []


def add_seen(seen, key):
    """Writes the seen file with `key` added. A failed write is not fatal: the act would then repeat on a later prompt."""
    seen.append(key)
    path = os.path.join(config_dir(), SEEN_NAME)
    tmp = "%s.%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(item + "\n" for item in seen[-SEEN_KEEP:]))
        os.replace(tmp, path)
    except OSError:
        pass


def settings_keys(source, rev):
    """The settings.json object at a commit, or None when it cannot be read."""
    text = git_out(source, "show", "%s:settings.json" % rev)
    try:
        data = json.loads(text) if text is not None else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def restart_line(source, old, new):
    """One line naming each changed path a new session must read again, "" when none, or an unknown line."""
    names = git_out(source, "diff", "--name-only", old, new)
    if names is None:
        return PREFIX + "restart check unknown (could not diff %s..%s)" % (old[:SHORT], new[:SHORT])
    changed = names.splitlines()
    needed = [p for p in RESTART_PATHS if any(c == p or c.startswith(p) for c in changed)]
    if "settings.json" in changed:
        before, after = settings_keys(source, old), settings_keys(source, new)
        if before is None or after is None:
            return PREFIX + "restart check unknown (could not read settings.json)"
        needed += [k for k in RESTART_SETTINGS_KEYS if before.get(k) != after.get(k)]
    return PREFIX + "restart needed for: " + ", ".join(needed) if needed else ""


def stop_group(proc):
    """SIGTERM to the installer's group, so install.sh's EXIT trap releases the install lock. SIGKILL to the group
    after TERM_GRACE, or at once after the leader's exit, for any member still running. Where os.killpg or
    signal.SIGKILL does not exist (Windows), stop_tree ends the process tree instead."""
    if not (hasattr(os, "killpg") and hasattr(signal, "SIGKILL")):
        stop_tree(proc)
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=TERM_GRACE)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.wait()


def stop_tree(proc):
    """Ends the installer and its children where there are no process groups, with the tree kill in _nowindow
    (taskkill /T /F). Windows has no TERM for a child with no console, so the EXIT trap does not run and the install lock
    stays until its own age limit clears it. Without taskkill the leader gets terminate, then kill. No wait is unbounded:
    a leader that will not end is left, and the hook still prints its timeout line."""
    taskkill_tree = getattr(_nowindow, "taskkill_tree", None)  # the stand-in module has none
    if taskkill_tree is not None:
        taskkill_tree(proc.pid, GIT_TIMEOUT)
    for stop in (proc.terminate, proc.kill):
        if proc.poll() is not None:
            return
        try:
            stop()
            proc.wait(timeout=TERM_GRACE)
        except (OSError, AttributeError, subprocess.TimeoutExpired):  # AttributeError: no signal.SIGKILL to kill with
            pass


def script_path(path):
    """A script path in the form Git Bash reads: forward slashes on Windows."""
    return path.replace("\\", "/") if os.name == "nt" else path


class Failure(str):
    """The failure text of run_script, which also says whether the run timed out and the pid it ran as."""
    timed_out = False
    pid = None


def run_script(record, argv, what, cwd=None):
    """Runs a recorded script once, in `cwd` when given. Returns None on success, else the failure text. Where there are
    process groups it runs in its own session so a stop reaches its children. Its output goes nowhere: the hook
    prints its own lines. Windows starts the Git Bash that hooks/git_bash.py finds; elsewhere bash on PATH."""
    limit = install_timeout()
    env = dict(os.environ, CLAUDE_SETTINGS_REF=record["ref"], CS_HOOK_INPUT=INSTALL_HOOK_INPUT)
    own_session = {} if os.name == "nt" else {"start_new_session": True}
    bash = find_git_bash()
    if bash is None and os.name == "nt":  # a bare "bash" on Windows is the WSL launcher (hooks/git_bash.py)
        return "%s not run (Git Bash not found)" % what
    try:
        proc = _nowindow.Popen([bash or "bash", *argv], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=cwd, **own_session)
    except OSError as err:
        return "%s failed (%s)" % (what, err)
    try:
        code = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        stop_group(proc)
        failure = Failure("%s failed (timed out after %g s)" % (what, limit))
        failure.timed_out, failure.pid = True, proc.pid
        return failure
    return None if code == 0 else "%s failed (exit %d)" % (what, code)


def reinstall_lines(record, target):
    """The lines for one run of the recorded installer toward `target`."""
    failure = run_script(record, [record["installer"], "--cloud"], "reinstall")
    if failure:
        return [PREFIX + failure]
    now, _ = load_record()
    if now is None or not covered(record["source"], target, now["sha"]):
        return [PREFIX + "reinstall did not reach %s (record at %s)"
                % (target[:SHORT], now["sha"][:SHORT] if now else "none")]
    installed = now["sha"]
    lines = [PREFIX + "reinstalled hooks at %s (was %s)" % (installed[:SHORT], record["sha"][:SHORT])]
    restart = restart_line(record["source"], record["sha"], installed)
    if restart:
        lines.append(restart)
    return lines


def followed_ref(record):
    """(rev, name, sha) for the ref the check reads in the record's source: the local origin/<record ref>, else, for
    the pin only, local main, which install_from_main.sh pins to when origin has no such ref. (None, None, None) when
    neither can be read."""
    source = record["source"]
    rev = "refs/remotes/origin/" + record["ref"]
    sha = local_sha(source, rev)
    if sha is None and is_pin(source):
        rev = "refs/heads/" + PIN_FALLBACK_BRANCH
        sha = local_sha(source, rev)
        return (rev, "local " + PIN_FALLBACK_BRANCH, sha) if sha else (None, None, None)
    return (rev, "origin/" + record["ref"], sha) if sha else (None, None, None)


def stale_line(record, target, name):
    """The line for a prompt on a head whose refresh already ran, and the record still does not cover it."""
    return PREFIX + "install still stale: record at %s, %s at %s; the refresh for that head ran and did not finish" \
        % (record["sha"][:SHORT], name, target[:SHORT])


def lock_held_by_other(own_pid=None):
    """True when another install holds the install lock: the file exists, is under LOCK_MAX_AGE old, and was not written
    by the run that had pid `own_pid` (its id ends with its pid). One stat, and a read when the file is fresh."""
    path = os.path.join(config_dir(), LOCK_NAME)
    try:
        if time.time() - os.stat(path).st_mtime > LOCK_MAX_AGE:
            return False
        with open(path, encoding="utf-8") as handle:
            holder = handle.readline().strip()
    except OSError:
        return False  # no lock, or it ended during the read
    return not (own_pid is not None and holder.endswith(str(own_pid)))


def pin_lines(record, head, seen, local_ref, where):
    """The one line for a pin refresh toward `head`, the tip of `local_ref` (shown as `where`). The pin's
    merge/install_from_main.sh runs once per head, and the line states the commits the pin was behind, counted from
    local objects. The head is marked seen once the refresh has ended, so a hook that was cut short tries it again.
    Another install holding the lock is no outcome of this refresh: the hook prints nothing and leaves the head unseen, so
    a later prompt checks again. It also skips the run, which would only wait behind that lock."""
    source = record["source"]
    if lock_held_by_other():
        return []
    before = commits_behind(source, "HEAD", local_ref)
    # install_from_main.sh finds its clone from the folder it runs in, and takes no argument; the head goes on its command
    # line only so a process listing shows which head the refresh is for.
    failure = run_script(record, [script_path(os.path.join(source, PIN_SCRIPT)), head], "pin refresh", cwd=source)
    if getattr(failure, "timed_out", False) and lock_held_by_other(failure.pid):
        return []  # the refresh waited behind another install's lock until the timeout
    add_seen(seen, "pin:" + head)
    after = commits_behind(source, "HEAD", local_ref)
    if failure:
        return [PREFIX + failure]
    if after is None:
        return [PREFIX + "pin refresh ran; its commits behind %s are unknown" % where]
    if after == 0:
        return [PREFIX + "pin refreshed: was %s behind %s" % (plural(before or 0), where)]
    return [PREFIX + "pin is %s behind %s after the refresh" % (plural(after), where)]


def shared_clone(config_text):
    """The real path of the folder in the first `@<folder>/CLAUDE.md` line of the config dir's CLAUDE.md, or None."""
    for text in config_text.splitlines():
        found = SHARED_LINE.fullmatch(text.strip())
        if found:
            return os.path.realpath(os.path.expanduser(found.group(1)))
    return None


def shared_lines(record, seen):
    """One line when the clone the config dir's CLAUDE.md points at is behind its own local origin ref, once per head.
    Silent when the file, the clone or its ref is absent: the check is advisory."""
    try:
        with open(os.path.join(config_dir(), "CLAUDE.md"), encoding="utf-8") as handle:
            clone = shared_clone(handle.read())
    except (OSError, UnicodeDecodeError):
        return []
    if clone is None or clone == os.path.realpath(record["source"]):
        return []
    local_ref = "refs/remotes/origin/" + record["ref"]
    tip = local_sha(clone, local_ref)
    key = "shared:%s:%s" % (clone, tip)
    if tip is None or key in seen:
        return []
    behind = commits_behind(clone, "HEAD", local_ref)
    if not behind:
        return []
    add_seen(seen, key)
    return [PREFIX + "the clone %s is %s behind origin/%s (origin at %s); pull it before it is read again"
            % (clone, plural(behind), record["ref"], tip[:SHORT])]


@functools.lru_cache(maxsize=None)
def is_pin(source):
    """True when the source is a detached checkout that holds the pin's refresh script."""
    if not os.path.isfile(os.path.join(source, PIN_SCRIPT)):
        return False
    done = git_run(source, "symbolic-ref", "-q", "HEAD")
    return done is not None and done.returncode == 1


def pin_record():
    """The record a local session has no file for: the live pin the hook file lives in, read as installed at its own
    HEAD, following PIN_REF. None, with no git call, when the hook lives in no pin or the pin holds no refresh script
    or HEAD."""
    # The installed hook is a symlink into the pin: resolve the file itself, then take its folder.
    here = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    found = PIN_TREE.fullmatch(here)
    if not found:
        return None
    link = found["clone"] + LIVE_PIN_SUFFIX
    # The link follows the pin as it moves; a plain <clone>-live directory is its own pin.
    source = link if os.path.isfile(os.path.join(link, PIN_SCRIPT)) else here
    if not os.path.isfile(os.path.join(source, PIN_SCRIPT)):
        return None
    sha = local_sha(source, "HEAD")
    if sha is None:
        return None
    return {"ref": PIN_REF, "sha": sha, "source": source, "installer": os.path.join(source, "install.sh")}


def check():
    """The lines to print for one prompt."""
    remote = os.environ.get("CLAUDE_CODE_REMOTE") == "true"
    record, reason = load_record()
    if record is None and not remote:
        record = pin_record()  # a Mac or Windows session has no record; no pin means nothing to say
        if record is None:
            return []
    elif record is None:
        return [unknown(reason)]
    source = record["source"]
    local_ref, name, head = followed_ref(record)
    if head is None:
        return [unknown("no local origin/%s in %s" % (record["ref"], source))]
    seen = load_seen()
    lines = []
    if not covered(source, head, record["sha"]):
        # A head's refresh runs once, whatever its outcome. A later prompt on that head reports the record as stale.
        key = ("pin:" if is_pin(source) else "install:") + head
        if key in seen:
            lines.append(stale_line(record, head, name))
        elif key.startswith("pin:"):
            lines += pin_lines(record, head, seen, local_ref, name)
        elif remote:  # a local session never runs install.sh --cloud
            add_seen(seen, key)
            lines += reinstall_lines(record, head)
    return lines + shared_lines(record, seen)


def main():
    try:
        sys.stdin.buffer.read()  # the payload is not needed; drain it so the caller's write never blocks
        for text in check():
            print(text)
    except Exception as err:  # advisory hook: fail open, and say the freshness is unknown
        print(unknown("hook error: %s" % " ".join(str(err).split())[:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
