#!/usr/bin/env python3
"""Cases for hooks/stale_install.py, the cloud-session check that reinstalls hooks when origin moves on.
Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_reinstall_stale.py

WHAT IT PROVES. In a cloud session a prompt makes no network call. The hook compares the record with the local
origin/main (or the record's ref) tracking ref, and it acts only on a trigger: a local ref that moved past the
record. It refreshes once per new head. A behind pin gets a stale line
that states its commit count. Each action reads the record, then either stays silent when the tip is the recorded
sha, reinstalls once with the recorded installer, or prints one unknown line when the record or the local ref is
missing. An installer that exits non-zero prints one failure line and is not retried. A restart line appears only
for a changed path that a new session must read again, and a local diff that cannot run prints a restart unknown
line.
After an installer run the hook reads the record again. A record that still names the old sha prints one line that
the reinstall did not reach the tip, never a reinstall line. The installer gets the record's ref, and a hook input
that no SessionStart entry fires on. At its timeout the installer gets SIGTERM before SIGKILL, and its child goes
with it.
The hook never names `main` itself, and it is wired once, under UserPromptSubmit.

THE PIN AND THE SHARED CLONE. The live pin is a detached checkout, a linked worktree behind a symlink. Its refs are
read through the worktree's common config, so a current pin is silent and a behind pin gets a verdict, never unknown.
A behind pin gets one stale line that states its commit count, and the pin refresh (merge/install_from_main.sh) runs
once per head. The clone the global rules file points at is read the same way, and a behind one gets a stale line
that names it. No prompt reads origin: decision stale-install-cost, no network lookup on prompts. The refresh
triggers are session start, a resume, and a local origin/main ref move.

OUTSIDE A CLOUD SESSION (class LocalSession, CLAUDE_CODE_REMOTE unset). A trigger refreshes the live pin as a cloud
session does, once per head. A prompt with no trigger reads no origin and makes at most four git reads, and a current
pin is silent. The timeout's stop path must work where os.killpg and signal.SIGKILL do not exist (class PosixOnlyStop).

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
SETTINGS = os.path.join(REPO, "settings.json")
REAL_GIT = shutil.which("git") or "git"
RECORD = ".claude-settings-install.json"
SEEN_NAME = ".claude-settings-refresh-seen"
PAYLOAD = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "test-session", "prompt": "hi"})
# The git subcommands that reach origin. A prompt makes none of them.
NETWORK = ("ls-remote", "fetch", "clone", "pull")
HOOK_GUARD = 60  # seconds: stops a hook that never returns, so a broken build fails instead of hanging CI
SHORT = 7
REINSTALL = "claude-settings: reinstalled hooks at %s (was %s)"
UNKNOWN = "claude-settings: install freshness unknown ("
PREFIX = "claude-settings: "
RESTART = "claude-settings: restart needed for:"
RESTART_UNKNOWN = "claude-settings: restart check unknown (could not diff %s..%s)"
NOT_REACHED = "claude-settings: reinstall did not reach %s (record at %s)"
# A timeout case waits out the installer bound the hook has on the code under test (100 s), so its guard sits above.
TIMEOUT_GUARD = 130
GIT_LOCATORS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX")
HOOK_ENV_DROP = GIT_LOCATORS + ("CLAUDE_CODE_REMOTE", "CLAUDE_CONFIG_DIR", "CLAUDE_SETTINGS_FETCH_TIMEOUT",
                                "CLAUDE_SETTINGS_REF", "CLAUDE_SETTINGS_REINSTALL_TIMEOUT", "CS_HOOK_INPUT",
                                "GIT_SHIM_LS_REMOTE", "GIT_SHIM_DIFF", "STUB_EXIT", "STUB_RECORD_SHA",
                                "STUB_REFRESH_COUNTER")
HOOK_ONLY = {"hooks/config_watch.py": "pass  # tweak\n"}
COST_TERMS = (
    ("the process starts", r"(?i)process(?:es)? starts?|python starts?|starts? (?:one|a|1) python"),
    ("the network calls per prompt", r"(?i)network calls?[^\n]{0,80}per prompt|per prompt[^\n]{0,80}network calls?"),
    ("the frequency", r"(?i)per prompt|per turn|each turn|every turn"),
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

# Stands in for install.sh: counts each run, logs the CLAUDE_SETTINGS_REF and CS_HOOK_INPUT it saw, fetches origin
# as the real installer does, and writes the install record when STUB_WRITE_RECORD is set. When STUB_EXIT is set it
# exits with that code first, before the fetch and the record. When STUB_RECORD_SHA is set it writes that sha and
# exits 0 with no fetch: an installer whose fetch failed after the hook's trigger reached it.
STUB = r'''#!/bin/sh
here=$(cd "$(dirname "$0")" && pwd -P)
printf '%s\n' "$*" >> "$STUB_COUNTER"
printf 'CLAUDE_SETTINGS_REF=%s\n' "${CLAUDE_SETTINGS_REF-unset}" >> "$STUB_ENV_LOG"
printf 'CS_HOOK_INPUT=%s\n' "${CS_HOOK_INPUT-unset}" >> "$STUB_ENV_LOG"
[ -n "$STUB_EXIT" ] && exit "$STUB_EXIT"
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
fi
'''

# Stands in for an install that holds the install lock when the hook stops it. Its TERM trap waits for the child it
# started, then writes a "term" mark and releases the lock. The wait ends only once that child has exited, so a
# "term" mark means the child was signalled too.
HANG_STUB = r'''#!/bin/sh
lock="$CLAUDE_CONFIG_DIR/.claude-settings-install.lock"
( set -C; printf '%s\n' "$$" > "$lock" ) 2>/dev/null || exit 1
sleep 300 >/dev/null 2>&1 &
grand=$!
printf '%s\n' "$grand" > "$STUB_GRAND"
trap 'wait "$grand" 2>/dev/null; printf "term\n" >> "$STUB_MARK"; rm -f "$lock"; exit 143' TERM
wait "$grand"
'''


# Stands in for merge/install_from_main.sh, the pin refresh. It counts each run and moves nothing: the pin and the
# record stay where they are, so a second prompt on the same head finds the same behind pin. It also logs the path
# it was started from ($0), so a case can tell a run through the live pin's link from a run through its target.
REFRESH_STUB = r'''#!/bin/sh
printf '%s\n' "$*" >> "$STUB_REFRESH_COUNTER"
printf '%s\n' "$0" >> "$STUB_REFRESH_COUNTER.where"
'''

# Stands in for a pin refresh that fails. It counts the run, then checks out the head it is given. A checkout that
# tracked changes block exits 1 before the move; a checkout that gets past the move exits 1 after it.
REFRESH_FAIL_STUB = r'''#!/bin/sh
printf '%s\n' "$*" >> "$STUB_REFRESH_COUNTER"
git checkout -q --detach "$1" || exit 1
exit 1
'''

# Runs the hook with os.killpg and signal.SIGKILL removed, as on Windows, where neither exists. The hook's own folder
# goes first on sys.path, so its `import _nowindow` resolves as it does in a real run.
NO_POSIX_SHIM = r'''import os, runpy, signal, sys
del os.killpg, signal.SIGKILL
sys.path.insert(0, os.path.dirname(sys.argv[1]))
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
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


# A string that names the main branch as a word: "main", "refs/heads/main", "origin/main" or ":-main".
# A word inside a longer name, such as install_from_main.sh or __main__, does not match.
MAIN_REF = re.compile(r"(?<![\w.])(?:refs/heads/|origin/|:-)?main(?![\w.-])")


def code_string_nodes(tree):
    """The str constants of the code. A docstring is prose, so it is left out. The parse is ast's, so a comment
    never reads as code."""
    prose = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                prose.add(id(first.value))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose]


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
        self.refresh_counter = os.path.join(self.root, "refresh-runs.txt")
        self.grand_path = os.path.join(self.root, "installer-child.pid")
        self.lock_path = os.path.join(self.config, ".claude-settings-install.lock")
        self.record_path = os.path.join(self.config, RECORD)
        self.seen_path = os.path.join(self.config, SEEN_NAME)
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
                 record_sha=None, reinstall_timeout=None):
        env = dict(os.environ)
        for key in HOOK_ENV_DROP:
            env.pop(key, None)
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.config,
                   PATH=self.shim_dir + os.pathsep + os.environ.get("PATH", ""),
                   GIT_SHIM_REAL=REAL_GIT, GIT_SHIM_LOG=self.git_log,
                   GIT_CONFIG_GLOBAL=self.gitconfig, GIT_CONFIG_NOSYSTEM="1",
                   STUB_COUNTER=self.counter, STUB_REF=self.ref, STUB_WRITE_RECORD="1",
                   STUB_ENV_LOG=self.env_log, STUB_MARK=self.marks, STUB_GRAND=self.grand_path,
                   STUB_REFRESH_COUNTER=self.refresh_counter)
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

    def child_commit(self, rev):
        """A commit on top of `rev`, written into the source's objects and held by no ref: the clone can read it, and
        no fetch moves a ref to it."""
        tree = self.sha(self.source, rev + "^{tree}")
        return self.git("-C", self.source, "commit-tree", tree, "-p", rev, "-m", "unreffed").strip()

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

    def run_hook(self, guard=HOOK_GUARD, no_posix=False, **options):
        """One hook run. The hook gets its own session and writes its output to files, so a stop at `guard`
        seconds ends the hook and everything it started, and the stop cannot hang on a pipe a child holds.
        `no_posix` runs it with os.killpg and signal.SIGKILL absent, as on Windows."""
        for path in (self.git_log, self.env_log):
            open(path, "w", encoding="utf-8").close()  # each run's calls start empty
        out_path = os.path.join(self.root, "hook-out.txt")
        err_path = os.path.join(self.root, "hook-err.txt")
        argv = [sys.executable, "-c", NO_POSIX_SHIM, HOOK] if no_posix else [sys.executable, HOOK]
        with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
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


def behind(name, changes=HOOK_ONLY, layout="checkout", ref="main", fetch=True):
    """A cloud fixture whose record holds the base sha while origin has moved on by one commit. The source then
    fetches, which moves its local ref: that move is the trigger a prompt acts on. `fetch=False` leaves it unmoved."""
    fx = Fixture(name)
    old = fx.base
    fx.clone(layout)
    fx.write_record(ref, old)
    new = fx.advance(changes)
    if fetch:
        fx.git("-C", fx.source, "fetch", "-q", "origin")
    return fx, old, new


def current(name, ref="main", branches=()):
    """A cloud fixture whose record holds origin's tip for `ref`."""
    fx = Fixture(name, branches=branches)
    fx.clone()
    fx.write_record(ref, fx.base)
    return fx


