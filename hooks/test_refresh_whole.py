#!/usr/bin/env python3
"""Cases for the cloud whole refresh: install.sh --cloud stages the whole shipped set in one new generation
folder, then switches one link to it. Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_refresh_whole.py

WHAT IT PROVES. A cloud run stages every landed folder, the hooks with guard.py and their guard.d/<id>/ set,
the skills, the agents, and the generated settings.json under <config>/installs/<id>/. One rename of
<config>/.cs-current onto that folder switches the install. Each <config>/<sub>/<file>,
<config>/skills/<name>, <config>/hooks/guard.d and <config>/settings.json is a link through .cs-current.
A failed run leaves the old generation whole and the install record as it was. A rename never runs while
the live settings.json names a hook file that is already gone. A generation retired more than an hour ago is removed;
one retired within the hour, and the current one, stay.

Two classes. Refresh holds the new claims: each one fails on the tree it is written for, and a red there
names the named cause or, where the fault point or the link is absent, a scope check that comes first.
KeptOnOldTree holds the claims the old copy-based install already meets. They guard the behaviour a whole
refresh must not lose, and they are green on the old tree by design.

THE SEAM. Each case gets a run folder with a bare origin on branch stable, a seed commit of the shipped set,
and a fake HOME with no checkout, so the first install clones its mirror the way a cloud session with none
does. A git config rewrites the GitHub origin to the bare origin, and GIT_ALLOW_PROTOCOL=file forbids any
network. The PATH holds a cp and a mv shim that log each call and fail the call a case names, and a pipx stub
so no pip runs. The mv shim also logs each hook the live settings.json names that is missing, before each
rename. The cases read the config folder through its links and watch it with a poller thread.

The fixture's settings.json is the repo's settings.json without its SessionStart event, plus one hook entry
that a second commit removes: the install runs the source's startup entries itself, and a test must not run
the repo's. Every other hook path in the repo's settings.json is kept.

The controls at the end (class Harness) pass on any tree. They prove the fixture, the shims, the poller and
the probe work, so a red elsewhere belongs to the install.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
sys.path.insert(0, os.path.join(REPO, "testing"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import tracked_tree  # noqa: E402  copies what git lists under a folder (testing/tracked_tree.py)

ROOT = _test_temp.run_folder()
INSTALL = os.path.join(REPO, "install.sh")
REAL_CP = shutil.which("cp") or "cp"
REAL_MV = shutil.which("mv") or "mv"
REPO_URL = "https://github.com/shivinate7/claude-settings.git"
REF = "stable"
RECORD = ".claude-settings-install.json"
ROOT_FILES = ("install.sh", "CLAUDE.md", "landed-dirs.txt", "retired-files.txt")
EXTRA_FILES = ("merge/cloud_allow.json",)
GEN2 = "refresh gen 2"
RETIRE_HOOK = "retire_me.py"
FAIL_CP_AT = 3
PAD_FILES = 24
PAD_TEXT = "pad line\n" * 400
PATH_MAX = 1024
LONG_HOME_NAME = "macos-style-temp-folder-for-a-long-path-check"
LONG_HOME_MIN = 100
COMPONENT_CAP = 40
OLD_ID = "20250101000000101"
YOUNG_ID = "20261115101010202"
OLD_AGE = 2 * 3600
YOUNG_AGE = 600
LIVE_THEN_OLD_AGE = 3 * 3600  # made 3 h before the switch that retires it: old by creation, new by retirement
RETIRED_AGE = 2 * 3600  # retired 2 h ago: past the hour
INSTALL_GUARD = 180
PROBE_GUARD = 60
HOOK_PATH = re.compile(r"\bhooks/([A-Za-z0-9_.-]+\.py)\b")
GIT_LOCATORS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX")

GITCONFIG = """[url "%s"]
\tinsteadOf = %s
[user]
\tname = fixture
\temail = fixture@example.invalid
"""

# Stands in for cp. A copy into the config folder is counted and logged; the copy numbered SHIM_FAIL_CP
# fails once and writes SHIM_FIRED. Every other copy runs the real cp.
CP_SHIM = r'''#!/bin/sh
for last; do :; done
case "$last" in
  "$SHIM_CFG"/*)
    n=$(( $(cat "$SHIM_COUNT" 2>/dev/null || echo 0) + 1 ))
    printf '%s\n' "$n" > "$SHIM_COUNT"
    printf 'cp %s\n' "$*" >> "$SHIM_LOG"
    if [ -n "$SHIM_FAIL_CP" ] && [ "$n" = "$SHIM_FAIL_CP" ]; then
      printf 'copy %s\n' "$n" > "$SHIM_FIRED"
      echo "cp: injected failure" >&2
      exit 1
    fi ;;
esac
exec "$SHIM_REAL_CP" "$@"
'''

# Stands in for mv. Before each rename, every hook the live settings.json names is tested, and a missing one is
# logged in SHIM_GAP. Every rename is logged in SHIM_MV_LOG. A rename onto a link named .cs-current fails once
# when SHIM_FAIL_SWITCH is set, and writes SHIM_FIRED. Every other rename runs the real mv.
MV_SHIM = r'''#!/bin/sh
printf 'mv %s\n' "$*" >> "$SHIM_MV_LOG"
if [ -n "$SHIM_GAP" ] && [ -f "$SHIM_CFG/settings.json" ]; then
  for hook in $(grep -o 'hooks/[A-Za-z0-9_.-]*\.py' "$SHIM_CFG/settings.json"); do
    [ -f "$SHIM_CFG/$hook" ] || printf '%s\n' "$hook" >> "$SHIM_GAP"
  done
fi
for last; do :; done
case "$last" in
  */.cs-current)
    if [ -n "$SHIM_FAIL_SWITCH" ]; then
      printf 'switch\n' > "$SHIM_FIRED"
      echo "mv: injected failure" >&2
      exit 1
    fi ;;
esac
exec "$SHIM_REAL_MV" "$@"
'''

PROBE_ENTRY = r'''import sys

sys.stdout.write("started\n")
sys.stdout.flush()
sys.stdin.readline()
import probe_sibling

sys.stdout.write(probe_sibling.VALUE + "\n")
sys.stdout.flush()
'''

# Imports the guard the way a hook does, then names the guard set the modules came from.
CHECK_GUARD = r'''import json, sys
sys.path.insert(0, sys.argv[1])
import guard
import guard_core
print(json.dumps({"id": getattr(guard, "INSTALL_ID", None), "core": guard_core.__file__}))
'''


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


def landed_dirs():
    """The folders install.sh lands, from landed-dirs.txt: the one list the installers read."""
    names = []
    with open(os.path.join(REPO, "landed-dirs.txt"), encoding="utf-8") as handle:
        for line in handle:
            name = line.split("#", 1)[0].strip()
            if name:
                names.append(name)
    return names


def skill_names(root):
    base = os.path.join(root, "skills")
    return sorted(name for name in os.listdir(base) if os.path.isfile(os.path.join(base, name, "SKILL.md")))


def write_file(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    if mode is not None:
        os.chmod(path, mode)


def read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def read_text(path):
    data = read_bytes(path)
    return None if data is None else data.decode("utf-8", "replace")


def digest(path):
    data = read_bytes(path)
    return None if data is None else hashlib.sha256(data).hexdigest()


def tail(done):
    rows = (done.stdout + done.stderr).strip().splitlines()
    return " | ".join(rows[-3:]) if rows else "(no output)"


def seed_tree(seed):
    """The shipped set at the seed's first commit: what git lists in each landed folder, the root files, the
    cloud allow rules, the probe pair a case imports, a hook a second commit removes, and a pad of files in each
    skill so a copy takes time."""
    tracked_tree.copy_tracked(seed, *landed_dirs())
    for rel in ROOT_FILES + EXTRA_FILES:
        src = os.path.join(REPO, rel)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(os.path.join(seed, rel)) or seed, exist_ok=True)
            shutil.copyfile(src, os.path.join(seed, rel))
    with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as handle:
        settings = json.load(handle)
    hooks = settings.setdefault("hooks", {})
    hooks.pop("SessionStart", None)
    hooks.setdefault("PreToolUse", []).append(
        {"matcher": "Bash", "hooks": [{"type": "command",
                                       "command": "python3 ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/" + RETIRE_HOOK}]})
    write_file(os.path.join(seed, "settings.json"), json.dumps(settings, indent=2) + "\n")
    write_file(os.path.join(seed, "hooks", "probe_entry.py"), PROBE_ENTRY)
    write_file(os.path.join(seed, "hooks", "probe_sibling.py"), 'VALUE = "old"\n')
    write_file(os.path.join(seed, "hooks", RETIRE_HOOK), "pass\n")
    for name in skill_names(seed):
        for index in range(PAD_FILES):
            write_file(os.path.join(seed, "skills", name, "refresh-pad", "%03d.txt" % index), PAD_TEXT)


def age(path, seconds):
    """Set the mtime of path and everything under it to `seconds` before now, as touch -d does. Returns it."""
    when = int(time.time()) - seconds
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            os.utime(os.path.join(dirpath, name), (when, when), follow_symlinks=False)
    os.utime(path, (when, when))
    return when


class SkillPoller:
    """Reads each path in a loop until halted. A read that finds no file is a miss."""

    def __init__(self, paths):
        self.paths = list(paths)
        self.halt_flag = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.reads = 0
        self.miss_count = 0
        self.misses = []

    def _pass(self):
        for path in self.paths:
            self.reads += 1
            try:
                with open(path, "rb") as handle:
                    handle.read()
            except OSError as exc:
                self.miss_count += 1
                if len(self.misses) < 5:
                    self.misses.append("%s (%s)" % (path, exc.strerror))

    def _loop(self):
        while not self.halt_flag.is_set():
            self._pass()

    def run_to(self, reads):
        """Synchronous: read until `reads` reads have been made. Used by the control."""
        while self.reads < reads:
            self._pass()

    def start(self):
        self.thread.start()

    def halt(self):
        self.halt_flag.set()
        self.thread.join()


class Probe:
    """A hook process that prints "started", waits for one input line, then imports its sibling and prints it.
    Each read blocks on the process, so no clock is read; a watchdog kills the process if it never answers."""

    def __init__(self, fixture):
        self.err = open(os.path.join(fixture.root, "probe-err.txt"), "w", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=fixture.home, CLAUDE_CONFIG_DIR=fixture.cfg)
        self.proc = subprocess.Popen([sys.executable, os.path.join(fixture.cfg, "hooks", "probe_entry.py")],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err,
                                     env=env, cwd=fixture.home, text=True)
        self.watchdog = threading.Timer(PROBE_GUARD, self.proc.kill)
        self.watchdog.start()

    def line(self):
        return self.proc.stdout.readline().strip()

    def answer(self):
        try:
            self.proc.stdin.write("go\n")
            self.proc.stdin.flush()
        except OSError:
            return ""
        return self.line()

    def close(self):
        self.watchdog.cancel()
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.err.close()


class Fixture:
    """One case's world under the run folder: a bare origin with a seed, a fake HOME, and the shims."""

    def __init__(self, name, home_name="home"):
        self.root = os.path.join(ROOT, name)
        self.home = os.path.join(self.root, home_name)
        self.cfg = os.path.join(self.home, ".claude")
        self.installs = os.path.join(self.cfg, "installs")
        self.current = os.path.join(self.cfg, ".cs-current")
        self.settings = os.path.join(self.cfg, "settings.json")
        self.record = os.path.join(self.cfg, RECORD)
        self.origin = os.path.join(self.root, "origin.git")
        self.seed = os.path.join(self.root, "seed")
        self.gitconfig = os.path.join(self.root, "gitconfig")
        self.shim_dir = os.path.join(self.root, "shim")
        self.cp_log = os.path.join(self.root, "cp-log.txt")
        self.cp_count = os.path.join(self.root, "cp-count.txt")
        self.mv_log = os.path.join(self.root, "mv-log.txt")
        self.fired_path = os.path.join(self.root, "fired.txt")
        self.gap_path = os.path.join(self.root, "gap.txt")
        os.makedirs(self.home)
        os.makedirs(self.shim_dir)
        write_file(self.gitconfig, GITCONFIG % (self.origin, REPO_URL))
        write_file(os.path.join(self.shim_dir, "cp"), CP_SHIM, mode=0o755)
        write_file(os.path.join(self.shim_dir, "mv"), MV_SHIM, mode=0o755)
        write_file(os.path.join(self.shim_dir, "pipx"), "#!/bin/sh\nexit 0\n", mode=0o755)
        self.git(self.root, "init", "-q", "--bare", "-b", REF, self.origin)
        self.git(self.root, "init", "-q", "-b", REF, self.seed)
        seed_tree(self.seed)
        self.commit("first")
        self.git(self.seed, "remote", "add", "origin", self.origin)
        self.git(self.seed, "push", "origin", REF)

    def git(self, cwd, *args):
        env = dict(os.environ)
        for key in GIT_LOCATORS:
            env.pop(key, None)
        env.update(GIT_CONFIG_GLOBAL=self.gitconfig, GIT_CONFIG_NOSYSTEM="1",
                   GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0")
        done = subprocess.run(["git", *args], cwd=cwd, env=_test_git.apply(env), capture_output=True, text=True)
        if done.returncode:
            raise RuntimeError("fixture git %s: %s" % (" ".join(args), done.stderr.strip()))
        return done.stdout.strip()

    def commit(self, message):
        self.git(self.seed, "add", "-A")
        self.git(self.seed, "commit", "-q", "-m", message)
        return self.seed_head()

    def seed_head(self):
        return self.git(self.seed, "rev-parse", "HEAD")

    def advance(self, retire=False):
        """The next version: every .md and .py file in a landed folder gets a marker line, and the probe sibling
        changes its value. With retire, the retire hook file and its settings entry are removed too. Pushed to
        origin, so the mirror is behind until the next install."""
        for sub in landed_dirs():
            for dirpath, _dirs, files in os.walk(os.path.join(self.seed, sub)):
                for name in files:
                    path = os.path.join(dirpath, name)
                    if name.endswith(".md"):
                        write_file(path, read_text(path) + "\n<!-- %s -->\n" % GEN2)
                    elif name.endswith(".py"):
                        write_file(path, read_text(path) + "\n# %s\n" % GEN2)
        write_file(os.path.join(self.seed, "hooks", "probe_sibling.py"), 'VALUE = "new"\n')
        if retire:
            os.remove(os.path.join(self.seed, "hooks", RETIRE_HOOK))
            path = os.path.join(self.seed, "settings.json")
            settings = json.loads(read_text(path))
            pre = settings["hooks"]["PreToolUse"]
            settings["hooks"]["PreToolUse"] = [entry for entry in pre if RETIRE_HOOK not in json.dumps(entry)]
            write_file(path, json.dumps(settings, indent=2) + "\n")
        self.commit("second")
        self.git(self.seed, "push", "origin", REF)

    def install_env(self, fail_cp=None, fail_switch=False):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("CLAUDE_", "CS_", "STUB_", "GIT_SHIM")) and k not in GIT_LOCATORS}
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg, SHELL="/bin/bash",
                   GIT_CONFIG_GLOBAL=self.gitconfig, GIT_CONFIG_NOSYSTEM="1",
                   GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0",
                   CLAUDE_SETTINGS_TEMP_ROOTS=os.path.join(self.root, "no-such-temp-root"),
                   CLAUDE_SETTINGS_SEARCH_ROOTS=os.path.join(self.root, "no-such-search-root"),
                   PATH=self.shim_dir + os.pathsep + os.environ.get("PATH", ""),
                   SHIM_CFG=self.cfg, SHIM_COUNT=self.cp_count, SHIM_LOG=self.cp_log,
                   SHIM_MV_LOG=self.mv_log, SHIM_FIRED=self.fired_path, SHIM_GAP=self.gap_path,
                   SHIM_REAL_CP=REAL_CP, SHIM_REAL_MV=REAL_MV)
        if fail_cp:
            env["SHIM_FAIL_CP"] = str(fail_cp)
        if fail_switch:
            env["SHIM_FAIL_SWITCH"] = "1"
        return env

    def install(self, fail_cp=None, fail_switch=False):
        """One `install.sh --cloud` run, the code under test piped in and run from HOME, as a cloud session does."""
        for path in (self.cp_count, self.cp_log, self.mv_log, self.fired_path, self.gap_path):
            if os.path.exists(path):
                os.remove(path)
        with open(INSTALL, "rb") as script:
            return subprocess.run(["bash", "-s", "--", "--cloud"], stdin=script, cwd=self.home,
                                  env=self.install_env(fail_cp, fail_switch), capture_output=True,
                                  text=True, timeout=INSTALL_GUARD)

    def fired(self):
        return os.path.exists(self.fired_path)

    def renames(self):
        """Each rename the last run made, as its argv, in order."""
        rows = (read_text(self.mv_log) or "").splitlines()
        return [row for row in rows if row.strip()]

    def guard_import(self):
        return subprocess.run([sys.executable, "-c", CHECK_GUARD, os.path.join(self.cfg, "hooks")],
                              capture_output=True, text=True, cwd=self.home,
                              env=dict(os.environ, HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg),
                              timeout=INSTALL_GUARD)

    def snapshot(self):
        """Digest of each landed file, read through its links, under the name the link has. A link that
        resolves to a different file in a new generation changes the digest, as a copy does."""
        seen = {}
        for sub in landed_dirs() + ["settings.json", "CLAUDE.md"]:
            top = os.path.join(self.cfg, sub)
            if os.path.isfile(top):
                seen[sub] = digest(top)
                continue
            for dirpath, _dirs, files in os.walk(top, followlinks=True):
                for name in files:
                    path = os.path.join(dirpath, name)
                    if os.path.isfile(path):
                        seen[os.path.relpath(path, self.cfg)] = digest(path)
        return seen

    def dangling(self):
        """Links under the landed folders, and the two root files, that do not resolve."""
        broken = []
        for sub in landed_dirs() + ["settings.json", "CLAUDE.md"]:
            top = os.path.join(self.cfg, sub)
            if os.path.islink(top) and not os.path.exists(top):
                broken.append(sub)
                continue
            if not os.path.isdir(top):
                continue
            for dirpath, dirnames, filenames in os.walk(top, followlinks=True):
                for name in dirnames + filenames:
                    path = os.path.join(dirpath, name)
                    if os.path.islink(path) and not os.path.exists(path):
                        broken.append(os.path.relpath(path, self.cfg))
        return sorted(broken)

    def current_target(self):
        return os.readlink(self.current) if os.path.islink(self.current) else None

    def generations(self):
        return sorted(os.listdir(self.installs)) if os.path.isdir(self.installs) else []

    def record_sha(self):
        text = read_text(self.record)
        try:
            return json.loads(text).get("sha") if text else None
        except ValueError:
            return None

    def skill_files(self):
        return [os.path.join(self.cfg, "skills", name, "SKILL.md") for name in skill_names(self.seed)]

    def settings_hook_files(self):
        """The hooks/<name>.py paths the settings file names in its commands."""
        return sorted(set(HOOK_PATH.findall(read_text(self.settings) or "")))


