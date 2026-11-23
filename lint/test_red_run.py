#!/usr/bin/env python3
"""Cases for bin/red-run, the copy of an old commit that a test-author runs its new tests in. Standard library only.

    python3 lint/test_red_run.py

Each case builds a fixture repo under this run's folder, then runs the command with that repo as its cwd. The
export takes the commit's tree from the caller's repo, so the fixture's commits are the only source a case reads.

RED_RUN_UNDER_TEST overrides the module path. A stub run points it at lint/red_run_stub_test.py, which exits 0 and
prints nothing, so each case fails on its own assert and not on a missing file. Each case first asserts that its
test command ran in a copy (the probe's report or marker), so a case whose subject did not run cannot pass.

The contract these cases read:
  - `bin/red-run <commit> [--add <path>]... [--replace <path> <old> <new>]... -- <test cmd>`, run from the caller's repo.
  - The test command runs in a copy at <TMPDIR>/claude-settings-test-temp/<pid>-<uuid>. Each case sets TMPDIR to a
    folder beside its fixture repo, never inside it.
  - The output names the class of the run as one word: pass, assert, build, crash or timeout (mutate_shared classify_run).
  - Exit 2 for a commit that does not exist, for a missing `--`, for a --replace whose old text is missing (STALE), and for
    a test command that cannot start. That call prints one verdict line, and leaves no copy.
  - The exit codes of a pass and of a fail are not read here.
  - A signal to red-run (TERM, HUP or INT) removes the copy and stops the child.
"""
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import proc_fixture  # noqa: E402  the one home of the process waits and kills (testing/proc_fixture.py)
import tracked_tree  # noqa: E402  copies and removes trees (testing/tracked_tree.py)

MODULE = os.path.abspath(os.environ.get("RED_RUN_UNDER_TEST") or os.path.join(HERE, "..", "bin", "red-run"))
HANG_CAP = 120  # a hang guard, far above any one case
RUN_FOLDER_RE = re.compile(r"[0-9]+-[0-9a-f]{32}")
BAD_SHA = "deadbeef" * 5  # no commit of any fixture has this sha
WIDGET_OLD = "def widget():\n    return 1\n"
WIDGET_NEW = "def widget():\n    return 2\n"
ONLY_IN_HEAD = "def head_only():\n    return 3\n"
NEW_TEST = "def test_new():\n    assert True\n"  # a test file the caller has not committed
# The probe runs in the copy. It writes its cwd, its pid, the paths it reads and the .git folders it finds up the tree.
PROBE = (
    "import json, os, sys\n"
    "out, paths = sys.argv[1], sys.argv[2:]\n"
    "here = os.getcwd()\n"
    "git, above = [], here\n"
    "while True:\n"
    "    if os.path.lexists(os.path.join(above, '.git')):\n"
    "        git.append(above)\n"
    "    parent = os.path.dirname(above)\n"
    "    if parent == above:\n"
    "        break\n"
    "    above = parent\n"
    "files = {}\n"
    "for rel in paths:\n"
    "    files[rel] = None\n"
    "    if os.path.isfile(rel):\n"
    "        with open(rel, encoding='utf-8') as handle:\n"
    "            files[rel] = handle.read()\n"
    "with open(out, 'w', encoding='utf-8') as handle:\n"
    "    json.dump({'pid': os.getpid(), 'cwd': here, 'files': files, 'git': git}, handle)\n"
)
# The stop probe writes its pid and cwd by a rename, so a reader never sees half of it. Then it blocks, passes or fails.
MARK = (
    "import json, os, sys, threading\n"
    "out, mode = sys.argv[1], sys.argv[2]\n"
    "with open(out + '.part', 'w', encoding='utf-8') as handle:\n"
    "    json.dump({'pid': os.getpid(), 'cwd': os.getcwd()}, handle)\n"
    "os.replace(out + '.part', out)\n"
    "if mode == 'block':\n"
    "    threading.Event().wait()\n"
    "if mode == 'fail':\n"
    "    print('FAIL: probe')\n"
    "    sys.exit(1)\n"
)
CRASH_CODE = 'raise RuntimeError("boom")'
FAIL_CODE = 'import sys\nprint("FAIL: probe")\nsys.exit(1)'
PASS_CODE = 'print("green")'
# The verdict line bin/red-run prints last: `red-run <sha7>: <class>`. A class word anywhere else in the output is the child's, not the verdict.
VERDICT_LINE = re.compile(r"^red-run [0-9a-f]{7,}: (pass|assert|build|crash|timeout)$", re.M)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def run_env(tmp):
    """The environment of red-run and of the fixture's git. Git's own variables are stripped, so the caller's repo is
    the one the fixture names. TMPDIR is this case's folder, so the copies land there."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "RED_RUN_UNDER_TEST"}
    env.update(TMPDIR=tmp, TMP=tmp, TEMP=tmp, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return _test_git.apply(env)


def git(repo, env, *args):
    done = subprocess.run(["git", "-C", repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
                           "-c", "core.autocrlf=false", *args], check=True, capture_output=True, text=True, env=env)
    return done.stdout


def commit(repo, env, files, message):
    for rel, text in files.items():
        write(os.path.join(repo, rel), text)
    git(repo, env, "add", "-A")
    git(repo, env, "commit", "-q", "-m", message)


def fixture_repo(repo, env):
    """The caller's repo: the old commit, then a HEAD that changes the widget and adds a file. Returns the old sha."""
    os.makedirs(repo)
    git(repo, env, "init", "-q", "-b", "main")
    commit(repo, env, {"src/widgets.py": WIDGET_OLD}, "old widget")
    old = git(repo, env, "rev-parse", "HEAD").strip()
    commit(repo, env, {"src/widgets.py": WIDGET_NEW, "src/only_in_head.py": ONLY_IN_HEAD}, "new widget")
    return old


