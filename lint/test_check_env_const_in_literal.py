#!/usr/bin/env python3
"""Cases for lint/check_env_const_in_literal.py. Standard library only.

    python3 lint/test_check_env_const_in_literal.py

Why the check exists: a test-author wrote a quote, a plus, ENV, a plus and a quote inside one string
literal, so eight guard cases never named the env file and passed while testing nothing. The check flags
a quote, `+`, an identifier (NAME or dotted NAME), `+` and a quote, all inside one string literal's body,
in hooks/test_*.py and lint/test_*.py under a root. It reads the source with tokenize.

The cases pin this contract:
- Exit 0 when clean. Exit 1 on a hit, one line per hit: path:line: env-const-in-literal: matched text.
  Exit 2 when a scanned file cannot be read or tokenized. Unknown is never clean.
- A real concatenation outside a literal, and the same words in a comment, never flag.
- Comment openers inside strings, a multi-line string, a lone quote in text and a large file never move a line.
- Only hooks/test_*.py and lint/test_*.py are scanned. --root names the tree. A tree with neither folder exits 0.

CHECK_ENV_CONST_IN_LITERAL_UNDER_TEST, when set, names the module to run instead. The red record runs a
stand-in that exits 0 and prints nothing, as lint/test_check_red_run.py does for its own check. Each case that
expects a flag then fails on its exit-code assert: a behavioural red, not a missing module (decision
test-practices, rule P3).
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
MODULE = os.path.abspath(os.environ.get("CHECK_ENV_CONST_IN_LITERAL_UNDER_TEST")
                         or os.path.join(HERE, "check_env_const_in_literal.py"))

DQ, SQ = '"', "'"
HIT = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): env-const-in-literal: \S")


def inc(quote, name="ENV"):
    """The concatenation text: quote, plus, name, plus, quote. It is built with %, because this file is
    itself scanned (lint/test_*.py), so no literal here may hold the pattern."""
    return "%s + %s + %s" % (quote, name, quote)


# Fixture text. Each is one line unless it says otherwise.
SINGLE_LINE = "GUARD = '%s'\n" % inc(DQ)                       # the incident in a single-quoted literal
DOUBLE_LINE = 'GUARD = "%s"\n' % inc(SQ, "env")                # the incident in a double-quoted literal
TRIPLE_LINE = "GUARD = '''%s'''\n" % inc(DQ)                   # the incident in a triple-quoted literal
DOTTED_LINE = "GUARD = '%s'\n" % inc(DQ, "cfg.ENV_FILE")       # a dotted name inside the literal
FSTRING_LINE = "F = f'%s'\n" % inc(DQ)                         # the incident in an f-string
MULTI_LINES = "\n".join(['DOC = """', "first line", "'%s'" % inc(DQ), "last line", '"""']) + "\n"
CONCAT_LINE = 'SUM = "a" %s ENV %s "b"\n' % ("+", "+")         # a real concatenation outside any literal
OPENER = {
    "/*": 'NOTE = "/* x"\n',
    "//": 'NOTE = "// x"\n',
    "#": 'NOTE = "# x"\n',
}
LONE_QUOTES = """A = "don't"
B = '"'
C = "'"
D = 'x'
"""
CLEAN = 'ENV = "/x/.env"\nMSG = "ok, then done"\nPATH = "x" + SUFFIX\n'


def tree(files):
    """Write each {relative path: text or bytes} under a new folder of this run. Returns the root."""
    root = tempfile.mkdtemp(prefix="envlit_", dir=RUN_FOLDER)
    for rel, body in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body if isinstance(body, bytes) else body.encode("utf-8"))
    return root


def scan(root, exe=None):
    """Run the check as the CLI on root, from inside root."""
    if not os.path.isfile(MODULE):
        raise AssertionError("module absent: lint/check_env_const_in_literal.py")
    return subprocess.run([exe or sys.executable, MODULE, "--root", root], cwd=root,
                          capture_output=True, text=True, timeout=120)


def hits_of(stdout, root):
    """The (relative path, line) of each hit line the check printed."""
    found = set()
    for line in stdout.splitlines():
        m = HIT.match(line)
        if m:
            rel = os.path.relpath(os.path.join(root, m.group("path")), root)
            found.add((rel.replace(os.sep, "/"), int(m.group("line"))))
    return found


def interpreters():
    """The running Python first, then each 3.11 to 3.13 on PATH, once per real path. Both tokenizers run."""
    seen, found = set(), []
    for exe in [sys.executable] + [shutil.which("python3." + v) for v in ("11", "12", "13")]:
        if exe and os.path.realpath(exe) not in seen:
            seen.add(os.path.realpath(exe))
            found.append(exe)
    return found


class Scan(unittest.TestCase):
    def assert_scan(self, files, want, cause):
        """Run the check on a fixture tree, then assert the exit code and the exact set of hits.

        want holds the (path, line) pairs the check must print. Empty means a clean tree, exit 0.
        cause names the one thing the case proves, and leads the failure message.
        """
        root = tree(files)
        got = scan(root)
        exit_want = 1 if want else 0
        self.assertEqual(got.returncode, exit_want, "%s: exit %d, want %d" % (cause, got.returncode, exit_want))
        self.assertEqual(hits_of(got.stdout, root), want, "%s: wrong hit lines" % cause)

    def test_single_quoted_incident_is_flagged(self):
        self.assert_scan({"hooks/test_single.py": SINGLE_LINE},
                         {("hooks/test_single.py", 1)}, "single-quoted literal holding the incident")

    def test_double_quoted_incident_is_flagged(self):
        self.assert_scan({"lint/test_double.py": DOUBLE_LINE},
                         {("lint/test_double.py", 1)}, "double-quoted literal holding the incident")

    def test_triple_quoted_incident_is_flagged(self):
        self.assert_scan({"hooks/test_triple.py": TRIPLE_LINE},
                         {("hooks/test_triple.py", 1)}, "triple-quoted literal holding the incident")

    def test_multiline_triple_quoted_hit_is_on_its_own_line(self):
        self.assert_scan({"lint/test_doc.py": MULTI_LINES},
                         {("lint/test_doc.py", 3)}, "hit inside a multi-line triple-quoted string")

    def test_fstring_incident_is_flagged_under_each_python(self):
        # Pre-3.12 tokenizes an f-string as one STRING token; 3.12 and later as FSTRING_START, MIDDLE and END.
        for exe in interpreters():
            root = tree({"hooks/test_fstring.py": FSTRING_LINE})
            got = scan(root, exe)
            self.assertEqual(got.returncode, 1, "f-string holding the incident: exit %d, want 1 under %s"
                             % (got.returncode, exe))
            self.assertEqual(hits_of(got.stdout, root), {("hooks/test_fstring.py", 1)},
                             "f-string holding the incident: wrong hit lines under %s" % exe)

    def test_dotted_name_inside_a_literal_is_flagged(self):
        self.assert_scan({"hooks/test_dotted.py": DOTTED_LINE},
                         {("hooks/test_dotted.py", 1)}, "dotted name inside a literal")

    def test_real_concatenation_outside_a_literal_is_clean(self):
        # The control in the same tree proves the scan ran before the clean line is read.
        root = tree({"hooks/test_control.py": SINGLE_LINE, "hooks/test_concat.py": CONCAT_LINE})
        hits = hits_of(scan(root).stdout, root)
        self.assertIn(("hooks/test_control.py", 1), hits,
                      "the control incident was not flagged, so the scan proves nothing")
        self.assertNotIn(("hooks/test_concat.py", 1), hits,
                         "a concatenation outside any literal was flagged")

    def test_slash_star_opener_then_hit_is_flagged_on_its_line(self):
        self.assert_scan({"lint/test_opener.py": OPENER["/*"] + SINGLE_LINE},
                         {("lint/test_opener.py", 2)}, "a /* opener in a string hid a later hit")

    def test_slash_star_opener_then_clean_line_is_clean(self):
        self.assert_scan({"lint/test_opener.py": OPENER["/*"] + CONCAT_LINE},
                         set(), "a /* opener in a string made a clean line flag")

    def test_double_slash_opener_then_hit_is_flagged_on_its_line(self):
        self.assert_scan({"lint/test_opener.py": OPENER["//"] + SINGLE_LINE},
                         {("lint/test_opener.py", 2)}, "a // opener in a string hid a later hit")

    def test_double_slash_opener_then_clean_line_is_clean(self):
        self.assert_scan({"lint/test_opener.py": OPENER["//"] + CONCAT_LINE},
                         set(), "a // opener in a string made a clean line flag")

    def test_hash_opener_then_hit_is_flagged_on_its_line(self):
        self.assert_scan({"lint/test_opener.py": OPENER["#"] + SINGLE_LINE},
                         {("lint/test_opener.py", 2)}, "a # opener in a string hid a later hit")

    def test_hash_opener_then_clean_line_is_clean(self):
        self.assert_scan({"lint/test_opener.py": OPENER["#"] + CONCAT_LINE},
                         set(), "a # opener in a string made a clean line flag")

    def test_hash_comment_holding_the_incident_is_clean(self):
        self.assert_scan({"hooks/test_hash.py": "# GUARD = '%s'\n" % inc(DQ)},
                         set(), "the incident inside a hash comment flagged")

    def test_lone_quotes_do_not_shift_a_later_hit(self):
        self.assert_scan({"hooks/test_quotes.py": LONE_QUOTES + SINGLE_LINE},
                         {("hooks/test_quotes.py", 5)}, "a lone quote in text moved a later hit")

    def test_lone_quotes_alone_are_clean(self):
        self.assert_scan({"hooks/test_quotes.py": LONE_QUOTES},
                         set(), "a lone quote in text flagged")

    def test_clean_file_exits_zero(self):
        self.assert_scan({"hooks/test_clean.py": CLEAN}, set(), "a clean file exited non-zero")

    def test_empty_files_are_clean(self):
        self.assert_scan({"hooks/test_empty.py": "", "lint/test_empty.py": ""},
                         set(), "an empty file flagged or failed")

    def test_hit_on_the_last_line_of_a_large_file(self):
        big = "".join("X%d = %d\n" % (i, i) for i in range(4000)) + SINGLE_LINE
        self.assert_scan({"lint/test_full.py": big},
                         {("lint/test_full.py", 4001)}, "hit on the last line of a 4001-line file")

    def test_untokenizable_file_exits_two_even_beside_a_clean_one(self):
        root = tree({"hooks/test_ok.py": CLEAN, "lint/test_broken.py": 'X = """never closed\n'})
        got = scan(root)
        self.assertEqual(got.returncode, 2, "a file that cannot be tokenized: exit %d, want 2" % got.returncode)

    def test_undecodable_file_exits_two(self):
        root = tree({"lint/test_bytes.py": b'X = "\xff\xfe"\n'})
        got = scan(root)
        self.assertEqual(got.returncode, 2, "a file that cannot be decoded: exit %d, want 2" % got.returncode)

    def test_both_scanned_folders_are_scanned(self):
        self.assert_scan({"hooks/test_a.py": SINGLE_LINE, "lint/test_b.py": SINGLE_LINE},
                         {("hooks/test_a.py", 1), ("lint/test_b.py", 1)},
                         "a test file in hooks/ or lint/ was not scanned")

    def test_files_outside_the_two_globs_are_not_scanned(self):
        root = tree({"hooks/test_control.py": SINGLE_LINE, "hooks/guard_x.py": SINGLE_LINE,
                     "lint/helper.py": SINGLE_LINE, "lint/check_other.py": SINGLE_LINE,
                     "tests/test_x.py": SINGLE_LINE})
        hits = hits_of(scan(root).stdout, root)
        self.assertIn(("hooks/test_control.py", 1), hits,
                      "the control in a scanned folder was not flagged, so the scope proves nothing")
        self.assertEqual(hits, {("hooks/test_control.py", 1)},
                         "a file outside hooks/test_*.py and lint/test_*.py was flagged")

    def test_root_with_neither_folder_exits_zero(self):
        control = tree({"hooks/test_control.py": SINGLE_LINE})
        self.assertEqual(scan(control).returncode, 1,
                         "--root not honored: the control tree's incident was not flagged")
        empty = tree({"README.md": "no test folders here\n"})
        got = scan(empty)
        self.assertEqual(got.returncode, 0, "a root with neither folder: exit %d, want 0" % got.returncode)
        self.assertEqual(hits_of(got.stdout, empty), set(), "a root with neither folder: hit lines printed")

    def test_repo_tree_gets_a_defined_exit(self):
        got = scan(REPO)
        self.assertIn(got.returncode, (0, 1),
                      "the repo tree: exit %d, want 0 or 1 (2 means unknown)" % got.returncode)

    def test_fixtures_are_the_shapes_they_name(self):
        # Green on any checker: ast reads each fixture as the literal its case names.
        def value(text):
            return ast.parse(text).body[0].value
        self.assertEqual(value(SINGLE_LINE).value, inc(DQ), "single-quoted fixture is not one string")
        self.assertEqual(value(DOUBLE_LINE).value, inc(SQ, "env"), "double-quoted fixture is not one string")
        self.assertEqual(value(TRIPLE_LINE).value, inc(DQ), "triple-quoted fixture is not one string")
        self.assertEqual(value(DOTTED_LINE).value, inc(DQ, "cfg.ENV_FILE"), "dotted fixture is not one string")
        self.assertEqual(value(FSTRING_LINE).values[0].value, inc(DQ), "f-string fixture has no literal text")
        self.assertEqual(value(MULTI_LINES).value.split("\n")[2], "'%s'" % inc(DQ),
                         "multi-line fixture does not hold the incident on line 3")
        self.assertIsInstance(value(CONCAT_LINE), ast.BinOp, "concatenation fixture is a literal")
        for key, line in OPENER.items():
            self.assertEqual(value(line).value, key + " x", "opener fixture %r is not one string" % key)
        self.assertEqual([s.value.value for s in ast.parse(LONE_QUOTES).body],
                         ["don't", '"', "'", "x"], "lone-quote fixture does not hold the four strings")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
