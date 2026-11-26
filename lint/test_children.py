#!/usr/bin/env python3
"""Cases for lint/children.py, the one reader of the child list. Standard library only.

    python3 lint/test_children.py

The list is one file, docs/children.txt. Each line reads `owner/name <since YYYY-MM-DD>`, sorted by name; `#`
comment lines and blank lines are allowed. The public file holds no repo ids. The reader's entry is
main(argv, fetch=None), which returns the exit code. `--file PATH` reads a fixture instead of the real list.
fetch(path) returns the parsed GitHub JSON for a REST path and raises for a path it cannot read. A child is read
from GitHub by its name. No case reaches the network or starts a process: run_reader refuses both and fails the
case if the reader tries.
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

ALPHA = "shivinate7/alpha-example"
BETA = "shivinate7/beta-example"
GAMMA = "shivinate7/gamma-example"
DELTA = "shivinate7/delta-example"
APP404 = "shivinate7/app-404"
SELF = "shivinate7/claude-settings"
ORDERED = "%s 2026-01-05\n%s 2026-02-01\n" % (ALPHA, GAMMA)
COMMENTED = "# child repos\n\n%s 2026-01-05\n\n# later\n%s 2026-02-01\n" % (ALPHA, GAMMA)
ACTIVE = "%s 2026-01-05\n%s 2026-01-06\n%s 2026-02-01\n" % (ALPHA, BETA, GAMMA)
BANCHI_ONLY = "%s 2026-01-05\n" % ALPHA
EMPTY = "# no children yet\n\n"
MALFORMED = {  # each goes on line 3 of the file below, after ALPHA on line 2
    "name has no owner": "beta-example 2026-01-06",
    "date is not YYYY-MM-DD": "%s 26-1-6" % BETA,
    "a field is missing": BETA,
    "a repo id is left in the line": "%s 555002 2026-01-06" % BETA,
}
LINE = re.compile(r"\S+/\S+ \d{4}-\d{2}-\d{2}")
GH_TEXT = {403: "Forbidden", 404: "Not Found", 500: "Internal Server Error"}
SCAN_REPOS = [
    {"id": 555001, "full_name": ALPHA},
    {"id": 555002, "full_name": BETA},
    {"id": 555003, "full_name": GAMMA},
    {"id": 555004, "full_name": DELTA},
    {"id": 555005, "full_name": SELF},
]
MOVED = "shivinate7/alpha-moved-example"  # ALPHA's name after a rename: a by-name read of ALPHA answers with this
DOT_OR_DASH = ["../..", "./.", "a/..", "../x", ".../x", "-a/b", "a/-b"]  # a dot-only segment or a leading dash
KEPT = ["a-b/c.d", "a/.github", "a/b", "a_b/c-d"]  # names the segment rule must still accept


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


def roster_fields():
    """The fields of each entry line in docs/children.txt, in file order."""
    return [line.split() for line in read(ROSTER).splitlines() if line.strip() and not line.startswith("#")]


def repo(ident, full_name, archived=False):
    return {"id": ident, "full_name": full_name, "archived": archived}


def gh_error(path, status):
    """The error gh_fetch raises for a failed read: the path, then gh's text and status."""
    return RuntimeError("gh api %s: gh: %s (HTTP %d)" % (path, GH_TEXT[status], status))


class NoFetch:
    """Records each call and raises. A subcommand that never reads GitHub leaves `calls` empty."""

    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        raise RuntimeError("no GitHub read expected: %s" % path)


