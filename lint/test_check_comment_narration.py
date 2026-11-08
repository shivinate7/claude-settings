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
- A comment that states a run's colour or result on a head, on main or on the base is history.
  It fails under the `history phrase` pattern. A colour phrase after when, if, unless, until, while or once in the
  same clause is a condition and stays clean.
- A run of 200 slashes before a date ends within the scan bound, and the date stays flagged.
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

# Run-state history: a comment that states a run's colour or result on a head, on main or on the base is history,
# whatever verb or label comes before it. A colour phrase after when, if, unless, until, while or once in the same
# clause is a condition and stays clean (see CLEAN). A condition word in an earlier clause, past a `;`, `:`, `.`, `,`,
# `!` or `?`, does not exempt a later run phrase. The `history phrase` pattern flags each hit. The list also joins
# FLAGGED, so every flagged test runs it.
RUN_STATE = [
    "RED on the head this branch starts from: the edit tool and the PATCH route are not judged",
    "PINS, green on the head this branch starts from: prose after the CI line is refused",
    "Red on main: main refuses every workflow edit by path, so each allow below fails",
    "Both are green on main: they pin the cost of the new check",
    "red on main", "green on the base", "was green before", "went red on the head",
    "passed on main before this change",
    "fails on main", "passes on the head", "This case passes on main.", "RED before this change",
    "(green before the fix)", "the run is red on main", "Control, green on main:",
    "if X; it passed on main", "when ready: this passed on main", "if cold, skip. The run is red on main",
    "Once the fix landed, the tests went green on main", "When it ran, it was red on main",
]

# Date text that stays flagged: a date with no ruling word, with or without a time, and an owner word with a date but
# no time. A ruling cite is an owner word that opens it, then a date, a 24-hour time and a zone. A word before owner,
# or a word after the time that is not a zone, stays flagged. The `date` pattern flags each hit. The list also joins
# FLAGGED, so every flagged test runs it.
DATE_CONTROLS = ["Fixed on 2026-11-01.", "Changed 2026-11-01 16:30 CST.", "Owner, 2026-11-01",
                 "Changed by the owner, 2026-11-01 16:30 CST.", "Fixed after owner, 2026-11-01 16:30 CST.",
                 "Owner, 2026-11-01 16:30 OLD: returns None"]

# Text the check must flag, in a comment or in a docstring line.
FLAGGED = [
    "fixed in round 2", "Round3 of changes", "after review round", "a review finding", "review points",
    "from PR #509", "PR 1234", "PR#4567",
    "reverted in 2ff288b3", "see 03d62e85", "added by 4a1b2c3", "cut at 9f8e7d6c5b",
    "MEASURED 40 ms", "CORRECTED from the old value", "ADDED 2026 for the batch",
    "since 2026-10-18", "dated 2025-01-03",
    "owner ruling", "Owner's order", "owner request", "Owner ask",
    "Previously this returned None", "previously it was a list", "Changed from the old behaviour",
    "changed from a dict to a list", "Added after review by billing", "added after review",
    "formerly returned None", "the old behaviour dropped rows",
    "round 2 of 3", "in round 2", "fixed 2026-10-30",
    "Fixed from 2026-10-30 onward", "Changed from 2024-01-01 to the new rule",
    "Fixed in round 2 places where the rows were summed", "Previously, this returned None",
    "Previously used a dict", "Added after code review", "Added after review of the PR feedback",
    "Changed from returning None to raising", "Changed from the previous default to 5",
    "changed from the old file layout to the new one", "changed from the old state machine to a table",
    "changed from the old hash function to sha256", "changed from the old base class to a mixin",
] + RUN_STATE + DATE_CONTROLS

