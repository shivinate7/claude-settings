#!/usr/bin/env python3
"""Cases for hooks/stale_install.py, the cloud-session check that reinstalls hooks when origin moves on.
Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_reinstall_stale.py

WHAT IT PROVES. In a cloud session the hook reads the install record, makes at most one `git ls-remote`
of the recorded ref, and then does one of three things: stays silent when the tip is the recorded sha,
reinstalls once with the recorded installer when the tip moved, or prints one unknown line when the read
or the record fails. An installer that exits non-zero prints one failure line and is not retried. A restart
line appears only for a changed path that a new session must read again, and a local diff that cannot run
prints a restart unknown line.
After an installer run the hook reads the record again. A record that still names the old sha prints one line that
the reinstall did not reach the tip, never a reinstall line. The installer gets the record's ref, and a hook input
that no SessionStart entry fires on. At its timeout the installer gets SIGTERM before SIGKILL, and its child goes
with it.
A prompt that reads origin writes no file in the config dir, the source clone or HOME. The hook never names `main`
itself, and it is wired once, under UserPromptSubmit. The cost record's Ruling section accepts that one read per cloud
prompt, with its measured figures.

THE STAMP. A cloud run that names a tip (CS_STALE_TIP) writes <config dir>/.claude-settings-install-attempt.json
when it starts, and removes it when its record lands at that tip. The hook skips the installer for that same tip
within the backoff, prints one skip line, and never writes the stamp. The stub installer models the stamp. No case
runs install.sh's own write_attempt_stamp, and none covers the install lock wait.

THE SEAM. Each fixture is a bare origin, a seed that pushes to it, and a source clone at the recorded sha,
all under the run folder. HOME and CLAUDE_CONFIG_DIR point into the run folder, so the real ~/.claude is
never read. A PATH shim on `git` logs each call's argv and then runs the real git. A stub installer logs
each run, fetches origin as the real installer does, and writes the record when told. The cases read the
hook's stdout, its exit code, the shim log and the stub log. They import nothing from the hook.

The controls at the end (class Harness) pass on any tree. They prove the fixture and the shim work, so a
red elsewhere belongs to the hook.
"""

import ast
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

ROOT = _test_temp.run_folder()
HOOK = os.path.join(HERE, "stale_install.py")
DECISION = os.path.join(REPO, "docs", "decisions", "stale-install-cost.md")
SETTINGS = os.path.join(REPO, "settings.json")
REAL_GIT = shutil.which("git") or "git"
RECORD = ".claude-settings-install.json"
PAYLOAD = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "test-session", "prompt": "hi"})
HOOK_GUARD = 60  # seconds: stops a hook that never returns, so a broken build fails instead of hanging CI
SHORT = 7
REINSTALL = "claude-settings: reinstalled hooks at %s (was %s)"
UNKNOWN = "claude-settings: install freshness unknown ("
RESTART = "claude-settings: restart needed for:"
RESTART_UNKNOWN = "claude-settings: restart check unknown (could not diff %s..%s)"
NOT_REACHED = "claude-settings: reinstall did not reach %s (record at %s)"
STAMP_NAME = ".claude-settings-install-attempt.json"
DEFAULT_BACKOFF = 900
# Seconds an aged stamp is moved back by. Far past the default backoff, so the reinstall is not a near miss.
AGED_BY = 3600
SKIPPED = re.compile(r"claude-settings: reinstall skipped \(install started at ([0-9a-f]{7}) not finished, "
                     r"retry in (\d+) s\)")
# A timeout case waits out the installer bound the hook has on the code under test (100 s), so its guard sits above.
TIMEOUT_GUARD = 130
GIT_LOCATORS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX")
HOOK_ENV_DROP = GIT_LOCATORS + ("CLAUDE_CODE_REMOTE", "CLAUDE_CONFIG_DIR", "CLAUDE_SETTINGS_FETCH_TIMEOUT",
                                "CLAUDE_SETTINGS_REF", "CLAUDE_SETTINGS_REINSTALL_TIMEOUT",
                                "CLAUDE_SETTINGS_REINSTALL_BACKOFF", "CS_HOOK_INPUT", "CS_STALE_TIP",
                                "GIT_SHIM_LS_REMOTE", "GIT_SHIM_DIFF", "STUB_EXIT", "STUB_RECORD_SHA")
HOOK_ONLY = {"hooks/config_watch.py": "pass  # tweak\n"}
COST_TERMS = (
    ("the process starts", r"(?i)process(?:es)? starts?|python starts?|starts? (?:one|a|1) python"),
    ("the network reads", r"(?i)network reads?|ls-remote"),
    ("the frequency", r"(?i)per turn|each turn|every turn"),
    ("no timer", r"(?i)\bno timers?\b"),
    ("no long-lived process", r"(?i)\bno long-lived\b"),
)

# Logs each call's argv (fields end in \037), makes ls-remote fail or hang when asked, makes diff fail when
# GIT_SHIM_DIFF is fail, else runs the real git.
SHIM = r'''#!/bin/sh
printf '%s\037' "$@" >> "$GIT_SHIM_LOG"
printf '\n' >> "$GIT_SHIM_LOG"
case " $* " in
  *" ls-remote "*)
    case "$GIT_SHIM_LS_REMOTE" in
      hang) exec sleep 60 ;;
      fail) echo "fatal: unable to access the remote" >&2; exit 128 ;;
    esac ;;
  *" diff "*)
    [ "$GIT_SHIM_DIFF" = fail ] && { echo "fatal: the local diff cannot run" >&2; exit 128; } ;;
esac
exec "$GIT_SHIM_REAL" "$@"
'''

# The installer's start, modelled on install.sh: counts the run, logs the environment it saw, and, when the hook named a
# tip (CS_STALE_TIP), writes the attempt stamp before anything else. START is the one home of that code. STUB and
# HANG_STUB both begin with it.
START = r'''printf '%s\n' "$*" >> "$STUB_COUNTER"
printf 'CLAUDE_SETTINGS_REF=%s\n' "${CLAUDE_SETTINGS_REF-unset}" >> "$STUB_ENV_LOG"
printf 'CS_HOOK_INPUT=%s\n' "${CS_HOOK_INPUT-unset}" >> "$STUB_ENV_LOG"
printf 'CS_STALE_TIP=%s\n' "${CS_STALE_TIP-unset}" >> "$STUB_ENV_LOG"
stamp="$CLAUDE_CONFIG_DIR/.claude-settings-install-attempt.json"
if [ -n "$CS_STALE_TIP" ]; then
  printf '{"tip": "%s", "epoch": %s}\n' "$CS_STALE_TIP" "$(date +%s)" > "$stamp.cs-new"
  mv -f "$stamp.cs-new" "$stamp"
fi
'''

