#!/usr/bin/env python3
"""Fixture suite for lint/check_comment_narration.py. Run: python3 lint/test_check_comment_narration.py

Rule: building-comments-say-why. A comment or docstring line that a change adds to a .py file
may not narrate history or review. Each case builds a throwaway git repo: a base commit that
is `origin/main`, a change commit on top. It then runs the check as a CLI with `--base origin/main`.

The cases pin this contract:
- Exit 0 on a clean diff. Exit 1 on a flagged one. Any other nonzero exit when the base cannot be read.
- Each hit prints `path:line` (the physical line of the comment or docstring text) and the matched text.
- Comments come from `tokenize`, docstrings from `ast`. The same words in any other string never fail.
- Only lines the diff adds can fail (a ratchet). Old lines never fail, even when the diff moves them.
- Line numbers follow `ast` and `tokenize`, which break lines on \\r\\n, \\r and \\n only. A U+2028, U+2029,
  \\x0b, \\x0c, \\x1c-\\x1e or \\x85 inside a string never shifts a reported line or hides an added one.
- Each hit row ends with a one-line remedy: say what and why; the history goes in git or the decision.
- The check is one file. The suite copies only that file into the fixture repo, so the check finds
  the repo from its working directory or from its own location, and both give the fixture repo.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
MODULE = os.path.join(HERE, "check_comment_narration.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)

# Text that one of the six patterns must flag, in a comment or in a docstring line.
FLAGGED = [
    "fixed in round 2", "Round3 of changes", "after review round", "a review finding", "review points",
    "from PR #509", "PR 1234", "PR#4567",
    "reverted in 2ff288b3", "see 03d62e85", "added by 4a1b2c3", "cut at 9f8e7d6c5b",
    "MEASURED 40 ms", "CORRECTED from the old value", "ADDED 2026 for the batch",
    "since 2026-10-18", "dated 2025-01-03",
    "owner ruling", "Owner's order", "owner request", "Owner ask",
]

# Near misses. No pattern may flag any of them.
CLEAN = [
    "round the total up to 2 places", "surround 2 items", "a round-trip to the server",
    "measured in ms, corrected for drift", "token deadbeef is all letters", "id 12345678 is all digits",
    "effaced", "see PR #12 for nothing", "ADDED to the list", "the owner of this file", "the owner's name",
    "review the code first", "ask the reviewer", "the year 2026",
]

# Characters that str.splitlines() treats as a line break but ast and tokenize do not.
NON_BREAKS = ["\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85"]

REMEDY = "say what and why; the history goes in git or the decision"


def at(src, needle):
    """1-based number of the first line of src that holds needle. Lines break on \\n only, as in ast."""
    for n, line in enumerate(src.split("\n"), 1):
        if needle in line:
            return n
    raise AssertionError("fixture lacks %r" % needle)


class Case(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_comment_narration.py")
        self.tree = tempfile.mkdtemp(prefix="cnl_")
        self.addCleanup(shutil.rmtree, self.tree, True)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the check's imports, whatever they become
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_comment_narration.py"))
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args):
        subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                        "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                       check=True, capture_output=True, text=True, env=GIT_ENV)

    def commit(self, msg, files):
        for rel, text in files.items():
            path = os.path.join(self.tree, rel)
            if text is None:
                os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)

    def base(self, files):
        self.commit("base", files)
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def change(self, files):
        self.commit("change", files)

    def lint(self, *args):
        args = args or ("--base", "origin/main")
        r = subprocess.run([sys.executable, os.path.join(self.tree, "lint", "check_comment_narration.py"), *args],
                           cwd=self.tree, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=GIT_ENV)
        return r.returncode, r.stdout + r.stderr

    def hit_line(self, out, path, line):
        """The output line that names path:line, or None."""
        for row in out.splitlines():
            if re.search(r"(?<!\w)%s:%d(?!\d)" % (re.escape(path), line), row):
                return row
        return None

    def assertHit(self, out, path, line):
        self.assertIsNotNone(self.hit_line(out, path, line), "no hit at %s:%d in:\n%s" % (path, line, out))

    def assertNoHit(self, out, path, line):
        self.assertIsNone(self.hit_line(out, path, line), "unexpected hit at %s:%d in:\n%s" % (path, line, out))

    def assertClean(self):
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)


class FlagsAddedLines(Case):
    def test_each_pattern_flags_an_added_comment(self):
        self.base({"keep.py": "x = 1\n"})
        files = {}
        for i, text in enumerate(FLAGGED):
            files["c%d.py" % i] = ("x = 1\n# %s\ny = 2\n" if i % 2 else "x = 1\ny = 2  # %s\n") % text
        self.change(files)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for i, text in enumerate(FLAGGED):
            with self.subTest(text):
                self.assertHit(out, "c%d.py" % i, 2)

    def test_each_pattern_flags_an_added_docstring_line(self):
        self.base({"keep.py": "x = 1\n"})
        files = {"d%d.py" % i: 'def f():\n    """Does a thing.\n\n    %s\n    """\n    return 1\n' % text
                 for i, text in enumerate(FLAGGED)}
        self.change(files)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for i, text in enumerate(FLAGGED):
            with self.subTest(text):
                self.assertHit(out, "d%d.py" % i, 4)

    def test_each_pattern_flags_a_one_line_docstring(self):
        self.base({"keep.py": "x = 1\n"})
        files = {"s%d.py" % i: 'def f():\n    """%s."""\n    return 1\n' % text for i, text in enumerate(FLAGGED)}
        self.change(files)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for i, text in enumerate(FLAGGED):
            with self.subTest(text):
                self.assertHit(out, "s%d.py" % i, 2)

    def test_docstring_kinds(self):
        self.base({"keep.py": "x = 1\n"})
        kinds = {
            "module.py": '"""Module thing.\n\nFixed in round 2.\n"""\nx = 1\n',
            "klass.py": 'class C:\n    """Thing.\n\n    Fixed in round 2.\n    """\n',
            "func.py": 'def f():\n    """Thing.\n\n    Fixed in round 2.\n    """\n',
            "afunc.py": 'async def f():\n    """Thing.\n\n    Fixed in round 2.\n    """\n',
            "method.py": 'class C:\n    def m(self):\n        """Thing.\n\n        Fixed in round 2.\n        """\n',
            "raw.py": 'def f():\n    r"""Thing.\n\n    Fixed in round 2.\n    """\n',
            "single.py": "def f():\n    '''Thing.\n\n    Fixed in round 2.\n    '''\n",
        }
        self.change(kinds)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for path, src in kinds.items():
            with self.subTest(path):
                self.assertHit(out, path, at(src, "round 2"))

    def test_flag_in_a_file_the_base_already_has(self):
        self.base({"pkg/mod.py": "import os\n\n\ndef f():\n    return os.sep\n"})
        self.change({"pkg/mod.py": "import os\n\n\ndef f():\n    # fixed in round 2\n    return os.sep\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "pkg/mod.py", 5)

    def test_output_names_file_line_and_matched_text(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"pkg/mod.py": "x = 1\ny = 2\n# fixed in round 2\nz = 3\n# MEASURED 40 ms\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("round 2", self.hit_line(out, "pkg/mod.py", 3) or "")
        self.assertIn("MEASURED", self.hit_line(out, "pkg/mod.py", 5) or "")
        self.assertNoHit(out, "pkg/mod.py", 1)
        self.assertNoHit(out, "pkg/mod.py", 4)

    def test_each_hit_row_carries_the_one_line_remedy(self):
        samples = ["fixed in round 2", "from PR #509", "reverted in 2ff288b3", "MEASURED 40 ms",
                   "since 2026-10-18", "owner ruling"]
        src = "".join("# %s\n" % t for t in samples) + 'def f():\n    """Does a thing.\n\n    %s\n    """\n' % samples[0]
        self.base({"keep.py": "x = 1\n"})
        self.change({"pkg/mod.py": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        lines = list(range(1, len(samples) + 1)) + [at(src, "    fixed in round 2")]
        for line in lines:
            with self.subTest(line=line):
                row = self.hit_line(out, "pkg/mod.py", line)
                self.assertIsNotNone(row, out)
                self.assertIn(REMEDY, row.lower())


class LineCounting(Case):
    """A character that only str.splitlines() breaks on, inside a string, must not move a line number."""

    @staticmethod
    def docstring_src(sep, narration):
        return 'S = "a%sb"\n\n\ndef f():\n    """Does a thing.\n\n    Returns one.\n%s    """\n    return S\n' % (
            sep, "    %s\n" % narration if narration else "")

    def test_added_docstring_line_after_a_non_break_in_a_string_is_flagged(self):
        files = {"n%d.py" % i: self.docstring_src(sep, None) for i, sep in enumerate(NON_BREAKS)}
        self.base(dict(files, **{"keep.py": "x = 1\n"}))
        changed = {"n%d.py" % i: self.docstring_src(sep, "Fixed in round 2.") for i, sep in enumerate(NON_BREAKS)}
        self.change(changed)
        rc, out = self.lint()
        for i, sep in enumerate(NON_BREAKS):
            with self.subTest(sep=repr(sep)):
                self.assertHit(out, "n%d.py" % i, at(changed["n%d.py" % i], "round 2"))
        self.assertEqual(rc, 1, out)

    def test_new_file_reports_the_ast_line_after_a_non_break_in_a_string(self):
        self.base({"keep.py": "x = 1\n"})
        files = {"f%d.py" % i: self.docstring_src(sep, "Fixed in round 2.") for i, sep in enumerate(NON_BREAKS)}
        self.change(files)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for i, sep in enumerate(NON_BREAKS):
            path, want = "f%d.py" % i, at(files["f%d.py" % i], "round 2")
            with self.subTest(sep=repr(sep)):
                self.assertHit(out, path, want)
                self.assertNoHit(out, path, want + 1)


class Ratchet(Case):
    OLD_COMMENT = "x = 1\n# fixed in round 2\ny = 2\n"
    OLD_DOC = 'def f():\n    """Does a thing.\n\n    Fixed in round 2.\n    """\n    return 1\n'

    def test_unchanged_old_lines_never_fail(self):
        self.base({"old.py": self.OLD_COMMENT + 'def g():\n    """Owner ruling applies."""\n', "doc.py": self.OLD_DOC})
        self.change({"new.py": "# a clean comment\nx = 1\n"})
        self.assertClean()

    def test_old_line_pushed_down_by_inserted_lines_never_fails(self):
        self.base({"old.py": self.OLD_COMMENT})
        self.change({"old.py": "import os\nimport sys\nimport re\n" + self.OLD_COMMENT})
        self.assertClean()

    def test_new_comment_beside_an_old_one_fails_only_the_new_line(self):
        self.base({"old.py": self.OLD_COMMENT})
        self.change({"old.py": self.OLD_COMMENT + "# owner ruling\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "old.py", 4)
        self.assertNoHit(out, "old.py", 2)

    def test_new_docstring_line_beside_an_old_one_fails_only_the_new_line(self):
        self.base({"doc.py": self.OLD_DOC})
        self.change({"doc.py": self.OLD_DOC.replace("    \"\"\"\n", "    Owner ruling applies.\n    \"\"\"\n")})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "doc.py", 5)
        self.assertNoHit(out, "doc.py", 4)

    def test_clean_line_added_inside_an_old_flagged_docstring_passes(self):
        self.base({"doc.py": self.OLD_DOC})
        self.change({"doc.py": self.OLD_DOC.replace("    \"\"\"\n", "\n    Returns one.\n    \"\"\"\n")})
        self.assertClean()

    def test_no_change_passes(self):
        self.base({"old.py": self.OLD_COMMENT})
        self.assertClean()

    def test_diff_that_only_deletes_passes(self):
        self.base({"gone.py": self.OLD_COMMENT, "trim.py": self.OLD_COMMENT + "z = 3\n"})
        self.change({"gone.py": None, "trim.py": "x = 1\ny = 2\nz = 3\n"})
        self.assertClean()

    def test_only_py_files_are_read(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({
            "notes.md": "Fixed in round 2. Owner ruling 2026-10-18.\n",
            "run.sh": "# fixed in round 2\n",
            "app.js": "// owner ruling 2026-10-18\n",
            "data.txt": "# MEASURED CORRECTED\n",
            "README": "# PR #509\n",
        })
        self.assertClean()

    def test_unreadable_base_never_reads_as_clean(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"new.py": "# a clean comment\n"})
        rc, out = self.lint("--base", "origin/no-such-branch")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("no-such-branch", out)


class Quiet(Case):
    def test_near_misses_pass_in_comments_and_docstrings(self):
        self.base({"keep.py": "x = 1\n"})
        files = {"c%d.py" % i: "x = 1\n# %s\ny = 2  # %s\n" % (text, text) for i, text in enumerate(CLEAN)}
        files.update({"d%d.py" % i: 'def f():\n    """Does a thing.\n\n    %s\n    """\n' % text
                      for i, text in enumerate(CLEAN)})
        self.change(files)
        self.assertClean()

    def test_same_words_in_string_literals_do_not_fail(self):
        src = '''\
A = "fixed in round 2"
B = 'Owner ruling dated 2026-10-18'
C = "see PR #509 and 2ff288b3"
D = ("MEASURED"
     "CORRECTED ADDED 2026")
E = f"{A} round 2 on 2026-10-18 # owner request"
F = b"round 2"
G = r"owner's ruling"
H = "a # round 2"
I = dict(note="review finding", other='it\\'s round 3')


def f(x="round 2"):
    assert x, "owner ruling"
    return x
'''
        self.base({"keep.py": "x = 1\n"})
        self.change({"strings.py": src})
        self.assertClean()

    def test_multi_line_string_that_is_not_a_docstring_does_not_fail(self):
        src = """\