class FirstInstall(unittest.TestCase):
    """Base of the case classes. installed(name) is a fixture whose generation 1 install ran and exited 0."""

    def installed(self, name, home_name="home"):
        fx = Fixture(name, home_name)
        done = fx.install()
        self.assertEqual(done.returncode, 0, "fixture: the first install exited %d: %s" % (done.returncode, tail(done)))
        return fx

    installed_fixture = installed


class Refresh(FirstInstall):
    """The new claims. Each one is red on the tree it was written for, for the reason its message names."""

    def assert_old_install_whole(self, fx, done, before, record, target, gens, cause):
        after = fx.snapshot()
        changed = sorted(path for path in before if after.get(path) != before[path])
        self.assertEqual(changed, [], "%d files changed under %s, so the old install is not whole: %s"
                         % (len(changed), cause, changed[:4]))
        self.assertEqual(fx.dangling(), [], "links under the landed folders do not resolve after %s: %s"
                         % (cause, fx.dangling()[:4]))
        self.assertEqual(read_bytes(fx.record), record, "the install record changed after %s" % cause)
        self.assertEqual(fx.current_target(), target, ".cs-current moved although %s failed" % cause)
        self.assertEqual(fx.generations(), gens, "a half-staged generation is left under installs/ after %s" % cause)
        self.assertNotEqual(done.returncode, 0, "the run exited 0 after %s; it must exit non-zero: %s"
                            % (cause, tail(done)))

    def test_a1_a_copy_that_fails_mid_staging_leaves_the_old_install_whole(self):
        fx = self.installed("a1-copy")
        before, record = fx.snapshot(), read_bytes(fx.record)
        target, gens = fx.current_target(), fx.generations()
        fx.advance()
        done = fx.install(fail_cp=FAIL_CP_AT)
        self.assertTrue(fx.fired(), "scope: the copy fault point never ran, so the case proves nothing")
        self.assert_old_install_whole(fx, done, before, record, target, gens, "a failed copy")

    def test_a2_a_failed_link_switch_leaves_the_old_install_live_and_fails_the_run(self):
        fx = self.installed("a2-switch")
        before, record = fx.snapshot(), read_bytes(fx.record)
        target, gens = fx.current_target(), fx.generations()
        fx.advance()
        done = fx.install(fail_switch=True)
        self.assertTrue(fx.fired(), "scope: no rename onto .cs-current ran, so the switch fault point is absent")
        self.assert_old_install_whole(fx, done, before, record, target, gens, "a failed link switch")

    def test_b_no_skill_file_is_missing_while_a_refresh_switches_the_set(self):
        fx = self.installed("b-skills")
        paths = fx.skill_files()
        self.assertTrue(paths, "fixture: the seed has no skill with a SKILL.md")
        fx.advance()
        poller = SkillPoller(paths)
        poller.start()
        try:
            done = fx.install()
        finally:
            poller.halt()
        self.assertGreater(poller.reads, 0, "fixture: the poller never read a SKILL.md")
        self.assertEqual(poller.miss_count, 0, "%d reads of a SKILL.md found no file during the refresh; first: %s"
                         % (poller.miss_count, "; ".join(poller.misses)))
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        stale = [path for path in paths if GEN2 not in (read_text(path) or "")]
        self.assertEqual(stale, [], "%d SKILL.md files lack the new content after the refresh; first: %s"
                         % (len(stale), stale[:2]))

    def test_c1_a_hook_started_before_the_switch_imports_the_old_sibling_after_it(self):
        fx = self.installed("c1-probe")
        probe = Probe(fx)
        try:
            self.assertEqual(probe.line(), "started", "fixture: the probe did not start")
            fx.advance()
            done = fx.install()
            self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
            got = probe.answer()
        finally:
            probe.close()
        self.assertEqual(got, "old", "a hook started before the switch imported %r after it: old and new "
                                     "generations mixed in one process" % got)

    def test_c3_the_guard_set_a_hook_loads_is_the_generation_behind_the_current_link(self):
        fx = self.installed("c3-generation")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        self.assertTrue(os.path.islink(fx.current), "scope: .cs-current is not a link, so there is no generation to match")
        check = fx.guard_import()
        self.assertEqual(check.returncode, 0, "import guard failed: %s" % tail(check))
        seen = json.loads(check.stdout.strip().splitlines()[-1])
        gen = os.path.realpath(fx.current)
        self.assertTrue(os.path.realpath(seen["core"]).startswith(gen + os.sep),
                        "guard_core loaded from %s, outside the generation behind .cs-current (%s)"
                        % (seen["core"], gen))

    def test_d_a_long_home_path_keeps_staged_names_short_and_links_under_path_max(self):
        fx = Fixture("d-long-home", home_name=LONG_HOME_NAME)
        self.assertGreaterEqual(len(fx.home), LONG_HOME_MIN, "fixture: the home path is only %d characters"
                                % len(fx.home))
        done = fx.install()
        self.assertEqual(done.returncode, 0, "gen 1 under a long home exited %d: %s" % (done.returncode, tail(done)))
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh under a long home exited %d: %s"
                         % (done.returncode, tail(done)))
        self.assertTrue(os.path.islink(fx.current), "scope: .cs-current is not a link, so there are no staged links")
        through = []
        long_names = []
        long_links = []
        for dirpath, dirnames, filenames in os.walk(fx.cfg):
            for name in dirnames + filenames:
                path = os.path.join(dirpath, name)
                if len(name) > COMPONENT_CAP:
                    long_names.append(os.path.relpath(path, fx.cfg))
                if os.path.islink(path):
                    if ".cs-current" in os.readlink(path).split("/"):
                        through.append(os.path.relpath(path, fx.cfg))
                    if len(os.readlink(path)) >= PATH_MAX or len(os.path.realpath(path)) >= PATH_MAX:
                        long_links.append(os.path.relpath(path, fx.cfg))
        self.assertTrue(through, "scope: no link under the config folder goes through .cs-current")
        self.assertEqual(long_names, [], "%d path components are longer than %d characters: %s"
                         % (len(long_names), COMPONENT_CAP, long_names[:3]))
        self.assertEqual(long_links, [], "%d links reach PATH_MAX (%d): %s" % (len(long_links), PATH_MAX, long_links[:3]))

    def test_e_a_generation_older_than_an_hour_is_pruned_and_a_younger_one_stays(self):
        fx = self.installed("e-prune")
        old = os.path.join(fx.installs, OLD_ID)
        young = os.path.join(fx.installs, YOUNG_ID)
        for path, seconds in ((old, OLD_AGE), (young, YOUNG_AGE)):
            write_file(os.path.join(path, "settings.json"), "{}\n")
            age(path, seconds)
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        self.assertFalse(os.path.exists(old), "a generation two hours old is still under installs/ after the refresh")
        self.assertTrue(os.path.isdir(young), "a generation ten minutes old was pruned by the refresh")
        self.assertTrue(os.path.islink(fx.current), "scope: .cs-current is not a link after the refresh")
        self.assertTrue(os.path.isdir(os.path.realpath(fx.current)), ".cs-current names a folder that is not there")

    def test_h_a_generation_counts_its_age_from_the_switch_that_retires_it(self):
        fx = self.installed("h-retire")
        self.assertTrue(os.path.islink(fx.current), "scope: .cs-current is not a link, so there is no generation to age")
        first = fx.current_target()
        gen1 = os.path.join(fx.cfg, first)
        age(gen1, LIVE_THEN_OLD_AGE)  # live until the next switch, so its age must count from that switch
        probe = Probe(fx)
        try:
            self.assertEqual(probe.line(), "started", "fixture: the probe did not start")
            fx.advance()
            done = fx.install()
            self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
            self.assertNotEqual(fx.current_target(), first, "scope: the refresh did not switch .cs-current")
            self.assertTrue(os.path.isdir(gen1), "generation 1 was removed by the run that retired it: a generation "
                                                 "counts its age from its creation, not from its retirement")
            fx.advance()
            done = fx.install()
            self.assertEqual(done.returncode, 0, "the second refresh exited %d: %s" % (done.returncode, tail(done)))
            got = probe.answer()
        finally:
            probe.close()
        self.assertEqual(got, "old", "a hook started in generation 1 imported %r after a second refresh within the "
                                     "hour: generation 1 was not whole" % got)
        second = fx.current_target()
        age(gen1, RETIRED_AGE)  # retired 2 h ago, so a later run must remove it
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the third refresh exited %d: %s" % (done.returncode, tail(done)))
        self.assertNotEqual(fx.current_target(), second, "scope: the third refresh did not switch .cs-current")
        self.assertFalse(os.path.exists(gen1), "a generation retired 2 hours ago is still under installs/ after a "
                                               "later refresh")

    def test_f1_settings_json_is_a_link_through_the_current_link(self):
        fx = self.installed("f1-settings")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        self.assertTrue(os.path.islink(fx.settings), "settings.json is a regular file, not a link")
        target = os.readlink(fx.settings)
        self.assertIn(".cs-current", target.split("/"), "settings.json links to %r, which does not go through "
                                                        ".cs-current" % target)

    def test_f3_no_rename_runs_while_the_live_settings_names_a_hook_that_is_gone(self):
        fx = self.installed("f3-gap")
        hook = os.path.join(fx.cfg, "hooks", RETIRE_HOOK)
        self.assertIn("hooks/" + RETIRE_HOOK, read_text(fx.settings) or "",
                      "fixture: gen 1 settings does not name the retire hook")
        fx.advance(retire=True)
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        self.assertFalse(os.path.exists(hook), "fixture: the refresh did not remove hooks/%s" % RETIRE_HOOK)
        missing = sorted(set((read_text(fx.gap_path) or "").split()))
        self.assertEqual(missing, [], "a rename ran while the live settings.json named hooks/%s, which the refresh "
                                      "had already removed: %s" % (RETIRE_HOOK, missing))

    def test_g4_the_record_is_renamed_after_the_switch(self):
        fx = self.installed("g4-order")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        rows = fx.renames()
        switch = [i for i, row in enumerate(rows) if row.split()[-1].endswith("/.cs-current")]
        self.assertTrue(switch, "scope: no rename onto .cs-current ran, so the record cannot come after a switch")
        record = [i for i, row in enumerate(rows) if row.split()[-1].endswith(RECORD)]
        self.assertTrue(record, "the run renamed no install record")
        self.assertGreater(record[-1], switch[-1], "the install record is renamed before the link switch")