COMMITS_BEHIND = re.compile(r"(\d+) commits? behind|behind by (\d+) commits?")


def commits_behind(line):
    """The commit count a line states as behind, or None when it states none."""
    found = COMMITS_BEHIND.search(line)
    return int(found.group(1) or found.group(2)) if found else None


def refresh_runs(fx):
    """Each run of the pin refresh stub so far. The counter keeps every turn's runs."""
    try:
        with open(fx.refresh_counter, encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle if line.strip()]
    except OSError:
        return []


def refresh_where(fx):
    """The path each pin refresh run was started from, as the stub logged it ($0), in run order."""
    try:
        with open(fx.refresh_counter + ".where", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle if line.strip()]
    except OSError:
        return []


def install_refresh(fx, text=REFRESH_STUB):
    """Puts the refresh stub where the record's source keeps merge/install_from_main.sh."""
    write_file(os.path.join(fx.source, "merge", "install_from_main.sh"), text, mode=0o755)


def detached(name, behind_by=0):
    """A cloud fixture whose record source is a clone detached at the recorded sha, as the live pin is kept.
    The source's origin is a plain clone's, so the read of it cannot fail for a layout reason. origin moves on
    by `behind_by` commits."""
    fx = Fixture(name)
    old = fx.base
    fx.clone()
    fx.git("-C", fx.source, "checkout", "-q", "--detach", old)
    fx.write_record("main", old)
    for _ in range(behind_by):
        fx.advance({})
    return fx, old