import textwrap

SQL = '''
# not a comment: round 2
owner ruling
2026-10-18 don't
'''


def f():
    x = textwrap.dedent('''
        MEASURED
        # round 3
    ''')
    return x
"""
        self.base({"keep.py": "x = 1\n"})
        self.change({"multi.py": src})
        self.assertClean()

    def test_hash_inside_a_string_is_not_a_comment(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"hash.py": 's = "a # b"\nt = "// /* # round 2"\nu = \'#\'\nv = """#"""\n# fine\n'})
        self.assertClean()


class Scanner(Case):
    def test_real_comment_after_a_string_that_holds_openers_is_flagged(self):
        src = 's = "a # b"  # fixed in round 2\nt = "// /* #"  # CORRECTED\nu = "it\'s"  # owner ruling\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"after.py": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for line in (1, 2, 3):
            self.assertHit(out, "after.py", line)

    def test_flagged_comment_after_a_multi_line_string_reports_its_own_line(self):
        src = "SQL = '''\n# not a comment\ndon't\n'''\nx = 1  # fine\n# fixed in round 2\ny = 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"after.py": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "after.py", at(src, "# fixed in round 2"))
        for line in (1, 2, 3, 4, 5, 7):
            self.assertNoHit(out, "after.py", line)

    def test_clean_comment_after_a_multi_line_string_passes(self):
        src = "SQL = '''\n# not a comment\ndon't\n'''\nx = 1  # fine\n# a clean comment\ny = 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"after.py": src})
        self.assertClean()

    def test_lone_quote_in_a_comment_parses(self):
        src = "# don't\nx = \"round 2\"\n# say \"hi\ny = 'owner ruling'\nz = 1  # it's fine\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"quote.py": src})
        self.assertClean()

    def test_flagged_comment_after_a_lone_quote_is_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"single.py": "# don't\n# fixed in round 2\nx = 1\n",
                     "double.py": "# say \"hi\n# fixed in round 2\nx = 1\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "single.py", 2)
        self.assertHit(out, "double.py", 2)

    def test_lone_quote_in_a_docstring_parses(self):
        flagged = 'def f():\n    """Don\'t do it.\n\n    Fixed in round 2.\n    """\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"flagged.py": flagged, "clean.py": 'def g():\n    """Don\'t."""\n'})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "flagged.py", at(flagged, "round 2"))
        self.assertNoHit(out, "clean.py", 2)


if __name__ == "__main__":
    unittest.main()
