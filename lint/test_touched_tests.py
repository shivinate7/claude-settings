#!/usr/bin/env python3
"""CLI tests for the touched-test selector (.github/scripts/touched-tests.py).

Each case builds a scratch git repo under this run's folder: it commits a base, commits the changed
paths on top, runs the selector in that checkout with BASE_SHA set, and reads the name=value lines the
selector wrote to $GITHUB_OUTPUT. TOUCHED_TESTS overrides the script path (for a successor).

The selector's HEAVY and NEEDS_SETUP lists are read from the script's own constants, never copied here.
The script keeps its main() under an `if __name__ == "__main__":` guard, so importing it for those
constants runs nothing.

Output names pinned (the selector writes them to $GITHUB_OUTPUT):
  files  a JSON list of the test files to run
  any    true when files is non-empty, else false
  files_windows  a JSON list of the test files the Windows job runs
  files_macos    a JSON list of the test files the macOS job runs

Run with:  python3 lint/test_touched_tests.py -v
"""
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies tracked folders into a scratch repo; rm_tree removes the run folder
SCRIPT = os.environ.get("TOUCHED_TESTS") or os.path.join(HERE, "..", ".github", "scripts", "touched-tests.py")
# The reason keys a skipped line carries: a word from each bucket's reason, never a whole sentence.
HEAVY_KEY = re.compile(r"heavy|shard", re.IGNORECASE)
NEEDS_SETUP_KEY = re.compile(r"needs", re.IGNORECASE)
WINDOWS_KEY = re.compile(r"windows", re.IGNORECASE)
# The per-OS output names: one JSON list for the Windows job and one for the macOS job.
OS_KEYS = ("files_windows", "files_macos")


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {args[0]} failed in a fixture: {r.stderr.strip()}")
    return r.stdout.strip()


def write(root, rel, text):
    full = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def covers(entries, path):
    """True when one entry of a selector list names `path`, as a path or as a glob."""
    return any(fnmatch.fnmatchcase(path, entry) for entry in entries)


def named(stdout, path, key):
    """True when one line of the selector's stdout names `path` and carries the reason key `key`."""
    return any(path in line and key.search(line) for line in stdout.splitlines())


