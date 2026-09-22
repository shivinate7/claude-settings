#!/usr/bin/env python3
"""Cases for janitor/install_schtasks.py. Standard library only, `unittest`, no pytest.

Run it from the repository root:

    python3 janitor/test_install_schtasks.py -v

The worktree refusal is proven by RUNNING THE INSTALLER FROM A REAL LINKED WORKTREE FIXTURE
(`git worktree add`), never by reading the source. A real worktree is the one thing that makes
`hooks/guard.py.is_worktree` answer True. That answer is what this installer's refusal turns on.

This suite never calls `schtasks` and never writes outside a throwaway temp directory: every
case passes `--output-dir` pointing at one.
"""
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
INSTALLER = os.path.join(HERE, "install_schtasks.py")
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402
import install_schtasks  # noqa: E402

VCS = "g" + "it"
IDENT = ["-c", "user.email=install-cases@example.invalid", "-c", "user.name=install-cases"]
NS = "{%s}" % install_schtasks.TASK_XML_NAMESPACE

ROOT = tempfile.mkdtemp(prefix="install_schtasks_cases_")


def run_vcs(where, *args):
    return subprocess.run([VCS, "-C", where, *args], capture_output=True, text=True, timeout=10)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def require(condition, message):
    if not condition:
        sys.exit("fixture setup failed: " + message)


def make_repo(where, branch="main"):
    os.makedirs(where, exist_ok=True)
    require(run_vcs(where, "init", "-q", "-b", branch, ".").returncode == 0, "init %r" % where)
    write(os.path.join(where, "README.md"), "hello\n")
    require(run_vcs(where, "add", "-A").returncode == 0, "add %r" % where)
    require(run_vcs(where, *IDENT, "commit", "-q", "-m", "first").returncode == 0,
            "first commit in %r" % where)


def run_installer(args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, INSTALLER] + args, capture_output=True, text=True, timeout=20, env=env,
    )


def make_blind_git(folder):
    """A `git` (and `git.cmd`, for a shell-form call) stand-in that fails to answer
    everything. It is the same trick janitor/test_sweep.py's own make_blind_git uses,
    kept local to this file.

    A list-form `subprocess.run(["git", ...])` never reaches `git.cmd` on Windows,
    because CreateProcess appends only `.exe` when it resolves a bare command from a
    list. See decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md."""
    os.makedirs(folder, exist_ok=True)
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\necho 'blind git: no answer' >&2\nexit 128\n")
    os.chmod(script, 0o755)
    cmd_script = os.path.join(folder, "git.cmd")
    write(cmd_script, "@echo off\necho blind git: no answer 1>&2\nexit /b 128\n")
    os.chmod(cmd_script, 0o755)


