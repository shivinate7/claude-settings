#!/usr/bin/env python3
"""UserPromptSubmit hook: in a cloud session, reinstall the hooks when the local origin ref moved past the installed sha, and say so.

A cloud session copies hooks at start, so a hook merged later stays stale for the whole session. A prompt reads no
origin (owner, 2026-11-17 09:34 CST, decision stale-install-cost). It reads the install record that install.sh --cloud
writes (<config dir>/.claude-settings-install.json: ref, sha, source, installer) and compares it with the local
refs/remotes/origin/<record ref> of the record's source clone. It acts on two triggers only:
- the local ref names a commit the record's sha does not cover (a session start, a resume or a fetch moved it);
- the newest merge notice in the session's inbox, "main moved to <sha>; refresh", names such a commit.
A commit the record's sha already contains is no trigger. With no trigger a prompt prints nothing and runs no installer.
A record, a source or a local ref that cannot be read prints one "install freshness unknown (reason)" line and
installs nothing. Unknown is never reported as current.
- source on a branch (a checkout or a mirror): runs the recorded installer once (`install.sh --cloud`), then reads
  the record again. A record now at the target prints one line naming both 7-character shas. A record still at another
  sha prints "reinstall did not reach <target> (record at <sha>)", never "reinstalled". A second line follows when a
  changed path needs a new session to read it again: CLAUDE.md, output-styles/, and the settings.json keys model and
  effortLevel. An installer that exits non-zero prints "reinstall failed (exit N)" and is not retried that turn. An
  installer past its timeout gets SIGTERM, so install.sh's EXIT trap releases its lock, then SIGKILL after a short
  wait; it prints "reinstall failed (timed out after N s)".
- source on a detached HEAD, the live pin, that holds merge/install_from_main.sh: runs it once per new head and prints
  one line that states how many commits the pin is behind the local ref, counted from local objects.
- the clone the config dir's CLAUDE.md points at (an @path line), when its HEAD is behind its own local origin ref:
  one line that names the clone and its commits behind, once per new head.
Once per head: the file <config dir>/.claude-settings-refresh-seen holds the last 20 heads a pin refresh or a clone
flag acted on.
The ref comes only from the record: the installer gets it as CLAUDE_SETTINGS_REF, replacing any value in the hook's
environment. The hook names no branch of its own. The installer also gets a CS_HOOK_INPUT whose source no SessionStart
entry fires on, so install.sh runs no startup entry for a reinstall in a running session.

Cost: one python process start per prompt. Network calls per prompt: 0. Local reads per prompt in a cloud session:
the install record, the session inbox's last 256 KB, the config dir's CLAUDE.md, and at most 5 local git reads
(rev-parse of the ref, one merge-base per trigger, symbolic-ref, rev-parse and rev-list of the shared clone). None
outside a cloud session. A trigger adds one installer run (the installer fetches; this hook does not) and, to find the
restart line, a few more local git reads. Files written by this hook: the seen file, only when a pin refresh or a
clone flag acts on a new head. No timer, no long-lived process.
"""
import json
import os
import re
import signal
import subprocess
import sys
try:
    import _nowindow  # the one home of a no-window child start; a flat hooks/ file
except ImportError:  # the helper lands a moment after the hook in an install; a hook never dies for it
    _nowindow = subprocess

RECORD_NAME = ".claude-settings-install.json"
SEEN_NAME = ".claude-settings-refresh-seen"
SEEN_KEEP = 20
SHORT = 7
# Seconds for one local git read.
GIT_TIMEOUT = 10
# Seconds for one installer run. CLAUDE_SETTINGS_REINSTALL_TIMEOUT replaces it. The hook's own limit in settings.json
# is 120. One turn can also spend up to 50 on local git reads and TERM_GRACE on a stop. The default leaves room.
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
# The merge notice the merge tool mails a session: its text lands in the session inbox as one fenced message.
NOTICE = re.compile(r"^main moved to ([0-9a-f]{40}); refresh[ \t]*$", re.MULTILINE)
INBOX_TAIL = 256 * 1024
PIN_SCRIPT = os.path.join("merge", "install_from_main.sh")
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
    is not covered: a notice naming a commit not fetched yet is new."""
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


def newest_notice(payload):
    """The sha of the newest merge notice in the session's inbox, or None. Reads the file's last INBOX_TAIL bytes."""
    try:
        import local_time  # the one home of the inbox path, a flat hooks/ file
        paths = local_time.inbox_paths(payload.get("session_id"))
        if paths is None:
            return None
        with open(paths[0], "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - INBOX_TAIL))
            text = handle.read().decode("utf-8", "replace")
    except (ImportError, OSError, ValueError, AttributeError):
        return None
    found = NOTICE.findall(text)
    return found[-1] if found else None


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
    after TERM_GRACE, or at once after the leader's exit, for any member still running."""
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


