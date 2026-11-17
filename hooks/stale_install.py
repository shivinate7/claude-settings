#!/usr/bin/env python3
"""UserPromptSubmit hook: in a cloud session, reinstall the hooks when origin's tip moved past the installed sha, and say so.

A cloud session copies hooks at start, so a hook merged later stays stale for the whole session. Each turn this
hook reads the install record that install.sh --cloud writes (<config dir>/.claude-settings-install.json: ref,
sha, source, installer). It asks origin for the recorded ref's tip and acts on the answer:
- tip equals the recorded sha: prints nothing.
- tip differs: runs the recorded installer once (`install.sh --cloud`), then reads the record again. A record now at
  the tip prints one line naming both 7-character shas. A record still at another sha (the installer exited 0 but
  its files did not come from the tip: its fetch missed it, or the source clone stayed on another commit) prints "reinstall did not reach <tip> (record at <sha>)", never "reinstalled". A second
  line follows when a changed path needs a new session to read it again: CLAUDE.md, output-styles/,
  and the settings.json keys model and effortLevel (the line names each key). An installer that exits non-zero
  prints "reinstall failed (exit N)" and is not retried that turn. An installer past its timeout gets SIGTERM, so
  install.sh's EXIT trap releases its lock, then SIGKILL after a short wait; it prints "reinstall failed (timed out
  after N s)".
- the record, the origin URL or the read fails: prints one "install freshness unknown (reason)" line and installs
  nothing. Unknown is never reported as current.
The ref comes only from the record: the installer gets it as CLAUDE_SETTINGS_REF, replacing any value in the
hook's environment. The hook names no branch of its own. The installer also gets a CS_HOOK_INPUT whose source no
SessionStart entry fires on, so install.sh runs no startup entry for a reinstall in a running session.

Cost: one python process start per turn. At most one `git ls-remote` per turn (a network read, bounded by
CLAUDE_SETTINGS_FETCH_TIMEOUT seconds, default 10), none outside a cloud session. The origin URL is read from the
source clone's .git/config, with no git call. A reinstall adds one installer run and, to find the restart line,
a few local git reads in the source clone. No timer, no long-lived process, no file written here (the installer
writes the record).
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
SHORT = 7
# Seconds for the one network read. CLAUDE_SETTINGS_FETCH_TIMEOUT replaces it.
FETCH_TIMEOUT = 10
# Seconds for one installer run. CLAUDE_SETTINGS_REINSTALL_TIMEOUT replaces it. The hook's own limit in settings.json
# is 120. One turn can also spend 10 on the origin read, up to 30 on the restart reads, and TERM_GRACE on a stop.
# The default leaves room for all of them.
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


def origin_url(source):
    """The url of remote origin in the clone's .git/config, read as text so no git process starts. None if absent."""
    try:
        with open(os.path.join(source, ".git", "config"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    in_origin = False
    for text in lines:
        text = text.strip()
        if text.startswith("["):
            in_origin = re.fullmatch(r'\[remote\s+"origin"\]', text) is not None
        elif in_origin:
            found = re.fullmatch(r"url\s*=\s*(.+)", text)
            if found:
                return found.group(1).strip()
    return None


def fetch_timeout():
    try:
        value = float(os.environ.get("CLAUDE_SETTINGS_FETCH_TIMEOUT", ""))
    except ValueError:
        return FETCH_TIMEOUT
    return value if value > 0 else FETCH_TIMEOUT


def install_timeout():
    try:
        value = float(os.environ.get("CLAUDE_SETTINGS_REINSTALL_TIMEOUT", ""))
    except ValueError:
        return INSTALL_TIMEOUT
    return value if value > 0 else INSTALL_TIMEOUT


def remote_tip(url, ref):
    """(sha, None), or (None, reason). One git ls-remote of the recorded ref."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        done = _nowindow.run(["git", "ls-remote", url, "refs/heads/" + ref], capture_output=True, text=True,
                              timeout=fetch_timeout(), env=env)
    except subprocess.TimeoutExpired:
        return None, "the read of origin timed out"
    except OSError as err:
        return None, "git did not run: %s" % err
    if done.returncode:
        return None, "the read of origin failed (exit %d)" % done.returncode
    for row in done.stdout.splitlines():
        fields = row.split()
        if len(fields) == 2 and fields[1] == "refs/heads/" + ref and re.fullmatch(r"[0-9a-f]{40}", fields[0]):
            return fields[0], None
    return None, "origin has no branch %s" % ref


def git_out(source, *args):
    """The text of one git command in the source clone, or None when it fails."""
    try:
        done = _nowindow.run(["git", "-C", source, *args], capture_output=True, text=True, timeout=fetch_timeout())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


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


def reinstall(record):
    """Runs the recorded installer once. Returns None on success, else the failure text. The installer runs in its
    own session so a stop reaches its children. Its output goes nowhere: the hook prints its own lines."""
    limit = install_timeout()
    env = dict(os.environ, CLAUDE_SETTINGS_REF=record["ref"], CS_HOOK_INPUT=INSTALL_HOOK_INPUT)
    try:
        proc = _nowindow.Popen(["bash", record["installer"], "--cloud"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                                start_new_session=True)
    except OSError as err:
        return "reinstall failed (%s)" % err
    try:
        code = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        stop_group(proc)
        return "reinstall failed (timed out after %g s)" % limit
    return None if code == 0 else "reinstall failed (exit %d)" % code


def check():
    """The lines to print for one turn."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return []
    record, reason = load_record()
    if record is None:
        return [unknown(reason)]
    url = origin_url(record["source"])
    if url is None:
        return [unknown("no origin url in %s" % record["source"])]
    tip, reason = remote_tip(url, record["ref"])
    if tip is None:
        return [unknown(reason)]
    if tip == record["sha"]:
        return []
    failure = reinstall(record)
    if failure:
        return [PREFIX + failure]
    now, _ = load_record()
    if now is None or now["sha"] != tip:
        return [PREFIX + "reinstall did not reach %s (record at %s)"
                % (tip[:SHORT], now["sha"][:SHORT] if now else "none")]
    lines = [PREFIX + "reinstalled hooks at %s (was %s)" % (tip[:SHORT], record["sha"][:SHORT])]
    restart = restart_line(record["source"], record["sha"], tip)
    if restart:
        lines.append(restart)
    return lines


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