# Stands in for install.sh: runs START, fetches origin as the real installer does, and writes the install record when
# STUB_WRITE_RECORD is set. When STUB_EXIT is set it exits with that code first, before the fetch and the record, so
# the stamp START wrote stays. When STUB_RECORD_SHA is set it writes that sha and exits 0 with no fetch: an installer
# whose fetch failed while the hook's ls-remote worked. When the record lands at CS_STALE_TIP it removes the stamp.
STUB = r'''#!/bin/sh
here=$(cd "$(dirname "$0")" && pwd -P)
''' + START + r'''[ -n "$STUB_EXIT" ] && exit "$STUB_EXIT"
if [ -n "$STUB_RECORD_SHA" ]; then
  sha=$STUB_RECORD_SHA
else
  git -C "$here" fetch -q origin || exit 1
  if [ -n "$STUB_WRITE_RECORD" ]; then
    sha=$(git -C "$here" rev-parse "origin/$STUB_REF") || exit 1
  fi
fi
if [ -n "$STUB_WRITE_RECORD" ] && [ -n "$sha" ]; then
  printf '{"ref": "%s", "sha": "%s", "source": "%s", "installer": "%s/install.sh"}\n' \
    "$STUB_REF" "$sha" "$here" "$here" > "$CLAUDE_CONFIG_DIR/.claude-settings-install.json"
  if [ -n "$CS_STALE_TIP" ] && [ "$sha" = "$CS_STALE_TIP" ]; then rm -f "$stamp"; fi
fi
'''

# Stands in for an install that holds the install lock when the hook stops it. Its TERM trap waits for the child it
# started, then writes a "term" mark and releases the lock. The wait ends only once that child has exited, so a
# "term" mark means the child was signalled too. It begins with START, so it counts its run and writes the stamp.
HANG_STUB = r'''#!/bin/sh
''' + START + r'''lock="$CLAUDE_CONFIG_DIR/.claude-settings-install.lock"
( set -C; printf '%s\n' "$$" > "$lock" ) 2>/dev/null || exit 1
sleep 300 >/dev/null 2>&1 &
grand=$!
printf '%s\n' "$grand" > "$STUB_GRAND"
trap 'wait "$grand" 2>/dev/null; printf "term\n" >> "$STUB_MARK"; rm -f "$lock"; exit 143' TERM
wait "$grand"
'''


def settings_text(**changes):
    data = {"model": "sonnet-a", "effortLevel": "low", "permissions": {"allow": ["Bash(ls)"]}}
    data.update(changes)
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


SEED_FILES = {
    "install.sh": STUB,
    "CLAUDE.md": "# Rules\n",
    "README.md": "readme\n",
    "settings.json": settings_text(),
    "hooks/config_watch.py": "pass\n",
    "output-styles/terse.md": "terse\n",
}


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