def linked_pin(name, behind_by=0):
    """A cloud fixture whose record source is the live pin's link: <clone>-live, a symlink to <clone>-live-<12 hex>,
    a locked worktree detached at the recorded sha, as install_from_main.sh makes it. origin moves on by
    `behind_by` commits."""
    fx = Fixture(name)
    old = fx.base
    fx.clone()
    pin = fx.source + "-live-" + old[:12]
    fx.git("-C", fx.source, "worktree", "add", "--detach", pin, old)
    fx.git("-C", fx.source, "worktree", "lock", "--reason", "claude-settings live pin", pin)
    link = fx.source + "-live"
    os.symlink(pin, link)
    fx.source = link
    fx.write_record("main", old)
    for _ in range(behind_by):
        fx.advance({})
    return fx, old, pin


def shared_behind(name, behind_by=0):
    """A cloud fixture whose record source is current, plus the clone the global rules file points at. That clone
    is made before origin moves on by `behind_by` commits, so it is behind by that many."""
    fx = Fixture(name)
    shared = os.path.join(fx.home, "shared", "claude-settings")
    os.makedirs(os.path.dirname(shared))
    fx.git("clone", "-q", fx.origin, shared)
    base = fx.base
    for _ in range(behind_by):
        fx.advance({})
    fx.git("-C", shared, "fetch", "-q", "origin")
    fx.clone()
    fx.write_record("main", fx.origin_tip("main"))
    write_file(os.path.join(fx.config, "CLAUDE.md"), "@%s/CLAUDE.md\n" % shared)
    return fx, shared, base


def no_trigger_worst(name):
    """A cloud fixture with no trigger that makes the most reads: the record is ahead of the local origin/main ref, so
    the prompt reads ancestry, and the clone the global rules file points at is current with its own origin ref. The
    record is ahead of the ref, so no trigger fires. The clone's count is zero, so no flag fires either."""
    fx, shared, base = shared_behind(name)
    fx.write_record("main", fx.child_commit(base))
    return fx, shared


def check_no_trigger_calls(case, fx, cloud):
    """A no-trigger prompt makes at most four git reads, and none of them reaches origin. One step for the cloud and
    the local case: the same fixture, run with the same bound."""
    case.assertNotEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), fx.record_sha(),
                        "scope: the record is not ahead of the local origin/main ref")
    fx.run_hook(cloud=cloud)
    calls = fx.subcommands()
    case.assertTrue(calls, "scope: the prompt made no git call, so the count proves nothing")
    case.assertLessEqual(len(calls), 4, "a no-trigger prompt made %d git calls, want at most 4: %r" % (len(calls), calls))
    case.assertEqual(network_reads(fx), [], "a no-trigger prompt read origin: %r" % calls)


def check_no_trigger_seen(case, fx, shared, cloud):
    """A no-trigger prompt writes no seen file and no other file in the config dir."""
    case.assertNotEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), fx.record_sha(),
                        "scope: the record is not ahead of the local origin/main ref")
    case.assertEqual(fx.sha(shared, "HEAD"), fx.sha(shared, "refs/remotes/origin/main"),
                     "scope: the shared clone is not current with its own origin ref")
    case.assertFalse(os.path.exists(fx.seen_path), "scope: the seen file exists before the prompt")
    before = sorted(os.listdir(fx.config))
    fx.run_hook(cloud=cloud)
    case.assertFalse(os.path.exists(fx.seen_path), "a no-trigger prompt wrote the seen file")
    case.assertEqual(sorted(os.listdir(fx.config)), before, "a no-trigger prompt wrote a file in the config dir")