class KeptOnOldTree(FirstInstall):
    """Claims the copy-based install already meets. They guard what a whole refresh must not lose, so they are
    green on the old tree by design. They are not new claims."""

    def test_c2_import_guard_after_the_refresh_loads_the_set_its_stamp_names(self):
        fx = self.installed("c2-guard")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        check = fx.guard_import()
        self.assertEqual(check.returncode, 0, "import guard failed: %s" % tail(check))
        rows = check.stdout.strip().splitlines()
        self.assertTrue(rows, "import guard printed nothing: %s" % tail(check))
        seen = json.loads(rows[-1])
        stamp = seen.get("id")
        self.assertTrue(stamp and stamp != "uninstalled", "guard.py carries no install id: %r" % stamp)
        self.assertIn(os.sep + "guard.d" + os.sep + stamp + os.sep, seen["core"],
                      "guard_core loaded from %s, not from guard.d/%s" % (seen["core"], stamp))
        self.assertFalse(os.path.exists(os.path.join(fx.cfg, "guard.log")),
                         "the guard took its crash path: guard.log was written")

    def test_f2_every_hook_path_settings_names_resolves_after_the_refresh(self):
        fx = self.installed("f2-hooks")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        names = fx.settings_hook_files()
        self.assertTrue(names, "fixture: settings.json names no hook file")
        missing = [name for name in names if not os.path.isfile(os.path.join(fx.cfg, "hooks", name))]
        self.assertEqual(missing, [], "settings.json names hook files the install does not leave: %s" % missing)

    def test_g1_the_record_names_the_new_sha_after_a_good_run(self):
        fx = self.installed("g1-record")
        first = fx.seed_head()
        self.assertEqual(fx.record_sha(), first, "fixture: gen 1 record does not name the first commit")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        self.assertNotEqual(fx.seed_head(), first, "fixture: the advance did not move the seed")
        self.assertEqual(fx.record_sha(), fx.seed_head(), "the record names %s after a good run, not the new commit"
                         % fx.record_sha())

    def test_g2_a_failed_run_leaves_the_prior_record_as_it_was(self):
        fx = self.installed("g2-record")
        record = read_bytes(fx.record)
        self.assertIsNotNone(record, "fixture: gen 1 wrote no install record")
        fx.advance()
        done = fx.install(fail_cp=FAIL_CP_AT)
        self.assertNotEqual(done.returncode, 0, "the run exited 0 although a copy failed: %s" % tail(done))
        self.assertEqual(read_bytes(fx.record), record, "a failed run changed the install record")

    def test_g3_the_record_is_the_last_rename_of_a_good_run(self):
        fx = self.installed("g3-order")
        fx.advance()
        done = fx.install()
        self.assertEqual(done.returncode, 0, "the refresh exited %d: %s" % (done.returncode, tail(done)))
        rows = fx.renames()
        self.assertTrue(rows, "fixture: the mv shim logged no rename in the refresh")
        self.assertTrue(rows[-1].split()[-1].endswith(RECORD), "the last rename of the run is not the record: %s"
                        % rows[-1])