# Near misses. No pattern may flag any of them.
CLEAN = [
    "round the total up to 2 places", "surround 2 items", "a round-trip to the server",
    "measured in ms, corrected for drift", "token deadbeef is all letters", "id 12345678 is all digits",
    "effaced", "see PR #12 for nothing", "ADDED to the list", "the owner of this file", "the owner's name",
    "review the code first", "ask the reviewer", "the year 2026",
    "round 2 decimals so the total matches the invoice", "Tax rule effective 2024-07-01",
    "rates valid until 2027-01-01", "skip previously seen keys", "cache the previously computed hash",
    "changed files only", "the user changed the value", "added to the queue after review of the input",
    "round 3 places", "used to compute the total",
    "Effective date 2024-07-01 (per state rule)", "Effective: 2024-07-01", "Tax rule effective on 2024-07-01",
    "Expires 2027-01-01", "Keep the old behaviour for legacy accounts so existing invoices still match",
    "Skip when previously it was seen in this loop",
    "Keep the old behaviour expected by legacy clients", "Keep the old behaviour required by billing",
    "Preserve the old behaviour relied on by v1 callers",
    "These run against a green head.", "the merge cases run on a green head, so merge-checks pass",
    "refuses a head that is not green", 'returns "red" when any job fails',
    "the red/green colour of the badge", "a green check proves only its platform",
    "the gate goes red when any job fails",
    # A colour phrase after when, if, unless, until, while, once or only ... when is a condition, so it stays clean.
    "only merge when green on the head", "if red on main, page the on-call",
    "None when it is green on the head", "until it is green on the base",
    "unless red on main, skip", "once green on the head, merge", "while it is red on the base, wait",
    # A pass or fail verb that names code, not a run, is not history.
    "Calling this fails on the main thread", "pass on the base class to the parent",
    "passes on the head of the list", "fails on main() when argv is empty",
    "has been passed before the loop", "was passed before the loop",
    "true if the hash changed from the previous snapshot", "true when the file changed from the previous run",
    "changed from the old snapshot", "changed from the original snapshot",
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
        self.checker_tree(self.tree)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def checker_tree(self, root, files=None):
        """Place the check at root/lint with the folders it imports, and write the given files. Returns the check's path."""
        tracked_tree.copy_tracked(root, "lint", "hooks", "actions/code-check")  # the imports and the standard
        shutil.copyfile(MODULE, os.path.join(root, "lint", "check_comment_narration.py"))
        for rel, text in (files or {}).items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        return os.path.join(root, "lint", "check_comment_narration.py")

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

    def lint(self, *args, path_tools=False, env=None, checker_root=None, timeout=None):
        args = args or ("--base", "origin/main")
        run_env = dict(GIT_ENV, **(env or {}))
        run_env.pop("CODE_CHECK_TOOLS", None)
        if path_tools:
            run_env["CODE_CHECK_TOOLS"] = "path"
        script = os.path.join(checker_root or self.tree, "lint", "check_comment_narration.py")
        r = subprocess.run([sys.executable, script, *args],
                           cwd=self.tree, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=run_env, timeout=timeout)
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

    def scan(self, files, extra_base=None):
        self.base({"keep.py": "x = 1\n", **(extra_base or {})})
        self.change(files)
        return self.lint()


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

    def test_run_state_hits_name_the_history_phrase_pattern(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"h%d.py" % i: "x = 1\n# %s\ny = 2\n" % text for i, text in enumerate(RUN_STATE)})
        _, out = self.lint()
        for i, text in enumerate(RUN_STATE):
            with self.subTest(text):
                self.assertHit(out, "h%d.py" % i, 2)
                self.assertIn("history phrase:", self.hit_line(out, "h%d.py" % i, 2))

    def test_date_controls_hit_the_date_pattern(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"d%d.py" % i: "x = 1\n# %s\ny = 2\n" % text for i, text in enumerate(DATE_CONTROLS)})
        _, out = self.lint()
        for i, text in enumerate(DATE_CONTROLS):
            with self.subTest(text):
                self.assertHit(out, "d%d.py" % i, 2)
                self.assertIn("date:", self.hit_line(out, "d%d.py" % i, 2))

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
            "run.zsh": "# fixed in round 2\n",
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
        rc, out = self.lint()
        self.assertIn(rc, (0, 1), out)
        self.assertNotIn("UNKNOWN", out)
        self.assertNotIn("COULD NOT RUN", out)
        self.assertNotIn("Traceback", out)
        for i, text in enumerate(CLEAN):
            with self.subTest(text):
                self.assertNoHit(out, "c%d.py" % i, 2)
                self.assertNoHit(out, "c%d.py" % i, 3)
                self.assertNoHit(out, "d%d.py" % i, 4)
        self.assertEqual(rc, 0, out)

    def test_ruling_cite_with_a_time_in_a_docstring_passes(self):
        src = ('def f():\n    """Does a thing.\n\n    Owner, 2026-11-01 16:30 CST: a re-pointed case.\n    """\n'
               '    # fixed in round 2\n    return 1\n')
        rc, out = self.scan({"cite.py": src})
        self.assertHit(out, "cite.py", at(src, "fixed in round 2"))
        self.assertNoHit(out, "cite.py", at(src, "re-pointed case"))

    def test_ruling_cite_with_a_time_in_a_comment_passes(self):
        src = "x = 1\n# (owner, 2026-10-30 16:20 CDT)\n# fixed in round 2\ny = 2\n"
        rc, out = self.scan({"cite.py": src})
        self.assertHit(out, "cite.py", at(src, "fixed in round 2"))
        self.assertNoHit(out, "cite.py", at(src, "16:20 CDT"))

    def test_ruling_cite_with_a_one_digit_hour_passes(self):
        src = "x = 1\n# Owner, 2026-11-01 9:05 CST\n# fixed in round 2\ny = 2\n"
        rc, out = self.scan({"cite.py": src})
        self.assertHit(out, "cite.py", at(src, "fixed in round 2"))
        self.assertNoHit(out, "cite.py", at(src, "9:05 CST"))

    def test_ruling_cite_with_a_lowercase_zone_passes(self):
        zones = ["cst", "cdt", "ct", "est", "edt", "et", "mst", "mdt", "mt", "pst", "pdt", "pt", "utc", "gmt"]
        files = {"z%d.py" % i: "x = 1\n# owner, 2026-10-30 16:20 %s\n# fixed in round 2\ny = 2\n" % zone
                 for i, zone in enumerate(zones)}
        _, out = self.scan(files)
        unread = [zone for i, zone in enumerate(zones) if self.hit_line(out, "z%d.py" % i, 3) is None]
        self.assertEqual(unread, [], "the scan did not read each control line:\n" + out)
        flagged = [zone for i, zone in enumerate(zones) if self.hit_line(out, "z%d.py" % i, 2) is not None]
        self.assertEqual(flagged, [], "a ruling cite with a lowercase zone is flagged as a date:\n" + out)

    def test_lowercase_zone_on_a_dated_line_that_is_not_a_cite_stays_flagged(self):
        texts = ["Changed by the owner, 2026-10-30 16:20 cdt", "Fixed after owner, 2026-10-30 16:20 cdt",
                 "Changed 2026-10-30 16:20 cdt"]
        files = {"n%d.py" % i: "x = 1\n# %s\ny = 2\n" % text for i, text in enumerate(texts)}
        _, out = self.scan(files)
        unflagged = [text for i, text in enumerate(texts)
                     if "date:" not in (self.hit_line(out, "n%d.py" % i, 2) or "")]
        self.assertEqual(unflagged, [], "a dated line that is not a cite is not flagged as a date:\n" + out)

    def test_long_slash_run_before_a_date_is_flagged_within_the_bound(self):
        # A run of slashes is not a cite, so the date stays flagged. The timeout keeps a stalled scan from hanging.
        run = "/" * 200 + " Section 2026-11-08"
        files = {"slash.py": "x = 1\n# %s\ny = 2\n" % run, "Slash.swift": "let x = 1\n// %s\n" % run}
        self.base({"keep.py": "x = 1\n"})
        self.change(files)
        try:
            rc, out = self.lint(timeout=5)
        except subprocess.TimeoutExpired:
            self.fail("the scan did not end within 5 s on a 200-slash comment before a date")
        self.assertEqual(rc, 1, out)
        for path in ("slash.py", "Slash.swift"):
            row = self.hit_line(out, path, 2)
            self.assertIsNotNone(row, "no hit at %s:2 in:\n%s" % (path, out))
            self.assertIn("date: 2026-11-08", row, out)

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

    def test_run_state_words_in_string_literals_do_not_fail(self):
        src = '''\
A = "red on main"
B = 'green on the base'
C = "# red on main"
D = '// green on the head'
E = "[new allow: red on main, passes on d7fb2f1]"
F = "passed on main before this change"
G = r"was green before"
H = f"{A} went red on the head"
I = dict(note="red on main")
J = """
# red on main
was green before
"""


def test_red_on_main_denies():
    sh("... denies (red on main too)", ...)
    assert I, "was green before"
'''
        self.base({"keep.py": "x = 1\n"})
        self.change({"run_state.py": src})
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

    def test_run_state_comment_after_strings_that_hold_openers_is_flagged(self):
        src = ('a = "# red on main"  # was green before\n'
               "b = '// green on the head'  # went red on the head\n"
               'c = "x"  # fine\n')
        self.base({"keep.py": "x = 1\n"})
        self.change({"after.py": src})
        rc, out = self.lint()
        self.assertHit(out, "after.py", 1)
        self.assertHit(out, "after.py", 2)
        self.assertNoHit(out, "after.py", 3)
        self.assertEqual(rc, 1, out)

    def test_run_state_comment_after_a_multi_line_string_reports_its_own_line(self):
        src = "SQL = '''\n# red on main\nwent red on the head\n'''\nx = 1  # fine\n# was green before\ny = 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"after.py": src})
        rc, out = self.lint()
        self.assertHit(out, "after.py", at(src, "# was green before"))
        for line in (1, 2, 3, 4, 5, 7):
            self.assertNoHit(out, "after.py", line)
        self.assertEqual(rc, 1, out)

    def test_run_state_comment_after_a_lone_quote_is_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"single.py": "# don't\n# red on main\nx = 1\n",
                     "double.py": '# say "hi\n# was green before\nx = 1\n'})
        rc, out = self.lint()
        self.assertHit(out, "single.py", 2)
        self.assertHit(out, "double.py", 2)
        self.assertEqual(rc, 1, out)


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

    def test_run_state_comment_is_flagged(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.ts": "const a = 1;\n// red on main\nexport {a};\n"})
        rc, out = self.lint(path_tools=True)
        self.assertHit(out, "app.ts", 2)
        self.assertEqual(rc, 1, out)

    def test_run_state_comment_openers_in_strings_do_not_hide_the_real_comment(self):
        src = 'const a = "# red on main";\nconst b = \'// green on the head\';\nconst c = 1; // was green before\n'
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.ts": src})
        rc, out = self.lint(path_tools=True)
        self.assertNoHit(out, "app.ts", 1)
        self.assertNoHit(out, "app.ts", 2)
        self.assertHit(out, "app.ts", 3)
        self.assertEqual(rc, 1, out)

    def test_run_state_template_literal_text_is_not_a_comment(self):
        src = "const s = `\n// red on main\nwent red on the head\n`;\n// was green before\nexport default s;\n"
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"util.ts": src})
        rc, out = self.lint(path_tools=True)
        self.assertNoHit(out, "util.ts", 2)
        self.assertNoHit(out, "util.ts", 3)
        self.assertHit(out, "util.ts", at(src, "was green before"))
        self.assertEqual(rc, 1, out)

    def test_run_state_lone_quote_in_jsx_text_does_not_hide_the_comment_after_it(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.js": "// don't\n// was green before\nconst x = 1;\n",
                     "view.tsx": "export const p = <p>Don't</p>;\n// red on main\n"})
        rc, out = self.lint(path_tools=True)
        self.assertHit(out, "app.js", 2)
        self.assertHit(out, "view.tsx", 2)
        self.assertEqual(rc, 1, out)

    def test_run_state_words_in_strings_and_template_text_are_clean(self):
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"app.js": 'const a = "# red on main";\nconst b = \'/* green on the head */\';\n'
                               "// These run against a green head.\n",
                     "util.ts": "const s = `\n// red on main\n`;\n",
                     "view.tsx": "export const p = <p>Don't was green before</p>;\n"})
        rc, out = self.lint(path_tools=True)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_ruling_cite_after_a_triple_slash_opener_in_ts_passes(self):
        src = ("/// owner, 2026-10-30 16:20 CDT\nexport const x = 1;\n"
               "// owner, 2026-10-30 16:20 CDT\n// fixed in round 2\n")
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"util.ts": src})
        rc, out = self.lint(path_tools=True)
        self.assertHit(out, "util.ts", 4)
        self.assertNoHit(out, "util.ts", 3)
        self.assertIsNone(self.hit_line(out, "util.ts", 1),
                          "a ruling cite after /// in a TS file is flagged as a date:\n" + out)


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

    def test_ruling_cite_in_an_html_comment_passes(self):
        src = ("<!-- owner, 2026-10-30 16:20 CDT -->\n<p>x</p>\n<!-- (owner, 2026-10-30 16:20 CDT) -->\n"
               "<!-- fixed in round 2 -->\n")
        self.base({"keep.js": "const k = 1;\n"})
        self.change({"page.astro": src})
        rc, out = self.lint(path_tools=True)
        self.assertHit(out, "page.astro", 4)
        self.assertNoHit(out, "page.astro", 3)
        self.assertIsNone(self.hit_line(out, "page.astro", 1),
                          "a ruling cite in an HTML comment is flagged as a date:\n" + out)


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

    def test_run_state_line_comment_is_flagged(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Thing.swift": "let c = 1 // green on the base\n"})
        rc, out = self.lint()
        self.assertHit(out, "Thing.swift", 1)
        self.assertEqual(rc, 1, out)

    def test_run_state_comment_openers_in_strings_do_not_hide_the_comment_after_them(self):
        src = 'let a = "// red on main"\nlet b = "/* green on the head */"\nlet c = 1 // was green before\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"Thing.swift": src})
        rc, out = self.lint()
        self.assertNoHit(out, "Thing.swift", 1)
        self.assertNoHit(out, "Thing.swift", 2)
        self.assertHit(out, "Thing.swift", 3)
        self.assertEqual(rc, 1, out)

    def test_run_state_multi_line_string_holding_a_comment_is_text(self):
        src = 'let s = """\n// red on main\nwent red on the head\n"""\nlet t = 1 // was green before\n'
        self.base({"keep.py": "x = 1\n"})
        self.change({"Thing.swift": src})
        rc, out = self.lint()
        self.assertNoHit(out, "Thing.swift", 2)
        self.assertNoHit(out, "Thing.swift", 3)
        self.assertHit(out, "Thing.swift", at(src, "was green before"))
        self.assertEqual(rc, 1, out)

    def test_run_state_lone_quote_in_a_line_comment_does_not_hide_the_next_comment(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Quote.swift": "// don't\n// red on main\nlet x = 1\n"})
        rc, out = self.lint()
        self.assertHit(out, "Quote.swift", 2)
        self.assertEqual(rc, 1, out)

    def test_run_state_strings_with_slashes_and_no_comment_are_clean(self):
        self.base({"keep.py": "x = 1\n"})
        self.change({"Urls.swift": 'let u = "http://x red on main"\nlet v = "/* green on the base */"\n'})
        self.assertClean()

    # The reader keeps the opener in the comment text, so the check reads the cite after it.
    def test_ruling_cite_after_a_triple_slash_opener_passes(self):
        src = "/// owner, 2026-10-30 16:20 CDT\nfunc f() {}\n// owner, 2026-10-30 16:20 CDT\n// fixed in round 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"Doc.swift": src})
        rc, out = self.lint()
        self.assertHit(out, "Doc.swift", 4)
        self.assertNoHit(out, "Doc.swift", 3)
        self.assertIsNone(self.hit_line(out, "Doc.swift", 1), "a ruling cite after /// is flagged as a date:\n" + out)

    def test_ruling_cite_after_a_bang_opener_passes(self):
        src = "//! owner, 2026-10-30 16:20 CDT\nlet x = 1\n// owner, 2026-10-30 16:20 CDT\n// fixed in round 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"Inner.swift": src})
        rc, out = self.lint()
        self.assertHit(out, "Inner.swift", 4)
        self.assertNoHit(out, "Inner.swift", 3)
        self.assertIsNone(self.hit_line(out, "Inner.swift", 1),
                          "a ruling cite after //! is flagged as a date:\n" + out)

    def test_parenthesised_ruling_cite_after_a_doc_opener_stays_clean(self):
        src = "/// (owner, 2026-10-30 16:20 CDT)\n//! (owner, 2026-10-30 16:20 CDT)\n// fixed in round 2\n"
        self.base({"keep.py": "x = 1\n"})
        self.change({"Doc.swift": src})
        rc, out = self.lint()
        self.assertHit(out, "Doc.swift", 3)
        self.assertNoHit(out, "Doc.swift", 1)
        self.assertNoHit(out, "Doc.swift", 2)

    def test_dated_line_after_a_doc_opener_without_a_cite_stays_flagged(self):
        src = ("/// Changed by the owner, 2026-10-30 16:20 CDT\n//! fixed on 2026-10-30 16:20 CDT\n"
               "// owner, 2026-10-30 16:20 CDT\n// fixed in round 2\n")
        self.base({"keep.py": "x = 1\n"})
        self.change({"Doc.swift": src})
        rc, out = self.lint()
        self.assertHit(out, "Doc.swift", 4)
        self.assertNoHit(out, "Doc.swift", 3)
        rows = [self.hit_line(out, "Doc.swift", n) for n in (1, 2)]
        self.assertTrue(all(row and "date:" in row for row in rows),
                        "a dated line with no cite after a doc opener is not flagged as a date:\n" + out)


class ShellScan(Case):
    """Shell comments: a `#` inside quotes, after an escape, in an expansion, in arithmetic or in a heredoc body is text."""

    def assertReadsClean(self, src):
        """The construct reads with no Unread, so the file exits 0."""
        rc, out = self.scan({"x.sh": src})
        self.assertEqual(rc, 0, out)

    def assertLaterCommentFlagged(self, src):
        """The construct reads, and a comment on the line after it is still flagged."""
        rc, out = self.scan({"x.sh": src + "# fixed in round 2\n"})
        self.assertEqual(rc, 1, out)
        self.assertHit(out, "x.sh", src.count("\n") + 1)

    def test_full_line_comment_is_flagged(self):
        rc, out = self.scan({"x.sh": "# fixed in round 2\necho hi\n"})
        self.assertHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_trailing_comment_after_a_command_is_flagged(self):
        rc, out = self.scan({"x.sh": "cmd  # fixed in round 2\n"})
        self.assertHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_incident_text_in_hooks_is_flagged(self):
        rc, out = self.scan({"hooks/x.sh": "# (incident 2026-11-07, /base_run.txt)\n"})
        self.assertHit(out, "hooks/x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_ruling_cite_with_a_time_in_a_shell_comment_passes(self):
        rc, out = self.scan({"x.sh": "# (owner, 2026-10-30 16:20 CDT)\n# fixed in round 2\necho hi\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)

    def test_extensionless_sh_shebang_script_is_flagged(self):
        rc, out = self.scan({"bin/run-sh": "#!/bin/sh\n# fixed in round 2\n"})
        self.assertHit(out, "bin/run-sh", 2)
        self.assertEqual(rc, 1, out)

    def test_extensionless_bash_shebang_script_is_flagged(self):
        rc, out = self.scan({"bin/run-bash": "#!/bin/bash\n# fixed in round 2\n"})
        self.assertHit(out, "bin/run-bash", 2)
        self.assertEqual(rc, 1, out)

    def test_extensionless_env_bash_shebang_script_is_flagged(self):
        rc, out = self.scan({"bin/run-env": "#!/usr/bin/env bash\n# fixed in round 2\n"})
        self.assertHit(out, "bin/run-env", 2)
        self.assertEqual(rc, 1, out)

    def test_bash_extension_is_flagged(self):
        rc, out = self.scan({"lib/x.bash": "# fixed in round 2\n"})
        self.assertHit(out, "lib/x.bash", 1)
        self.assertEqual(rc, 1, out)

    def test_comment_after_a_multi_line_double_quoted_string_is_flagged(self):
        rc, out = self.scan({"x.sh": 'echo "one\ntwo"\n# fixed in round 2\n'})
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_hash_inside_double_quotes_is_text(self):
        rc, out = self.scan({"x.sh": 'echo "x # fixed in round 2"\n# fixed in round 2\n'})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_hash_inside_single_quotes_is_text(self):
        rc, out = self.scan({"x.sh": "echo 'x # fixed in round 2'\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_hash_inside_ansi_c_quotes_is_text(self):
        rc, out = self.scan({"x.sh": "echo $'x # fixed in round 2'\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_escaped_hash_is_text(self):
        rc, out = self.scan({"x.sh": "echo \\# fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_hash_inside_a_word_is_text(self):
        rc, out = self.scan({"x.sh": "echo a#b fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_dollar_hash_is_text(self):
        rc, out = self.scan({"x.sh": "echo $# fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_length_expansion_hash_is_text(self):
        rc, out = self.scan({"x.sh": "echo ${#var} fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_prefix_strip_expansion_hash_is_text(self):
        rc, out = self.scan({"x.sh": "echo ${x#*/} fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_longest_prefix_strip_expansion_hash_is_text(self):
        rc, out = self.scan({"x.sh": "echo ${x##*/} fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_arithmetic_base_hash_is_text(self):
        rc, out = self.scan({"x.sh": "echo $((16#ff)) fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_heredoc_body_with_plain_opener_is_text(self):
        rc, out = self.scan({"x.sh": "cat <<EOF\n# fixed on 2026-10-28\nEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 4)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_heredoc_body_with_single_quoted_opener_is_text(self):
        rc, out = self.scan({"x.sh": "cat <<'EOF'\n# fixed on 2026-10-28\nEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 4)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_heredoc_body_with_double_quoted_opener_is_text(self):
        rc, out = self.scan({"x.sh": 'cat <<"EOF"\n# fixed on 2026-10-28\nEOF\n# fixed in round 2\n'})
        self.assertHit(out, "x.sh", 4)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_heredoc_body_with_backslash_opener_is_text(self):
        rc, out = self.scan({"x.sh": "cat <<\\EOF\n# fixed on 2026-10-28\nEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 4)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_heredoc_body_with_tab_stripping_opener_and_tab_terminator_is_text(self):
        rc, out = self.scan({"x.sh": "cat <<-EOF\n\t# fixed on 2026-10-28\n\tEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 4)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_two_heredocs_on_one_line_keep_both_bodies_as_text(self):
        src = "cat <<A; cat <<B\n# fixed on 2026-10-28\nA\n# fixed on 2026-10-28\nB\n# fixed in round 2\n"
        rc, out = self.scan({"x.sh": src})
        self.assertHit(out, "x.sh", 6)
        self.assertNoHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 4)
        self.assertEqual(rc, 1, out)

    def test_here_string_does_not_swallow_the_next_line(self):
        rc, out = self.scan({"x.sh": 'cat <<< "# fixed on 2026-10-28"\n# fixed in round 2\n'})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_lone_apostrophe_in_a_comment_does_not_hide_the_next_comment(self):
        rc, out = self.scan({"x.sh": "# don't\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_lone_apostrophe_in_an_unquoted_heredoc_body_does_not_hide_the_next_comment(self):
        rc, out = self.scan({"x.sh": "cat <<EOF\n# don't, fixed on 2026-10-28\nEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 4)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_unclosed_double_quote_exits_unknown(self):
        rc, out = self.scan({"x.sh": 'echo "open\n# fixed in round 2\n'})
        self.assertEqual(rc, 2, out)
        self.assertRegex(out, r"UNKNOWN.*x\.sh")

    def test_unclosed_heredoc_exits_unknown(self):
        rc, out = self.scan({"x.sh": "cat <<EOF\n# fixed in round 2\n"})
        self.assertEqual(rc, 2, out)
        self.assertRegex(out, r"UNKNOWN.*x\.sh")

    def test_why_comment_is_clean(self):
        rc, out = self.scan({"x.sh": "# git may be missing in a fresh container\ngit status\n"})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_shebang_on_line_one_is_clean(self):
        rc, out = self.scan({"x.sh": "#!/bin/sh\necho ok\n"})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_reader_pin_comment_inside_command_substitution_is_flagged(self):
        rc, out = self.scan({"x.sh": "x=$(\n  # fixed in round 2\n  echo a\n)\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_reader_pin_comment_inside_backticks_is_flagged(self):
        rc, out = self.scan({"x.sh": "x=`\n  # fixed in round 2\n  echo a\n`\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_reader_pin_comment_in_a_case_arm_is_flagged(self):
        rc, out = self.scan({"x.sh": 'case "$x" in\n  a)\n    # fixed in round 2\n    echo a ;;\nesac\n'})
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_reader_pin_comment_in_a_function_body_is_flagged(self):
        rc, out = self.scan({"x.sh": "f() {\n  # fixed in round 2\n  echo a\n}\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_reader_pin_trailing_comment_after_a_closing_quote_is_flagged(self):
        rc, out = self.scan({"x.sh": 'x="a" # fixed in round 2\n'})
        self.assertHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_line_continuation_keeps_a_comment_on_its_line(self):
        rc, out = self.scan({"x.sh": "echo a \\\n#P60 fixed in round 2\n b\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_arithmetic_then_subshell_pipeline_does_not_hide_the_later_comment(self):
        rc, out = self.scan({"x.sh": "((cd /tmp; ls) | wc -l)\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_dollar_arithmetic_with_a_subshell_does_not_hide_the_later_comment(self):
        rc, out = self.scan({"x.sh": "echo $((echo a) | cat)\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_backticks_with_a_comment_inside_do_not_hide_the_later_comment(self):
        rc, out = self.scan({"x.sh": "x=`echo a # note`\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_round2_pin_arithmetic_base_with_a_trailing_comment_then_a_later_comment(self):
        rc, out = self.scan({"x.sh": "(( x = 16#ff )) # c\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_round2_pin_shift_assignment_in_arithmetic_then_a_later_comment(self):
        rc, out = self.scan({"x.sh": "(( n <<= 1 ))\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_round2_pin_hash_joined_to_a_continued_word_is_text(self):
        rc, out = self.scan({"x.sh": "echo a\\\n#x fixed in round 2\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 3)
        self.assertNoHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_round2_pin_arithmetic_that_falls_back_to_a_subshell_then_a_later_comment(self):
        rc, out = self.scan({"x.sh": "(( 1 ) ; echo a)\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_round2_gap_regex_group_hash_is_text_not_a_comment(self):
        rc, out = self.scan({"x.sh": "[[ $x =~ ^(a)(#b.round2)$ ]]\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_round2_gap_extglob_hash_is_text_not_a_comment(self):
        rc, out = self.scan({"x.sh": "case $x in +(a|b)#round2) echo;; esac\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertNoHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_round2_gap_subscript_shift_is_not_a_heredoc(self):
        rc, out = self.scan({"x.sh": "a[1<<2]=x\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_round2_gap_control_comment_after_a_closing_paren_still_hits(self):
        rc, out = self.scan({"x.sh": "(cmd) # fixed in round 2\n"})
        self.assertHit(out, "x.sh", 1)
        self.assertEqual(rc, 1, out)

    def test_round2_gap_control_real_heredoc_after_a_subscript_shift_still_skips_its_body(self):
        rc, out = self.scan({"x.sh": "a[1<<2]=x\ncat <<EOF\n# fixed on 2026-10-28\nEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 5)
        self.assertNoHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_comment_in_a_case_arm_in_a_quoted_substitution_is_flagged(self):
        rc, out = self.scan({"x.sh": 'x="$(case $k in\na) echo ;;\n# fixed in round 2\nesac)"\n'})
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_comment_in_a_case_arm_in_an_unquoted_substitution_is_flagged(self):
        rc, out = self.scan({"x.sh": "x=$(case $k in\na) echo ;;\n# fixed in round 2\nesac)\n"})
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_comment_in_a_case_arm_in_an_unquoted_parameter_default_is_flagged(self):
        rc, out = self.scan({"x.sh": "x=${y:-$(case $k in\na) echo ;;\n# fixed in round 2\nesac)}\n"})
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_hash_in_a_quoted_string_in_a_later_arm_is_text(self):
        src = 'x="$(case $k in\na) echo ;;\nb) echo "# fixed in round 2" ;;\nesac)"\n# fixed in round 2\n'
        rc, out = self.scan({"x.sh": src})
        self.assertHit(out, "x.sh", 5)
        self.assertNoHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_let_argument_redirect_is_a_heredoc_and_skips_its_body(self):
        rc, out = self.scan({"x.sh": "let x=1 <<EOF\nit's\nEOF\n# fixed in round 2\n"})
        self.assertHit(out, "x.sh", 4)
        self.assertEqual(rc, 1, out)

    def test_reader_gap_spaced_hash_in_a_quoted_string_in_a_later_arm_is_text(self):
        rc, out = self.scan({"x.sh": 'x="$(case $k in\na) echo ;;\nb) echo "x # fixed in round 2" ;;\nesac)"\n'})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_reader_gap_comment_after_a_quoted_word_in_a_later_arm_is_flagged(self):
        rc, out = self.scan({"x.sh": 'x="$(case $k in\na) echo ;;\nb) echo "x" # fixed in round 2\nesac)"\n'})
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_case_inside_backticks_reads_clean(self):
        self.assertReadsClean("x=`case $x in a) echo 1;; esac`\n")

    def test_case_inside_double_quoted_backticks_reads_clean(self):
        self.assertReadsClean('x="`case $x in a) echo 1;; esac`"\n')

    def test_case_as_array_element_reads_clean(self):
        self.assertReadsClean("kw=(case esac)\n")

    def test_case_as_appended_array_element_reads_clean(self):
        self.assertReadsClean("arr+=(case)\n")

    def test_case_as_first_element_of_multi_line_array_reads_clean(self):
        self.assertReadsClean("arr=(\n  case\n  b\n)\n")

    def test_case_in_regex_alternation_reads_clean(self):
        self.assertReadsClean("[[ $w =~ ^(if|case|esac)$ ]]\n")

    def test_case_in_extglob_pattern_reads_clean(self):
        self.assertReadsClean("[[ $w == @(case|esac) ]]\n")

    def test_one_line_function_with_case_reads_clean(self):
        self.assertReadsClean("function f { case $1 in a) :;; esac; }\n")

    def test_case_word_in_echo_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("echo case\n")

    def test_case_word_in_assignment_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("x=case\n")

    def test_case_word_as_option_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("cmd --case\n")

    def test_esac_as_argument_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("echo esac\n")

    def test_nested_case_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("case $x in\n  a) case $y in\n    b) echo ;;\n  esac ;;\nesac\n")

    def test_paren_led_pattern_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("case $x in\n  (a|b) echo 1 ;;\nesac\n")

    def test_fallthrough_and_continue_terminators_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("case $x in\n  a) echo 1 ;&\n  b) echo 2 ;;&\n  c) echo 3 ;;\nesac\n")

    def test_heredoc_inside_arm_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("case $x in\n  a) cat <<EOF\nhello\nEOF\n;;\nesac\n")

    def test_subshell_inside_arm_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("case $x in\n  a) (cd /tmp; ls) ;;\nesac\n")

    def test_case_with_no_esac_at_end_of_input_exits_unknown(self):
        rc, out = self.scan({"x.sh": "case $x in\n  a) echo 1 ;;\n"})
        self.assertEqual(rc, 2, out)
        self.assertRegex(out, r"UNKNOWN.*x\.sh")
        self.assertIn("case never ends with esac", out)

    def test_esac_with_no_case_exits_unknown(self):
        rc, out = self.scan({"x.sh": "echo x\nesac\n"})
        self.assertEqual(rc, 2, out)
        self.assertRegex(out, r"UNKNOWN.*x\.sh")
        self.assertIn("esac with no case", out)

    def test_unclosed_backtick_exits_unknown(self):
        rc, out = self.scan({"x.sh": "x=`echo a\n"})
        self.assertEqual(rc, 2, out)
        self.assertRegex(out, r"UNKNOWN.*x\.sh")
        self.assertIn("command substitution never closes", out)

    def test_run_state_after_a_condition_across_a_comma_is_flagged(self):
        rc, out = self.scan({"x.sh": "# Once the fix landed, the tests went green on main\necho hi\n"
                                     "# When it ran, it was red on main\n"})
        self.assertHit(out, "x.sh", 1)
        self.assertHit(out, "x.sh", 3)
        self.assertEqual(rc, 1, out)

    def test_run_state_condition_clauses_stay_clean_in_a_shell_comment(self):
        rc, out = self.scan({"x.sh": "# if red on main, page the on-call\n# once green on the head, merge\necho hi\n"})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_bracket_paren_in_a_case_arm_reads_and_flags_the_history_comment(self):
        rc, out = self.scan({"x.sh": "case $x in\n  a) [[ $y == [(] ]] # changed from a dict to a list\n;;\nesac\n"})
        self.assertNotEqual(rc, 2, out)  # the file is read: exit 2 would be the reader's cause
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_bracket_without_a_paren_in_a_case_arm_flags_the_history_comment(self):
        rc, out = self.scan({"x.sh": "case $x in\n  a) [[ $y == [x] ]] # changed from a dict to a list\n;;\nesac\n"})
        self.assertHit(out, "x.sh", 2)
        self.assertEqual(rc, 1, out)

    def test_bracket_close_paren_in_a_case_pattern_reads_and_flags_a_later_comment(self):
        self.assertLaterCommentFlagged("case $x in [)]) echo;; esac\n")

    def test_bracket_without_a_paren_in_a_case_pattern_reads_and_flags_a_later_comment(self):
        self.assertLaterCommentFlagged("case $x in [x]) echo;; esac\n")

    def test_bracket_paren_arm_before_a_nested_case_later_comment_is_flagged(self):
        self.assertLaterCommentFlagged("case $x in\n  [(]) case $y in\n    b) echo ;;\n  esac ;;\nesac\n")


class RuleQuotes(Case):
    DECISION = {"docs/decisions/hold-unsafe-after-round-3.md": "# hold-unsafe-after-round-3\n\nA held change stays parked until the owner decides.\n"}

    def scan(self, files):
        return super().scan(files, extra_base=self.DECISION)

    def test_round_outside_the_gloss_stays_flagged_even_with_a_real_id(self):
        rc, out = self.scan({"x.py": "# keeps the net value round 3 gave (decision hold-unsafe-after-round-3, net-value hold after round 3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_inside_a_decision_gloss_is_clean(self):
        rc, out = self.scan({"x.py": "# (decision hold-unsafe-after-round-3, net-value hold after round 3)\nx = 1\n"})
        self.assertEqual(rc, 0, out)

    def test_round_with_a_non_gloss_citation_stays_flagged(self):
        rc, out = self.scan({"x.py": "# (added in round 3, per hold-unsafe-after-round-3)\n# Added during round 3 (hold-unsafe-after-round-3)\n# Round 3 fix: x (hold-unsafe-after-round-3)\n# Round 2 fix (round-2 finding)\n# the round 2 reviewer asked (round-2 review)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertHit(out, "x.py", 2)
        self.assertHit(out, "x.py", 3)
        self.assertHit(out, "x.py", 4)
        self.assertHit(out, "x.py", 5)
        self.assertEqual(rc, 1, out)

    def test_id_before_a_gloss_is_clean(self):
        rc, out = self.scan({"x.py": "# Decision hold-unsafe-after-round-3 (net-value hold after round 3)\n# `hold-unsafe-after-round-3` (net-value hold after round 3)\nx = 1\n"})
        self.assertEqual(rc, 0, out)

    def test_gloss_with_an_id_that_has_no_decision_file_stays_flagged(self):
        rc, out = self.scan({"x.py": "# (decision some-other-round-3, net-value hold after round 3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_without_a_cited_id_stays_flagged(self):
        rc, out = self.scan({"x.py": "# fixed in round 2\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_citing_an_id_with_another_number_stays_flagged(self):
        rc, out = self.scan({"x.py": "# fixed in round 2 (decision hold-unsafe-after-round-3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_history_forms_citing_an_id_stay_flagged(self):
        rc, out = self.scan({"x.py": "# Added in round 3 (hold-unsafe-after-round-3).\n# fixed in round 3; the round-3 trip is slow\n# Previously in round 3, see round-3\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertHit(out, "x.py", 2)
        self.assertHit(out, "x.py", 3)
        self.assertEqual(rc, 1, out)

    def test_gloss_that_opens_with_the_bare_id_still_flags_the_round(self):
        rc, out = self.scan({"x.py": "# (hold-unsafe-after-round-3, round 3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_bare_id_before_round_parentheses_still_flags_the_round(self):
        rc, out = self.scan({"x.py": "# hold-unsafe-after-round-3 (added in round 3)\nx = 1\n"})
        self.assertTrue(os.path.isfile(os.path.join(self.tree, "docs", "decisions", "hold-unsafe-after-round-3.md")))
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_rule_name_before_bare_id_round_parentheses_still_flags_the_round(self):
        rc, out = self.scan({"x.py": "# Rule hold-unsafe-after-round-3 (fixed in round 3)\nx = 1\n"})
        self.assertTrue(os.path.isfile(os.path.join(self.tree, "docs", "decisions", "hold-unsafe-after-round-3.md")))
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def home_tree(self, files):
        """A checker tree that is its own git repo, holding the given files. Returns its root."""
        root = tempfile.mkdtemp(prefix="cnl_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        self.checker_tree(root, files)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True, env=GIT_ENV)
        return root

    def test_review_round_form_inside_a_decision_gloss_is_clean(self):
        rc, out = self.scan({"x.py": "# (decision hold-unsafe-after-round-3, review round 3)\nx = 1\n"})
        self.assertEqual(rc, 0, out)

    def test_see_decision_gloss_with_a_round_number_is_clean(self):
        rc, out = self.scan({"x.py": "# (see decision hold-unsafe-after-round-3, round 3)\nx = 1\n"})
        self.assertEqual(rc, 0, out)

    def test_decision_gloss_with_a_colon_after_the_id_stays_flagged(self):
        rc, out = self.scan({"x.py": "# (decision hold-unsafe-after-round-3: the net-value hold after round 3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_directly_before_a_decision_gloss_stays_flagged(self):
        rc, out = self.scan({"x.py": "# Holds a change after round 3 (decision hold-unsafe-after-round-3).\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_decision_pinned_in_the_checker_tree_counts_for_a_gloss(self):
        checker_root = self.home_tree(self.DECISION)
        self.base({"keep.py": "x = 1\n"})
        self.change({"x.py": "# (decision hold-unsafe-after-round-3, round 3)\nx = 1\n"})
        # Scope first: the scanned repo has no decisions folder, and the check's own tree holds the decision.
        self.assertFalse(os.path.isdir(os.path.join(self.tree, "docs")))
        self.assertTrue(os.path.isfile(os.path.join(checker_root, "docs", "decisions", "hold-unsafe-after-round-3.md")))
        rc, out = self.lint(checker_root=checker_root)
        self.assertEqual(rc, 0, out)

    def test_decision_absent_from_the_checker_tree_stays_flagged(self):
        checker_root = self.home_tree({})
        self.base({"keep.py": "x = 1\n"})
        self.change({"x.py": "# (decision hold-unsafe-after-round-3, round 3)\nx = 1\n"})
        self.assertFalse(os.path.isdir(os.path.join(self.tree, "docs")))
        self.assertFalse(os.path.isdir(os.path.join(checker_root, "docs")))
        rc, out = self.lint(checker_root=checker_root)
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_fixed_in_round_before_a_real_decision_gloss_stays_flagged(self):
        rc, out = self.scan({"x.py": "# fixed in round 3 (decision hold-unsafe-after-round-3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_with_an_unknown_decision_id_stays_flagged(self):
        rc, out = self.scan({"x.py": "# Holds a change after round 3 (decision some-unknown-round-3).\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_then_a_verb_before_a_real_decision_gloss_stays_flagged(self):
        rc, out = self.scan({"x.py": "# round 3 fixed it (decision hold-unsafe-after-round-3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_colon_opener_with_added_after_a_round_before_a_decision_gloss_stays_flagged(self):
        rc, out = self.scan({"x.py": "# Added the colon opener after round 3 (decision hold-unsafe-after-round-3).\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_round_before_a_decision_gloss_with_a_word_between_stays_flagged(self):
        rc, out = self.scan({"x.py": "# In round 3 (decision hold-unsafe-after-round-3), we added the net-value line.\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)

    def test_colon_opener_with_added_after_a_round_inside_the_gloss_stays_flagged(self):
        rc, out = self.scan({"x.py": "# (decision hold-unsafe-after-round-3: added after round 3)\nx = 1\n"})
        self.assertHit(out, "x.py", 1)
        self.assertEqual(rc, 1, out)


class SelfCheck(unittest.TestCase):
    def test_check_file_comments_and_docstrings_hit_no_pattern(self):
        import check_comment_narration as checker
        hits = []
        for line, text in checker.narrated_lines(MODULE):
            for name, pat in checker.PATTERNS.items():
                for m in pat.finditer(text):
                    hits.append("%d: %s: %s" % (line, name, m.group(0)))
        self.assertEqual(hits, [], "\n".join(hits))


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