def read_text(path):
    """The file's text, or "" when it cannot be read. An absent file then fails the assert that reads it."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return ""


def ruling_text():
    """The cost record's Ruling section, from its heading to the next "## " heading or the end, with each run of
    whitespace made one space. "" when the record has no Ruling heading."""
    match = re.search(r"(?m)^## Ruling[ \t]*$(.*?)(?=^## |\Z)", read_text(DECISION), re.S)
    return " ".join(match.group(1).split()) if match else ""


def tree_state(root):
    """{path: (size, mtime_ns)} for `root` and everything under it, each path relative to `root`.
    An absent root is {}."""
    state = {}
    if not os.path.isdir(root):
        return state
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [dirpath] + [os.path.join(dirpath, rest) for rest in dirnames + filenames]:
            st = os.lstat(name)
            state[os.path.relpath(name, root)] = (st.st_size, st.st_mtime_ns)
    return state


def state_changes(before, after):
    """One row per path the two snapshots disagree on: created, removed or changed. [] when they match."""
    rows = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            rows.append("%s created" % path)
        elif path not in after:
            rows.append("%s removed" % path)
        elif before[path] != after[path]:
            rows.append("%s changed" % path)
    return rows


def write_file(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    if mode is not None:
        os.chmod(path, mode)


def write_tree(root, files):
    for rel, text in files.items():
        write_file(os.path.join(root, rel), text, mode=0o755 if rel == "install.sh" else None)


def subcommand(argv):
    """The git subcommand of an argv, past global options such as -C <path> and -c <key=value>."""
    rest = iter(argv)
    for arg in rest:
        if arg in ("-C", "-c"):
            next(rest, None)
        elif not arg.startswith("-"):
            return arg
    return ""


class Run:
    """One hook run: exit code (None when the safety stop ended it), stdout and stderr."""

    def __init__(self, rc, out, err):
        self.rc = rc
        self.out = out
        self.err = err
        self.lines = [line for line in out.splitlines() if line.strip()]

    def tail(self):
        rows = self.err.strip().splitlines()
        return rows[-1] if rows else "(no stderr)"


class Fixture:
    """One case's world under the run folder: origin, seed, source clone, record, stub installer and shim."""

    def __init__(self, name, branches=()):
        self.root = os.path.join(ROOT, name)
        self.home = os.path.join(self.root, "home")
        self.config = os.path.join(self.root, "config")
        self.shim_dir = os.path.join(self.root, "shim")
        self.origin = os.path.join(self.root, "origin.git")
        self.seed = os.path.join(self.root, "seed")
        self.gitconfig = os.path.join(self.root, "gitconfig")
        self.counter = os.path.join(self.root, "installer-runs.txt")
        self.git_log = os.path.join(self.root, "git-calls.txt")
        self.env_log = os.path.join(self.root, "installer-env.txt")
        self.marks = os.path.join(self.root, "installer-marks.txt")
        self.grand_path = os.path.join(self.root, "installer-child.pid")
        self.lock_path = os.path.join(self.config, ".claude-settings-install.lock")
        self.record_path = os.path.join(self.config, RECORD)
        self.stamp_path = os.path.join(self.config, STAMP_NAME)
        self.source = None
        self.ref = "main"
        for folder in (self.home, self.config, self.shim_dir, self.seed):
            os.makedirs(folder)
        write_file(self.gitconfig, "")
        write_file(os.path.join(self.shim_dir, "git"), SHIM, mode=0o755)
        self.git("init", "-q", "--bare", "-b", "main", self.origin)
        self.git("init", "-q", "-b", "main", self.seed)
        write_tree(self.seed, SEED_FILES)
        self.git("-C", self.seed, "add", "-A")
        self.git("-C", self.seed, "commit", "-q", "-m", "base")
        self.git("-C", self.seed, "remote", "add", "origin", self.origin)
        self.git("-C", self.seed, "push", "-q", "origin", "main")
        for branch in branches:
            self.git("-C", self.seed, "push", "-q", "origin", "main:refs/heads/" + branch)
        self.base = self.sha(self.seed, "HEAD")

    def git(self, *args):
        done = subprocess.run([REAL_GIT, *args], cwd=self.root, env=self.git_env(),
                              capture_output=True, text=True)
        if done.returncode:
            raise RuntimeError("fixture git %s: %s" % (" ".join(args), done.stderr.strip()))
        return done.stdout

    def git_env(self):
        env = dict(os.environ)
        for key in GIT_LOCATORS:
            env.pop(key, None)
        env.update(HOME=self.home, GIT_CONFIG_GLOBAL=self.gitconfig, GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                   GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        return env

    def hook_env(self, cloud=True, ls_remote=None, timeout=None, diff=None, stub_exit=None, settings_ref=None,
                 record_sha=None, reinstall_timeout=None, stale_tip=None, backoff=None):
        env = dict(os.environ)
        for key in HOOK_ENV_DROP:
            env.pop(key, None)
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.config,
                   PATH=self.shim_dir + os.pathsep + os.environ.get("PATH", ""),
                   GIT_SHIM_REAL=REAL_GIT, GIT_SHIM_LOG=self.git_log,
                   GIT_CONFIG_GLOBAL=self.gitconfig, GIT_CONFIG_NOSYSTEM="1",
                   STUB_COUNTER=self.counter, STUB_REF=self.ref, STUB_WRITE_RECORD="1",
                   STUB_ENV_LOG=self.env_log, STUB_MARK=self.marks, STUB_GRAND=self.grand_path)
        if cloud:
            env["CLAUDE_CODE_REMOTE"] = "true"
        if ls_remote:
            env["GIT_SHIM_LS_REMOTE"] = ls_remote
        if timeout:
            env["CLAUDE_SETTINGS_FETCH_TIMEOUT"] = timeout
        if diff:
            env["GIT_SHIM_DIFF"] = diff
        if stub_exit:
            env["STUB_EXIT"] = stub_exit
        if settings_ref:
            env["CLAUDE_SETTINGS_REF"] = settings_ref
        if record_sha:
            env["STUB_RECORD_SHA"] = record_sha
        if reinstall_timeout:
            env["CLAUDE_SETTINGS_REINSTALL_TIMEOUT"] = reinstall_timeout
        if stale_tip:
            env["CS_STALE_TIP"] = stale_tip
        if backoff:
            env["CLAUDE_SETTINGS_REINSTALL_BACKOFF"] = backoff
        return env

    def sha(self, repo, rev):
        return self.git("-C", repo, "rev-parse", rev).strip()

    def origin_tip(self, branch):
        return self.sha(self.origin, "refs/heads/" + branch)

    def clone(self, layout="checkout"):
        name = "claude-settings-main" if layout == "mirror" else "claude-settings"
        self.source = os.path.join(self.home, name)
        self.git("clone", "-q", self.origin, self.source)
        return self.source

    def lane_commit(self, branch):
        self.git("-C", self.source, "checkout", "-q", "-b", branch)
        write_file(os.path.join(self.source, "lane.txt"), "local only\n")
        self.git("-C", self.source, "add", "-A")
        self.git("-C", self.source, "commit", "-q", "-m", "lane work")

    def advance(self, changes, branch="main"):
        """Commit `changes` on the seed and push it: origin moves on, the source clone does not."""
        self.git("-C", self.seed, "checkout", "-q", branch)
        write_tree(self.seed, changes)
        self.git("-C", self.seed, "add", "-A")
        self.git("-C", self.seed, "commit", "-q", "--allow-empty", "-m", "next")
        self.git("-C", self.seed, "push", "-q", "origin", branch)
        return self.sha(self.seed, "HEAD")

    def changed(self, old, new):
        return sorted(self.git("-C", self.seed, "diff", "--name-only", old, new).split())

    def show(self, rev, rel):
        return self.git("-C", self.seed, "show", "%s:%s" % (rev, rel))

    def write_record(self, ref, sha):
        self.ref = ref
        record = {"ref": ref, "sha": sha, "source": self.source,
                  "installer": os.path.join(self.source, "install.sh")}
        write_file(self.record_path, json.dumps(record) + "\n")

    def record_sha(self):
        try:
            with open(self.record_path, encoding="utf-8") as handle:
                return json.load(handle).get("sha")
        except (OSError, ValueError, AttributeError):
            return None

    def read_stamp(self):
        """The attempt stamp as a dict, or None when it is absent or unreadable."""
        try:
            with open(self.stamp_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def write_stamp(self, text):
        write_file(self.stamp_path, text)

    def age_stamp(self, seconds):
        """Moves the stamp's epoch back by `seconds`, so the hook reads it as that much older. No clock is read."""
        stamp = self.read_stamp()
        if stamp is None or not isinstance(stamp.get("epoch"), int):
            raise RuntimeError("fixture: no stamp with an integer epoch to age")
        stamp["epoch"] -= seconds
        write_file(self.stamp_path, json.dumps(stamp) + "\n")

    def changes_since(self, before):
        """One row per change since the snapshot `before`, under the config dir, the source clone or the home dir."""
        after = self.watched()
        rows = []
        for label in ("config", "source", "home"):
            rows += ["%s: %s" % (label, row) for row in state_changes(before[label], after[label])]
        return rows

    def run_hook(self, guard=HOOK_GUARD, **options):
        """One hook run. The hook gets its own session and writes its output to files, so a stop at `guard`
        seconds ends the hook and everything it started, and the stop cannot hang on a pipe a child holds."""
        for path in (self.git_log, self.env_log):
            open(path, "w", encoding="utf-8").close()  # each run's calls start empty
        out_path = os.path.join(self.root, "hook-out.txt")
        err_path = os.path.join(self.root, "hook-err.txt")
        with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
            proc = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE, stdout=out, stderr=err,
                                    cwd=self.home, env=self.hook_env(**options), start_new_session=True, text=True)
            proc.stdin.write(PAYLOAD)
            proc.stdin.close()
            try:
                rc = proc.wait(timeout=guard)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                return Run(None, read_text(out_path), "still running after %d s; stopped" % guard)
        return Run(rc, read_text(out_path), read_text(err_path))

    def run_stub(self, **options):
        return subprocess.run([os.path.join(self.source, "install.sh"), "--cloud"], capture_output=True,
                              text=True, cwd=self.home, env=self.hook_env(**options))

    def installer_env(self):
        """The CLAUDE_SETTINGS_REF and CS_HOOK_INPUT the installer saw last, as text; "unset" where it saw none."""
        seen = {}
        try:
            with open(self.env_log, encoding="utf-8") as handle:
                for line in handle:
                    key, _, value = line.rstrip("\n").partition("=")
                    if key:
                        seen[key] = value
        except OSError:
            pass
        return seen

    def git_calls(self):
        """Each git call the last hook run made, as its argv."""
        try:
            with open(self.git_log, encoding="utf-8") as handle:
                rows = handle.read().split("\n")
        except OSError:
            return []
        calls = [row.split("\x1f")[:-1] for row in rows]
        return [argv for argv in calls if argv]

    def subcommands(self):
        return [subcommand(argv) for argv in self.git_calls()]

    def ls_remote_calls(self):
        return [argv for argv in self.git_calls() if subcommand(argv) == "ls-remote"]

    def installer_runs(self):
        """Each stub run so far, as its arguments. The counter keeps every turn's runs."""
        try:
            with open(self.counter, encoding="utf-8") as handle:
                return [line.rstrip("\n") for line in handle if line.strip()]
        except OSError:
            return []

    def watched(self):
        """The trees a prompt could write: the config dir, the source clone, and the home dir, which is both the hook's
        cwd and its HOME. Each maps its paths to (size, mtime_ns)."""
        return {"config": tree_state(self.config), "source": tree_state(self.source), "home": tree_state(self.home)}


def behind(name, changes=HOOK_ONLY, layout="checkout", ref="main"):
    """A cloud fixture whose record holds the base sha while origin has moved on by one commit."""
    fx = Fixture(name)
    old = fx.base
    fx.clone(layout)
    fx.write_record(ref, old)
    return fx, old, fx.advance(changes)


def current(name, ref="main", branches=()):
    """A cloud fixture whose record holds origin's tip for `ref`."""
    fx = Fixture(name, branches=branches)
    fx.clone()
    fx.write_record(ref, fx.base)
    return fx


def read_pid(path):
    """The pid a stub wrote to `path`, or None."""
    try:
        return int(read_text(path).strip())
    except ValueError:
        return None


def pid_alive(pid):
    """True while the process runs. A zombie has stopped and waits only to be reaped, so it counts as gone."""
    done = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    state = done.stdout.strip()
    return bool(state) and not state.startswith("Z")


