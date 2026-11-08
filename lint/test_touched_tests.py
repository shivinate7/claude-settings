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
MACOS_KEY = re.compile(r"macos", re.IGNORECASE)
NO_JOB_KEY = re.compile(r"\bno\b.*\bjob runs it", re.IGNORECASE)  # "no CI job runs it", or a worded "no Windows or macOS job runs it"
# The per-OS output names: one JSON list for the Windows job and one for the macOS job.
OS_KEYS = ("files_windows", "files_macos")
CI_PATH = ".github/workflows/checks.yml"
# The checks.yml the derivation cases commit in place of the real one. Each runner names one test: the Windows job
# test_a, the Linux job test_b, the macOS job test_c. A test named by none of them is in no job.
FIXTURE_CI = """name: fixture checks
on: pull_request
jobs:
  windows:
    runs-on: windows-latest
    steps:
      - run: python3 lint/test_a.py
  linux:
    runs-on: ubuntu-latest
    steps:
      - run: python3 lint/test_b.py
  macos:
    runs-on: macos-latest
    steps:
      - run: python3 lint/test_c.py
"""


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


def skipped_on(stdout, path, key):
    """True when a skip line names `path` and the reason key `key`. A run or touched line never counts as a skip."""
    return any(path in line and key.search(line) and not line.startswith(("run ", "touched "))
               for line in stdout.splitlines())


def ci_for(paths):
    """A checks.yml whose windows-latest job runs each of `paths`, so the derivation selects them on Windows."""
    steps = "".join(f"      - run: python3 {p}\n" for p in paths)
    return "name: fixture checks\non: pull_request\njobs:\n  windows:\n    runs-on: windows-latest\n    steps:\n" + steps