def verdict_classes(out):
    """The class word of each verdict line in OUT, in order."""
    return VERDICT_LINE.findall(out)


def reap(proc):
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=HANG_CAP)


RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


class RedRunFixture(unittest.TestCase):
    """One fixture repo per case, and the shared steps: the red-run call, the probe's scope check, and the run folders."""

    def setUp(self):
        self.case = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.repo = os.path.join(self.case, "repo")
        self.tmp = os.path.join(self.case, "tmp")  # TMPDIR of the run: a sibling of the repo
        self.outs = os.path.join(self.case, "out")
        for folder in (self.tmp, self.outs):
            os.makedirs(folder)
        self.temp_root = os.path.join(self.tmp, "claude-settings-test-temp")
        self.env = run_env(self.tmp)
        self.old = fixture_repo(self.repo, self.env)

    def red_run(self, *args):
        done = subprocess.run([sys.executable, MODULE, *args], cwd=self.repo, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=HANG_CAP)
        return done.returncode, done.stdout + done.stderr

    def probe(self, name, *paths):
        """The test command that writes the probe's report to outs/<name>, then reads each of PATHS in the copy."""
        return [sys.executable, "-c", PROBE, os.path.join(self.outs, name), *paths]

    def scoped_report(self, name):
        """The report that the test command wrote. The first assert of each case: no report means no test command ran
        in a copy, so the case's subject never ran. The report must come from a run folder under the temp root."""
        path = os.path.join(self.outs, name)
        self.assertTrue(os.path.isfile(path), "no test command ran in a copy: no report was written")
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
        self.assertEqual(os.path.dirname(os.path.realpath(report["cwd"])), os.path.realpath(self.temp_root),
                         "the test command ran outside the temp root's run folders, in %s" % report["cwd"])
        self.assertIsNotNone(RUN_FOLDER_RE.fullmatch(os.path.basename(report["cwd"])),
                             "the copy is not named <pid>-<uuid>: %s" % report["cwd"])
        return report

    def run_folders(self):
        if not os.path.isdir(self.temp_root):
            return []
        return [name for name in os.listdir(self.temp_root)
                if RUN_FOLDER_RE.fullmatch(name) and os.path.isdir(os.path.join(self.temp_root, name))]

    def status(self):
        return git(self.repo, self.env, "status", "--porcelain")

    def assertVerdict(self, out, want, cause):
        """OUT holds one verdict line and its class is WANT. Each failure names one cause: no single line, or another class."""
        classes = verdict_classes(out)
        self.assertEqual(len(classes), 1, "%s: %d verdict lines, want 1" % (cause, len(classes)))
        self.assertEqual(classes[0], want, "%s: the verdict line reads %s, want %s" % (cause, classes[0], want))


class RedRunCopyCases(RedRunFixture):
    """What the copy holds, and what the command does to the copy and to the caller's checkout."""

    def test_the_copy_holds_the_commit_tree_not_head(self):
        self.red_run(self.old, "--", *self.probe("tree.json", "src/widgets.py", "src/only_in_head.py"))
        report = self.scoped_report("tree.json")
        self.assertEqual(report["files"]["src/widgets.py"], WIDGET_OLD, "the copy holds HEAD's widget, not the commit's")
        self.assertIsNone(report["files"]["src/only_in_head.py"], "the copy holds a file that only HEAD has")

    def test_add_puts_the_callers_file_at_the_same_path(self):
        write(os.path.join(self.repo, "tests", "test_new.py"), NEW_TEST)
        self.red_run(self.old, "--add", "tests/test_new.py", "--", *self.probe("add.json", "tests/test_new.py"))
        report = self.scoped_report("add.json")
        self.assertEqual(report["files"]["tests/test_new.py"], NEW_TEST, "--add did not put the caller's file in the copy")

    def test_the_copy_has_no_git_in_it_or_above(self):
        self.red_run(self.old, "--", *self.probe("git.json"))
        report = self.scoped_report("git.json")
        self.assertEqual(report["git"], [], "a .git sits in or above the copy: %s" % report["git"])

    def test_replace_mutates_the_copy_and_not_the_callers_checkout(self):
        self.red_run(self.old, "--replace", "src/widgets.py", "return 1", "return 7",
                     "--", *self.probe("replace.json", "src/widgets.py"))
        report = self.scoped_report("replace.json")
        self.assertEqual(report["files"]["src/widgets.py"], "def widget():\n    return 7\n",
                         "--replace did not mutate the copy")
        self.assertEqual(self.status(), "", "--replace left the caller's checkout changed")

    def test_replace_with_missing_old_text_exits_2_as_stale(self):
        rc, out = self.red_run(self.old, "--replace", "src/widgets.py", "return 99", "return 7",
                               "--", *self.probe("stale.json", "src/widgets.py"))
        self.assertEqual(rc, 2, "a --replace whose old text is missing exited %d, want 2" % rc)
        self.assertIn("STALE", out, "a --replace whose old text is missing named no STALE")

    def test_a_crashing_child_reads_as_crash(self):
        _, out = self.red_run(self.old, "--", sys.executable, "-c", CRASH_CODE)
        self.assertVerdict(out, "crash", "a child that raised an error")

    def test_a_failing_child_reads_as_assert(self):
        _, out = self.red_run(self.old, "--", sys.executable, "-c", FAIL_CODE)
        self.assertVerdict(out, "assert", "a child that printed a FAIL line")

    def test_a_passing_child_reads_as_pass(self):
        _, out = self.red_run(self.old, "--", sys.executable, "-c", PASS_CODE)
        self.assertVerdict(out, "pass", "a child that exits 0")


