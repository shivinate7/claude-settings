#!/usr/bin/env python3
"""Cases for janitor/install_launchd.py. Standard library only, `unittest`, no pytest.

Run it from the repository root:

    python3 janitor/test_install_launchd.py -v

The worktree refusal is proven by RUNNING THE INSTALLER FROM A REAL LINKED WORKTREE FIXTURE
(`git worktree add`), never by reading the source: a real worktree is the one thing that makes
`hooks/guard.py.is_worktree` answer True, and that answer is what this installer's refusal
turns on.

This suite never writes to the real `~/Library` and never calls `launchctl`: every case passes
`--library-dir` pointing at a throwaway temp directory.
"""
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
INSTALLER = os.path.join(HERE, "install_launchd.py")
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402
import install_launchd  # noqa: E402

VCS = "g" + "it"
IDENT = ["-c", "user.email=install-cases@example.invalid", "-c", "user.name=install-cases"]

ROOT = tempfile.mkdtemp(prefix="install_launchd_cases_")


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


def run_installer(args, cfg_dir=None, env_extra=None):
    env = dict(os.environ)
    if cfg_dir:
        env["CLAUDE_CONFIG_DIR"] = cfg_dir
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, INSTALLER] + args, capture_output=True, text=True, timeout=20, env=env,
    )


def make_blind_git(folder):
    """A `git` stand-in that fails to answer everything, the same trick
    janitor/test_sweep.py's own make_blind_git uses, kept local to this file."""
    os.makedirs(folder, exist_ok=True)
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\necho 'blind git: no answer' >&2\nexit 128\n")
    os.chmod(script, 0o755)


class GeneratesPlistForAnOrdinaryCheckout(unittest.TestCase):
    """Not the refusal arm: proves the happy path actually writes a usable plist, so the
    refusal arm below is proven against a working installer, not a broken one that always
    refuses."""

    @classmethod
    def setUpClass(cls):
        cls.repo = os.path.join(ROOT, "ordinary_checkout")
        make_repo(cls.repo)
        require(guard.is_worktree(cls.repo) is False,
                "fixture: an ordinary checkout must answer is_worktree() == False")

    def test_writes_plist_under_library_launchagents(self):
        lib_dir = os.path.join(ROOT, "lib_happy")
        cfg = os.path.join(ROOT, "cfg_happy")
        result = run_installer(
            ["--repo-root", self.repo, "--library-dir", lib_dir,
             "--discover-root", os.path.join(ROOT, "discover_happy")],
            cfg_dir=cfg,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plist_path = os.path.join(lib_dir, "LaunchAgents", install_launchd.LABEL + ".plist")
        self.assertTrue(os.path.isfile(plist_path), result.stdout + result.stderr)
        with open(plist_path, "rb") as handle:
            data = plistlib.load(handle)
        self.assertEqual(data["Label"], install_launchd.LABEL)
        self.assertNotIn("worktree", data["Label"].lower())
        args_joined = " ".join(data["ProgramArguments"])
        self.assertIn("sweep.py", args_joined)
        self.assertIn("--confirm", data["ProgramArguments"])
        self.assertIn("--discover", data["ProgramArguments"])
        self.assertIn("StartCalendarInterval", data)
        self.assertFalse(data["RunAtLoad"])

    def test_never_touches_the_repo_tree_git_status_stays_clean(self):
        """Check 7: the generated plist must not become a tracked path. Uses the ordinary
        fixture checkout, not REPO_ROOT itself -- this suite runs from inside a linked
        worktree of the real repository, and `--repo-root REPO_ROOT` would just hit the
        refusal arm above. Any ordinary checkout proves the same thing: the plist lands only
        under `--library-dir`, never inside the tree the installer was pointed at."""
        before = subprocess.run(
            [VCS, "-C", self.repo, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        require(before.returncode == 0, "git status before install")
        lib_dir = os.path.join(ROOT, "lib_status_check")
        result = run_installer(
            ["--repo-root", self.repo, "--library-dir", lib_dir,
             "--discover-root", os.path.join(ROOT, "discover_status_check")],
            cfg_dir=os.path.join(ROOT, "cfg_status_check"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = subprocess.run(
            [VCS, "-C", self.repo, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        require(after.returncode == 0, "git status after install")
        self.assertEqual(before.stdout, after.stdout,
                          "generating the plist must leave the checkout's git status "
                          "untouched -- it must never land inside the tracked tree")


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
        lib_dir = os.path.join(ROOT, "lib_refusal")
        result = run_installer(
            ["--repo-root", self.linked, "--library-dir", lib_dir],
            cfg_dir=os.path.join(ROOT, "cfg_refusal"),
        )
        self.assertNotEqual(result.returncode, 0,
                             "the installer must refuse a linked worktree, not proceed")
        self.assertIn("worktree", result.stderr.lower())
        self.assertIn(os.path.realpath(self.primary), result.stderr,
                       "the refusal must name the main checkout as the remedy")
        plist_path = os.path.join(lib_dir, "LaunchAgents", install_launchd.LABEL + ".plist")
        self.assertFalse(os.path.isfile(plist_path),
                          "a refused install must not write any plist at all")

    def test_label_never_names_the_worktree(self):
        # Even on the happy path the label is fixed and generic; here we additionally confirm
        # the refusal path prints no plist whose Label could have named the worktree, by way of
        # there being no plist at all (checked above). This case documents that guarantee
        # directly against install_launchd.LABEL rather than by absence alone.
        self.assertNotIn(os.path.basename(self.linked), install_launchd.LABEL)
        self.assertNotIn("worktree", install_launchd.LABEL.lower())


class RefusesWhenWorktreeStatusIsUnreadable(unittest.TestCase):
    """Same conservative direction as a linked worktree, when the read itself fails."""

    def test_unreadable_worktree_status_refuses_too(self):
        repo = os.path.join(ROOT, "unreadable_repo")
        make_repo(repo)
        blind_bin = os.path.join(ROOT, "blind_bin_install")
        make_blind_git(blind_bin)
        env = dict(os.environ)
        env["PATH"] = blind_bin + os.pathsep + env.get("PATH", "")
        lib_dir = os.path.join(ROOT, "lib_unreadable")
        result = subprocess.run(
            [sys.executable, INSTALLER, "--repo-root", repo, "--library-dir", lib_dir],
            capture_output=True, text=True, timeout=20, env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        plist_path = os.path.join(lib_dir, "LaunchAgents", install_launchd.LABEL + ".plist")
        self.assertFalse(os.path.isfile(plist_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