def run_script(record, argv, what, cwd=None):
    """Runs a recorded script once, in `cwd` when given. Returns None on success, else the failure text. It runs in its
    own session so a stop reaches its children. Its output goes nowhere: the hook prints its own lines."""
    limit = install_timeout()
    env = dict(os.environ, CLAUDE_SETTINGS_REF=record["ref"], CS_HOOK_INPUT=INSTALL_HOOK_INPUT)
    try:
        proc = _nowindow.Popen(["bash", *argv], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=env, cwd=cwd, start_new_session=True)
    except OSError as err:
        return "%s failed (%s)" % (what, err)
    try:
        code = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        stop_group(proc)
        return "%s failed (timed out after %g s)" % (what, limit)
    return None if code == 0 else "%s failed (exit %d)" % (what, code)


def reinstall_lines(record, target):
    """The lines for one run of the recorded installer toward `target`."""
    failure = run_script(record, [record["installer"], "--cloud"], "reinstall")
    if failure:
        return [PREFIX + failure]
    now, _ = load_record()
    if now is None or now["sha"] != target:
        return [PREFIX + "reinstall did not reach %s (record at %s)"
                % (target[:SHORT], now["sha"][:SHORT] if now else "none")]
    lines = [PREFIX + "reinstalled hooks at %s (was %s)" % (target[:SHORT], record["sha"][:SHORT])]
    restart = restart_line(record["source"], record["sha"], target)
    if restart:
        lines.append(restart)
    return lines


def pin_lines(record, head, seen):
    """The one line for a pin refresh toward the local ref `head`. The pin's merge/install_from_main.sh runs once per
    head, and the line states the commits the pin was behind, counted from local objects."""
    source, local_ref = record["source"], "refs/remotes/origin/" + record["ref"]
    where = "origin/" + record["ref"]
    before = commits_behind(source, "HEAD", local_ref)
    add_seen(seen, "pin:" + head)
    # install_from_main.sh finds its clone from the folder it runs in, and takes no argument; the head goes on its command
    # line only so a process listing shows which head the refresh is for.
    failure = run_script(record, [os.path.join(source, PIN_SCRIPT), head], "pin refresh", cwd=source)
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


def target_for(record, head, notice):
    """The commit a trigger names that the record does not cover, or None. The local ref comes before the notice."""
    for sha in (head, notice):
        if sha and not covered(record["source"], sha, record["sha"]):
            return sha
    return None


def is_pin(source):
    """True when the source is a detached checkout that holds the pin's refresh script."""
    if not os.path.isfile(os.path.join(source, PIN_SCRIPT)):
        return False
    done = git_run(source, "symbolic-ref", "-q", "HEAD")
    return done is not None and done.returncode == 1


def check(payload):
    """The lines to print for one prompt."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return []
    record, reason = load_record()
    if record is None:
        return [unknown(reason)]
    source = record["source"]
    head = local_sha(source, "refs/remotes/origin/" + record["ref"])
    if head is None:
        return [unknown("no local origin/%s in %s" % (record["ref"], source))]
    seen = load_seen()
    lines = []
    target = target_for(record, head, newest_notice(payload))
    if target is not None:
        if not is_pin(source):
            lines += reinstall_lines(record, target)
        elif "pin:" + target not in seen:
            lines += pin_lines(record, target, seen)
    return lines + shared_lines(record, seen)


def main():
    try:
        raw = sys.stdin.buffer.read()  # drained, so the caller's write never blocks
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            payload = {}
        for text in check(payload if isinstance(payload, dict) else {}):
            print(text)
    except Exception as err:  # advisory hook: fail open, and say the freshness is unknown
        print(unknown("hook error: %s" % " ".join(str(err).split())[:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
