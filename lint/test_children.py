#!/usr/bin/env python3
"""Cases for lint/children.py, the one reader of the child list. Standard library only.

    python3 lint/test_children.py

The list is one file, docs/children.txt. Each line reads `owner/name <GitHub repo id> <since YYYY-MM-DD>`,
sorted by name; `#` comment lines and blank lines are allowed. The reader's entry is main(argv, fetch=None),
which returns the exit code. `--file PATH` reads a fixture instead of the real list. fetch(path) returns the
parsed GitHub JSON for a REST path and raises for a path it cannot read. No case reaches the network or
starts a process: run_reader refuses both and fails the case if the reader tries.
"""
import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the temp-file standard for lint/ suites (decision test-temp-standard)

CHILDREN = os.path.join(HERE, "children.py")
ROSTER = os.path.join(os.path.dirname(HERE), "docs", "children.txt")
RUN = []  # this run's folder, made once in setUpModule and removed in tearDownModule

# The eight children in file order. sillage's GitHub name is frag-head-beta: the file keeps sillage, and the
# reader resolves the name by id.
EIGHT = [
    ("shivinate7/banchi", "1350816723"),
    ("shivinate7/degen", "1413478819"),
    ("shivinate7/home", "1413914462"),
    ("shivinate7/ios-adblock", "1413478645"),
    ("shivinate7/joyous", "1413623012"),
    ("shivinate7/mailaudit", "1313026125"),
    ("shivinate7/q_max", "1337628957"),
    ("shivinate7/sillage", "1333311712"),
]
ORDERED = "shivinate7/banchi 1350816723 2026-01-05\nshivinate7/sillage 1333311712 2026-02-01\n"
COMMENTED = ("# child repos\n\nshivinate7/banchi 1350816723 2026-01-05\n\n# later\n"
             "shivinate7/sillage 1333311712 2026-02-01\n")
ACTIVE = ("shivinate7/banchi 1350816723 2026-01-05\nshivinate7/degen 1413478819 2026-01-06\n"
          "shivinate7/sillage 1333311712 2026-02-01\n")
BANCHI_ONLY = "shivinate7/banchi 1350816723 2026-01-05\n"
MALFORMED = {  # each goes on line 3 of the file below
    "id is not digits": "shivinate7/degen 14134x8819 2026-01-06",
    "date is not YYYY-MM-DD": "shivinate7/degen 1413478819 26-1-6",
    "name has no owner": "degen 1413478819 2026-01-06",
    "a field is missing": "shivinate7/degen 1413478819",
}
LINE = re.compile(r"\S+/\S+ \d+ \d{4}-\d{2}-\d{2}")
SCAN_REPOS = [
    {"id": 1350816723, "full_name": "shivinate7/banchi"},
    {"id": 1413478819, "full_name": "shivinate7/degen"},
    {"id": 555001, "full_name": "shivinate7/newrepo"},
    {"id": 555002, "full_name": "shivinate7/plain"},
    {"id": 555003, "full_name": "shivinate7/claude-settings"},
]
SCAN_MARKED = ["shivinate7/banchi", "shivinate7/degen", "shivinate7/newrepo", "shivinate7/claude-settings"]


def setUpModule():
    RUN.append(_test_temp.run_folder())


def tearDownModule():
    shutil.rmtree(RUN[0], ignore_errors=True)


