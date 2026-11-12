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
The hook never names `main` itself, and it is wired once, under UserPromptSubmit.

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
PAYLOAD = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "test-session", "prompt": "hi"})
HOOK_GUARD = 60  # seconds: stops a hook that never returns, so a broken build fails instead of hanging CI
SHORT = 7
REINSTALL = "claude-settings: reinstalled hooks at %s (was %s)"
UNKNOWN = "claude-settings: install freshness unknown ("
RESTART = "claude-settings: restart needed for:"
RESTART_UNKNOWN = "claude-settings: restart check unknown (could not diff %s..%s)"
GIT_LOCATORS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX")
HOOK_ENV_DROP = GIT_LOCATORS + ("CLAUDE_CODE_REMOTE", "CLAUDE_CONFIG_DIR", "CLAUDE_SETTINGS_FETCH_TIMEOUT",
                                "GIT_SHIM_LS_REMOTE", "GIT_SHIM_DIFF", "STUB_EXIT")
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

# Stands in for install.sh: counts each run, fetches origin as the real installer does, and writes the
# install record when STUB_WRITE_RECORD is set. When STUB_EXIT is set it exits with that code first, before
# the fetch and the record.
STUB = r'''#!/bin/sh
here=$(cd "$(dirname "$0")" && pwd -P)
printf '%s\n' "$*" >> "$STUB_COUNTER"
[ -n "$STUB_EXIT" ] && exit "$STUB_EXIT"
git -C "$here" fetch -q origin || exit 1
if [ -n "$STUB_WRITE_RECORD" ]; then
  sha=$(git -C "$here" rev-parse "origin/$STUB_REF") || exit 1
  printf '{"ref": "%s", "sha": "%s", "source": "%s", "installer": "%s/install.sh"}\n' \
    "$STUB_REF" "$sha" "$here" "$here" > "$CLAUDE_CONFIG_DIR/.claude-settings-install.json"
fi
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
        self.record_path = os.path.join(self.config, RECORD)
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

    def hook_env(self, cloud=True, ls_remote=None, timeout=None, diff=None, stub_exit=None):
        env = dict(os.environ)
        for key in HOOK_ENV_DROP:
            env.pop(key, None)
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.config,
                   PATH=self.shim_dir + os.pathsep + os.environ.get("PATH", ""),
                   GIT_SHIM_REAL=REAL_GIT, GIT_SHIM_LOG=self.git_log,
                   GIT_CONFIG_GLOBAL=self.gitconfig, GIT_CONFIG_NOSYSTEM="1",
                   STUB_COUNTER=self.counter, STUB_REF=self.ref, STUB_WRITE_RECORD="1")
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

    def run_hook(self, **options):
        open(self.git_log, "w", encoding="utf-8").close()  # each run's git calls start empty
        try:
            done = subprocess.run([sys.executable, HOOK], input=PAYLOAD, capture_output=True, text=True,
                                  cwd=self.home, env=self.hook_env(**options), timeout=HOOK_GUARD)
        except subprocess.TimeoutExpired:
            return Run(None, "", "still running after %d s; stopped" % HOOK_GUARD)
        return Run(done.returncode, done.stdout, done.stderr)

    def run_stub(self):
        return subprocess.run([os.path.join(self.source, "install.sh"), "--cloud"], capture_output=True,
                              text=True, cwd=self.home, env=self.hook_env())

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