def network_reads(fx):
    """Each network read the last hook run made: a lookup or a fetch of origin."""
    return [name for name in fx.subcommands() if name in NETWORK]


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

    # A prompt reads no origin (decision stale-install-cost). The refresh triggers are a local origin/main ref
    # move, and session start, whose SessionStart fetch this hook does not run.

    # Behind origin, after a local fetch: one reinstall, no lookup, the recorded installer.

    def test_behind_origin_reinstalls_once_and_names_both_shas(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin is not ahead of the record")
        run = fx.run_hook()
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line; stderr: %s" % run.tail())
        self.assertEqual(fx.installer_runs(), ["--cloud"], "want one installer run, with --cloud")
        self.assertEqual(fx.ls_remote_calls(), [], "the prompt looked up origin: %r" % fx.subcommands())

    def test_second_turn_after_reinstall_is_silent(self):
        fx, old, new = behind(self._testMethodName)
        fx.run_hook()
        self.assertEqual(fx.record_sha(), new, "scope: turn 1 did not reinstall; the record still holds the old sha")
        run = fx.run_hook()
        self.assertEqual(run.lines, [], "turn 2 printed %r, want silence" % run.lines)
        self.assertEqual(network_reads(fx), [], "turn 2 read origin: %r, want none" % fx.subcommands())
        self.assertEqual(len(fx.installer_runs()), 1, "turn 2 ran the installer again")

    # Current: no read of origin on the prompt, silence.

    def test_current_prompt_makes_no_network_read_and_no_install(self):
        fx = current(self._testMethodName)
        self.assertEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin and the record differ")
        run = fx.run_hook()
        self.assertEqual(network_reads(fx), [], "a current prompt read origin: %r, want none" % fx.subcommands())
        self.assertEqual(run.lines, [], "current install printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "current install ran the installer")

    def test_current_stable_record_ignores_a_moved_main(self):
        fx = current(self._testMethodName, ref="stable", branches=("stable",))
        fx.advance(HOOK_ONLY)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        self.assertEqual(fx.origin_tip("stable"), fx.record_sha(), "scope: stable is not the recorded sha")
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: main did not move on")
        run = fx.run_hook()
        self.assertEqual(network_reads(fx), [], "a prompt read origin: %r, want none" % fx.subcommands())
        self.assertEqual(run.lines, [], "current install on stable printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "current install on stable ran the installer")

    # Not a cloud session: the live pin is refreshed on a trigger, as a cloud session refreshes it. The old case
    # (silent, no git call) no longer holds: the local ref moved, so this prompt is a trigger. Kept: exit 0, no lookup
    # of origin, and no installer run for a pin. The rest of the local rules are in class LocalSession.

    def test_not_cloud_pin_behind_refreshes_once_with_exit_zero_and_no_lookup(self):
        fx, old = detached(self._testMethodName, behind_by=1)
        install_refresh(fx)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        new = fx.origin_tip("main")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), new,
                         "scope: the local origin/main ref did not move")
        run = fx.run_hook(cloud=False)
        self.assertEqual(run.rc, 0, "exit code outside a cloud session; stderr: %s" % run.tail())
        self.assertEqual(refresh_runs(fx), [new], "outside a cloud session the pin refresh ran %r, want once at %s"
                         % (refresh_runs(fx), new[:SHORT]))
        self.assertEqual(network_reads(fx), [], "a local prompt read origin: %r" % fx.subcommands())
        self.assertEqual(fx.installer_runs(), [], "the installer ran for a pin outside a cloud session")

    # A hanging or failing origin is not read on a prompt, so it cannot stall one or print an unknown line.

    def test_hanging_origin_is_not_read_on_a_prompt(self):
        fx, old, new = behind(self._testMethodName, fetch=False)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin is not ahead of the record")
        run = fx.run_hook(ls_remote="hang", timeout="1")
        self.assertEqual(network_reads(fx), [], "a prompt read origin: %r, want none" % fx.subcommands())
        self.assertEqual(run.lines, [], "a hanging origin printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "the installer ran on a prompt with no trigger")

    def test_failing_origin_is_not_read_on_a_prompt(self):
        fx, old, new = behind(self._testMethodName, fetch=False)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin is not ahead of the record")
        run = fx.run_hook(ls_remote="fail")
        self.assertEqual(network_reads(fx), [], "a prompt read origin: %r, want none" % fx.subcommands())
        self.assertEqual(run.lines, [], "a failing origin printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "the installer ran on a prompt with no trigger")

    # A local ref that names no branch of origin's is unknown, and no read of origin is made to find out.

    def test_unknown_ref_reports_unknown_without_a_read(self):
        fx, old, new = behind(self._testMethodName, ref="nope")
        self.assertNotIn("refs/heads/nope", fx.git("-C", fx.origin, "for-each-ref", "--format=%(refname)"),
                         "scope: origin has a branch named nope")
        run = fx.run_hook()
        self.assertEqual(network_reads(fx), [], "a prompt read origin: %r, want none" % fx.subcommands())
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

    # A failed reinstall is not retried for the same head, and a later prompt on that head still reports the install as
    # stale. A fixture installer that exits 1 stands in for a reinstall that cannot run (a held lock, a mirror that
    # cannot refresh).

    def test_failed_reinstall_runs_once_per_head_and_later_prompts_stay_stale(self):
        fx, old, new = behind(self._testMethodName)
        self.assertNotEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin is not ahead of the record")
        fx.run_hook(stub_exit="1")
        self.assertEqual(fx.installer_runs(), ["--cloud"], "scope: the first prompt did not run the installer once")
        run = fx.run_hook(stub_exit="1")
        self.assertEqual(fx.installer_runs(), ["--cloud"],
                         "the failed reinstall ran %d times for one head, want once" % len(fx.installer_runs()))
        self.assertTrue(run.lines, "the second prompt on the same head printed nothing: the stale install went silent")

    def test_failed_reinstall_is_tried_again_when_a_new_head_arrives(self):
        fx, old, new = behind(self._testMethodName)
        fx.run_hook(stub_exit="1")
        self.assertEqual(fx.installer_runs(), ["--cloud"], "scope: the first prompt did not run the installer once")
        newer = fx.advance(HOOK_ONLY)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), newer,
                         "scope: the local origin/main ref did not move to the newer head")
        fx.run_hook(stub_exit="1")
        self.assertEqual(len(fx.installer_runs()), 2,
                         "a new head ran the installer %d times in all, want 2" % len(fx.installer_runs()))

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
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "--abbrev-ref", "HEAD").strip(), "lane-x",
                         "scope: the source is not on the lane branch")
        run = fx.run_hook()
        self.assertEqual(fx.ls_remote_calls(), [], "the prompt looked up origin: %r" % fx.git_calls())
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

    # The installer leaves the record past the target the hook read: origin moved on again before the installer ran. The
    # record holds the target, so the reinstall reached it. The hook prints a reinstalled line and the restart line, and
    # never "did not reach". The fixture writes the record sha itself, as the installer's record would hold it.

    def test_record_past_the_target_reads_as_reinstalled(self):
        fx, old, new = behind(self._testMethodName, changes={"CLAUDE.md": "# Rules v2\n"})
        past = fx.child_commit(new)
        self.assertEqual(fx.sha(fx.source, past + "^"), new, "scope: the commit past the target does not build on it")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), new,
                         "scope: the local origin/main ref is not the target")
        run = fx.run_hook(record_sha=past)
        self.assertEqual(fx.record_sha(), past, "scope: the installer did not leave the record past the target")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), new,
                         "scope: the installer moved the local origin/main ref")
        self.assertFalse([line for line in run.lines if "did not reach" in line],
                         "the record holds the target, yet the hook says the reinstall did not reach it: %r"
                         % run.lines)
        reinstalled = [line for line in run.lines if line.startswith(PREFIX + "reinstalled hooks at ")]
        self.assertEqual(len(reinstalled), 1, "want one reinstalled line, got %r; stderr: %s"
                         % (run.lines, run.tail()))
        self.assertTrue(reinstalled[0].endswith("(was %s)" % old[:SHORT]),
                        "the reinstalled line does not name the old sha: %r" % reinstalled[0])
        restarts = [line for line in run.lines if line.startswith(RESTART)]
        self.assertEqual(len(restarts), 1, "want one restart line, got %r" % restarts)
        self.assertIn("CLAUDE.md", restarts[0], "the restart line does not name CLAUDE.md: %r" % restarts[0])
        self.assertEqual(len(run.lines), 2, "output beyond the reinstalled and restart lines: %r" % run.lines)

    # The record holds a commit the local origin ref has not reached. The record covers the ref by ancestry, so the
    # prompt is silent and runs no installer.

    def test_record_ahead_of_the_local_ref_is_silent_with_no_install(self):
        fx = current(self._testMethodName)
        ahead = fx.child_commit(fx.base)
        fx.write_record("main", ahead)
        self.assertEqual(fx.sha(fx.source, ahead + "^"), fx.base, "scope: the record does not build on the local ref")
        self.assertNotEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), ahead,
                            "scope: the record is not ahead of the local origin/main ref")
        run = fx.run_hook()
        self.assertEqual(run.lines, [], "a record ahead of the local ref printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "a record ahead of the local ref ran the installer")

    # A prompt with no trigger writes no file. The seen file records a head that a reinstall, a pin refresh or a clone
    # flag acted on, so a prompt that acts on none of them leaves the config dir as it was. This is the worst no-trigger
    # prompt: the record ahead of the local ref, and the shared clone current.

    def test_no_trigger_prompt_writes_no_seen_file(self):
        fx, shared = no_trigger_worst(self._testMethodName)
        check_no_trigger_seen(self, fx, shared, cloud=True)

    # A no-trigger prompt makes at most four git reads, and none of them reaches origin. The worst one is the one the
    # helper builds: the ancestry read of the local ref, then the shared clone's ref and its count.

    def test_no_trigger_prompt_makes_at_most_four_git_calls_and_no_network_read(self):
        fx, shared = no_trigger_worst(self._testMethodName)
        check_no_trigger_calls(self, fx, cloud=True)

    # The seen file keeps the last twenty heads. It starts with twenty-five older heads, so a reinstall on a new head
    # both adds one and drops the oldest six. The expected list is written out here, not read from the hook.

    def test_seen_file_keeps_the_last_twenty_heads(self):
        fx, old, new = behind(self._testMethodName)
        older = ["install:%040x" % number for number in range(1, 26)]
        write_file(fx.seen_path, "".join(key + "\n" for key in older))
        self.assertEqual(read_text(fx.seen_path).splitlines(), older,
                         "scope: the seen file does not start with the 25 older heads")
        fx.run_hook()
        self.assertEqual(fx.installer_runs(), ["--cloud"], "scope: the new head did not run the installer once")
        self.assertEqual(read_text(fx.seen_path).splitlines(), older[6:] + ["install:" + new],
                         "the seen file does not hold the last 20 heads, newest last")

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


    # The trigger: a local origin/main ref move. It reads no origin on the prompt itself; the refresh it starts is the
    # only network work.

    def test_local_ref_move_triggers_the_refresh_with_no_lookup(self):
        fx, old, new = behind(self._testMethodName)
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), new,
                         "scope: the local origin/main ref did not move")
        run = fx.run_hook(ls_remote="fail")
        self.assertEqual(fx.installer_runs(), ["--cloud"],
                         "the local ref move did not refresh: installer runs %r, want one --cloud run"
                         % fx.installer_runs())
        self.assertEqual(run.lines, [REINSTALL % (new[:SHORT], old[:SHORT])],
                         "want the reinstall line; stderr: %s" % run.tail())
        self.assertEqual(fx.ls_remote_calls(), [], "the prompt looked up origin: %r" % fx.git_calls())

    def test_prompt_with_no_trigger_reads_no_origin(self):
        fx, old, new = behind(self._testMethodName, fetch=False)
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), old,
                         "scope: the local origin/main ref moved without a fetch")
        run = fx.run_hook()
        self.assertEqual(network_reads(fx), [], "a prompt with no trigger read origin: %r, want none"
                         % fx.subcommands())
        self.assertEqual(run.lines, [], "a prompt with no trigger printed %r, want silence" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "a prompt with no trigger ran the installer")

    # The live pin: a detached checkout. A local ref move refreshes it once per head, and its stale line states the
    # commit count from the local objects, so the prompt itself reads nothing.

    def test_behind_pin_stale_line_names_its_commit_count(self):
        fx, old = detached(self._testMethodName, behind_by=24)
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "--abbrev-ref", "HEAD").strip(), "HEAD",
                         "scope: the source is not detached")
        counted = int(fx.git("-C", fx.seed, "rev-list", "--count", "%s..%s" % (old, fx.origin_tip("main"))))
        self.assertEqual(counted, 24, "scope: the pin is not 24 commits behind origin")
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        install_refresh(fx)
        run = fx.run_hook()
        stale = [line for line in run.lines if line.startswith(PREFIX) and commits_behind(line) is not None]
        self.assertEqual(len(stale), 1, "want one line that states the commits behind, got %r; stderr: %s"
                         % (run.lines, run.tail()))
        self.assertEqual(commits_behind(stale[0]), 24, "the stale line states %r commits behind, want 24: %r"
                         % (commits_behind(stale[0]), stale[0]))

    def test_behind_pin_refreshes_once_per_head(self):
        fx, old = detached(self._testMethodName, behind_by=24)
        install_refresh(fx)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        fx.run_hook()
        self.assertEqual(len(refresh_runs(fx)), 1, "the local ref move ran the pin refresh %d times, want 1"
                         % len(refresh_runs(fx)))
        fx.run_hook()
        self.assertEqual(network_reads(fx), [], "a prompt with no trigger read origin: %r" % fx.subcommands())
        self.assertEqual(len(refresh_runs(fx)), 1, "a prompt with no trigger ran the pin refresh again: %d runs in all, "
                         "want 1" % len(refresh_runs(fx)))
        fx.advance({})
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        fx.run_hook()
        self.assertEqual(len(refresh_runs(fx)), 2, "a new head ran the pin refresh %d times in all, want 2"
                         % len(refresh_runs(fx)))

    # A failed pin refresh marks its head as tried. A later prompt on that head reruns nothing, and it must not go silent.

    def test_pin_move_blocked_by_tracked_changes_stays_stale_on_later_prompts(self):
        fx, old = detached(self._testMethodName)
        fx.advance({"CLAUDE.md": "# Rules v2\n"})
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        write_file(os.path.join(fx.source, "CLAUDE.md"), "# local edit\n")
        self.assertTrue(fx.git("-C", fx.source, "status", "--porcelain", "--untracked-files=no").strip(),
                        "scope: the pin has no tracked change")
        install_refresh(fx, REFRESH_FAIL_STUB)
        fx.run_hook()
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "HEAD").strip(), old,
                         "scope: the pin moved despite its tracked change")
        self.assertEqual(len(refresh_runs(fx)), 1,
                         "scope: the first prompt ran the pin refresh %d times, want 1" % len(refresh_runs(fx)))
        run = fx.run_hook()
        self.assertTrue(run.lines, "the second prompt on the same head printed nothing: the failed pin move went silent")
        self.assertEqual(len(refresh_runs(fx)), 1,
                         "a later prompt reran the pin refresh: %d runs in all, want 1" % len(refresh_runs(fx)))

    def test_installer_failure_after_the_pin_moved_stays_stale_on_later_prompts(self):
        fx, old = detached(self._testMethodName)
        new = fx.advance({"CLAUDE.md": "# Rules v2\n"})
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        install_refresh(fx, REFRESH_FAIL_STUB)
        fx.run_hook()
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "HEAD").strip(), new,
                         "scope: the pin did not move to the head before the installer failed")
        self.assertEqual(len(refresh_runs(fx)), 1,
                         "scope: the first prompt ran the pin refresh %d times, want 1" % len(refresh_runs(fx)))
        run = fx.run_hook()
        self.assertTrue(run.lines, "the second prompt on the same head printed nothing: the failed install went silent")
        self.assertEqual(len(refresh_runs(fx)), 1,
                         "a later prompt reran the pin refresh: %d runs in all, want 1" % len(refresh_runs(fx)))

    # A linked worktree as the live pin is kept: its refs read through the common config, so no verdict is unknown.

    def test_linked_pin_current_is_silent_with_no_read(self):
        fx, old, pin = linked_pin(self._testMethodName)
        self.assertTrue(os.path.isfile(os.path.join(pin, ".git")),
                        "scope: the pin's .git is not a file: no linked worktree")
        self.assertEqual(os.path.realpath(fx.source), os.path.realpath(pin),
                         "scope: the source link does not reach the pin")
        self.assertEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin and the record differ")
        run = fx.run_hook()
        self.assertEqual(run.lines, [], "current linked pin printed %r, want silence; stderr: %s"
                         % (run.lines, run.tail()))
        self.assertEqual(network_reads(fx), [], "a prompt read origin: %r, want none" % fx.subcommands())

    def test_linked_pin_behind_gets_a_verdict_not_unknown(self):
        fx, old, pin = linked_pin(self._testMethodName)
        new = fx.advance(HOOK_ONLY)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        self.assertTrue(os.path.isfile(os.path.join(pin, ".git")),
                        "scope: the pin's .git is not a file: no linked worktree")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), new,
                         "scope: the local origin/main ref did not move")
        install_refresh(fx)
        run = fx.run_hook()
        unknown = [line for line in run.lines if line.startswith(UNKNOWN)]
        self.assertEqual(unknown, [], "the behind linked pin reads as unknown: %r; stderr: %s"
                         % (unknown, run.tail()))
        self.assertTrue(run.lines, "the behind linked pin printed no verdict line")

    # origin has no stable: the pin follows local main (merge/install_from_main.sh, pin_commit), so the check reads local
    # main and gives a verdict. It reads no origin/main here, which holds the old commit.

    def test_missing_origin_stable_reads_local_main_for_a_verdict(self):
        fx, old = detached(self._testMethodName)
        fx.write_record("stable", old)
        new = fx.advance(HOOK_ONLY)
        fx.git("-C", fx.source, "fetch", "-q", fx.origin, "+refs/heads/main:refs/heads/main")
        self.assertNotIn("refs/heads/stable", fx.git("-C", fx.origin, "for-each-ref", "--format=%(refname)"),
                         "scope: origin has a stable branch")
        self.assertNotIn("refs/remotes/origin/stable", fx.git("-C", fx.source, "for-each-ref", "--format=%(refname)"),
                         "scope: the source has a local origin/stable")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/heads/main").strip(), new,
                         "scope: local main did not move to the new commit")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), old,
                         "scope: origin/main moved too, so local main is not the only new ref")
        install_refresh(fx)
        run = fx.run_hook()
        unknown = [line for line in run.lines if "unknown" in line]
        self.assertEqual(unknown, [], "the stable record reads as unknown with origin/stable absent: %r; stderr: %s"
                         % (unknown, run.tail()))
        self.assertEqual(refresh_runs(fx), [new],
                         "the check did not act on local main's tip: pin refresh runs %r, want one at %s"
                         % (refresh_runs(fx), new[:SHORT]))
        self.assertIn(1, [commits_behind(line) for line in run.lines],
                      "no line states the commits behind local main: %r" % run.lines)

    # The clone the global rules file points at: its own local origin/main ref, against its HEAD.

    def test_behind_shared_clone_is_flagged_with_its_commit_count(self):
        fx, shared, base = shared_behind(self._testMethodName, behind_by=2)
        self.assertEqual(fx.sha(shared, "HEAD"), base, "scope: the shared clone is not at the base")
        self.assertNotEqual(fx.sha(shared, "refs/remotes/origin/main"), base,
                            "scope: the shared clone's local origin/main ref did not move")
        self.assertEqual(fx.record_sha(), fx.origin_tip("main"), "scope: the record is not current")
        run = fx.run_hook()
        flagged = [line for line in run.lines if os.path.realpath(shared) in line and commits_behind(line) is not None]
        self.assertEqual(len(flagged), 1, "want one line that flags the shared clone with its commits behind, got %r; "
                         "stderr: %s" % (run.lines, run.tail()))
        self.assertEqual(commits_behind(flagged[0]), 2, "the shared clone's line states %r commits behind, want 2: %r"
                         % (commits_behind(flagged[0]), flagged[0]))
        outside = [argv for argv in fx.git_calls() if any(REPO in arg for arg in argv)]
        self.assertEqual(outside, [], "the hook ran git on a clone outside the fixture: %r" % outside)

    def test_shared_clone_at_the_tip_is_not_flagged(self):
        fx, shared, base = shared_behind(self._testMethodName, behind_by=0)
        self.assertEqual(fx.sha(shared, "HEAD"), fx.origin_tip("main"), "scope: the shared clone is not at the tip")
        run = fx.run_hook()
        self.assertEqual(run.lines, [], "a current shared clone and record printed %r, want silence" % run.lines)

    def test_shared_check_reads_no_origin_on_a_prompt(self):
        fx, shared, base = shared_behind(self._testMethodName, behind_by=2)
        fx.run_hook()
        self.assertEqual(network_reads(fx), [], "the prompt read origin: %r, want none" % fx.subcommands())