class GeneratesTaskXmlForAnOrdinaryCheckout(unittest.TestCase):
    """Not the refusal arm: proves the happy path actually writes a usable task definition. The
    refusal arm below is then proven against a working installer, not a broken one that always
    refuses."""

    @classmethod
    def setUpClass(cls):
        cls.repo = os.path.join(ROOT, "ordinary_checkout")
        make_repo(cls.repo)
        require(guard.is_worktree(cls.repo) is False,
                "fixture: an ordinary checkout must answer is_worktree() == False")

    def test_writes_well_formed_xml_with_the_expected_task_and_command(self):
        out_dir = os.path.join(ROOT, "out_happy")
        result = run_installer(
            ["--repo-root", self.repo, "--output-dir", out_dir,
             "--discover-root", os.path.join(ROOT, "discover_happy")],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        xml_path = os.path.join(out_dir, install_schtasks.TASK_NAME + ".xml")
        self.assertTrue(os.path.isfile(xml_path), result.stdout + result.stderr)

        tree = ET.parse(xml_path)
        root = tree.getroot()
        self.assertEqual(root.tag, NS + "Task")
        self.assertNotIn("worktree", install_schtasks.TASK_NAME.lower())

        command = root.find("%sActions/%sExec/%sCommand" % (NS, NS, NS))
        arguments = root.find("%sActions/%sExec/%sArguments" % (NS, NS, NS))
        self.assertIsNotNone(command)
        self.assertIsNotNone(arguments)
        self.assertEqual(command.text, sys.executable)
        self.assertIn("sweep.py", arguments.text)
        self.assertIn("--confirm", arguments.text)
        self.assertIn("--discover", arguments.text)

        trigger = root.find("%sTriggers/%sCalendarTrigger" % (NS, NS))
        self.assertIsNotNone(trigger, "must schedule a daily CalendarTrigger")

    def test_prints_the_real_schtasks_command_and_never_calls_it(self):
        out_dir = os.path.join(ROOT, "out_print_check")
        result = run_installer(
            ["--repo-root", self.repo, "--output-dir", out_dir,
             "--discover-root", os.path.join(ROOT, "discover_print_check")],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        xml_path = os.path.join(out_dir, install_schtasks.TASK_NAME + ".xml")
        self.assertIn("schtasks /create /tn", result.stdout)
        self.assertIn(install_schtasks.TASK_NAME, result.stdout)
        self.assertIn(xml_path, result.stdout)

    def test_never_touches_the_repo_tree_git_status_stays_clean(self):
        before = subprocess.run(
            [VCS, "-C", self.repo, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        require(before.returncode == 0, "git status before install")
        out_dir = os.path.join(ROOT, "out_status_check")
        result = run_installer(
            ["--repo-root", self.repo, "--output-dir", out_dir,
             "--discover-root", os.path.join(ROOT, "discover_status_check")],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = subprocess.run(
            [VCS, "-C", self.repo, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        require(after.returncode == 0, "git status after install")
        self.assertEqual(before.stdout, after.stdout,
                          "generating the XML must leave the checkout's git status untouched "
                          "-- it must never land inside the tracked tree")


class RefusesALinkedWorktree(unittest.TestCase):
    """Runs the installer from a REAL linked worktree fixture, not a mock."""

    @classmethod
    def setUpClass(cls):
        cls.primary = os.path.join(ROOT, "refusal_primary")
        make_repo(cls.primary)
        cls.linked = os.path.join(ROOT, "refusal_linked")
        branch = "refusal-branch"
        require(run_vcs(cls.primary, "branch", branch).returncode == 0, "branch for worktree")
        require(run_vcs(cls.primary, "worktree", "add", cls.linked, branch).returncode == 0,
                "worktree add")
        require(os.path.isdir(cls.linked), "fixture: linked worktree exists")
        require(guard.is_worktree(cls.linked) is True,
                "fixture: the linked worktree must answer is_worktree() == True")

    def test_refuses_and_names_the_main_checkout_in_its_remedy(self):
        out_dir = os.path.join(ROOT, "out_refusal")
        result = run_installer(["--repo-root", self.linked, "--output-dir", out_dir])
        self.assertNotEqual(result.returncode, 0,
                             "the installer must refuse a linked worktree, not proceed")
        self.assertIn("worktree", result.stderr.lower())
        self.assertIn(os.path.realpath(self.primary), result.stderr,
                       "the refusal must name the main checkout as the remedy")
        xml_path = os.path.join(out_dir, install_schtasks.TASK_NAME + ".xml")
        self.assertFalse(os.path.isfile(xml_path),
                          "a refused install must not write any task XML at all")

    def test_task_name_never_names_the_worktree(self):
        self.assertNotIn(os.path.basename(self.linked), install_schtasks.TASK_NAME)
        self.assertNotIn("worktree", install_schtasks.TASK_NAME.lower())


class RefusesWhenWorktreeStatusIsUnreadable(unittest.TestCase):
    """Same conservative direction as a linked worktree, when the read itself fails."""

    @unittest.skipIf(
        os.name == "nt",
        "Windows CreateProcess resolves a list-form subprocess call by appending "
        "only .exe, so this PATH-shadowing git.cmd stand-in is never reached. "
        "See decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md.",
    )
    def test_unreadable_worktree_status_refuses_too(self):
        repo = os.path.join(ROOT, "unreadable_repo")
        make_repo(repo)
        blind_bin = os.path.join(ROOT, "blind_bin_install")
        make_blind_git(blind_bin)
        env = dict(os.environ)
        env["PATH"] = blind_bin + os.pathsep + env.get("PATH", "")
        out_dir = os.path.join(ROOT, "out_unreadable")
        result = subprocess.run(
            [sys.executable, INSTALLER, "--repo-root", repo, "--output-dir", out_dir],
            capture_output=True, text=True, timeout=20, env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        xml_path = os.path.join(out_dir, install_schtasks.TASK_NAME + ".xml")
        self.assertFalse(os.path.isfile(xml_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