class Selector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_dir = _test_temp.run_folder()

    @classmethod
    def tearDownClass(cls):
        tracked_tree.rm_tree(cls.run_dir)

    def fixture(self, base, change=None, delete=()):
        """A scratch repo under the run folder. `base` ({path: text}) is committed first. Then `change` is written and
        the paths in `delete` are removed, in one head commit. -> (repo, base sha, GITHUB_OUTPUT path).
        The repo holds the real .github/scripts and .github/workflows, so a selector that reads them finds them."""
        case = tempfile.mkdtemp(dir=self.run_dir)
        repo = os.path.join(case, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q")
        for key, value in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false"),
                           ("gc.auto", "0"), ("maintenance.auto", "false")):
            git(repo, "config", key, value)
        tracked_tree.copy_tracked(repo, ".github/scripts", ".github/workflows")
        for rel, text in base.items():
            write(repo, rel, text)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        base_sha = git(repo, "rev-parse", "HEAD")
        for rel, text in (change or {}).items():
            write(repo, rel, text)
        for rel in delete:
            os.remove(os.path.join(repo, *rel.split("/")))
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "head", "--allow-empty")
        return repo, base_sha, os.path.join(case, "github-output.txt")

    def select(self, repo, base_sha, out):
        """Run the selector in `repo` with BASE_SHA set to `base_sha` (None leaves it unset). -> (CompletedProcess, outputs).
        The scope check comes first: with the script absent, every case fails on this one named cause."""
        self.assertTrue(os.path.isfile(SCRIPT), f"the selector is absent: {SCRIPT} does not exist")
        env = {k: v for k, v in os.environ.items() if k != "BASE_SHA"}
        env["GITHUB_OUTPUT"] = out
        if base_sha is not None:
            env["BASE_SHA"] = base_sha
        r = subprocess.run([sys.executable, SCRIPT], cwd=repo, env=env, capture_output=True, text=True)
        outputs = {}
        if os.path.isfile(out):
            with open(out) as f:
                for line in f.read().splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        outputs[key] = value
        return r, outputs

    def listed(self, base, change=None, delete=()):
        """Run the selector on a fixture with a readable diff. -> (sorted files, stdout). The scope is checked first:
        the run exited 0, wrote both outputs, and any agrees with files."""
        repo, sha, out = self.fixture(base, change, delete)
        r, outputs = self.select(repo, sha, out)
        self.assertEqual(r.returncode, 0, f"the selector exited {r.returncode} on a readable diff:\n{r.stdout}{r.stderr}")
        self.assertIn("files", outputs, f"no files= line in GITHUB_OUTPUT: {outputs}")
        self.assertIn("any", outputs, f"no any= line in GITHUB_OUTPUT: {outputs}")
        try:
            files = json.loads(outputs["files"])
        except ValueError:
            self.fail(f"files= is not JSON: {outputs['files']!r}")
        self.assertIsInstance(files, list, f"files= is not a JSON list: {outputs['files']!r}")
        self.assertEqual(outputs["any"], "true" if files else "false", f"any disagrees with files: {outputs}")
        return sorted(files), r.stdout

    def constant(self, name):
        """The list the selector holds as its constant `name`. The script is loaded for it, never copied here."""
        spec = importlib.util.spec_from_file_location("touched_tests", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value = getattr(module, name, None)
        self.assertIsNotNone(value, f"the selector has no {name} constant")
        return list(value)

    def json_list(self, text, key):
        """The JSON list one output line holds. A value that is not a JSON list fails the case by name."""
        try:
            value = json.loads(text)
        except ValueError:
            self.fail(f"{key}= is not JSON: {text!r}")
        self.assertIsInstance(value, list, f"{key}= is not a JSON list: {text!r}")
        return value

    def per_os(self, base, change=None, delete=()):
        """Run the selector on a fixture with a readable diff. -> (sorted files_windows, sorted files_macos, stdout).
        The scope is checked first: the run exited 0 and wrote both per-OS outputs."""
        repo, sha, out = self.fixture(base, change, delete)
        r, outputs = self.select(repo, sha, out)
        self.assertEqual(r.returncode, 0, f"the selector exited {r.returncode} on a readable diff:\n{r.stdout}{r.stderr}")
        lists = {}
        for key in OS_KEYS:
            self.assertIn(key, outputs, f"the selector writes no {key}= line, so the per-OS lists are not built: {outputs}")
            lists[key] = self.json_list(outputs[key], key)
        return sorted(lists["files_windows"]), sorted(lists["files_macos"]), r.stdout

    def test_control_the_fixture_diff_names_the_changed_path(self):
        """Green control: with no selector, the fixture's own diff still holds the path it changed, so each red case
        is the selector's failure and not the fixture's. It asserts nothing about the selector."""
        path = "skills/alpha/tests/a.test.mjs"
        repo, sha, _ = self.fixture({path: "old\n"}, {path: "new\n"})
        self.assertEqual(git(repo, "diff", "--name-only", "--no-renames", f"{sha}...HEAD").split(), [path],
                         "the fixture's diff does not hold the changed path")
        self.assertTrue(os.path.isdir(os.path.join(repo, ".github", "workflows")), "the fixture did not copy .github/workflows")

    def test_touched_skill_test_is_listed(self):
        path = "skills/alpha/tests/a.test.mjs"
        files, stdout = self.listed({path: "old\n"}, {path: "new\n"})
        self.assertEqual(files, [path], "a touched skill test was not listed")
        self.assertIn(path, stdout, "the log does not name the listed test")

    def test_each_test_file_pattern_is_listed(self):
        paths = ["skills/alpha/tests/a.test.mjs", "skills/alpha/tests/b.test.js", "lint/test_c.py",
                 "lint/test_d.sh", "lint/e.test.sh"]
        files, _ = self.listed({p: "old\n" for p in paths}, {p: "new\n" for p in paths})
        self.assertEqual(files, sorted(paths), "a test-file pattern is missing from the list, or a path is listed twice")

    def test_source_with_sibling_test_lists_that_test(self):
        files, _ = self.listed({"lint/check_foo.py": "old\n", "lint/test_check_foo.py": "old\n"},
                               {"lint/check_foo.py": "new\n"})
        self.assertEqual(files, ["lint/test_check_foo.py"], "a touched source did not list its sibling test_*.py")

    def test_source_without_a_test_lists_nothing(self):
        files, _ = self.listed({"lint/check_bare.py": "old\n"}, {"lint/check_bare.py": "new\n"})
        self.assertEqual(files, [], "a source with no test file listed something")

    def test_mjs_source_lists_the_test_in_its_tests_folder(self):
        test = "mods/plain-diff/tests/check.test.mjs"
        files, _ = self.listed({test: "old\n", "mods/plain-diff/check.mjs": "old\n"}, {"mods/plain-diff/check.mjs": "new\n"})
        self.assertEqual(files, [test], "a touched .mjs did not list its dir/tests/x.test.mjs")

    def test_plain_english_map_script_lists_every_map_test(self):
        tests = [f"skills/plain-english-map/tests/{n}.test.mjs" for n in ("a", "b", "c")]
        script = "skills/plain-english-map/scripts/build.mjs"
        files, _ = self.listed({p: "old\n" for p in tests + [script]}, {script: "new\n"})
        self.assertEqual(files, tests, "a plain-english-map script did not list the whole tests folder")

    def test_plain_english_map_markdown_lists_nothing(self):
        md = "skills/plain-english-map/SKILL.md"
        files, _ = self.listed({md: "old\n", "skills/plain-english-map/tests/a.test.mjs": "old\n"}, {md: "new\n"})
        self.assertEqual(files, [], "a .md under the map skill listed a test")

    def test_docs_only_change_lists_nothing(self):
        docs = {"README.md": "old\n", "docs/notes.md": "old\n"}
        files, _ = self.listed(docs, {p: "new\n" for p in docs})
        self.assertEqual(files, [], "a docs-only change listed a test")

    def test_helper_in_a_tests_folder_lists_every_test_in_that_folder(self):
        mine = ["skills/alpha/tests/a.test.mjs", "skills/alpha/tests/b.test.mjs"]
        helper = "skills/alpha/tests/helpers.mjs"
        other = "skills/beta/tests/z.test.mjs"
        files, _ = self.listed({p: "old\n" for p in mine + [helper, other]}, {helper: "new\n"})
        self.assertEqual(files, mine, "a helper did not list every test in its folder, or listed a test from another folder")

    def test_heavy_suite_touched_is_not_listed_and_is_named(self):
        suite = "hooks/test_guard.py"
        files, stdout = self.listed({suite: "old\n"}, {suite: "new\n"})
        self.assertTrue(covers(self.constant("HEAVY"), suite), "the selector's HEAVY constant does not name hooks/test_guard.py")
        self.assertNotIn(suite, files, "a HEAVY suite was listed for a lane push")
        self.assertTrue(named(stdout, suite, HEAVY_KEY), "the log does not name the HEAVY suite with its reason")

    def test_needs_setup_suite_touched_is_not_listed_and_is_named(self):
        page = "skills/alpha/tests/page.test.mjs"
        files, stdout = self.listed({page: "old\n"}, {page: "new\n"})
        self.assertTrue(covers(self.constant("NEEDS_SETUP"), page),
                        "the selector's NEEDS_SETUP constant does not cover a browser suite named page.test.mjs")
        self.assertNotIn(page, files, "a NEEDS_SETUP suite was listed for a lane push")
        self.assertTrue(named(stdout, page, NEEDS_SETUP_KEY), "the log does not name the NEEDS_SETUP suite with its reason")

    def test_deleted_test_is_not_listed(self):
        gone = "skills/alpha/tests/gone.test.mjs"
        files, _ = self.listed({gone: "old\n"}, delete=[gone])
        self.assertEqual(files, [], "a deleted test file was listed, though it does not exist at HEAD")

    def test_missing_base_sha_exits_nonzero(self):
        repo, _, out = self.fixture({"lint/check_foo.py": "old\n"}, {"lint/check_foo.py": "new\n"})
        r, outputs = self.select(repo, None, out)
        self.assertNotEqual(r.returncode, 0, f"no BASE_SHA exited 0:\n{r.stdout}{r.stderr}")
        self.assertNotEqual(outputs.get("any"), "false", "no BASE_SHA wrote any=false: an unknown diff reads as nothing to run")

    def test_unreadable_base_sha_exits_nonzero(self):
        repo, _, out = self.fixture({"lint/check_foo.py": "old\n"}, {"lint/check_foo.py": "new\n"})
        r, outputs = self.select(repo, "0" * 40, out)
        self.assertNotEqual(r.returncode, 0, f"an unreadable BASE_SHA exited 0:\n{r.stdout}{r.stderr}")
        self.assertNotEqual(outputs.get("any"), "false", "an unreadable BASE_SHA wrote any=false: an unknown diff reads as nothing to run")

    def test_powershell_test_is_listed_for_windows_only(self):
        """A touched *.test.ps1 runs on Windows only: it is in files_windows and not in files_macos."""
        path = "install.test.ps1"
        windows, macos, stdout = self.per_os({path: "old\n"}, {path: "new\n"})
        self.assertIn(path, windows, "a touched *.test.ps1 is not in files_windows")
        self.assertNotIn(path, macos, "a touched *.test.ps1 is in files_macos, where it cannot run")
        self.assertIn(path, stdout, "the log does not name the touched *.test.ps1")

    def test_mjs_source_lists_its_sibling_test_stem_mjs(self):
        test = "actions/stamp/test_stamp.mjs"
        files, _ = self.listed({test: "old\n", "actions/stamp/stamp.mjs": "old\n"}, {"actions/stamp/stamp.mjs": "new\n"})
        self.assertEqual(files, [test], "a touched stamp.mjs did not list its sibling test_stamp.mjs")

    def test_sh_source_lists_its_sibling_test_stem_sh(self):
        test = "merge/test_install_from_main.sh"
        files, _ = self.listed({test: "old\n", "merge/install_from_main.sh": "old\n"}, {"merge/install_from_main.sh": "new\n"})
        self.assertEqual(files, [test], "a touched install_from_main.sh did not list its sibling test_install_from_main.sh")

    def test_a_test_no_windows_job_runs_is_left_out_of_files_windows_with_a_reason(self):
        paths = ["merge/test_install_from_main.sh", "hooks/test_cloud_setup.sh"]
        windows, _, stdout = self.per_os({p: "old\n" for p in paths}, {p: "new\n" for p in paths})
        not_on_windows = self.constant("NOT_ON_WINDOWS")
        for path in paths:
            self.assertTrue(covers(not_on_windows, path), f"the selector's NOT_ON_WINDOWS constant does not cover {path}")
            self.assertNotIn(path, windows, f"{path} is in files_windows, though no Windows job runs it")
            self.assertTrue(named(stdout, path, WINDOWS_KEY), f"the log does not name {path} with a Windows reason")


if __name__ == "__main__":
    unittest.main()