class LocalSession(unittest.TestCase):
    """The live pin's refresh in a session that is not a cloud session (CLAUDE_CODE_REMOTE unset): a Mac, or a Windows
    machine. The rules are the cloud rules. A trigger is a moved local ref, a prompt with no trigger reads nothing of
    origin, and a pin refreshes once per head. The fixtures are the pin's shapes: a detached checkout, and a linked
    worktree behind a symlink. None of them runs install.sh --cloud."""

    def test_local_trigger_refreshes_the_pin_once_and_prints_the_cloud_line(self):
        fx, old = detached(self._testMethodName, behind_by=1)
        install_refresh(fx)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        new = fx.origin_tip("main")
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), new,
                         "scope: the local origin/main ref did not move")
        run = fx.run_hook(cloud=False)
        self.assertEqual(refresh_runs(fx), [new], "a local trigger ran the pin refresh %r, want once at %s"
                         % (refresh_runs(fx), new[:SHORT]))
        self.assertEqual(run.lines, [PREFIX + "pin is 1 commit behind origin/main after the refresh"],
                         "want the one pin line a cloud session prints; stderr: %s" % run.tail())

    def test_local_second_prompt_on_the_same_head_runs_nothing_and_a_new_head_refreshes_again(self):
        fx, old = detached(self._testMethodName, behind_by=1)
        install_refresh(fx)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        first = fx.origin_tip("main")
        fx.run_hook(cloud=False)
        run = fx.run_hook(cloud=False)
        self.assertEqual(refresh_runs(fx), [first], "the second prompt on the same head ran the pin refresh again: %r"
                         % refresh_runs(fx))
        self.assertEqual(network_reads(fx), [], "a local prompt read origin: %r" % fx.subcommands())
        self.assertTrue(run.lines and run.lines[0].startswith(PREFIX + "install still stale"),
                        "the second prompt on the same head printed %r, want the stale line" % run.lines)
        fx.advance({})
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        second = fx.origin_tip("main")
        fx.run_hook(cloud=False)
        self.assertEqual(refresh_runs(fx), [first, second], "a new head ran the pin refresh %r, want one run per head"
                         % refresh_runs(fx))

    def test_local_failed_pin_refresh_prints_its_line_and_is_not_retried_on_the_same_head(self):
        fx, old = detached(self._testMethodName, behind_by=1)
        install_refresh(fx, REFRESH_FAIL_STUB)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        new = fx.origin_tip("main")
        run = fx.run_hook(cloud=False)
        self.assertEqual(run.lines, [PREFIX + "pin refresh failed (exit 1)"],
                         "want one failure line for the failed pin refresh; stderr: %s" % run.tail())
        later = fx.run_hook(cloud=False)
        self.assertEqual(refresh_runs(fx), [new], "a later prompt on the same head reran the failed refresh: %r"
                         % refresh_runs(fx))
        self.assertTrue(later.lines and later.lines[0].startswith(PREFIX + "install still stale"),
                        "the later prompt printed %r, want the stale line" % later.lines)

    def test_local_unknown_ref_reads_unknown_with_no_read_of_origin(self):
        fx, old, new = behind(self._testMethodName, ref="nope")
        self.assertNotIn("refs/heads/nope", fx.git("-C", fx.origin, "for-each-ref", "--format=%(refname)"),
                         "scope: origin has a branch named nope")
        run = fx.run_hook(cloud=False)
        self.assertEqual(len(run.lines), 1, "want one unknown line, got %r; stderr: %s" % (run.lines, run.tail()))
        self.assertTrue(run.lines[0].startswith(UNKNOWN), "not the unknown line: %r" % run.lines[0])
        self.assertEqual(network_reads(fx), [], "a local prompt read origin: %r" % fx.subcommands())
        self.assertEqual(fx.installer_runs(), [], "the installer ran for an unknown ref")

    def test_local_record_ahead_of_the_local_ref_is_silent_with_no_install(self):
        fx = current(self._testMethodName)
        ahead = fx.child_commit(fx.base)
        fx.write_record("main", ahead)
        run = fx.run_hook(cloud=False)
        self.assertEqual(run.lines, [], "a record ahead of the local ref printed %r outside a cloud session" % run.lines)
        self.assertEqual(fx.installer_runs(), [], "a record ahead of the local ref ran the installer")

    def test_local_current_linked_pin_is_silent_with_no_read(self):
        fx, old, pin = linked_pin(self._testMethodName)
        install_refresh(fx)
        self.assertEqual(fx.origin_tip("main"), fx.record_sha(), "scope: origin and the record differ")
        run = fx.run_hook(cloud=False)
        self.assertEqual(run.lines, [], "a current linked pin printed %r outside a cloud session; stderr: %s"
                         % (run.lines, run.tail()))
        self.assertEqual(network_reads(fx), [], "a local prompt read origin: %r" % fx.subcommands())
        self.assertEqual(refresh_runs(fx), [], "a current linked pin ran the pin refresh")

    def test_local_no_trigger_prompt_reads_no_origin_and_runs_nothing(self):
        fx, old = detached(self._testMethodName, behind_by=1)
        install_refresh(fx)
        self.assertEqual(fx.git("-C", fx.source, "rev-parse", "refs/remotes/origin/main").strip(), old,
                         "scope: the local origin/main ref moved without a fetch")
        run = fx.run_hook(cloud=False)
        self.assertEqual(run.lines, [], "a local prompt with no trigger printed %r" % run.lines)
        self.assertEqual(network_reads(fx), [], "a local prompt with no trigger read origin: %r" % fx.subcommands())
        self.assertEqual(refresh_runs(fx), [], "a local prompt with no trigger ran the pin refresh")
        self.assertEqual(fx.installer_runs(), [], "a local prompt with no trigger ran the installer")

    def test_local_no_trigger_prompt_makes_at_most_four_git_calls_and_no_network_read(self):
        fx, shared = no_trigger_worst(self._testMethodName)
        check_no_trigger_calls(self, fx, cloud=False)

    def test_local_no_trigger_prompt_writes_no_seen_file(self):
        fx, shared = no_trigger_worst(self._testMethodName)
        check_no_trigger_seen(self, fx, shared, cloud=False)

    def test_local_linked_pin_refresh_starts_through_the_symlink(self):
        fx, old, pin = linked_pin(self._testMethodName, behind_by=1)
        install_refresh(fx)
        fx.git("-C", fx.source, "fetch", "-q", "origin")
        new = fx.origin_tip("main")
        self.assertTrue(os.path.islink(fx.source), "scope: the pin's link is not a symlink")
        run = fx.run_hook(cloud=False)
        self.assertEqual(refresh_runs(fx), [new], "the local pin refresh did not run once at the new head: %r; stderr: %s"
                         % (refresh_runs(fx), run.tail()))
        self.assertEqual(refresh_where(fx), [os.path.join(fx.source, "merge", "install_from_main.sh")],
                         "the refresh did not start from the pin's link: %r" % refresh_where(fx))
        self.assertEqual(run.lines, [PREFIX + "pin is 1 commit behind origin/main after the refresh"],
                         "want the one pin line through the link; stderr: %s" % run.tail())


