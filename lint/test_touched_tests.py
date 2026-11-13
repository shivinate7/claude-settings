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
  matrix         {"include": [{"os", "files": [path]}]}, one entry per OS with files
  commands_windows, commands_macos   {path: cmd} over that OS's files; cmd is the interpreter the run line names

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
from textwrap import dedent

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


def with_checks(base, text):
    """`base` with `text` as the checks.yml the selector reads, in place of the real one."""
    out = dict(base)
    out[CI_PATH] = text
    return out


def with_ci(base, paths=None):
    """`base` with a checks.yml in place of the real one. With `paths`, its windows job runs each of them. Without,
    the fixture checks.yml runs test_a (Windows), test_b (Linux) and test_c (macOS)."""
    return with_checks(base, ci_for(paths) if paths is not None else FIXTURE_CI)


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
        """The matrix's include entries, each as {os, files}. The workflow reads files as text, so files must be a
        string that decodes to a sorted JSON list of path strings. -> the decoded lists."""
        matrix = self.json_value(matrix_text, "matrix")
        self.assertIsInstance(matrix, dict, f"matrix= is not a JSON object: {matrix_text!r}")
        include = matrix.get("include")
        self.assertIsInstance(include, list, f"matrix has no include list: {matrix_text!r}")
        entries = []
        for entry in include:
            self.assertIsInstance(entry, dict, f"a matrix entry is not an object: {entry!r}")
            files = entry.get("files")
            self.assertIsInstance(files, str, f"a matrix entry's files is not text, as the workflow reads it: {entry!r}")
            decoded = self.json_value(files, "matrix files")
            self.assertIsInstance(decoded, list, f"a matrix entry's files does not decode to a JSON list: {entry!r}")
            for item in decoded:
                self.assertIsInstance(item, str, f"a matrix file is not a path string: {item!r}")
            self.assertEqual(decoded, sorted(decoded), f"a matrix entry's files is not sorted: {entry!r}")
            entries.append({"os": entry.get("os"), "files": decoded})
        return sorted(entries, key=lambda e: str(e["os"]))

    def commands_of(self, outputs, key):
        """The per-OS output `key` (commands_windows or commands_macos): a JSON object {path: cmd} over that OS's files."""
        self.assertIn(key, outputs, f"no {key}= line in GITHUB_OUTPUT: {outputs}")
        commands = self.json_value(outputs[key], key)
        self.assertIsInstance(commands, dict, f"{key}= is not a JSON object: {outputs[key]!r}")
        return commands

    def exits_1(self, base, change=None, delete=()):
        """Run the selector on a checks.yml it cannot read. -> its stderr. The run exits 1 and writes no output."""
        repo, sha, out = self.fixture(base, change, delete)
        r, outputs = self.select(repo, sha, out)
        self.assertEqual(r.returncode, 1, f"the selector exited {r.returncode}, not 1, on a checks.yml it cannot read:\n{r.stderr}")
        self.assertEqual(outputs, {}, f"the selector wrote output on its exit 1: {outputs}")
        return r.stderr

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
        test = "lint/tests/foo.test.mjs"
        files, _ = self.listed(with_ci({test: "old\n", "lint/foo.mjs": "old\n"}, [test]), {"lint/foo.mjs": "new\n"})
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

    def test_guard_section_file_touched_names_the_heavy_guard_suite(self):
        # A section file is a part of hooks/test_guard.py. Its change runs in that suite's shard jobs, so the
        # selector lists no file of the section folder and names hooks/test_guard.py with its HEAVY reason.
        section = "tests/guard/s00442-misc.py"
        files, stdout = self.listed({section: "old\n"}, {section: "new\n"})
        self.assertNotIn(section, files, "a section file was listed for a lane push")
        self.assertTrue(named(stdout, "hooks/test_guard.py", HEAVY_KEY),
                        "the log does not name hooks/test_guard.py with its HEAVY reason for a section file change")

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
        # The fixture's run lines name python3 for each file: a on Windows, c on macOS.
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "python3"},
                         "commands_windows does not name the Windows file's command from its run line")
        self.assertEqual(self.commands_of(outputs, "commands_macos"), {c: "python3"},
                         "commands_macos does not name the macOS file's command from its run line")

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

    # Row 2: a .ps1 source maps to its own .test.ps1 and install-*.test.ps1 beside it.
    def test_a_ps1_source_lists_its_test_and_its_dash_tests(self):
        base = {"install.ps1": "old\n", "install.test.ps1": "old\n", "install-no-gap.test.ps1": "old\n"}
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - shell: powershell
                    run: powershell -NoProfile -File install.test.ps1
                  - shell: powershell
                    run: powershell -NoProfile -File install-no-gap.test.ps1
            """)
        windows, _, _ = self.per_os(with_checks(base, text), {"install.ps1": "new\n"})
        self.assertEqual(windows, ["install-no-gap.test.ps1", "install.test.ps1"],
                         "install.ps1 does not list its install.test.ps1 and install-*.test.ps1")

    # Row 2: a .sh source maps to its .test.sh beside it, as well as test_<stem>.sh.
    def test_a_sh_source_also_lists_its_dot_test_sh(self):
        base = {"merge/install_from_main.sh": "old\n", "merge/install_from_main.test.sh": "old\n",
                "merge/test_install_from_main.sh": "old\n"}
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: sh merge/install_from_main.test.sh
                  - run: sh merge/test_install_from_main.sh
            """)
        windows, _, _ = self.per_os(with_checks(base, text), {"merge/install_from_main.sh": "new\n"})
        self.assertEqual(windows, ["merge/install_from_main.test.sh", "merge/test_install_from_main.sh"],
                         "install_from_main.sh does not list its install_from_main.test.sh")

    # Row 2 control: a tools/*.ps1 with no test beside it stays unmapped, and the log says so. This passes before the fix.
    def test_a_ps1_tool_with_no_test_beside_it_maps_to_nothing(self):
        windows, macos, stdout = self.per_os(with_ci({"tools/fmt.ps1": "old\n"}), {"tools/fmt.ps1": "new\n"})
        self.assertEqual(windows + macos, [], "a tools/*.ps1 with no test beside it listed a test")
        self.assertIn("no test file maps to it", stdout, "the log does not say the tools/*.ps1 maps to no test")

    # Row 3: a touched mods/<mod>/ source maps to every mods/<mod>/**/*.test.mjs, not node_modules.
    def test_a_mods_source_lists_every_mod_test_but_not_node_modules(self):
        base = {"mods/plain-diff/check.mjs": "old\n", "mods/plain-diff/tests/a.test.mjs": "old\n",
                "mods/plain-diff/sub/b.test.mjs": "old\n", "mods/plain-diff/node_modules/pkg/c.test.mjs": "old\n"}
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: node mods/plain-diff/tests/a.test.mjs
                  - run: node mods/plain-diff/sub/b.test.mjs
                  - run: node mods/plain-diff/node_modules/pkg/c.test.mjs
            """)
        windows, _, _ = self.per_os(with_checks(base, text), {"mods/plain-diff/check.mjs": "new\n"})
        self.assertEqual(windows, ["mods/plain-diff/sub/b.test.mjs", "mods/plain-diff/tests/a.test.mjs"],
                         "a touched mods/<mod>/ source does not list every test under it, or lists one under node_modules")

    # Row 4: a trailing comment on runs-on does not hide the runner. The unquoted form passes before the fix.
    def test_a_runner_with_a_trailing_comment_is_read(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest  # the Windows runner
                steps:
                  - run: python3 lint/test_a.py
            """)
        windows, _, _ = self.per_os(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertEqual(windows, [a], "a trailing comment on an unquoted runs-on hid the runner")

    # Row 4: a comment after a quoted runner is cut outside the quotes, so the runner is read.
    def test_a_quoted_runner_with_a_trailing_comment_is_read(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: "windows-latest"  # the Windows runner
                steps:
                  - run: python3 lint/test_a.py
            """)
        windows, _, _ = self.per_os(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertEqual(windows, [a], "a comment after a quoted runs-on was not cut, so the runner was not read")

    # Row 5: a flow-style step in a job the selector reads exits 1, naming its line. It is never misread in silence.
    def test_a_flow_style_step_exits_1_naming_its_line(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - { run: python3 lint/test_a.py }
            """)
        n = next(i for i, line in enumerate(text.splitlines(), 1) if line.lstrip().startswith("- {"))
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {n}", stderr, f"the exit does not name the flow step's line {n}: {stderr}")

    # Row 5: a powershell step names lint\test_x.py. The backslash reads as a slash there, so the test runs on Windows.
    def test_a_powershell_step_naming_a_backslash_path_is_eligible_on_windows(self):
        a = "lint/test_x.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - shell: powershell
                    run: python lint\\test_x.py
            """)
        windows, _, _ = self.per_os(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertEqual(windows, [a], "a powershell step's backslash path was not read as lint/test_x.py")

    # Row 6: each exit-1 branch exits 1 with no output, and names what it could not read.
    def test_exit_1_when_runs_on_is_a_matrix_expression(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              matrix-os:
                runs-on: ${{ matrix.os }}
                steps:
                  - run: python3 lint/test_a.py
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn("matrix-os", stderr, f"the exit does not name the job with the matrix runs-on: {stderr}")

    def test_exit_1_when_runs_on_is_a_list(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              list-os:
                runs-on: [self-hosted, windows]
                steps:
                  - run: python3 lint/test_a.py
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn("list-os", stderr, f"the exit does not name the job with the list runs-on: {stderr}")

    def test_exit_1_when_a_job_has_no_runs_on(self):
        """A reusable job (`uses:`) has no runs-on this can read."""
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              reusable:
                uses: ./.github/workflows/reusable.yml
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn("reusable", stderr, f"the exit does not name the job with no runs-on: {stderr}")

    def test_exit_1_when_checks_yml_has_no_jobs(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn("checks.yml", stderr, f"the exit does not name the checks.yml with no jobs: {stderr}")

    def test_exit_1_when_checks_yml_is_indented_with_a_tab(self):
        a = "lint/test_a.py"
        text = ("name: fixture checks\non: pull_request\njobs:\n  windows:\n\truns-on: windows-latest\n"
                "    steps:\n      - run: python3 lint/test_a.py\n")
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn("checks.yml", stderr, f"the exit does not name the checks.yml indented with a tab: {stderr}")

    def test_exit_1_when_checks_yml_is_missing_at_head(self):
        a = "lint/test_a.py"
        stderr = self.exits_1({a: "old\n"}, {a: "new\n"}, delete=[CI_PATH])
        self.assertIn("checks.yml", stderr, f"the exit does not name a checks.yml missing at HEAD: {stderr}")

    # Row 7: each file's cmd is the command its run line names before the path.
    def test_commands_name_each_files_command_from_its_run_line(self):
        files = ["merge/test_y.sh", "lint/z.test.mjs", "skills/alpha/tests/a.test.mjs"]
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: sh merge/test_y.sh
                  - run: node lint/z.test.mjs
                  - run: node --test skills/alpha/tests/a.test.mjs
            """)
        outputs, _ = self.run_outputs(with_checks({p: "old\n" for p in files}, text), {p: "new\n" for p in files})
        self.assertIn("matrix", outputs, f"no matrix= line in GITHUB_OUTPUT: {outputs}")
        self.assertEqual(self.include_entries(outputs["matrix"]), [{"os": "windows-latest", "files": [
            "lint/z.test.mjs", "merge/test_y.sh", "skills/alpha/tests/a.test.mjs",
        ]}], "the windows matrix entry is not the windows job's paths")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {
            "lint/z.test.mjs": "node",
            "merge/test_y.sh": "sh",
            "skills/alpha/tests/a.test.mjs": "node --test",
        }, "commands_windows does not name each file's command from its run line")

    # Row 7: a file mod-tests.sh runs keeps that script's form: node for a mods test, node --test for a map skill test.
    def test_a_runner_script_file_keeps_the_script_form(self):
        mods, skill = "mods/plain-diff/tests/a.test.mjs", "skills/plain-english-map/tests/b.test.mjs"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: bash .github/scripts/mod-tests.sh
            """)
        outputs, _ = self.run_outputs(with_checks({mods: "old\n", skill: "old\n"}, text), {mods: "new\n", skill: "new\n"})
        self.assertIn("matrix", outputs, f"no matrix= line in GITHUB_OUTPUT: {outputs}")
        self.assertEqual(self.include_entries(outputs["matrix"]), [{"os": "windows-latest", "files": [mods, skill]}],
                         "the windows matrix entry is not the runner script's paths")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {mods: "node", skill: "node --test"},
                         "a runner-script file did not keep the script's own command form")

    def line_of(self, text, needle):
        """The 1-based number of the first line of `text` that holds `needle`."""
        return next(i for i, line in enumerate(text.splitlines(), 1) if needle in line)

    # F2: the command is the interpreter alone. An env prefix or a word before the interpreter cannot be read: exit 1.
    def test_an_env_prefix_before_node_exits_1_naming_its_line(self):
        a = "lint/test_x.mjs"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: FOO=x node lint/test_x.mjs
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, 'FOO=x')}", stderr, f"the exit does not name the env-prefixed run line: {stderr}")

    def test_an_env_prefix_before_python3_exits_1_naming_its_line(self):
        a = "lint/test_y.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: PYTHONPATH=. python3 lint/test_y.py
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, 'PYTHONPATH')}", stderr,
                      f"the exit does not name the env-prefixed python3 run line: {stderr}")

    def test_a_cd_prefix_before_node_exits_1_naming_its_line(self):
        a = "lint/test_z.mjs"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: cd a && node lint/test_z.mjs
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, 'cd a')}", stderr, f"the exit does not name the cd-prefixed run line: {stderr}")

    # F1: a one-line flow sequence of steps is not read: exit 1, naming the steps line.
    def test_a_one_line_flow_steps_list_exits_1_naming_its_line(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps: [{run: python3 lint/test_a.py}]
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, 'steps:')}", stderr,
                      f"the exit does not name the one-line flow steps: {stderr}")

    # F3: one test run under two interpreters. Each OS's commands output names its own interpreter.
    def test_each_os_names_its_own_command_for_a_test_both_run(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: python lint/test_a.py
              macos:
                runs-on: macos-latest
                steps:
                  - run: python3 lint/test_a.py
            """)
        outputs, _ = self.run_outputs(with_checks({a: "old\n"}, text), {a: "new\n"})
        windows, macos = self.os_lists(outputs)
        self.assertEqual(windows, [a], "files_windows does not list the test the Windows job runs")
        self.assertEqual(macos, [a], "files_macos does not list the test the macOS job runs")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "python"},
                         "commands_windows does not name the Windows job's interpreter")
        self.assertEqual(self.commands_of(outputs, "commands_macos"), {a: "python3"},
                         "commands_macos does not name the macOS job's interpreter")

    # F4: a mod source with no sibling test lists the mod's tests by the lint form, mods/<mod>/**/*.test.mjs.
    def test_a_mod_source_with_no_sibling_test_lists_the_mods_tests(self):
        base = {"mods/m/check.mjs": "old\n", "mods/m/tests/a.test.mjs": "old\n",
                "mods/m/sub/deep/b.test.mjs": "old\n", "mods/other/c.test.mjs": "old\n"}
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: node mods/m/tests/a.test.mjs
                  - run: node mods/m/sub/deep/b.test.mjs
                  - run: node mods/other/c.test.mjs
            """)
        windows, _, _ = self.per_os(with_checks(base, text), {"mods/m/check.mjs": "new\n"})
        self.assertEqual(windows, ["mods/m/sub/deep/b.test.mjs", "mods/m/tests/a.test.mjs"],
                         "a touched mods/m/ source does not list every test under mods/m/, or lists another mod's test")

    # Item 1: a touched mods/<mod>/ source selects that mod's check.mjs, which mod-tests.sh runs with node. The negatives
    # are a check.mjs in another mod, one under node_modules, and a file named precheck.mjs.
    def test_a_touched_mod_source_selects_its_check_mjs(self):
        base = {"mods/m/check.mjs": "old\n", "mods/m/lib.mjs": "old\n", "mods/m/tests/a.test.mjs": "old\n",
                "mods/other/check.mjs": "old\n", "mods/m/node_modules/x/check.mjs": "old\n", "mods/m/precheck.mjs": "old\n"}
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: bash .github/scripts/mod-tests.sh
            """)
        outputs, _ = self.run_outputs(with_checks(base, text), {"mods/m/lib.mjs": "new\n"})
        windows, _ = self.os_lists(outputs)
        self.assertIn("mods/m/check.mjs", windows, "a touched mods/m/ source does not select mods/m/check.mjs")
        self.assertEqual(self.commands_of(outputs, "commands_windows").get("mods/m/check.mjs"), "node",
                         "mods/m/check.mjs is not given the command node")
        self.assertNotIn("mods/other/check.mjs", windows, "a touched mods/m/ source selected another mod's check.mjs")
        self.assertNotIn("mods/m/node_modules/x/check.mjs", windows,
                         "a touched mods/m/ source selected a check.mjs under node_modules")
        self.assertNotIn("mods/m/precheck.mjs", windows, "a file named precheck.mjs was selected as a check.mjs")

    # Item 2: a job-level defaults block exits 1, naming its line, with no output: a default shell changes how a step reads.
    def test_a_job_level_defaults_exits_1_naming_its_line(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                defaults:
                  run:
                    shell: bash
                steps:
                  - run: python3 lint/test_a.py
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, 'defaults:')}", stderr,
                      f"the exit does not name the job-level defaults line: {stderr}")

    # Item 2: a workflow-level defaults block exits 1, naming its line, with no output.
    def test_a_workflow_level_defaults_exits_1_naming_its_line(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            defaults:
              run:
                shell: bash
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: python3 lint/test_a.py
            """)
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, 'defaults:')}", stderr,
                      f"the exit does not name the workflow-level defaults line: {stderr}")

    # Item 3: a backslash at a line's end joins that line to the next, so the command is the joined line's first word.
    def test_a_line_join_with_a_backslash_resolves_the_command(self):
        a = "lint/test_a.mjs"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: |
                      node --test \\
                        lint/test_a.mjs
            """)
        outputs, _ = self.run_outputs(with_checks({a: "old\n"}, text), {a: "new\n"})
        windows, _ = self.os_lists(outputs)
        self.assertEqual(windows, [a], "a backslash-joined run line did not list its test on Windows")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "node --test"},
                         "a backslash-joined run line did not resolve its command to node --test")

    # Item 4: a chain before the test path is not a command word. The run line exits 1, naming its line.
    def run_line_exits_1(self, run, a="lint/test_a.py"):
        """A checks.yml whose one windows run line is `run`, with test `a` changed. Exit 1, no output, the line named."""
        text = ("name: fixture checks\non: pull_request\njobs:\n  windows:\n    runs-on: windows-latest\n"
                f"    steps:\n      - run: {run}\n")
        stderr = self.exits_1(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertIn(f"line {self.line_of(text, run)}", stderr, f"the exit does not name the run line: {stderr}")

    def test_a_chain_and_before_the_test_path_exits_1_naming_its_line(self):
        self.run_line_exits_1("python3 lint/gen.py && python3 lint/test_a.py")

    def test_a_chain_semicolon_before_the_test_path_exits_1_naming_its_line(self):
        self.run_line_exits_1("python3 lint/gen.py; python3 lint/test_a.py")

    def test_a_chain_pipe_before_the_test_path_exits_1_naming_its_line(self):
        self.run_line_exits_1("python3 lint/gen.py | python3 lint/test_a.py")

    # Item 4 control: a chain after the test path leaves the command word as the path's own command.
    def test_a_chain_after_the_test_path_still_resolves_the_command(self):
        a = "lint/test_a.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: python3 lint/test_a.py && echo ok
            """)
        outputs, _ = self.run_outputs(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "python3"},
                         "a chain after the test path changed its command")

    # Item 4 control: a pipe inside quotes is part of an argument, not a chain. A naive split on | would break it.
    def test_a_quoted_pipe_before_the_test_path_is_not_a_chain(self):
        a = "lint/test_a.mjs"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - run: node --test --test-name-pattern="a|b" lint/test_a.mjs
            """)
        outputs, _ = self.run_outputs(with_checks({a: "old\n"}, text), {a: "new\n"})
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "node --test"},
                         "a pipe inside quotes was read as a chain, which changed the command")

    # Item 5: a powershell step's backtick at a line's end continues the line, as a backslash does in bash.
    def test_a_powershell_backtick_continuation_resolves_the_command(self):
        a = "lint/test_x.py"
        text = dedent("""\
            name: fixture checks
            on: pull_request
            jobs:
              windows:
                runs-on: windows-latest
                steps:
                  - shell: powershell
                    run: |
                      python `
                        lint\\test_x.py
            """)
        repo, sha, out = self.fixture(with_checks({a: "old\n"}, text), {a: "new\n"})
        r, outputs = self.select(repo, sha, out)
        self.assertEqual(r.returncode, 0,
                         f"a powershell backtick at a line's end was not joined to the next line: {r.stderr}")
        windows, _ = self.os_lists(outputs)
        self.assertEqual(windows, [a], "a backtick-continued powershell run line did not list its test on Windows")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "python"},
                         "a backtick-continued powershell run line did not resolve its command to python")

    # An interpreter named by its absolute path reads as that interpreter: the basename is the command word.
    def run_line_in_both_jobs(self, a, run):
        """A checks.yml whose windows and macos jobs each run `run`, with test `a` changed. -> outputs, exit 0 checked."""
        text = ("name: fixture checks\non: pull_request\njobs:\n"
                "  windows:\n    runs-on: windows-latest\n    steps:\n"
                f"      - run: {run}\n"
                "  macos:\n    runs-on: macos-latest\n    steps:\n"
                f"      - run: {run}\n")
        outputs, _ = self.run_outputs(with_checks({a: "old\n"}, text), {a: "new\n"})
        return outputs

    def test_a_bin_bash_run_line_reads_as_bash_on_the_windows_and_macos_jobs(self):
        a = "lint/test_x.sh"
        outputs = self.run_line_in_both_jobs(a, "/bin/bash lint/test_x.sh")
        windows, macos = self.os_lists(outputs)
        self.assertEqual(windows, [a], "files_windows does not list the test the Windows job runs by /bin/bash")
        self.assertEqual(macos, [a], "files_macos does not list the test the macOS job runs by /bin/bash")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "bash"},
                         "commands_windows does not read /bin/bash as bash")
        self.assertEqual(self.commands_of(outputs, "commands_macos"), {a: "bash"},
                         "commands_macos does not read /bin/bash as bash")

    def test_a_usr_bin_python3_run_line_reads_as_python3_on_the_windows_and_macos_jobs(self):
        a = "lint/test_x.py"
        outputs = self.run_line_in_both_jobs(a, "/usr/bin/python3 lint/test_x.py")
        windows, macos = self.os_lists(outputs)
        self.assertEqual(windows, [a], "files_windows does not list the test the Windows job runs by /usr/bin/python3")
        self.assertEqual(macos, [a], "files_macos does not list the test the macOS job runs by /usr/bin/python3")
        self.assertEqual(self.commands_of(outputs, "commands_windows"), {a: "python3"},
                         "commands_windows does not read /usr/bin/python3 as python3")
        self.assertEqual(self.commands_of(outputs, "commands_macos"), {a: "python3"},
                         "commands_macos does not read /usr/bin/python3 as python3")

    # Controls: a path that names no interpreter, or a basename that only starts with one, still exits 1 naming its line.
    def test_an_absolute_path_that_is_not_an_interpreter_exits_1_naming_its_line(self):
        self.run_line_exits_1("/tmp/evil lint/test_x.sh", a="lint/test_x.sh")

    def test_an_absolute_bashx_basename_exits_1_naming_its_line(self):
        self.run_line_exits_1("/bin/bashx lint/test_x.sh", a="lint/test_x.sh")

    # The real checks.yml at HEAD, the full-size state. Its shell-macos job runs the duo-fold harness by /bin/bash, so
    # touching that test must read the line, not fail on it.
    def test_the_real_checks_yml_at_head_reads_the_shell_macos_bin_bash_line(self):
        a = "lint/test_duo_fold.sh"
        with open(os.path.join(HERE, "..", ".github", "workflows", "checks.yml"), encoding="utf-8") as f:
            real_lines = [line.strip() for line in f.read().splitlines()]
        self.assertIn("run: /bin/bash lint/test_duo_fold.sh", real_lines,
                      "the real checks.yml runs no test by /bin/bash, so this case probes nothing")
        outputs, _ = self.run_outputs({a: "old\n"}, {a: "new\n"})
        windows, macos = self.os_lists(outputs)
        self.assertEqual(windows, [], "files_windows lists the duo-fold test, which no Windows job runs")
        self.assertEqual(macos, [a], "files_macos does not list the duo-fold test the shell-macos job runs")
        self.assertEqual(self.commands_of(outputs, "commands_macos"), {a: "bash"},
                         "commands_macos does not read the shell-macos job's /bin/bash line as bash")


if __name__ == "__main__":
    unittest.main()