class ByName:
    """Answers each read by the child's name. `answers` maps a name to a repo dict, or to a status: a status makes
    the read fail with gh's error for that status. A path that names no child in `answers` is gh's Not Found."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        for name, found in self.answers.items():
            if name in path:
                if isinstance(found, int):
                    raise gh_error(path, found)
                return found
        raise gh_error(path, 404)


class ScanFetch:
    """Answers the owner's repo listing with `repos`. A stamp read answers for a repo in `marked`, by its name or its
    id in the path. `errors` maps a name to the status its stamp read fails with; any other stamp read is Not Found.
    `listing_status` makes the listing fail with that status."""

    def __init__(self, repos, marked, errors=None, listing_status=None):
        self.repos = repos
        self.marked = set(marked)
        self.errors = errors or {}
        self.listing_status = listing_status
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if "stamp.json" not in path:
            if self.listing_status:
                raise gh_error(path, self.listing_status)
            return self.repos
        for item in self.repos:
            if item["full_name"] not in path and str(item["id"]) not in path:
                continue
            if item["full_name"] in self.errors:
                raise gh_error(path, self.errors[item["full_name"]])
            if item["full_name"] in self.marked:
                return {"name": "stamp.json"}
        raise gh_error(path, 404)


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
    """docs/children.txt, the list the reader reads when no --file is given. The cases pin the list's shape, not its
    names or its count, so a child added, renamed or removed does not break them."""

    def test_list_prints_each_name_in_file_order(self):
        self.assertTrue(os.path.isfile(CHILDREN), "lint/children.py is missing: there is no reader to run")
        self.assertTrue(os.path.isfile(ROSTER), "docs/children.txt is missing: the list has no file")
        names = [fields[0] for fields in roster_fields()]
        out = subprocess.run([sys.executable, CHILDREN, "list"], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout), (0, "".join(name + "\n" for name in names)), out.stderr)

    def test_the_list_is_not_empty(self):
        self.assertTrue(os.path.isfile(ROSTER), "docs/children.txt is missing: the list has no file")
        self.assertTrue(roster_fields(), "docs/children.txt has no entry line")

    def test_each_line_is_owner_name_and_since_with_no_repo_id(self):
        self.assertTrue(os.path.isfile(ROSTER), "docs/children.txt is missing: the list has no file")
        bad = [line for line in read(ROSTER).splitlines()
               if line.strip() and not line.startswith("#") and not LINE.fullmatch(line)]
        self.assertEqual(bad, [], "docs/children.txt has a line that is not `owner/name YYYY-MM-DD`")

    def test_names_are_sorted_and_unique(self):
        names = [fields[0] for fields in roster_fields()]
        self.assertEqual(names, sorted(names), "the names are not in sorted order")
        self.assertEqual(len(set(names)), len(names), "a name is listed twice")


class ListCommand(unittest.TestCase):
    def test_prints_each_name_in_file_order(self):
        code, out, err = run_reader(self, ["--file", fixture(ORDERED), "list"], NoFetch())
        self.assertEqual((code, out), (0, "%s\n%s\n" % (ALPHA, GAMMA)), err)

    def test_skips_comment_and_blank_lines(self):
        code, out, err = run_reader(self, ["--file", fixture(COMMENTED), "list"], NoFetch())
        self.assertEqual((code, out), (0, "%s\n%s\n" % (ALPHA, GAMMA)), err)

    def test_empty_file_lists_nothing(self):
        code, out, err = run_reader(self, ["--file", fixture(EMPTY), "list"], NoFetch())
        self.assertEqual((code, out), (0, ""), err)

    def test_makes_no_github_read(self):
        fake = NoFetch()
        code, out, err = run_reader(self, ["--file", fixture(ORDERED), "list"], fake)
        self.assertEqual(code, 0, err)
        self.assertEqual(fake.calls, [], "list read GitHub")

    def test_malformed_line_is_refused_with_its_number(self):
        for why, bad in MALFORMED.items():
            with self.subTest(why=why):
                text = "# child repos\n%s 2026-01-05\n%s\n" % (ALPHA, bad)
                code, out, err = run_reader(self, ["--file", fixture(text), "list"], NoFetch())
                self.assertEqual((code, out), (2, ""), err)
                self.assertRegex(err, r"\bline 3\b", "the refusal does not name line 3")


class EverySubcommand(unittest.TestCase):
    def test_malformed_line_is_refused_by_list_active_scan_and_add(self):
        text = "%s 2026-01-05\n%s 26-1-6\n" % (ALPHA, BETA)
        cases = {
            "list --active": (["list", "--active"], ByName({})),
            "scan": (["scan"], ScanFetch([], [])),
            "add": (["add", GAMMA, "2026-01-07"], NoFetch()),
        }
        for why, (tail, fake) in cases.items():
            with self.subTest(why=why):
                path = fixture(text)
                code, out, err = run_reader(self, ["--file", path, *tail], fake)
                self.assertEqual((code, out), (2, ""), err)
                self.assertRegex(err, r"\bline 2\b", "the refusal does not name line 2")
                self.assertEqual(read(path), text, "a refused subcommand changed the list")


class NameSegments(unittest.TestCase):
    """The name rule: a dot-only segment or a leading dash is refused with exit 2 and never reaches GitHub."""

    def test_add_refuses_a_dot_only_or_leading_dash_name_and_writes_nothing(self):
        for name in DOT_OR_DASH:
            with self.subTest(name=name):
                path = fixture(EMPTY)
                before = read(path)
                # `--` keeps argparse from reading a leading dash as an option, so the reader's own check must refuse it.
                code, out, err = run_reader(self, ["--file", path, "add", "--", name, "2026-01-06"], NoFetch())
                self.assertEqual(code, 2, "%s was not refused: %r" % (name, err))
                self.assertIn(name, err, "the refusal does not name %s: %r" % (name, err))
                self.assertEqual(read(path), before, "%s was written to the list" % name)

    def test_a_file_line_with_a_dot_only_or_leading_dash_name_is_refused_before_any_read(self):
        for name in DOT_OR_DASH:
            with self.subTest(name=name):
                fake = ByName({})
                code, out, err = run_reader(self, ["--file", fixture("%s 2026-01-05\n" % name), "list", "--active"], fake)
                self.assertEqual(code, 2, "%s on a file line was not refused: %r" % (name, err))
                self.assertRegex(err, r"\bline 1\b", "the refusal does not name line 1: %r" % err)
                self.assertEqual(out, "", "%s printed a line" % name)
                self.assertEqual(fake.calls, [], "%s reached GitHub: %r" % (name, fake.calls))

    def test_names_the_segment_rule_must_keep_are_still_accepted(self):
        text = "".join("%s 2026-01-05\n" % name for name in KEPT)
        code, out, err = run_reader(self, ["--file", fixture(text), "list"], NoFetch())
        self.assertEqual((code, out), (0, "".join("%s\n" % name for name in KEPT)), err)
        for name in KEPT:
            with self.subTest(name=name):
                path = fixture(EMPTY)
                code, out, err = run_reader(self, ["--file", path, "add", name, "2026-01-06"], NoFetch())
                self.assertEqual(code, 0, err)
                self.assertIn("%s 2026-01-06" % name, read(path).splitlines())


class ListActive(unittest.TestCase):
    def test_drops_an_archived_child(self):
        fake = ByName({ALPHA: repo(555001, ALPHA), BETA: repo(555002, BETA),
                       GAMMA: repo(555003, GAMMA, archived=True)})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, "%s\n%s\n" % (ALPHA, BETA)), err)

    def test_a_child_GitHub_answers_404_for_by_name_is_unknown_and_a_rename_is_not_followed(self):
        fake = ByName({ALPHA: repo(555001, ALPHA), BETA: 404, GAMMA: repo(555003, GAMMA)})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(out, "%s\n%s\n" % (ALPHA, GAMMA), "the readable children were not all listed")
        self.assertEqual(err.splitlines(), ["unknown: %s" % BETA], err)
        self.assertEqual(code, 3)

    def test_a_non_404_error_on_a_child_is_unknown_and_exit_3(self):
        fake = ByName({ALPHA: repo(555001, ALPHA), BETA: 403, GAMMA: repo(555003, GAMMA)})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(out, "%s\n%s\n" % (ALPHA, GAMMA), "the readable children were not all listed")
        self.assertEqual(err.splitlines(), ["unknown: %s" % BETA], err)
        self.assertEqual(code, 3)

    def test_a_by_name_answer_under_another_name_is_a_rename_and_is_unknown(self):
        # GitHub redirects a renamed child's old name to the new one. An answer under another name is not this child's.
        fake = ByName({ALPHA: repo(555001, MOVED), BETA: repo(555002, BETA), GAMMA: repo(555003, GAMMA)})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(out, "%s\n%s\n" % (BETA, GAMMA), "a renamed child was listed, or a readable one was not: %r" % out)
        self.assertEqual(err.splitlines(), ["unknown: %s" % ALPHA], err)
        self.assertEqual(code, 3, "a renamed child did not make the exit code 3")

    def test_exit_3_names_every_unreadable_child_and_a_caller_must_read_the_exit_code(self):
        # Exit 3 still prints the readable actives, so a caller that ignores the exit code under-counts.
        fake = ByName({ALPHA: repo(555001, ALPHA), BETA: 404, GAMMA: 500})
        code, out, err = run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(out, "%s\n" % ALPHA, "stdout does not hold only the readable actives: %r" % out)
        self.assertEqual(err.splitlines(), ["unknown: %s" % BETA, "unknown: %s" % GAMMA], err)
        self.assertEqual(code, 3, err)

    def test_asks_github_by_name(self):
        fake = ByName({ALPHA: repo(555001, ALPHA), BETA: repo(555002, BETA), GAMMA: repo(555003, GAMMA)})
        run_reader(self, ["--file", fixture(ACTIVE), "list", "--active"], fake)
        for name in (ALPHA, BETA, GAMMA):
            self.assertTrue(any(name in call for call in fake.calls), "no read by name %s: %r" % (name, fake.calls))


class AddCommand(unittest.TestCase):
    def test_keeps_the_file_sorted(self):
        path = fixture(ORDERED)
        code, out, err = run_reader(self, ["--file", path, "add", BETA, "2026-01-06"], NoFetch())
        self.assertEqual(code, 0, err)
        self.assertEqual(read(path).splitlines(), [
            "%s 2026-01-05" % ALPHA,
            "%s 2026-01-06" % BETA,
            "%s 2026-02-01" % GAMMA,
        ])

    def test_refuses_a_duplicate_name_and_names_it(self):
        path = fixture(ORDERED)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "add", ALPHA, "2026-02-01"], NoFetch())
        self.assertEqual(code, 2, err)
        self.assertEqual(len(err.strip().splitlines()), 1, "the refusal is not one line: %r" % err)
        self.assertIn(ALPHA, err, "the refusal does not name the duplicate: %r" % err)
        self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_an_extra_argument_such_as_an_id_with_exit_2(self):
        path = fixture(EMPTY)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "add", BETA, "555002", "2026-01-06"], NoFetch())
        self.assertEqual(code, 2, "an extra argument was not refused: %r" % err)
        self.assertIn("555002", err, "the refusal does not name the extra argument: %r" % err)
        self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_a_malformed_argument_and_names_it(self):
        tails = {
            "name has no owner": (["beta-example", "2026-01-06"], "beta-example"),
            "name has two slashes": (["a/b/c", "2026-01-06"], "a/b/c"),
            "since is not a date": ([BETA, "26-1-6"], "26-1-6"),
        }
        for why, (tail, token) in tails.items():
            with self.subTest(why=why):
                path = fixture(EMPTY)
                before = read(path)
                code, out, err = run_reader(self, ["--file", path, "add", *tail], NoFetch())
                self.assertEqual(code, 2, err)
                self.assertEqual(len(err.strip().splitlines()), 1, "the refusal is not one line: %r" % err)
                self.assertIn(token, err, "the refusal does not name %s: %r" % (token, err))
                self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_an_add_with_no_since(self):
        path = fixture(EMPTY)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "add", BETA], NoFetch())
        self.assertEqual(code, 2, err)
        self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_a_duplicate_that_differs_only_in_letter_case_and_names_the_existing_entry(self):
        for name in ("Shivinate7/alpha-example", "shivinate7/Alpha-Example", "SHIVINATE7/ALPHA-EXAMPLE"):
            with self.subTest(name=name):
                path = fixture(ORDERED)
                before = read(path)
                code, out, err = run_reader(self, ["--file", path, "add", name, "2026-02-01"], NoFetch())
                self.assertEqual(code, 2, "a duplicate in another letter case was not refused: %r" % err)
                self.assertEqual(len(err.strip().splitlines()), 1, "the refusal is not one line: %r" % err)
                self.assertIn(ALPHA.casefold(), err.casefold(), "the refusal does not name the existing entry: %r" % err)
                self.assertEqual(read(path), before, "a refused add changed the list")

    def test_refuses_claude_settings_in_any_letter_case(self):
        for name in (SELF, "Shivinate7/claude-settings", "SHIVINATE7/CLAUDE-SETTINGS", "shivinate7/Claude-Settings"):
            with self.subTest(name=name):
                path = fixture(EMPTY)
                before = read(path)
                code, out, err = run_reader(self, ["--file", path, "add", name, "2026-01-07"], NoFetch())
                self.assertEqual(code, 2, err)
                self.assertRegex(err.lower(), "claude-settings", "the refusal does not name claude-settings: %r" % err)
                self.assertEqual(read(path), before, "claude-settings was written as a child")


class ScanCommand(unittest.TestCase):
    def test_lists_marked_children_not_in_the_file_by_name(self):
        fake = ScanFetch(SCAN_REPOS, [BETA, GAMMA, SELF])
        code, out, err = run_reader(self, ["--file", fixture(BANCHI_ONLY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(out.splitlines()), [BETA, GAMMA], out)

    def test_never_lists_claude_settings(self):
        fake = ScanFetch([repo(555005, SELF)], [SELF])
        code, out, err = run_reader(self, ["--file", fixture(EMPTY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, ""), err)

    def test_compares_by_name_so_a_child_in_the_file_is_not_read_again(self):
        fake = ScanFetch([repo(555009, ALPHA)], [ALPHA])
        code, out, err = run_reader(self, ["--file", fixture(BANCHI_ONLY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (0, ""), err)
        self.assertFalse(any("stamp.json" in call for call in fake.calls),
                         "a child in the file was read again: %r" % fake.calls)

    def test_writes_nothing(self):
        path = fixture(BANCHI_ONLY)
        before = read(path)
        code, out, err = run_reader(self, ["--file", path, "scan"], ScanFetch(SCAN_REPOS, [BETA, GAMMA, SELF]))
        self.assertEqual(code, 0, err)
        self.assertEqual(read(path), before, "scan changed the list")

    def test_a_403_on_a_file_read_is_unknown_when_the_name_holds_404(self):
        fake = ScanFetch([repo(555404, APP404)], [], errors={APP404: 403})
        code, out, err = run_reader(self, ["--file", fixture(EMPTY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (3, ""), "a 403 on a stamp read was taken for no stamp file: %s" % err)
        self.assertEqual(err.splitlines(), ["unknown: %s" % APP404], err)

    def test_a_403_on_a_file_read_is_unknown_for_a_name_without_404(self):
        fake = ScanFetch([repo(555001, ALPHA)], [], errors={ALPHA: 403})
        code, out, err = run_reader(self, ["--file", fixture(EMPTY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (3, ""), err)
        self.assertEqual(err.splitlines(), ["unknown: %s" % ALPHA], err)

    def test_a_404_on_a_file_read_is_no_file_even_when_the_name_holds_404(self):
        fake = ScanFetch([repo(555404, APP404)], [], errors={APP404: 404})
        code, out, err = run_reader(self, ["--file", fixture(EMPTY), "scan"], fake)
        self.assertTrue(any("stamp.json" in call for call in fake.calls), "the stamp read never happened")
        self.assertEqual((code, out, err), (0, "", ""), "a real 404 on a stamp read was reported")

    def test_a_failed_owner_listing_is_one_unknown_line_and_exit_3(self):
        fake = ScanFetch([], [], listing_status=500)
        code, out, err = run_reader(self, ["--file", fixture(EMPTY), "scan"], fake)
        self.assertTrue(fake.calls, "the fixture never reached the reader")
        self.assertEqual((code, out), (3, ""), err)
        self.assertEqual(len(err.splitlines()), 1, "a failed listing did not print one line: %r" % err)
        self.assertTrue(err.startswith("unknown: "), "the failed listing is not an unknown line: %r" % err)


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


if __name__ == "__main__":
    unittest.main()