class PosixOnlyStop(unittest.TestCase):
    """The timeout's stop path where os.killpg and signal.SIGKILL do not exist (Windows). It runs in a cloud session,
    so the stop path is the only difference from the other cases."""

    def test_timeout_without_killpg_or_sigkill_prints_the_timeout_line(self):
        fx, old, new = behind(self._testMethodName)
        write_file(os.path.join(fx.source, "install.sh"), HANG_STUB, mode=0o755)
        self.assertEqual(fx.record_sha(), old, "scope: the record is not the base sha")
        run = fx.run_hook(guard=TIMEOUT_GUARD, reinstall_timeout="1", no_posix=True)
        grand = read_pid(fx.grand_path)
        installer = read_pid(fx.lock_path)
        self.addCleanup(kill_if_alive, grand)
        self.addCleanup(kill_if_alive, installer)
        self.assertIsNotNone(run.rc, "the hook ran past %d s; stderr: %s" % (TIMEOUT_GUARD, run.tail()))
        self.assertFalse([line for line in run.lines if "hook error" in line],
                         "the stop path raised instead of stopping the installer: %r" % run.lines)
        self.assertEqual(run.lines, [PREFIX + "reinstall failed (timed out after 1 s)"],
                         "want the timeout line; stderr: %s" % run.tail())


class HookFile(unittest.TestCase):
    """Static reads of the hook source and of settings.json. The behaviour cases above prove the rest."""

    def test_hook_names_main_only_as_the_pin_fallback_constant(self):
        text = read_text(HOOK)
        self.assertTrue(text.strip(), "scope: %s has no text to read" % HOOK)
        for needle in ("refs/heads/main", ":-main"):
            self.assertNotIn(needle, text, "the hook names %r literally" % needle)
        tree = ast.parse(text)
        allowed = {id(node.value) for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "PIN_FALLBACK_BRANCH" for target in node.targets)
                   and isinstance(node.value, ast.Constant) and node.value.value == "main"}
        named = [(node.lineno, node.value) for node in code_string_nodes(tree)
                 if id(node) not in allowed and MAIN_REF.search(node.value)]
        self.assertEqual(named, [], "the hook names main in code outside PIN_FALLBACK_BRANCH: %r" % named)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