def with_ci(base, paths=None):
    """`base` with a checks.yml in place of the real one. With `paths`, its windows job runs each of them. Without,
    the fixture checks.yml runs test_a (Windows), test_b (Linux) and test_c (macOS)."""
    out = dict(base)
    out[CI_PATH] = ci_for(paths) if paths is not None else FIXTURE_CI
    return out


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

    def json_value(self, text, key):
        """The JSON value one output line holds. A value that does not parse fails the case by name."""
        try:
            return json.loads(text)
        except ValueError:
            self.fail(f"{key}= is not JSON: {text!r}")

    def run_outputs(self, base, change=None, delete=()):
        """Run the selector on a fixture with a readable diff. -> (outputs, stdout). The scope is checked first: exit 0."""
        repo, sha, out = self.fixture(base, change, delete)
        r, outputs = self.select(repo, sha, out)
        self.assertEqual(r.returncode, 0, f"the selector exited {r.returncode} on a readable diff:\n{r.stdout}{r.stderr}")
        return outputs, r.stdout

    def os_lists(self, outputs):
        """-> (sorted files_windows, sorted files_macos). Fails by name when the selector wrote no per-OS list."""
        lists = {}
        for key in OS_KEYS:
            self.assertIn(key, outputs, f"the selector writes no {key}= line, so the per-OS lists are not built: {outputs}")
            lists[key] = sorted(self.json_list(outputs[key], key))
        return lists["files_windows"], lists["files_macos"]

    def per_os(self, base, change=None, delete=()):
        """-> (sorted files_windows, sorted files_macos, stdout) for a fixture with a readable diff."""
        outputs, stdout = self.run_outputs(base, change, delete)
        windows, macos = self.os_lists(outputs)
        return windows, macos, stdout

    def include_entries(self, matrix_text):
        """The matrix's include entries, each as {os, files} with files a sorted list read from its JSON text."""
        matrix = self.json_value(matrix_text, "matrix")
        self.assertIsInstance(matrix, dict, f"matrix= is not a JSON object: {matrix_text!r}")
        include = matrix.get("include")
        self.assertIsInstance(include, list, f"matrix has no include list: {matrix_text!r}")
        entries = []
        for entry in include:
            self.assertIsInstance(entry, dict, f"a matrix entry is not an object: {entry!r}")
            self.assertIsInstance(entry.get("files"), str, f"a matrix entry's files is not JSON text: {entry!r}")
            entries.append({"os": entry.get("os"), "files": sorted(self.json_list(entry["files"], "matrix files"))})
        return sorted(entries, key=lambda e: str(e["os"]))

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
        files, stdout = self.listed(with_ci({path: "old\n"}, [path]), {path: "new\n"})
        self.assertEqual(files, [path], "a touched skill test was not listed")
        self.assertIn(path, stdout, "the log does not name the listed test")

    def test_each_test_file_pattern_is_listed(self):
        paths = ["skills/alpha/tests/a.test.mjs", "skills/alpha/tests/b.test.js", "lint/test_c.py",
                 "lint/test_d.sh", "lint/e.test.sh"]
        files, _ = self.listed(with_ci({p: "old\n" for p in paths}, paths), {p: "new\n" for p in paths})
        self.assertEqual(files, sorted(paths), "a test-file pattern is missing from the list, or a path is listed twice")

    def test_source_with_sibling_test_lists_that_test(self):
        files, _ = self.listed(with_ci({"lint/check_foo.py": "old\n", "lint/test_check_foo.py": "old\n"},
                                       ["lint/test_check_foo.py"]),
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
        # The sibling folder's test is named by a job too, so only the folder rule keeps it out of the list.
        files, _ = self.listed(with_ci({p: "old\n" for p in mine + [helper, other]}, mine + [other]), {helper: "new\n"})
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
        """The real checks.yml runs these two on no Windows job (a Linux job, and the macOS job for one), so they are not
        in files_windows, and the log names each one as skipped on Windows."""
        paths = ["merge/test_install_from_main.sh", "hooks/test_cloud_setup.sh"]
        windows, _, stdout = self.per_os({p: "old\n" for p in paths}, {p: "new\n" for p in paths})
        for path in paths:
            self.assertNotIn(path, windows, f"{path} is in files_windows, though no Windows job runs it")
            self.assertTrue(skipped_on(stdout, path, WINDOWS_KEY), f"the log does not name {path} as skipped on Windows")

    # The derivation cases commit FIXTURE_CI, so the lists follow that checks.yml, not a list in the selector.
    def test_windows_list_follows_checks_yml_not_a_hand_list(self):
        """A test only the Linux job runs is not in files_windows, and the log names it as skipped on Windows."""
        a, b = "lint/test_a.py", "lint/test_b.py"
        windows, _, stdout = self.per_os(with_ci({a: "old\n", b: "old\n"}), {a: "new\n", b: "new\n"})
        self.assertEqual(windows, [a], "files_windows is not the Windows job's tests: a Linux-only test is in it")
        self.assertTrue(skipped_on(stdout, b, WINDOWS_KEY), f"the log does not name {b} as skipped on Windows")

    def test_a_test_no_ci_job_runs_is_left_out_of_both_lists_with_a_reason(self):
        """A test named by no job is in neither list, and the log says no CI job runs it. It is not dropped silently."""
        d = "lint/test_d.py"
        windows, macos, stdout = self.per_os(with_ci({}), {d: "new\n"})
        self.assertEqual(windows, [], "files_windows lists a test no CI job runs")
        self.assertEqual(macos, [], "files_macos lists a test no CI job runs")
        self.assertTrue(skipped_on(stdout, d, NO_JOB_KEY), f"the log does not name {d} with the reason no CI job runs it")

    def test_matrix_has_one_entry_per_os_with_files(self):
        """The matrix is the include entries built from files_windows and files_macos: one per OS with a non-empty list."""
        a, c = "lint/test_a.py", "lint/test_c.py"
        outputs, _ = self.run_outputs(with_ci({a: "old\n", c: "old\n"}), {a: "new\n", c: "new\n"})
        windows, macos = self.os_lists(outputs)
        self.assertEqual(windows, [a], "files_windows names a test no Windows job runs")
        self.assertEqual(macos, [c], "files_macos names a test no macOS job runs")
        self.assertIn("matrix", outputs, f"no matrix= line in GITHUB_OUTPUT: {outputs}")
        built = [{"os": name, "files": listed} for name, listed in (("windows-latest", windows), ("macos-latest", macos)) if listed]
        self.assertEqual(self.include_entries(outputs["matrix"]), sorted(built, key=lambda e: e["os"]),
                         "matrix is not the include entries built from files_windows and files_macos")

    def test_matrix_is_empty_when_nothing_is_selected(self):
        """A touched test no CI job runs selects nothing, so the matrix is {"include": []}."""
        outputs, _ = self.run_outputs(with_ci({}), {"lint/test_d.py": "new\n"})
        self.assertIn("matrix", outputs, f"no matrix= line in GITHUB_OUTPUT: {outputs}")
        self.assertEqual(self.json_value(outputs["matrix"], "matrix"), {"include": []},
                         "a touched test no CI job runs still put an entry in the matrix")

    def test_a_test_only_a_windows_job_runs_is_absent_from_files_macos(self):
        """A test only the Windows job runs is in files_windows, is absent from files_macos, and the log names it as
        skipped on macOS."""
        a = "lint/test_a.py"
        windows, macos, stdout = self.per_os(with_ci({a: "old\n"}), {a: "new\n"})
        self.assertIn(a, windows, "a Windows-only test is not in files_windows")
        self.assertNotIn(a, macos, "a Windows-only test is in files_macos, though no macOS job runs it")
        self.assertTrue(skipped_on(stdout, a, MACOS_KEY), f"the log does not name {a} as skipped on macOS")


if __name__ == "__main__":
    unittest.main()