def fixture(text):
    """A list file holding `text`, in a fresh folder under this run's folder. Returns its path."""
    folder = tempfile.mkdtemp(dir=RUN[0])
    path = os.path.join(folder, "children.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def repo(ident, full_name, archived=False):
    return {"id": ident, "full_name": full_name, "archived": archived}


class NoFetch:
    """Records each call and raises. A subcommand that never reads GitHub leaves `calls` empty."""

    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        raise RuntimeError("no GitHub read expected: %s" % path)


class ById:
    """Answers each repo id with a dict. An id that is not in `answers`, or maps to an exception, raises."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        ident = int(re.findall(r"\d+", path)[-1])
        found = self.answers.get(ident, RuntimeError("404 Not Found: %s" % path))
        if isinstance(found, Exception):
            raise found
        return found


class ScanFetch:
    """Answers the owner's repo listing with `repos`. A stamp read answers only for a repo in `marked`, by its
    full name or its id; any other read raises."""

    def __init__(self, repos, marked):
        self.repos = repos
        self.marked = set(marked)
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if "stamp.json" not in path:
            return self.repos
        for item in self.repos:
            if item["full_name"] in self.marked and (item["full_name"] in path or str(item["id"]) in path):
                return {"name": "stamp.json"}
        raise RuntimeError("404 Not Found: %s" % path)


def run_reader(case, argv, fetch):
    """(exit code, stdout, stderr) of the reader's main(argv, fetch=fetch). The reader may not start a process
    or open a socket: each try is recorded and fails the case."""
    case.assertTrue(os.path.isfile(CHILDREN), "lint/children.py is missing: there is no reader to run")
    spec = importlib.util.spec_from_file_location("children", CHILDREN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tries = []

    def refuse(what):
        def attempt(*args, **kwargs):
            tries.append(what)
            raise AssertionError("the reader tried to %s" % what)
        return attempt

    out, err = io.StringIO(), io.StringIO()
    with mock.patch("subprocess.Popen", side_effect=refuse("start a process")), \
            mock.patch("os.system", side_effect=refuse("start a process")), \
            mock.patch("socket.socket", side_effect=refuse("open a socket")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(argv, fetch=fetch)
    case.assertEqual(tries, [], "the reader started a process or opened a socket")
    return code, out.getvalue(), err.getvalue()


class RealRoster(unittest.TestCase):
    """docs/children.txt, the list the reader reads when no --file is given."""

    def test_list_prints_the_eight_children_in_order(self):
        self.assertTrue(os.path.isfile(CHILDREN), "lint/children.py is missing: there is no reader to run")
        out = subprocess.run([sys.executable, CHILDREN, "list"], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout), (0, "".join(name + "\n" for name, _ in EIGHT)), out.stderr)

    def test_names_and_ids_are_the_eight_in_sorted_order(self):
        self.assertTrue(os.path.isfile(ROSTER), "docs/children.txt is missing: the list has no file")
        rows = [tuple(line.split()[:2]) for line in read(ROSTER).splitlines()
                if line.strip() and not line.startswith("#")]
        self.assertEqual(rows, EIGHT, "the list does not hold exactly the eight children, sorted")

    def test_each_line_has_a_since_date(self):
        self.assertTrue(os.path.isfile(ROSTER), "docs/children.txt is missing: the list has no file")
        bad = [line for line in read(ROSTER).splitlines()
               if line.strip() and not line.startswith("#") and not LINE.fullmatch(line)]
        self.assertEqual(bad, [], "lines that are not owner/name, id and YYYY-MM-DD")


class ListCommand(unittest.TestCase):
    def test_prints_each_name_in_file_order(self):
        code, out, err = run_reader(self, ["--file", fixture(ORDERED), "list"], NoFetch())
        self.assertEqual((code, out), (0, "shivinate7/banchi\nshivinate7/sillage\n"), err)

    def test_skips_comment_and_blank_lines(self):
        code, out, err = run_reader(self, ["--file", fixture(COMMENTED), "list"], NoFetch())
        self.assertEqual((code, out), (0, "shivinate7/banchi\nshivinate7/sillage\n"), err)

    def test_empty_file_lists_nothing(self):
        code, out, err = run_reader(self, ["--file", fixture("# no children yet\n\n"), "list"], NoFetch())
        self.assertEqual((code, out), (0, ""), err)

    def test_makes_no_github_read(self):
        fake = NoFetch()
        run_reader(self, ["--file", fixture(ORDERED), "list"], fake)
        self.assertEqual(fake.calls, [], "list read GitHub")

    def test_malformed_line_is_refused_with_its_number(self):
        for why, bad in MALFORMED.items():
            with self.subTest(why=why):
                text = "# child repos\nshivinate7/banchi 1350816723 2026-01-05\n" + bad + "\n"
                code, out, err = run_reader(self, ["--file", fixture(text), "list"], NoFetch())
                self.assertEqual((code, out), (2, ""), err)
                self.assertRegex(err, r"\bline 3\b", "the refusal does not name line 3")


class EverySubcommand(unittest.TestCase):
    def test_malformed_line_is_refused_by_list_active_scan_and_add(self):
        text = "shivinate7/banchi 1350816723 2026-01-05\nshivinate7/degen 14134x8819 2026-01-06\n"
        cases = {
            "list --active": (["list", "--active"], ById({})),
            "scan": (["scan"], ScanFetch([], [])),
            "add": (["add", "shivinate7/home", "1413914462", "2026-01-07"], ById({})),
        }
        for why, (tail, fake) in cases.items():
            with self.subTest(why=why):
                path = fixture(text)
                code, out, err = run_reader(self, ["--file", path, *tail], fake)
                self.assertEqual((code, out), (2, ""), err)
                self.assertRegex(err, r"\bline 2\b", "the refusal does not name line 2")
                self.assertEqual(read(path), text, "a refused subcommand changed the list")


class ListActive(unittest.TestCase):
    def test_drops_an_archived_child(self):
        fake = ById({1350816723: repo(1350816723, "shivinate7/banchi"),
                     1413478819: repo(1413478819, "shivinate7/degen", archived=True),
                     1333311712: repo(1333311712, "shivinate7/sillage")})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, "shivinate7/banchi\nshivinate7/sillage\n"), err)

    def test_prints_the_current_name_of_a_renamed_child(self):
        fake = ById({1350816723: repo(1350816723, "shivinate7/banchi"),
                     1413478819: repo(1413478819, "shivinate7/degen"),
                     1333311712: repo(1333311712, "shivinate7/frag-head-beta")})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, "shivinate7/banchi\nshivinate7/degen\nshivinate7/frag-head-beta\n"), err)

    def test_unreadable_child_is_unknown_on_stderr_and_exits_3(self):
        fake = ById({1350816723: repo(1350816723, "shivinate7/banchi"),
                     1333311712: repo(1333311712, "shivinate7/sillage")})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(out, "shivinate7/banchi\nshivinate7/sillage\n", "the readable children were not all listed")
        unknown = [line for line in err.splitlines() if line.startswith("unknown: shivinate7/degen")]
        self.assertEqual(len(unknown), 1, "no 'unknown: shivinate7/degen' line on stderr: %r" % err)
        self.assertEqual(code, 3)

    def test_asks_github_by_repo_id_and_never_by_name(self):
        fake = ById({1350816723: repo(1350816723, "shivinate7/banchi"),
                     1413478819: repo(1413478819, "shivinate7/degen"),
                     1333311712: repo(1333311712, "shivinate7/sillage")})
        run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        for ident in ("1350816723", "1413478819", "1333311712"):
            self.assertTrue(any(ident in call for call in fake.calls), "no read by id %s: %r" % (ident, fake.calls))
        for name in ("shivinate7/banchi", "shivinate7/degen", "shivinate7/sillage"):
            self.assertFalse(any(name in call for call in fake.calls), "a read by name %s: %r" % (name, fake.calls))


class AddCommand(unittest.TestCase):
    def test_keeps_the_file_sorted(self):
        path = fixture(ORDERED)
        code, out, err = run_reader(self, ["--file", path, "add", "shivinate7/degen", "1413478819", "2026-01-06"],
                                    ById({1413478819: repo(1413478819, "shivinate7/degen")}))
        self.assertEqual(code, 0, err)
        self.assertEqual(read(path).splitlines(), [
            "shivinate7/banchi 1350816723 2026-01-05",
            "shivinate7/degen 1413478819 2026-01-06",
            "shivinate7/sillage 1333311712 2026-02-01",
        ])

    def test_refuses_a_duplicate_id_under_a_new_name(self):
        path = fixture(ORDERED)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "add", "shivinate7/banchi-two", "1350816723", "2026-02-01"],
                                    ById({1350816723: repo(1350816723, "shivinate7/banchi")}))
        self.assertEqual(code, 2, err)
        self.assertEqual(len(err.strip().splitlines()), 1, "the refusal is not one line: %r" % err)
        self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_a_malformed_argument(self):
        tails = {
            "no since": ["shivinate7/degen", "1413478819"],
            "id is not digits": ["shivinate7/degen", "14x", "2026-01-06"],
            "name has no owner": ["degen", "1413478819", "2026-01-06"],
            "since is not a date": ["shivinate7/degen", "1413478819", "26-1-6"],
        }
        for why, tail in tails.items():
            with self.subTest(why=why):
                path = fixture(ORDERED)
                before = read(path)
                code, out, err = run_reader(self, ["--file", path, "add", *tail], ById({}))
                self.assertEqual(code, 2, err)
                self.assertEqual(len(err.strip().splitlines()), 1, "the refusal is not one line: %r" % err)
                self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_claude_settings_as_a_line(self):
        path = fixture(ORDERED)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "add", "shivinate7/claude-settings", "555003", "2026-01-07"],
                                    ById({555003: repo(555003, "shivinate7/claude-settings")}))
        self.assertEqual(code, 2, err)
        self.assertEqual(read(path), before, "claude-settings was written as a child")


class ScanCommand(unittest.TestCase):
    def test_lists_marked_children_not_in_the_file(self):
        fake = ScanFetch(SCAN_REPOS, SCAN_MARKED)
        code, out, err = run_reader(self, ["--file", fixture(BANCHI_ONLY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(out.splitlines()), ["shivinate7/degen", "shivinate7/newrepo"], out)

    def test_never_lists_claude_settings(self):
        fake = ScanFetch([{"id": 555003, "full_name": "shivinate7/claude-settings"}], ["shivinate7/claude-settings"])
        code, out, err = run_reader(self, ["--file", fixture(BANCHI_ONLY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, ""), err)

    def test_matches_a_renamed_child_by_its_id(self):
        fake = ScanFetch([{"id": 1333311712, "full_name": "shivinate7/frag-head-beta"}],
                         ["shivinate7/frag-head-beta"])
        code, out, err = run_reader(self, ["--file", fixture("shivinate7/sillage 1333311712 2026-02-01\n"), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, ""), err)

    def test_writes_nothing(self):
        path = fixture(BANCHI_ONLY)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "scan"], ScanFetch(SCAN_REPOS, SCAN_MARKED))
        self.assertEqual(read(path), before, "scan changed the list")


class Control(unittest.TestCase):
    """Green on the old tree: the harness and the fixtures are sound without the reader."""

    def test_fixture_round_trips_through_this_runs_folder(self):
        path = fixture(ORDERED)
        self.assertTrue(path.startswith(RUN[0] + os.sep), path)
        self.assertEqual(read(path), ORDERED)

    def test_fixture_lines_are_well_formed_and_sorted(self):
        for text in (ORDERED, COMMENTED, ACTIVE, BANCHI_ONLY):
            rows = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
            self.assertTrue(all(LINE.fullmatch(row) for row in rows), text)
            names = [row.split()[0] for row in rows]
            self.assertEqual(names, sorted(names), text)
        names = [name for name, _ in EIGHT]
        self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