def kill_if_alive(pid):
    """Cleanup for a case's own child, which a failed case may leave running."""
    if pid and pid_alive(pid):
        os.kill(pid, signal.SIGKILL)


def session_start_matchers():
    """The matcher of each SessionStart entry in the repo's settings.json, "" where a group has none."""
    with open(SETTINGS, encoding="utf-8") as handle:
        groups = (json.load(handle).get("hooks") or {}).get("SessionStart") or []
    return [group.get("matcher") or "" for group in groups]


def fires(matcher, source):
    """install.sh's rule: an empty or * matcher fires on any source, any other is an anchored regex on the source."""
    return matcher in ("", "*") or re.fullmatch("(?:%s)" % matcher, source) is not None


class StaleInstall(unittest.TestCase):
    """The cases that run the hook. Each makes its own fixture under the run folder."""

    def assert_unknown(self, run):
        self.assertEqual(len(run.lines), 1, "want one unknown line, got %r; stderr: %s" % (run.lines, run.tail()))
        line = run.lines[0]
        self.assertTrue(line.startswith(UNKNOWN) and line.endswith(")"), "not the unknown line: %r" % line)
        self.assertNotIn("current", line, "the unknown line says current: %r" % line)

    def assert_reinstall_only(self, run, old, new):
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want only the reinstall line; stderr: %s" % run.tail())

    def assert_reinstall_and_restart(self, run, old, new, names):
        restarts = [line for line in run.lines if line.startswith(RESTART)]
        self.assertIn(REINSTALL % (new[:SHORT], old[:SHORT]), run.lines,
                      "no reinstall line; stderr: %s" % run.tail())
        self.assertEqual(len(restarts), 1, "want one restart line, got %r" % restarts)
        for name in names:
            self.assertIn(name, restarts[0], "restart line does not name %r: %r" % (name, restarts[0]))
        self.assertEqual(len(run.lines), 2, "output beyond the reinstall and restart lines: %r" % run.lines)

    def assert_wrote_no_file(self, fx, before):
        rows = fx.changes_since(before)
        self.assertEqual(rows, [], "the prompt changed files: %s" % "; ".join(rows))

    # Behind origin: one reinstall, one read, the recorded installer.

    def test_behind_origin_reinstalls_once_and_names_both_shas(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin is not ahead of the record")
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "want one installer run, with --cloud")
        self.assertEqual([argv[-1] for argv in fx.ls_remote_calls()], ["refs/heads/main"],
                         "the read did not name the recorded ref, or made more than one read")

    def test_second_turn_after_reinstall_is_silent(self):
        fx, old, new = behind(self._testMethodName)
        fx.run_hook()
        self.assertEqual(fx.record_sha(), new, "scope: turn 1 did not reinstall; the record still holds the old sha")
        run = fx.run_hook()
        self.assertEqual(run.lines, [], "turn 2 printed %r, want silence" % run.lines)
        self.assertEqual(len(fx.ls_remote_calls()), 1, "turn 2 made %d ls-remote reads, want 1"
                         % len(fx.ls_remote_calls()))
        self.assertEqual(len(fx.installer_runs()), 1, "turn 2 ran the installer again")

    # Current: one read, no fetch or clone, silence.

    def test_current_makes_one_ls_remote_and_no_install(self):
        fx = current(self._testMethodName)
        self.assertEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin and the record differ")
        run = fx.run_hook()
        self.assertEqual(fx.subcommands(), ["ls-remote"],
                         "git calls were %r, want one ls-remote and no fetch or clone" % fx.subcommands())
        self.assertEqual(run.lines, [], "current install printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "current install ran the installer")

    def test_current_on_stable_reads_the_recorded_ref(self):
        fx = current(self._testMethodName, ref="stable", branches=("stable",))
        fx.advance(HOOK_ONLY)
        self.assertEqual(fx.origin_tip("stable"), fx.record_sha(), "scope: stable is not the recorded sha")
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: main did not move on")
        run = fx.run_hook()
        self.assertEqual([argv[-1] for argv in fx.ls_remote_calls()], ["refs/heads/stable"],
                         "ls-remote reads did not name only the recorded ref")
        self.assertEqual(run.lines, [], "current install on stable printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "current install on stable ran the installer")

    # A prompt that reads origin writes no file. The current tip reads once; a missing record reads nothing.

    def test_current_prompt_makes_one_ls_remote_and_writes_no_file(self):
        fx = current(self._testMethodName)
        self.assertEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin and the record differ")
        before = fx.watched()
        run = fx.run_hook()
        self.assertEqual(run.lines, [], "scope: the current prompt printed %r, want silence" % run.lines)
        self.assertEqual(fx.subcommands(), ["ls-remote"],
                         "git calls were %r, want one ls-remote and no other" % fx.subcommands())
        self.assert_wrote_no_file(fx, before)

    def test_unknown_record_prompt_writes_no_file(self):
        fx = current(self._testMethodName)
        os.remove(fx.record_path)
        self.assertFalse(os.path.exists(fx.record_path), "scope: the record is still there")
        before = fx.watched()
        run = fx.run_hook()
        self.assert_unknown(run)
        calls = fx.subcommands()
        self.assertEqual([call for call in calls if call != "ls-remote"], [],
                         "git calls other than ls-remote: %r" % calls)
        self.assertLessEqual(calls.count("ls-remote"), 1,
                             "the prompt made %d ls-remote reads, want at most 1" % calls.count("ls-remote"))
        self.assert_wrote_no_file(fx, before)

    # Not a cloud session: silent, exit 0, no git.

    def test_not_cloud_is_silent_with_no_git_call(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: the fixture is not behind")
        run = fx.run_hook(cloud=False)
        self.assertEqual(run.rc, 0, "exit code outside a cloud session; stderr: %s" % run.tail())
        self.assertEqual(run.lines, [], "printed %r outside a cloud session" % run.lines)
        self.assertEqual(fx.git_calls(), [], "git ran outside a cloud session: %r" % fx.git_calls())
        self.assertEqual(fx.installer_runs(), [], "the installer ran outside a cloud session")

    # The read cannot run: one unknown line, no install.

    def test_ls_remote_timeout_reports_unknown_and_installs_nothing(self):
        fx, old, new = behind(self._testMethodName)
        run = fx.run_hook(ls_remote="hang", timeout="1")
        self.assertEqual(len(fx.ls_remote_calls()), 1, "the hook made %d ls-remote reads, want 1"
                         % len(fx.ls_remote_calls()))
        self.assert_unknown(run)
        self.assertEqual(fx.installer_runs(), [], "the installer ran after a timed-out read")

    def test_ls_remote_failure_reports_unknown_and_installs_nothing(self):
        fx, old, new = behind(self._testMethodName)
        run = fx.run_hook(ls_remote="fail")
        self.assertEqual(len(fx.ls_remote_calls()), 1, "the hook made %d ls-remote reads, want 1"
                         % len(fx.ls_remote_calls()))
        self.assert_unknown(run)
        self.assertEqual(fx.installer_runs(), [], "the installer ran after a failed read")

    def test_unknown_ref_reports_unknown_and_installs_nothing(self):
        fx, old, new = behind(self._testMethodName, ref="nope")
        self.assertNotIn("refs/heads/nope", fx.git("-C", fx.origin, "for-each-ref", "--format=%(refname)"),
                         "scope: origin has a branch named nope")
        run = fx.run_hook()
        self.assertEqual([argv[-1] for argv in fx.ls_remote_calls()], ["refs/heads/nope"],
                         "the hook did not read the recorded ref")
        self.assert_unknown(run)
        self.assertEqual(fx.installer_runs(), [], "the installer ran for an unknown ref")

    def test_missing_record_reports_unknown_and_installs_nothing(self):
        fx, old, new = behind(self._testMethodName)
        os.remove(fx.record_path)
        self.assertFalse(os.path.exists(fx.record_path), "scope: the record is still there")
        run = fx.run_hook()
        self.assert_unknown(run)
        self.assertEqual(fx.installer_runs(), [], "the installer ran with no record")

    def test_unreadable_record_reports_unknown_and_installs_nothing(self):
        fx, old, new = behind(self._testMethodName)
        with open(fx.record_path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIsNone(fx.record_sha(), "scope: the record still parses")
        run = fx.run_hook()
        self.assert_unknown(run)
        self.assertEqual(fx.installer_runs(), [], "the installer ran with an unreadable record")

    # Restart lines: only for a changed path that a new session must read again.

    def test_changed_claude_md_prints_restart_line(self):
        fx, old, new = behind(self._testMethodName, changes={"CLAUDE.md": "# Rules v2\n"})
        self.assertEqual(fx.changed(old, new), ["CLAUDE.md"], "scope: the change is not CLAUDE.md alone")
        run = fx.run_hook()
        self.assert_reinstall_and_restart(run, old, new, ["CLAUDE.md"])

    def test_changed_output_styles_prints_restart_line(self):
        fx, old, new = behind(self._testMethodName, changes={"output-styles/terse.md": "terse v2\n"})
        self.assertEqual(fx.changed(old, new), ["output-styles/terse.md"], "scope: wrong changed paths")
        run = fx.run_hook()
        self.assert_reinstall_and_restart(run, old, new, ["output-styles/"])

    def test_changed_settings_model_prints_restart_line(self):
        fx, old, new = behind(self._testMethodName, changes={"settings.json": settings_text(model="sonnet-b")})
        self.assertEqual(fx.changed(old, new), ["settings.json"], "scope: wrong changed paths")
        self.assertNotEqual(json.loads(fx.show(old, "settings.json"))["model"],
                            json.loads(fx.show(new, "settings.json"))["model"], "scope: model did not change")
        run = fx.run_hook()
        self.assert_reinstall_and_restart(run, old, new, ["model"])

    def test_changed_settings_effort_level_prints_restart_line(self):
        fx, old, new = behind(self._testMethodName, changes={"settings.json": settings_text(effortLevel="high")})
        self.assertEqual(fx.changed(old, new), ["settings.json"], "scope: wrong changed paths")
        self.assertNotEqual(json.loads(fx.show(old, "settings.json"))["effortLevel"],
                            json.loads(fx.show(new, "settings.json"))["effortLevel"],
                            "scope: effortLevel did not change")
        run = fx.run_hook()
        self.assert_reinstall_and_restart(run, old, new, ["effortLevel"])

    def test_changed_unrelated_settings_key_prints_no_restart_line(self):
        changes = {"settings.json": settings_text(permissions={"allow": ["Bash(ls)", "Bash(cat)"]})}
        fx, old, new = behind(self._testMethodName, changes=changes)
        self.assertEqual(fx.changed(old, new), ["settings.json"], "scope: wrong changed paths")
        before, after = json.loads(fx.show(old, "settings.json")), json.loads(fx.show(new, "settings.json"))
        self.assertEqual([before["model"], before["effortLevel"]], [after["model"], after["effortLevel"]],
                         "scope: model or effortLevel changed")
        run = fx.run_hook()
        self.assert_reinstall_only(run, old, new)

    def test_only_hook_files_changed_prints_no_restart_line(self):
        changes = {"hooks/config_watch.py": "pass  # v2\n", "hooks/stale_helper.py": "pass\n"}
        fx, old, new = behind(self._testMethodName, changes=changes)
        self.assertTrue(all(p.startswith("hooks/") for p in fx.changed(old, new)), "scope: a non-hook path changed")
        run = fx.run_hook()
        self.assert_reinstall_only(run, old, new)

    def test_empty_diff_reinstalls_without_restart_line(self):
        fx, old, new = behind(self._testMethodName, changes={})
        self.assertEqual(fx.changed(old, new), [], "scope: the commit changed paths")
        run = fx.run_hook()
        self.assert_reinstall_only(run, old, new)

    def test_full_size_diff_names_restart_once(self):
        changes = {("hooks/gen_%03d.py" % i): "pass\n" for i in range(250)}
        changes["CLAUDE.md"] = "# Rules v2\n"
        fx, old, new = behind(self._testMethodName, changes=changes)
        self.assertEqual(len(fx.changed(old, new)), 251, "scope: the diff is not 251 paths")
        run = fx.run_hook()
        restarts = [line for line in run.lines if line.startswith(RESTART)]
        self.assertIn(REINSTALL % (new[:SHORT], old[:SHORT]), run.lines, "no reinstall line; stderr: %s" % run.tail())
        self.assertEqual(len(restarts), 1, "want one restart line for 251 paths, got %r" % restarts)
        self.assertIn("CLAUDE.md", restarts[0], "restart line does not name CLAUDE.md: %r" % restarts[0])
        self.assertNotIn("hooks/", restarts[0], "restart line names hook files: %r" % restarts[0])

    # The installer exits non-zero: one failure line, and the installer ran once.

    def test_installer_exit_3_prints_one_failure_line_and_runs_once(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin is not ahead of the record")
        run = fx.run_hook(stub_exit="3")
        self.assertEqual(run.lines, ["claude-settings: reinstall failed (exit 3)"],
                         "want one failure line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "want one installer run, with --cloud")

    # The local diff cannot run: the reinstall still happens, and the restart line says the check is unknown.

    def test_failed_local_diff_prints_restart_unknown_line(self):
        fx, old, new = behind(self._testMethodName)
        run = fx.run_hook(diff="fail")
        diffs = fx.subcommands().count("diff")
        self.assertEqual(diffs, 1, "scope: the hook made %d diff calls, want 1" % diffs)
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT]),
                                     RESTART_UNKNOWN % (old[:SHORT], new[:SHORT])],
                         "want the reinstall line, then the unknown restart line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "want one installer run, with --cloud")

    # Source layouts.

    def test_mirror_layout_reinstalls(self):
        fx, old, new = behind(self._testMethodName, layout="mirror")
        self.assertTrue(fx.source.endswith("claude-settings-main"), "scope: source is not the mirror")
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "want one installer run, with --cloud")

    def test_lane_branch_checkout_installs_only_the_recorded_ref(self):
        fx = Fixture(self._testMethodName)
        old = fx.base
        fx.clone()
        fx.write_record("main", old)
        fx.lane_commit("lane-x")
        new = fx.advance(HOOK_ONLY)
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "--abbrev-ref", "HEAD").strip(), "lane-x",
                         "scope: the source is not on the lane branch")
        run = fx.run_hook()
        self.assertEqual([argv[-1] for argv in fx.ls_remote_calls()], ["refs/heads/main"],
                         "the read did not name only the recorded ref")
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "want one installer run, with --cloud")
        self.assertFalse(any("lane-x" in arg for argv in fx.git_calls() for arg in argv),
                         "git was given the lane branch name: %r" % fx.git_calls())


    # The installer exits 0 but the record still names the old sha: no reinstall line, one line that says so.

    def test_installer_exit_zero_with_the_record_at_the_old_sha_is_not_a_reinstall(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.origin_tip("main"), old, "scope: origin did not move on")
        run = fx.run_hook(record_sha=old)
        self.assertEqual(fx.record_sha(), old, "scope: the installer did not leave the record at the old sha")
        self.assertEqual(fx.installer_runs(), ["--cloud"], "scope: want one installer run, with --cloud")
        self.assertEqual(run.lines, [NOT_REACHED % (new[:SHORT], old[:SHORT])],
                         "want one line that the reinstall did not reach the tip; stderr: %s" % run.tail())

    # The installer's environment: the record's ref, and a hook input that no SessionStart entry fires on.

    def test_installer_gets_the_record_ref_even_when_the_hook_env_names_another(self):
        fx, old, new = behind(self._testMethodName)
        self.assertEqual(fx.ref, "main", "scope: the record does not name main")
        self.assertEqual(fx.hook_env(settings_ref="other")["CLAUDE_SETTINGS_REF"], "other",
                         "scope: the hook env does not name another ref")
        run = fx.run_hook(settings_ref="other")
        seen = fx.installer_env().get("CLAUDE_SETTINGS_REF")
        self.assertEqual(seen, "main",
                         "the installer saw CLAUDE_SETTINGS_REF=%r, want the record's ref main; stderr: %s"
                         % (seen, run.tail()))

    def test_installer_gets_hook_input_that_fires_no_session_start_entry(self):
        fx, old, new = behind(self._testMethodName)
        matchers = session_start_matchers()
        self.assertTrue(matchers, "scope: settings.json has no SessionStart entries to fire")
        run = fx.run_hook()
        raw = fx.installer_env().get("CS_HOOK_INPUT", "unset")
        try:
            source = json.loads(raw)["source"]
        except (ValueError, KeyError, TypeError):
            source = None
        self.assertIsInstance(source, str, "the installer got no hook input with a source (CS_HOOK_INPUT is %r): "
                              "install.sh reads the source as startup, so the startup entries run; stderr: %s"
                              % (raw, run.tail()))
        fired = [matcher for matcher in matchers if fires(matcher, source)]
        self.assertEqual(fired, [], "source %r fires SessionStart entries with matchers %r" % (source, fired))

    # A timeout: the installer gets SIGTERM before SIGKILL, releases its lock, and its child goes with it.

    def test_timeout_sends_term_and_the_installer_releases_its_lock_and_child(self):
        fx, old, new = behind(self._testMethodName)
        write_file(os.path.join(fx.source, "install.sh"), HANG_STUB, mode=0o755)
        self.assertEqual(fx.record_sha(), old, "scope: the record is not the base sha")
        run = fx.run_hook(guard=TIMEOUT_GUARD, reinstall_timeout="1")
        grand = read_pid(fx.grand_path)
        self.addCleanup(kill_if_alive, grand)
        self.assertIsNotNone(grand, "scope: the installer did not start its child; stderr: %s" % run.tail())
        self.assertIsNotNone(run.rc, "the hook ran past %d s: the installer was not stopped at its timeout"
                             % TIMEOUT_GUARD)
        self.assertIn("term", read_text(fx.marks).split(),
                      "the installer got no SIGTERM at its timeout (no TERM mark): the hook sent KILL first")
        self.assertFalse(os.path.exists(fx.lock_path),
                         "the install lock stayed after the timeout: the installer's TERM handler did not release it")
        self.assertFalse(pid_alive(grand), "the installer's child survived the timeout: the group was not signalled")


