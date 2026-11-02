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
- `--exclude PREFIX` skips the files under that path prefix. Repeat it for each prefix.
- JS, TS, Astro and Swift comments follow the same rule. The same words in their strings or template text never fail.
- The check is one file. The suite copies only that file into the fixture repo, so the check finds
  the repo from its working directory or from its own location, and both give the fixture repo.
"""
import json
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
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
MODULE = os.path.join(HERE, "check_comment_narration.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
STANDARD = os.path.join(HERE, "..", "actions", "code-check", "standard.json")
with open(STANDARD, encoding="utf-8") as f:
    TS_PIN = json.load(f)["tools"]["typescript"]
NEEDS_TSC = unittest.skipUnless(shutil.which("tsc") or os.environ.get("CI"),
                                "tsc not on PATH; npm ci --ignore-scripts --prefix actions/code-check/tools (CI does)")

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


def lines_of(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


class Case(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_comment_narration.py")
        self.tree = tempfile.mkdtemp(prefix="cnl_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.tree, True)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks", "actions/code-check")  # the imports and the standard
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_comment_narration.py"))
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args):
        subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                        "-c", "core.autocrlf=false", *args],
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

    def lint(self, *args, path_tools=False, env=None):
        args = args or ("--base", "origin/main")
        run_env = dict(GIT_ENV, **(env or {}))
        run_env.pop("CODE_CHECK_TOOLS", None)
        if path_tools:
            run_env["CODE_CHECK_TOOLS"] = "path"
        r = subprocess.run([sys.executable, os.path.join(self.tree, "lint", "check_comment_narration.py"), *args],
                           cwd=self.tree, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=run_env)
        return r.returncode, r.stdout + r.stderr

    def fake_tool(self, name, body):
        """A stub command first on PATH that runs body, with @LOG@ as its log file. Returns (env, log path)."""
        folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, folder, True)
        log = os.path.join(folder, name + ".log")
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\n" + body.replace("@LOG@", log))
        os.chmod(os.path.join(folder, name), 0o755)
        return {"PATH": os.pathsep.join([folder, GIT_ENV["PATH"]])}, log

    def path_with(self, *tools):
        """A PATH holding only the named tools, each linked from this machine. Returns {"PATH": folder}."""
        folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, folder, True)
        for tool in tools:
            os.symlink(shutil.which(tool, path=GIT_ENV["PATH"]), os.path.join(folder, tool))
        return {"PATH": folder}

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

    def test_files_outside_the_comment_languages_are_not_read(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({
            "a.rb": "# fixed in round 2\n",
            "notes.txt": "# owner ruling 2026-10-18\n",
            "notes.md": "Fixed in round 2. Owner ruling 2026-10-18.\n",
            "run.sh": "# fixed in round 2\n",
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


class Exclude(Case):
    def test_exclude_prefix_drops_a_narrating_line_under_it_and_not_elsewhere(self):
        self.base({"vendor/x.py": "def f():\n    return 1\n", "pkg/mod.py": "def g():\n    return 2\n"})
        self.change({"vendor/x.py": "def f():\n    # fixed in round 2\n    return 1\n",
                     "pkg/mod.py": "def g():\n    # fixed in round 2\n    return 2\n"})
        rc, out = self.lint("--base", "origin/main", "--exclude", "vendor/")
        self.assertEqual(rc, 1, out)
        self.assertNoHit(out, "vendor/x.py", 2)
        self.assertHit(out, "pkg/mod.py", 2)
        self.assertNotIn("Traceback", out)

    def test_exclude_matches_a_path_prefix_not_a_substring(self):
        self.base({"pkg/vendor/y.py": "def f():\n    return 1\n"})
        self.change({"pkg/vendor/y.py": "def f():\n    # fixed in round 2\n    return 1\n"})
        rc, out = self.lint("--base", "origin/main", "--exclude", "vendor/")
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "pkg/vendor/y.py", 2)


class Scripts(Case):
    def test_round_comment_in_an_extensionless_python_script_is_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"bin/tool": "#!/usr/bin/env python3\n# fixed in round 2\nprint(1)\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "bin/tool", 2)

    def test_round_comment_in_a_pyi_stub_is_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"stub.pyi": "# fixed in round 2\ndef f(x: int) -> int: ...\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "stub.pyi", 1)

    def test_round_comment_in_an_extensionless_file_without_a_shebang_is_not_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"notes/log": "# fixed in round 2\n"})
        self.assertClean()


@NEEDS_TSC
class JsTsScan(Case):
    def test_comment_openers_in_strings_do_not_hide_the_real_comment_after_them(self):
        src = 'const a = "//";\nconst b = "fixed on 2026-10-28" + \'/*\';\nconst c = "#"; // fixed in round 2\n'
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.ts": src})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertNoHit(out, "app.ts", 1)
        self.assertNoHit(out, "app.ts", 2)
        self.assertHit(out, "app.ts", 3)

    def test_template_literal_text_is_not_a_comment_and_a_comment_after_it_is_flagged(self):
        src = "const s = `\n// fixed on 2026-10-28\n`;\n// fixed in round 2\nexport default s;\n"
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"util.ts": src})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertNoHit(out, "util.ts", 2)
        self.assertHit(out, "util.ts", at(src, "round 2"))

    def test_lone_quote_in_text_does_not_hide_the_comment_after_it(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.js": "// don't\n// fixed in round 2\nconst x = 1;\n",
                     "view.tsx": "export const p = <p>Don't</p>;\n// fixed in round 2\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "app.js", 2)
        self.assertHit(out, "view.tsx", 2)

    def test_strings_and_template_text_holding_the_words_are_clean(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.js": 'const a = "// fixed in round 2";\nconst b = \'/*\';\n',
                     "util.ts": "const s = `\n// fixed on 2026-10-28\n`;\n",
                     "view.tsx": "export const p = <p>Don't fixed on 2026-10-28</p>;\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_jsx_expression_comment_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"view.tsx": "export const p = <p>{/* fixed on 2026-10-28 */}</p>;\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "view.tsx", 1)

    def test_jsdoc_comment_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"util.ts": "/**\n * owner ruling 2026-10-18\n */\nexport const x = 1;\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "util.ts", 2)

    def test_crlf_line_endings_keep_the_line_numbers(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"crlf.ts": "const a = 1;\r\n// fixed in round 2\r\nexport {a};\r\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "crlf.ts", 2)

    def test_cts_and_mts_files_are_scanned(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"a.cts": "// fixed in round 2\nexport {};\n", "b.mts": "// fixed in round 2\nexport {};\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "a.cts", 1)
        self.assertHit(out, "b.mts", 1)


@NEEDS_TSC
class AstroScan(Case):
    def test_narrating_comment_in_frontmatter_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "---\n// fixed on 2026-10-28\nconst n: number = 2;\n---\n<p>{n}</p>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "page.astro", 2)

    def test_narrating_comment_in_script_block_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "<p>x</p>\n<script>\n  // fixed in round 2\n  console.log(1);\n</script>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "page.astro", 3)

    def test_narrating_html_comment_in_template_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "<!-- fixed in round 2 -->\n<p>x</p>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "page.astro", 1)

    def test_narrating_jsx_comment_in_template_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "<p>x</p>\n{/* fixed on 2026-10-28 */}\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "page.astro", 2)

    def test_same_words_in_template_text_are_clean(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "---\nconst n: number = 2;\n---\n<p>fixed in round 2 on 2026-10-28</p>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 0, out)

    def test_comment_inside_a_template_expression_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "<ul>{items.map(i => /* fixed on 2026-10-28 */ i)}</ul>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "page.astro", 1)

    def test_narrating_words_in_style_are_not_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "<p>x</p>\n<style>\n  /* fixed in round 2 */\n  p { color: red; }\n</style>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 0, out)

    def test_script_comment_without_frontmatter_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": "<script>\n  // fixed in round 2\n</script>\n<p>x</p>\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "page.astro", 2)


class SwiftScan(Case):
    def test_comment_openers_in_strings_do_not_hide_the_real_comment_after_them(self):
        src = 'let a = "//"\nlet b = "/*"\nlet c = 1 // fixed in round 2\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"Thing.swift": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertNoHit(out, "Thing.swift", 1)
        self.assertNoHit(out, "Thing.swift", 2)
        self.assertHit(out, "Thing.swift", 3)

    def test_multi_line_string_holding_a_comment_is_text_and_a_comment_after_it_is_flagged(self):
        src = 'let s = """\n// fixed on 2026-10-28\n"""\nlet t = 1 // fixed in round 2\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"Thing.swift": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertNoHit(out, "Thing.swift", 2)
        self.assertHit(out, "Thing.swift", at(src, "round 2"))

    def test_raw_string_with_a_quote_does_not_hide_the_comment_after_it(self):
        src = 'let r = #"a"b"#; // fixed in round 2\nlet q = #"// fixed on 2026-10-28"#\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"Thing.swift": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "Thing.swift", 1)
        self.assertNoHit(out, "Thing.swift", 2)

    def test_nested_block_comment_keeps_a_narrating_line_inside_it(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Nest.swift": "/* outer\n/* inner */\nfixed in round 2\n*/\nlet x = 1\n",
                     "Nest2.swift": "/* /* */ fixed on 2026-10-28 */\nlet y = 2\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "Nest.swift", 3)
        self.assertHit(out, "Nest2.swift", 1)

    def test_lone_quote_in_a_line_comment_does_not_hide_the_next_comment(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Quote.swift": "// don't\n// fixed in round 2\nlet x = 1\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "Quote.swift", 2)

    def test_comment_openers_inside_an_interpolated_string_are_text(self):
        src = r'let s = "\(f("// fixed on 2026-10-28"))"' + "\n" + "let t = 1 // fixed in round 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"Interp.swift": src})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertNoHit(out, "Interp.swift", 1)
        self.assertHit(out, "Interp.swift", 2)

    def test_doc_comment_line_is_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Doc.swift": "/// fixed in round 2\nfunc f() {}\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "Doc.swift", 1)

    def test_strings_with_slashes_and_no_comment_are_clean(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Urls.swift": 'let u = "http://x"\nlet v = "/* fixed on 2026-10-28 */"\n'})
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)


class Degraded(Case):
    def test_node_failure_still_prints_python_and_swift_hits_and_exits_3(self):
        env, _ = self.fake_tool("tsc", "echo bogus >&2\nexit 3\n")
        self.base({"keep.py": "x = 1\n"})
        self.change({"bad.py": "x = 1  # fixed in round 2\n", "Thing.swift": "let a = 1 // fixed on 2026-10-28\n",
                     "app.ts": "const a = 1;\n"})
        rc, out = self.lint(path_tools=True, env=env)
        self.assertEqual(rc, 3, out)
        self.assertHit(out, "bad.py", 1)
        self.assertHit(out, "Thing.swift", 1)

    def test_unreadable_python_file_does_not_hide_a_later_hit(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"a.py": "def f(:\n", "b.py": "x = 1  # fixed in round 2\n"})
        rc, out = self.lint()
        self.assertEqual(rc, 2, out)
        self.assertHit(out, "b.py", 1)


class NodeCost(Case):
    def test_one_node_process_covers_every_js_ts_and_astro_file(self):
        env, log = self.fake_tool("node", 'echo invoked >> "@LOG@"\n')
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.js": "const a = 1;\n", "util.ts": "const b = 1;\n", "page.astro": "<p>x</p>\n"})
        self.lint(path_tools=True, env=env)
        self.assertEqual(len(lines_of(log)), 1)

    def test_a_python_only_diff_starts_no_node_process(self):
        env, log = self.fake_tool("node", 'echo invoked >> "@LOG@"\n')
        self.base({"keep.py": "x = 1\n"})
        self.change({"a.py": "x = 2  # plain\n"})
        rc, out = self.lint(path_tools=True, env=env)
        self.assertEqual(rc, 0, out)
        self.assertEqual(lines_of(log), [])


class NodeTool(Case):
    def test_no_npx_on_path_exits_3_and_still_prints_the_python_hit(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"bad.py": "x = 1  # fixed in round 2\n", "app.js": "const a = 1;\n// fixed on 2026-10-28\n"})
        rc, out = self.lint(env=self.path_with("git"))
        self.assertEqual(rc, 3, out)
        self.assertIn("npx", out)
        self.assertHit(out, "bad.py", 1)


class NpxPath(Case):
    def test_comment_scan_starts_through_npx_with_the_pinned_typescript(self):
        env, log = self.fake_tool("npx", 'printf "%s\\n" "$@" >> "@LOG@"\nexit 1\n')
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.js": "const a = 1;\n// fixed in round 2\n"})
        rc, out = self.lint(env=env)
        self.assertEqual(rc, 3, out)
        argv = lines_of(log)
        self.assertIn("--yes", argv, out)
        self.assertIn("typescript@" + TS_PIN, argv, out)
        self.assertIn("node", argv, out)
        self.assertTrue(any(a.endswith("comment_scan.mjs") for a in argv), out)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