class RedRunBadCallCases(RedRunFixture):
    """A call that is refused leaves no run folder behind."""

    def test_a_commit_that_does_not_exist_exits_2_and_leaves_no_folder(self):
        rc, _ = self.red_run(BAD_SHA, "--", *self.probe("bad.json"))
        self.assertEqual(rc, 2, "a commit that does not exist exited %d, want 2" % rc)
        self.assertEqual(self.run_folders(), [], "a commit that does not exist left a run folder")

    def test_a_missing_dashdash_exits_2_and_leaves_no_folder(self):
        rc, _ = self.red_run(self.old, *self.probe("nodash.json"))
        self.assertEqual(rc, 2, "a call with no `--` exited %d, want 2" % rc)
        self.assertEqual(self.run_folders(), [], "a call with no `--` left a run folder")

    def test_a_command_that_cannot_start_exits_2_with_one_verdict_line_and_leaves_no_folder(self):
        rc, out = self.red_run("HEAD", "--", "no-such-test-runner-xyz")
        self.assertEqual(rc, 2, "a test command that cannot start exited %d, want 2" % rc)
        self.assertNotIn("Traceback (most recent call last)", out, "a test command that cannot start printed a traceback")
        lines = verdict_classes(out)
        self.assertEqual(len(lines), 1, "a test command that cannot start printed %d verdict lines, want 1" % len(lines))
        self.assertEqual(self.run_folders(), [], "a test command that cannot start left a run folder")


@unittest.skipIf(os.name == "nt", "proc_fixture's waits and kills are POSIX only, and the signal cases need a POSIX child")
class RedRunStopCases(RedRunFixture):
    """The copy goes at the end of a run, and at a signal the child is stopped and the copy goes."""

    def run_to_end(self, mode):
        self.red_run(self.old, "--", sys.executable, "-c", MARK, os.path.join(self.outs, mode + ".json"), mode)
        report = self.scoped_report(mode + ".json")
        self.assertFalse(os.path.exists(report["cwd"]), "a run that ended with %s left its copy behind" % mode)

    def stop_while_running(self, name, sig):
        marker = os.path.join(self.outs, name + ".json")
        log = os.path.join(self.outs, name + ".log")
        with open(log, "w", encoding="utf-8") as out:
            proc = subprocess.Popen([sys.executable, MODULE, self.old, "--", sys.executable, "-c", MARK, marker, "block"],
                                    cwd=self.repo, env=self.env, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, preexec_fn=proc_fixture.default_sigint())
        self.addCleanup(reap, proc)
        started = proc_fixture.wait_for(marker, HANG_CAP, proc=proc)
        if not started and proc.poll() is not None:
            self.fail("red-run exited %d before its test command started in a copy" % proc.returncode)
        self.assertTrue(started, "red-run started no test command in a copy within the hang cap")
        report = self.scoped_report(name + ".json")
        self.addCleanup(proc_fixture.kill_all, [report["pid"]])
        proc.send_signal(sig)
        try:
            proc.wait(timeout=HANG_CAP)
        except subprocess.TimeoutExpired:
            self.fail("red-run did not exit after %s" % name)
        self.assertFalse(os.path.exists(report["cwd"]), "the copy survived %s" % name)
        self.assertTrue(proc_fixture.wait_gone(report["pid"], HANG_CAP), "the test command survived %s" % name)

    def test_a_passing_run_removes_the_copy(self):
        self.run_to_end("pass")

    def test_a_failing_run_removes_the_copy(self):
        self.run_to_end("fail")

    def test_term_removes_the_copy_and_stops_the_child(self):
        self.stop_while_running("term", signal.SIGTERM)

    def test_hup_removes_the_copy_and_stops_the_child(self):
        self.stop_while_running("hup", signal.SIGHUP)

    def test_int_removes_the_copy_and_stops_the_child(self):
        self.stop_while_running("int", signal.SIGINT)


if __name__ == "__main__":
    unittest.main()