class StaleInstallBackoff(unittest.TestCase):
    """The attempt stamp. A cloud run that fails, times out or misses the tip leaves the stamp the installer wrote, and
    the hook skips the installer for that same tip within the backoff. The hook never writes the stamp.

    The cases seed the stamp with the stub installer (seed_stamp), so the stamp is the one the installer writes. A case
    that must not block first shows the skip, which a tree without the stamp fails, and then makes its own change to
    the stamp: an age, a garble, a newer tip or a success.
    """

    def assert_skipped(self, run, tip):
        self.assertEqual(len(run.lines), 1, "want one skip line, got %r; stderr: %s" % (run.lines, run.tail()))
        found = SKIPPED.fullmatch(run.lines[0])
        self.assertIsNotNone(found, "not the skip line: %r" % run.lines[0])
        self.assertEqual(found.group(1), tip[:SHORT], "the skip line names the wrong tip: %r" % run.lines[0])
        self.assertTrue(1 <= int(found.group(2)) <= DEFAULT_BACKOFF,
                        "the retry count is outside 1 to %d: %r" % (DEFAULT_BACKOFF, run.lines[0]))

    def seed_stamp(self, fx, tip):
        """The stamp a failed install leaves: one stub run with a tip, failing before its record. Returns the installer
        runs so far, so a case counts only the runs after it."""
        done = fx.run_stub(stale_tip=tip, stub_exit="3")
        self.assertEqual(done.returncode, 3, "scope: the stub did not exit 3: %s" % done.stderr.strip())
        stamp = fx.read_stamp()
        self.assertIsNotNone(stamp, "scope: the stub left no attempt stamp")
        self.assertEqual(stamp.get("tip"), tip, "scope: the attempt stamp does not name the tip")
        return len(fx.installer_runs())

    # A hook-driven failed install: the installer's own stamp holds the next turn to a skip.

    def test_failed_install_skips_the_retry_within_backoff(self):
        fx, old, new = behind(self._testMethodName)
        run = fx.run_hook(stub_exit="3")
        self.assertEqual(fx.installer_runs(), ["--cloud"],
                         "scope: turn 1 did not run the installer once: %r" % run.lines)
        self.assertIsNotNone(fx.read_stamp(), "scope: the failed install left no attempt stamp")
        self.assertEqual(fx.read_stamp().get("tip"), new, "scope: the attempt stamp does not name the tip")
        self.assertEqual(fx.record_sha(), old, "scope: the failed install moved the record")
        run = fx.run_hook()
        self.assertEqual(len(fx.installer_runs()), 1,
                         "turn 2 ran the installer again: %d runs in all" % len(fx.installer_runs()))
        self.assertEqual(fx.subcommands(), ["ls-remote"], "turn 2 made git calls %r, want one ls-remote"
                         % fx.subcommands())
        self.assert_skipped(run, new)

    # The stamp is cleared by a success, and a later tip is not held by it.

    def test_success_clears_the_stamp_and_a_later_stale_tip_reinstalls(self):
        fx, old, new = behind(self._testMethodName)
        self.seed_stamp(fx, new)
        fx.age_stamp(AGED_BY)
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line; stderr: %s" % run.tail())
        self.assertFalse(os.path.exists(fx.stamp_path), "the successful reinstall at the tip left the attempt stamp")
        newer = fx.advance(HOOK_ONLY)
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (newer[:SHORT], new[:SHORT])],
                         "want the reinstall line for the later tip; stderr: %s" % run.tail())

    def test_stamp_for_an_older_tip_does_not_block_a_newer_tip(self):
        fx, old, new = behind(self._testMethodName)
        base = self.seed_stamp(fx, new)
        self.assert_skipped(fx.run_hook(), new)
        newer = fx.advance(HOOK_ONLY)
        self.assertNotEqual(newer, new, "scope: origin did not move on")
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (newer[:SHORT], old[:SHORT])],
                         "want the reinstall of the newer tip; stderr: %s" % run.tail())
        self.assertEqual(len(fx.installer_runs()) - base, 1, "the newer tip ran the installer %d times, want 1"
                         % (len(fx.installer_runs()) - base))

    def test_stamp_older_than_backoff_reinstalls(self):
        fx, old, new = behind(self._testMethodName)
        base = self.seed_stamp(fx, new)
        self.assert_skipped(fx.run_hook(), new)
        fx.age_stamp(AGED_BY)
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line for an aged stamp; stderr: %s" % run.tail())
        self.assertEqual(len(fx.installer_runs()) - base, 1, "the aged stamp ran the installer %d times, want 1"
                         % (len(fx.installer_runs()) - base))

    def test_garbled_stamp_reinstalls_without_a_crash(self):
        garbles = ("{not json", "", "[]", '{"tip": "not-a-sha", "epoch": 1}', '{"tip": "TIP", "epoch": "soon"}')
        for index, text in enumerate(garbles):
            with self.subTest(garbled=text):
                fx, old, new = behind("%s-%d" % (self._testMethodName, index))
                base = self.seed_stamp(fx, new)
                self.assert_skipped(fx.run_hook(), new)
                fx.write_stamp(text.replace("TIP", new))
                run = fx.run_hook()
                self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                                 "garbled stamp %r: want the reinstall line; stderr: %s" % (text, run.tail()))
                self.assertEqual(len(fx.installer_runs()) - base, 1,
                                 "garbled stamp %r: the installer ran %d times, want 1"
                                 % (text, len(fx.installer_runs()) - base))

    # The backoff: the env value replaces 900 when it is a positive number, and only then.

    def test_backoff_override_of_5_reinstalls_a_stamp_10_s_old(self):
        fx, old, new = behind(self._testMethodName)
        base = self.seed_stamp(fx, new)
        self.assert_skipped(fx.run_hook(), new)
        fx.age_stamp(10)
        run = fx.run_hook(backoff="5")
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "backoff 5 did not reinstall a stamp 10 s old; stderr: %s" % run.tail())
        self.assertEqual(len(fx.installer_runs()) - base, 1, "backoff 5 ran the installer %d times, want 1"
                         % (len(fx.installer_runs()) - base))

    def test_invalid_backoff_falls_back_to_900(self):
        for index, value in enumerate(("junk", "0", "-5")):
            with self.subTest(backoff=value):
                fx, old, new = behind("%s-%d" % (self._testMethodName, index))
                base = self.seed_stamp(fx, new)
                self.assert_skipped(fx.run_hook(), new)
                fx.age_stamp(10)
                run = fx.run_hook(backoff=value)
                self.assert_skipped(run, new)
                self.assertEqual(len(fx.installer_runs()) - base, 0,
                                 "backoff %r ran the installer; want the 900 default to skip" % value)

    # The tip the installer gets is the tip the hook read from origin, whatever the hook's environment names.

    def test_hook_passes_the_tip_to_the_installer_as_CS_STALE_TIP(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.record_sha(), new, "scope: the record is at the tip, so the tip is not the record sha")
        run = fx.run_hook()
        seen = fx.installer_env().get("CS_STALE_TIP")
        self.assertEqual(seen, new, "the installer got CS_STALE_TIP=%r, want the origin tip; stderr: %s"
                         % (seen, run.tail()))

    def test_hook_env_naming_another_tip_does_not_reach_the_installer(self):
        fx, old, new = behind(self._testMethodName)
        self.assertEqual(fx.hook_env(stale_tip="bogus")["CS_STALE_TIP"], "bogus",
                         "scope: the hook env does not name another tip")
        run = fx.run_hook(stale_tip="bogus")
        seen = fx.installer_env().get("CS_STALE_TIP")
        self.assertEqual(seen, new, "the installer got CS_STALE_TIP=%r, want the origin tip; stderr: %s"
                         % (seen, run.tail()))

    # A timeout kill is a failure too: the stamp stays, and the next turn skips.

    def test_timeout_kill_leaves_the_stamp_and_the_next_turn_skips(self):
        fx, old, new = behind(self._testMethodName)
        write_file(os.path.join(fx.source, "install.sh"), HANG_STUB, mode=0o755)
        run = fx.run_hook(guard=TIMEOUT_GUARD, reinstall_timeout="1")
        grand = read_pid(fx.grand_path)
        self.addCleanup(kill_if_alive, grand)
        self.assertIsNotNone(run.rc, "the hook ran past %d s: the installer was not stopped at its timeout"
                             % TIMEOUT_GUARD)
        self.assertIsNotNone(grand, "scope: the installer did not start its child; stderr: %s" % run.tail())
        self.assertEqual(run.lines, ["claude-settings: reinstall failed (timed out after 1 s)"],
                         "scope: the install did not time out: %r" % run.lines)
        stamp = fx.read_stamp()
        self.assertIsNotNone(stamp, "the timed-out install left no attempt stamp")
        self.assertEqual(stamp.get("tip"), new, "the attempt stamp does not name the tip")
        run = fx.run_hook()
        self.assertEqual(fx.installer_runs(), ["--cloud"],
                         "turn 2 ran the installer again: %r" % fx.installer_runs())
        self.assertEqual(fx.subcommands(), ["ls-remote"], "turn 2 made git calls %r, want one ls-remote"
                         % fx.subcommands())
        self.assert_skipped(run, new)

    # The skip is a read, not a write: the hook writes no file on a skip turn.

    def test_skip_turn_writes_no_file(self):
        fx, old, new = behind(self._testMethodName)
        self.seed_stamp(fx, new)
        before = fx.watched()
        run = fx.run_hook()
        self.assert_skipped(run, new)
        self.assertEqual(fx.subcommands(), ["ls-remote"], "skip turn made git calls %r, want one ls-remote"
                         % fx.subcommands())
        rows = fx.changes_since(before)
        self.assertEqual(rows, [], "the skip turn changed files: %s" % "; ".join(rows))

    # An installer that exits 0 but leaves the record short of the tip is a failure: the stamp stays.

    def test_exit_zero_with_the_record_short_of_the_tip_keeps_the_stamp(self):
        fx, old, new = behind(self._testMethodName)
        run = fx.run_hook(record_sha=old)
        self.assertEqual(run.lines, [NOT_REACHED % (new[:SHORT], old[:SHORT])],
                         "scope: the record-short install did not print the not-reached line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "scope: turn 1 did not run the installer once")
        stamp = fx.read_stamp()
        self.assertIsNotNone(stamp, "the install that missed the tip left no attempt stamp")
        self.assertEqual(stamp.get("tip"), new, "the attempt stamp does not name the tip")
        run = fx.run_hook()
        self.assertEqual(len(fx.installer_runs()), 1,
                         "turn 2 ran the installer again: %d runs in all" % len(fx.installer_runs()))
        self.assert_skipped(run, new)


class HookFile(unittest.TestCase):
    """Static reads of the hook source and of settings.json. The behaviour cases above prove the rest."""

    def test_hook_source_has_no_literal_main_ref(self):
        text = read_text(HOOK)
        self.assertTrue(text.strip(), "scope: %s has no text to read" % HOOK)
        for needle in ("refs/heads/main", ":-main"):
            self.assertNotIn(needle, text, "the hook names %r literally" % needle)

    def test_hook_is_wired_once_under_user_prompt_submit(self):
        with open(SETTINGS, encoding="utf-8") as handle:
            config = json.load(handle)
        events = []
        for event, groups in (config.get("hooks") or {}).items():
            for group in groups or []:
                for hook in group.get("hooks") or []:
                    if "stale_install" in str(hook.get("command", "")):
                        events.append(event)
        self.assertEqual(events, ["UserPromptSubmit"],
                         "stale_install is wired under %r; want one entry, under UserPromptSubmit" % events)

    def test_docstring_states_the_cost(self):
        try:
            doc = ast.get_docstring(ast.parse(read_text(HOOK))) or ""
        except SyntaxError:
            doc = ""
        missing = [name for name, pattern in COST_TERMS if not re.search(pattern, doc)]
        self.assertEqual(missing, [], "the cost record does not state: %s" % ", ".join(missing))

    # The cost record's Ruling section: the accepted read, its measured figures, and what is not measured.

    def ruling(self):
        text = ruling_text()
        self.assertTrue(text, "scope: the cost record has no Ruling section to read")
        return text

    def test_ruling_is_no_longer_open(self):
        text = self.ruling()
        self.assertFalse("Not ruled" in text, "the Ruling section still says Not ruled")
        self.assertFalse(text.startswith("Open:"), "the Ruling section still opens with the open question")

    def test_ruling_accepts_one_ls_remote_per_cloud_prompt(self):
        text = self.ruling()
        self.assertTrue(re.search(r"(?i)\bruling a\b", text), "the Ruling section does not name ruling a")
        self.assertTrue(re.search(r"(?i)\baccepted\b", text), "ruling a does not say accepted")
        self.assertTrue(re.search(r"(?i)one `?(?:git )?ls-remote`? per cloud prompt", text),
                        "ruling a does not name one ls-remote per cloud prompt")

    def test_ruling_states_the_measured_read_figures(self):
        text = self.ruling()
        self.assertTrue(re.search(r"367 ms[^.]*median|median[^.]*367 ms", text),
                        "the Ruling section has no 367 ms median")
        self.assertTrue(re.search(r"610 ms[^.]*p95|p95[^.]*610 ms", text), "the Ruling section has no 610 ms p95")
        self.assertTrue(re.search(r"20 reads", text), "the Ruling section does not give the 20 reads")

    def test_ruling_says_a_mac_network_is_not_measured(self):
        text = self.ruling()
        self.assertTrue(re.search(r"(?i)mac.s own network is not measured", text),
                        "the Ruling section does not say a Mac's own network is not measured")


class Harness(unittest.TestCase):
    """Controls: they pass on any tree, so a red elsewhere belongs to the hook, not to the fixture."""

    def test_control_fixture_is_behind_and_the_stub_records_the_tip(self):
        fx, old, new = behind(self._testMethodName)
        self.assertEqual(fx.origin_tip("main"), new, "fixture: origin main is not the new commit")
        self.assertEqual(fx.record_sha(), old, "fixture: the record is not the base sha")
        done = fx.run_stub()
        self.assertEqual(done.returncode, 0, "stub installer exited %d: %s" % (done.returncode, done.stderr.strip()))
        self.assertEqual(fx.installer_runs(), ["--cloud"], "stub did not count one --cloud run")
        self.assertEqual(fx.record_sha(), new, "stub did not write the new tip into the record")

    def test_control_git_shim_logs_each_call_and_passes_it_through(self):
        fx = Fixture(self._testMethodName)
        done = subprocess.run([os.path.join(fx.shim_dir, "git"), "ls-remote", fx.origin, "refs/heads/main"],
                              capture_output=True, text=True, cwd=fx.home, env=fx.hook_env())
        self.assertEqual(done.returncode, 0, "shim did not pass ls-remote to git: %s" % done.stderr.strip())
        self.assertIn(fx.origin_tip("main"), done.stdout, "shim output does not carry the origin tip")
        self.assertEqual(fx.git_calls(), [["ls-remote", fx.origin, "refs/heads/main"]],
                         "shim log does not hold the one call")


    def test_control_stub_logs_the_env_it_sees(self):
        fx, old, new = behind(self._testMethodName)
        done = fx.run_stub(settings_ref="other")
        self.assertEqual(done.returncode, 0, "stub installer exited %d: %s" % (done.returncode, done.stderr.strip()))
        seen = fx.installer_env()
        self.assertEqual(seen.get("CLAUDE_SETTINGS_REF"), "other", "stub did not log the ref it was given: %r" % seen)
        self.assertEqual(seen.get("CS_HOOK_INPUT"), "unset", "stub logged a hook input nobody set: %r" % seen)

    def test_control_stub_writes_the_record_sha_it_is_given(self):
        fx, old, new = behind(self._testMethodName)
        done = fx.run_stub(record_sha=old)
        self.assertEqual(done.returncode, 0, "stub installer exited %d: %s" % (done.returncode, done.stderr.strip()))
        self.assertEqual(fx.record_sha(), old, "stub did not write the sha it was given")
        self.assertNotEqual(fx.origin_tip("main"), old, "scope: origin did not move on, so the sha is not stale")

    def test_control_stub_writes_the_stamp_and_a_failed_run_keeps_it(self):
        fx, old, new = behind(self._testMethodName)
        done = fx.run_stub(stale_tip=new, stub_exit="3")
        self.assertEqual(done.returncode, 3,
                         "stub installer exited %d, want 3: %s" % (done.returncode, done.stderr.strip()))
        stamp = fx.read_stamp()
        self.assertIsNotNone(stamp, "stub wrote no attempt stamp for a tip")
        self.assertEqual(stamp.get("tip"), new, "stub stamp names %r, want the tip" % stamp.get("tip"))
        self.assertEqual(fx.record_sha(), old, "the failed stub run moved the record")

    def test_control_stub_clears_the_stamp_when_its_record_lands_at_the_tip(self):
        fx, old, new = behind(self._testMethodName)
        fx.run_stub(stale_tip=new, stub_exit="3")
        self.assertIsNotNone(fx.read_stamp(), "scope: no stamp to clear")
        done = fx.run_stub(stale_tip=new)
        self.assertEqual(done.returncode, 0, "stub installer exited %d: %s" % (done.returncode, done.stderr.strip()))
        self.assertEqual(fx.record_sha(), new, "stub did not write the tip into the record")
        self.assertFalse(os.path.exists(fx.stamp_path), "stub left the stamp after its record landed at the tip")

    def test_control_stub_keeps_the_stamp_when_its_record_misses_the_tip(self):
        fx, old, new = behind(self._testMethodName)
        done = fx.run_stub(stale_tip=new, record_sha=old)
        self.assertEqual(done.returncode, 0, "stub installer exited %d: %s" % (done.returncode, done.stderr.strip()))
        self.assertEqual(fx.record_sha(), old, "scope: stub did not write the sha it was given")
        self.assertIsNotNone(fx.read_stamp(), "stub removed the stamp although its record missed the tip")

    def test_control_stub_writes_no_stamp_without_a_tip(self):
        fx, old, new = behind(self._testMethodName)
        done = fx.run_stub()
        self.assertEqual(done.returncode, 0, "stub installer exited %d: %s" % (done.returncode, done.stderr.strip()))
        self.assertFalse(os.path.exists(fx.stamp_path), "stub wrote a stamp with no tip given")


if __name__ == "__main__":
    unittest.main(verbosity=2)
