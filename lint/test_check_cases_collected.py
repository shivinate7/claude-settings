#!/usr/bin/env python3
"""Fixture suite for lint/check_cases_collected.py. Run: python3 lint/test_check_cases_collected.py

The lint reads each hooks/test_*.py under --root and lists each case function the runner would not
run. A case function takes no arguments. It is registered when it carries @case (or the file's own
registering decorator), or when its name is in a module-level table the runner iterates: a *_ROWS
tuple, or a CASES tuple or list. Exit 1 with one line per unregistered case, naming its file and
function. Exit 0 otherwise.

Not cases: a function with arguments; a helper that another function in the file calls; a name that
appears only in a string or a comment. A file that imports unittest is out of scope.

CHECK_CASES_LINT names the lint to run (a stub, in a check of this suite). Temp files live under the
run folder from lint/_test_temp.py.
"""
import atexit
import glob
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
LINT = os.environ.get("CHECK_CASES_LINT") or os.path.join(HERE, "check_cases_collected.py")
RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, ignore_errors=True)

EXPECT = '''def expect(ok, msg):
    return [] if ok else [msg]
'''

CASE_DECORATED = '''CASES = []


def case(fn):
    CASES.append(fn)
    return fn


''' + EXPECT + '''

@case
def decorated_case():
    return expect(True, "unused")
'''

OWN_DECORATOR = '''CASES = []


def posix_case(fn):
    CASES.append(fn)
    return fn


''' + EXPECT + '''

@posix_case
def own_decorated_case():
    return expect(True, "unused")
'''

TABLE_MEMBER = EXPECT + '''

def row_case():
    return expect(True, "unused")


NOTICE_ROWS = (row_case,)
'''

LITERAL_CASES = EXPECT + '''

def literal_case():
    return expect(True, "unused")


CASES = (literal_case,)
'''

ORPHAN = EXPECT + '''

def orphan_case():
    return expect(True, "unused")
'''

HELPER_WITH_ARGS = EXPECT + '''

def check_row(x):
    return expect(x, "unused")
'''

ZERO_ARG_HELPER = '''def case(fn):
    return fn


def fresh_dir():
    return "unused"


@case
def uses_fresh_dir():
    fresh_dir()
    return "unused"
'''

QUOTED = '''# quoted_case is listed in NOTICE_ROWS once the table exists
# NOTICE_ROWS = (quoted_case,)
HINT = "quoted_case, Don't wait for it"
OPENER = "# quoted_case"
SNIPPET = "@case\\ndef quoted_case():"
BLOCK = """
quoted_case
"""


''' + EXPECT + '''

def quoted_case():
    return expect(True, "unused")
'''

UNITTEST_FILE = '''import unittest


class Cases(unittest.TestCase):
    def test_nothing(self):
        self.assertTrue(True)


''' + EXPECT + '''

def out_of_scope_case():
    return expect(True, "unused")
'''


def make_root(name, files):
    """A fixture root for one check: each relative path in files gets its text."""
    root = os.path.join(RUN_FOLDER, name)
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return root


def real_hooks_tests():
    files = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "hooks", "test_*.py"))):
        with open(path, encoding="utf-8") as fh:
            files["hooks/" + os.path.basename(path)] = fh.read()
    return files


class CheckCasesCollected(unittest.TestCase):
    def lint(self, root):
        """Run the lint on root and return (exit code, output lines). An absent lint fails by assert."""
        self.assertTrue(os.path.isfile(LINT), "lint is missing: %s" % LINT)
        r = subprocess.run([sys.executable, LINT, "--root", root], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertNotIn("Traceback", r.stderr, "the lint raised instead of reporting")
        return r.returncode, [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]

    def assert_clean(self, rc, lines):
        self.assertEqual(rc, 0, "exit %d, want 0" % rc)
        listed = [ln for ln in lines if ".py" in ln]
        self.assertEqual(listed, [], "want no unregistered case listed")

    def assert_one_orphan(self, rc, lines, filename, fn):
        self.assertEqual(rc, 1, "exit %d, want 1" % rc)
        listed = [ln for ln in lines if ".py" in ln]
        self.assertEqual(len(listed), 1, "want one line per orphan, got %d: %s" % (len(listed), listed[:3]))
        self.assertIn(filename, listed[0], "the line must name its file")
        self.assertIn(fn, listed[0], "the line must name its function")

    def test_case_decorator_passes(self):
        root = make_root("case_decorator", {"hooks/test_decorated.py": CASE_DECORATED})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_own_registering_decorator_passes(self):
        root = make_root("own_decorator", {"hooks/test_own.py": OWN_DECORATOR})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_table_member_passes(self):
        root = make_root("table_member", {"hooks/test_table.py": TABLE_MEMBER})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_literal_cases_table_passes(self):
        root = make_root("literal_cases", {"hooks/test_literal.py": LITERAL_CASES})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_orphan_case_is_listed(self):
        root = make_root("orphan", {"hooks/test_orphan.py": ORPHAN})
        rc, lines = self.lint(root)
        self.assert_one_orphan(rc, lines, "test_orphan.py", "orphan_case")

    def test_helper_with_arguments_is_not_a_case(self):
        root = make_root("helper_args", {"hooks/test_helper.py": HELPER_WITH_ARGS})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_zero_arg_helper_called_by_a_case_is_not_a_case(self):
        root = make_root("zero_arg_helper", {"hooks/test_helper0.py": ZERO_ARG_HELPER})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_name_in_string_or_comment_is_not_a_registration(self):
        root = make_root("quoted", {"hooks/test_quoted.py": QUOTED})
        rc, lines = self.lint(root)
        self.assert_one_orphan(rc, lines, "test_quoted.py", "quoted_case")

    def test_unittest_file_is_out_of_scope(self):
        root = make_root("unittest_scope", {"hooks/test_unit.py": UNITTEST_FILE})
        rc, lines = self.lint(root)
        self.assert_clean(rc, lines)

    def test_real_hooks_pass_and_planted_orphan_is_listed(self):
        rc, lines = self.lint(ROOT)
        self.assert_clean(rc, lines)
        files = real_hooks_tests()
        files["hooks/test_planted.py"] = ORPHAN
        root = make_root("planted_on_real", files)
        rc, lines = self.lint(root)
        self.assert_one_orphan(rc, lines, "test_planted.py", "orphan_case")


if __name__ == "__main__":
    unittest.main(verbosity=2)