class Harness(FirstInstall):
    """Controls: they pass on any tree, so a red elsewhere belongs to the install, not to the fixture."""

    def test_control_gen1_lands_every_landed_folder(self):
        fx = self.installed("ctl-landed")
        empty = []
        for sub in landed_dirs():
            found = []
            for _dirpath, _dirs, files in os.walk(os.path.join(fx.cfg, sub), followlinks=True):
                found += files
            if not found:
                empty.append(sub)
        self.assertEqual(empty, [], "gen 1 left these landed folders without a file")

    def test_control_gen1_record_names_the_first_commit(self):
        fx = self.installed_fixture("ctl-record")
        self.assertEqual(fx.record_sha(), fx.seed_head(), "gen 1 record does not name the seed's commit")

    def test_control_copy_shim_fails_only_the_numbered_copy(self):
        fx = Fixture("ctl-cp")
        os.makedirs(fx.cfg, exist_ok=True)
        src = os.path.join(fx.root, "src.txt")
        write_file(src, "x\n")
        env = dict(os.environ, SHIM_CFG=fx.cfg, SHIM_COUNT=fx.cp_count, SHIM_LOG=fx.cp_log,
                   SHIM_FIRED=fx.fired_path, SHIM_REAL_CP=REAL_CP, SHIM_FAIL_CP="2")
        codes = []
        for name in ("one", "two", "three"):
            codes.append(subprocess.run([os.path.join(fx.shim_dir, "cp"), src, os.path.join(fx.cfg, name)],
                                        env=env, capture_output=True).returncode)
        self.assertEqual(codes, [0, 1, 0], "the shim failed the wrong copies: %r" % codes)
        self.assertTrue(fx.fired(), "the shim did not mark the copy it failed")

    def test_control_move_shim_passes_a_rename_and_fails_a_switch_on_request(self):
        fx = Fixture("ctl-mv")
        os.makedirs(fx.cfg, exist_ok=True)
        base = dict(os.environ, SHIM_MV_LOG=fx.mv_log, SHIM_FIRED=fx.fired_path, SHIM_REAL_MV=REAL_MV)
        a, b = os.path.join(fx.root, "a.txt"), os.path.join(fx.root, "b.txt")
        write_file(a, "x\n")
        plain = subprocess.run([os.path.join(fx.shim_dir, "mv"), a, b], env=base, capture_output=True)
        self.assertEqual(plain.returncode, 0, "a plain rename through the shim failed")
        self.assertTrue(os.path.exists(b), "the plain rename through the shim did not move the file")
        link_tmp = os.path.join(fx.cfg, ".cs-current.cs-new")
        os.symlink("installs/x", link_tmp)
        switch = subprocess.run([os.path.join(fx.shim_dir, "mv"), "-fT", link_tmp, fx.current],
                                env=dict(base, SHIM_FAIL_SWITCH="1"), capture_output=True)
        self.assertNotEqual(switch.returncode, 0, "the shim let a switch onto .cs-current through")
        self.assertTrue(fx.fired(), "the shim did not mark the switch it failed")

    def test_control_gap_shim_logs_a_named_hook_that_is_gone_and_no_other(self):
        fx = Fixture("ctl-gap")
        os.makedirs(fx.cfg, exist_ok=True)
        write_file(fx.settings, '{"command": "python3 x/hooks/gone.py; python3 x/hooks/here.py"}\n')
        write_file(os.path.join(fx.cfg, "hooks", "here.py"), "pass\n")
        env = dict(os.environ, SHIM_CFG=fx.cfg, SHIM_MV_LOG=fx.mv_log, SHIM_GAP=fx.gap_path,
                   SHIM_REAL_MV=REAL_MV)
        src, dest = os.path.join(fx.root, "s.txt"), os.path.join(fx.root, "d.txt")
        write_file(src, "x\n")
        done = subprocess.run([os.path.join(fx.shim_dir, "mv"), src, dest], env=env, capture_output=True)
        self.assertEqual(done.returncode, 0, "the gap shim failed a plain rename")
        self.assertEqual(sorted(set((read_text(fx.gap_path) or "").split())), ["hooks/gone.py"],
                         "the gap shim did not log exactly the missing hook")

    def test_control_poller_counts_misses_and_clean_reads(self):
        fx = Fixture("ctl-poll")
        present = os.path.join(fx.root, "present.txt")
        write_file(present, "here\n")
        clean = SkillPoller([present])
        clean.run_to(50)
        self.assertEqual(clean.miss_count, 0, "the poller counted a miss on a file that exists")
        gone = SkillPoller([os.path.join(fx.root, "missing.txt")])
        gone.run_to(20)
        self.assertEqual(gone.miss_count, gone.reads, "the poller did not count each read of a missing file")

    def test_control_probe_imports_its_sibling_when_nothing_switches(self):
        fx = self.installed_fixture("ctl-probe")
        probe = Probe(fx)
        try:
            self.assertEqual(probe.line(), "started", "the probe did not start")
            got = probe.answer()
        finally:
            probe.close()
        self.assertEqual(got, "old", "with no refresh the probe imported %r, not the gen 1 sibling" % got)

    def test_control_snapshot_names_every_skill_file(self):
        fx = self.installed_fixture("ctl-snap")
        first = fx.snapshot()
        self.assertEqual(first, fx.snapshot(), "two snapshots of an unchanged install differ")
        missing = [name for name in skill_names(fx.seed) if "skills/%s/SKILL.md" % name not in first]
        self.assertEqual(missing, [], "the snapshot misses these skill files")

    def test_control_settings_names_hook_files_gen1_has(self):
        fx = self.installed_fixture("ctl-hooks")
        names = fx.settings_hook_files()
        self.assertTrue(names, "the fixture settings.json names no hook file")
        missing = [name for name in names if not os.path.isfile(os.path.join(fx.cfg, "hooks", name))]
        self.assertEqual(missing, [], "gen 1 settings names hook files it does not land")

    def test_control_age_sets_the_exact_mtime(self):
        fx = Fixture("ctl-age")
        path = os.path.join(fx.root, "aged")
        write_file(os.path.join(path, "inner.txt"), "x\n")
        when = age(path, 7200)
        self.assertEqual(int(os.stat(path).st_mtime), when, "the folder mtime is not the aged value")
        self.assertEqual(int(os.stat(os.path.join(path, "inner.txt")).st_mtime), when, "the file mtime is not aged")

    def test_control_run_folder_sweep_removes_an_old_sibling_and_keeps_a_new_one(self):
        base = os.path.join(ROOT, "ctl-sweep")
        os.makedirs(base)
        own = os.path.join(base, "%d-%s" % (os.getpid(), "a" * 32))
        old = os.path.join(base, "1-%s" % ("b" * 32))
        new = os.path.join(base, "2-%s" % ("c" * 32))
        for path in (own, old, new):
            os.makedirs(path)
        now = time.time()
        os.utime(old, (now - 2 * 24 * 3600, now - 2 * 24 * 3600))
        _test_temp.sweep(base, own, now)
        self.assertFalse(os.path.exists(old), "the sweep kept a run folder two days old")
        self.assertTrue(os.path.isdir(new), "the sweep removed a run folder that is new")


if __name__ == "__main__":
    unittest.main(verbosity=2)
