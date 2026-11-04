#!/usr/bin/env python3
"""Cases for lint/stale_cites.py. Standard library only.

    python3 lint/test_stale_cites.py

The merge check refuses stale prose. A tracked Markdown line that names a repo path the range deleted
or renamed is STALE001. A `<file.py> <name>` pair on one line is STALE002 when the name was bound at module
level in that file at base (a def, class, assignment or import) and is not bound there at head. Each finding
is one line, `path:line: CODE message`. A Python value cite `file.py: NAME = literal` is STALE004: a line that quotes
the value the range changed, or a line the range added whose cite is not the value at head. A JSON or JavaScript value
cite prints unknown, and only in a run that already reads Markdown. The Python grammar is read here as the map check
reads it, and tests/value-cite-parity.json (beside the skill's tests) holds both copies to one set of rows.
A clean run prints `stale-cites: PASS` and exits 0.

Each case makes a temp git repo: the base commit on `main`, the head commit on `topic`. The check runs
with the repo as cwd and the range as commit ids. The step cases run bin/ste-changed, which runs
actions/ste-lint/run.sh with the step's env. TMPDIR is the case folder, so temp files stay in the run folder.
"""
import ast
import atexit
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
MODULE = os.environ.get("STALE_CITES_UNDER_TEST") or os.path.join(HERE, "stale_cites.py")
STEP = os.path.join(ROOT, "bin", "ste-changed")
STEP_SH = os.path.join(ROOT, "actions", "ste-lint", "run.sh")
BASH = "/bin/bash" if os.path.exists("/bin/bash") else (shutil.which("bash") or "bash")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree, for a base with no shared history
PARITY = os.path.join(ROOT, "skills", "plain-english-map", "tests", "value-cite-parity.json")  # the rows both copies read
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  removes a fixture tree, read-only git objects included (testing/tracked_tree.py)

RUN_FOLDER = _test_temp.run_folder()
atexit.register(tracked_tree.rm_tree, RUN_FOLDER)

NOTES = "docs/debts/notes.md"
MOVED = "mods/session-board/hooks/lib.mjs"
LIB = "export const refusals = [\n  'a',\n  'b',\n  'c',\n  'd',\n];\n"  # long enough that git pairs a move as a rename
GUARD = "def _process_start_ms(path):\n    return 0\n\n\ndef keep():\n    return 1\n"
CODE = {
    "hooks/lib.mjs": LIB,
    "hooks/guard.py": GUARD,
    "hooks/guard_core.py": "def core():\n    return 2\n",
    "lint/x.py": "def check():\n    return 3\n",
}
Range = collections.namedtuple("Range", "case repo base head")
FINDING = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): (?P<code>STALE00[1-4]) (?P<text>.*)$")


def base_files(notes="# Notes\n", extra=None):
    files = dict(CODE)
    files[NOTES] = notes
    files.update(extra or {})
    return files


def rows_text(rows):
    """Markdown for (line, flagged) rows, and the line numbers a check must flag."""
    text = "".join(line + "\n" for line, _ in rows)
    return text, [n for n, (_, flagged) in enumerate(rows, 1) if flagged]


def git(cwd, *args):
    done = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                          cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def write(repo, path, text):
    full = os.path.join(repo, *path.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def move(repo, old, new):
    os.makedirs(os.path.dirname(os.path.join(repo, *new.split("/"))), exist_ok=True)
    git(repo, "mv", old, new)


def commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "head")


def parse(out):
    """(path, line, code, text) for each finding line the check printed."""
    matches = (FINDING.match(line) for line in out.splitlines())
    return [(m.group("path"), int(m.group("line")), m.group("code"), m.group("text")) for m in matches if m]


def direct_step_env(rng, fail):
    """The env bin/ste-changed sets for the step, with FAIL given. run.sh runs from here, so FAIL can differ."""
    return dict(os.environ, TMPDIR=rng.case, GITHUB_STEP_SUMMARY=os.path.join(rng.case, "summary.md"),
                EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main", REF_NAME="topic",
                SCOPE="changed", FAIL=fail, PATHS_GLOB="**/*.md", EXCLUDE="", CHANGED_PATHS_GLOB="*.md",
                DECISIONS_DIR="")


def git_subcommands(trace_path):
    """The git subcommands a run started, read from a GIT_TRACE file: one `built-in: git <sub>` line each."""
    subs = []
    with open(trace_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            found = re.search(r"trace: built-in: git (\S+)", line)
            if found:
                subs.append(found.group(1))
    return subs


def paths_under(folder):
    """Every file and folder under `folder`, relative to it, with .git left out."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in dirnames + filenames:
            found.add(os.path.relpath(os.path.join(dirpath, name), folder))
    return found


def tuple_named(path, name):
    """The set of strings in the module-level tuple `name` of a Python file. Read with ast, never imported."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError("%s binds no %s tuple" % (path, name))


def repo_modules_imported(path):
    """Repo files that `path` imports by bare name: lint/<name>.py or hooks/<name>.py, repo-relative."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    found = []
    for name in sorted(names):
        for folder in ("lint", "hooks"):
            rel = "%s/%s.py" % (folder, name)
            if os.path.isfile(os.path.join(ROOT, *rel.split("/"))):
                found.append(rel)
    return found


def paths_loaded_by_path(path):
    """Repo-relative .py files the module names as the parts of an os.path.join call, resolved from its folder:
    a file it loads by path (importlib, not an import). Read with ast, never imported."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    folder = os.path.relpath(os.path.dirname(os.path.abspath(path)), ROOT)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            parts = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if parts and parts[-1].endswith(".py"):
                rel = os.path.normpath(os.path.join(folder, *parts)).replace(os.sep, "/")
                if rel not in found:
                    found.append(rel)
    return found


def binding_kind(source, name):
    """How a Python source binds `name` at module level, also under a module-level if or try: "def" for a def
    or class, "assign", "import", or None. Read with ast, never imported. A case asserts this on its fixtures
    before it probes the check on the name."""
    found = []

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    found.append("def")
            elif isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    found.append("assign")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if any((alias.asname or alias.name.split(".")[0]) == name for alias in node.names):
                    found.append("import")
            elif isinstance(node, (ast.If, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    visit(getattr(node, field, None) or [])
                for handler in getattr(node, "handlers", None) or []:
                    visit(handler.body)
    visit(ast.parse(source).body)
    return found[-1] if found else None


def assigned_value(source, name):
    """The literal the last module-level assignment of `name` binds, read with ast and never run."""
    found = None
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            found = ast.literal_eval(node.value)
    return found


def json_value(text, dotted):
    """The value at a dotted path of a JSON document."""
    node = json.loads(text)
    for part in dotted.split("."):
        node = node[part]
    return node


def parity_rows():
    """The rows of the parity fixture that both suites read, as data."""
    with open(PARITY, encoding="utf-8") as f:
        return json.load(f)["rows"]


def value_at(row, text, symbol):
    """The value `symbol` holds in the text of the row's file: a dotted JSON path, or a module-level literal."""
    return json_value(text, symbol) if row["file"].endswith(".json") else assigned_value(text, symbol)


class StaleCase(unittest.TestCase):
    def make_range(self, base, change):
        """Commit `base` on main, then run `change(repo)` on topic. `change` makes its own commit, so a case
        can leave a file untracked after it."""
        case = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, case)
        repo = os.path.join(case, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q")
        git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        for path, text in base.items():
            write(repo, path, text)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        base_sha = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "topic")
        change(repo)
        return Range(case, repo, base_sha, git(repo, "rev-parse", "HEAD"))

    def run_check(self, rng, base=None, extra_env=None):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/stale_cites.py")
        env = dict(os.environ, TMPDIR=rng.case, **(extra_env or {}))
        spec = "%s...%s" % (rng.base if base is None else base, rng.head)
        done = subprocess.run([sys.executable, MODULE, "--range", spec],
                              cwd=rng.repo, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        return done.returncode, done.stdout + done.stderr

    def assert_flags(self, rng, expected):
        """Exit 1 and exactly the expected (path, line, code) findings. Returns the findings."""
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 1, out)
        found = parse(out)
        self.assertEqual(sorted((p, n, c) for p, n, c, _ in found), sorted(expected), out)
        return found

    def assert_passes(self, rng):
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)
        self.assertEqual(parse(out), [], out)


class MoveTests(StaleCase):
    def test_moved_file_named_by_a_line_the_range_adds_is_flagged_with_its_new_home(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, "# Notes\n\n- refusal list in `hooks/lib.mjs`\n")
            commit(repo)
        found = self.assert_flags(self.make_range(base_files(), change), [(NOTES, 3, "STALE001")])
        self.assertIn(MOVED, found[0][3])

    def test_code_only_range_still_flags_a_stale_line_already_on_main(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        found = self.assert_flags(rng, [(NOTES, 3, "STALE001")])
        self.assertIn(MOVED, found[0][3])

    def test_deleted_path_named_by_a_line_is_flagged(self):
        def change(repo):
            git(repo, "rm", "-q", "hooks/lib.mjs")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        self.assert_flags(rng, [(NOTES, 3, "STALE001")])

    def test_a_path_match_needs_a_path_boundary_on_both_sides(self):
        rows = [
            ("A: `hooks/lib.mjs`", True),
            ("B: ends a sentence with hooks/lib.mjs.", True),
            ("C: mods/hooks/lib.mjs", False),  # a `/` before the match
            ("D: xhooks/lib.mjs", False),  # a word char before the match
            ("E: hooks/lib.mjsx", False),  # a word char after the match
            ("F: hooks/lib.mjs.bak", False),  # `.` and a word char after the match
            ("G: hooks/lib.mjs/index", False),  # a `/` after the match
            ("H: hooks/lib.mjs_v2", False),  # a word char after the match
        ]
        text, lines = rows_text(rows)

        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, text)
            commit(repo)
        self.assert_flags(self.make_range(base_files(""), change), [(NOTES, n, "STALE001") for n in lines])

    def test_new_path_that_ends_with_the_old_one_is_not_flagged(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, "# Notes\n\nHome: %s\n" % MOVED)
            commit(repo)
        self.assert_passes(self.make_range(base_files(), change))

    def test_prefix_of_a_deleted_path_is_not_flagged(self):
        def change(repo):
            git(repo, "rm", "-q", "hooks/guard_core.py")
            commit(repo)
        self.assert_passes(self.make_range(base_files("# Notes\n\n- the gate is in `hooks/guard`\n"), change))

    def test_generated_records_page_is_never_checked(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        extra = {"docs/records.md": "# Records\n\n- refusal list in `hooks/lib.mjs`\n"}
        self.assert_passes(self.make_range(base_files(extra=extra), change))

    def test_file_matched_by_ste_lint_exclude_is_not_checked(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        extra = {
            ".ste-lint-exclude": "# Third-party prose.\nthird_party/**\n",
            "third_party/notes.md": "- refusal list in `hooks/lib.mjs`\n",
        }
        self.assert_passes(self.make_range(base_files(extra=extra), change))

    def test_disable_line_names_its_code_and_no_other(self):
        rows = [
            ("- refusal list in `hooks/lib.mjs` <!-- ste-disable-line STALE001 -->", False),
            ("- refusal list in `hooks/lib.mjs` <!-- ste-disable-line STE001 -->", True),
            ("- refusal list in `hooks/lib.mjs`", True),
        ]
        text, lines = rows_text(rows)

        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, text)
            commit(repo)
        self.assert_flags(self.make_range(base_files(""), change), [(NOTES, n, "STALE001") for n in lines])

    def test_cite_already_stale_at_base_for_an_untouched_path_is_not_flagged(self):
        notes = "# Notes\n\n- refusal list in `hooks/removed_long_ago.mjs`\n- (hooks/gone.py old_fn)\n"

        def change(repo):
            write(repo, "hooks/new.py", "def fresh():\n    return 5\n")
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes), change))

    def test_path_deleted_then_written_again_is_not_flagged(self):
        def change(repo):
            git(repo, "rm", "-q", "hooks/lib.mjs")
            write(repo, "hooks/lib.mjs", "export const refusals = [];\n")
            commit(repo)
        self.assert_passes(self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change))

    def test_untracked_markdown_is_not_checked(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
            write(repo, "scratch.md", "- refusal list in `hooks/lib.mjs`\n")
        self.assert_passes(self.make_range(base_files(), change))


    def test_a_dash_or_a_dot_before_the_match_is_not_a_boundary(self):
        notes = "# Notes\n\n- see `pre-hooks/guard.py`\n- see `x.hooks/guard.py`\n"

        def change(repo):
            git(repo, "rm", "-q", "hooks/guard.py")
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes), change))


class ScanTests(StaleCase):
    def test_comment_openers_in_strings_and_a_multi_line_block_do_not_hide_later_lines(self):
        rows = [
            ("# Refusal list in `hooks/lib.mjs`", True),  # a heading opens with `#`
            ("Use `#` to start a comment. The list is in `hooks/lib.mjs`.", True),
            ("Open a comment with `<!--`. The list is in `hooks/lib.mjs`.", True),
            ("Don't read `hooks/lib.mjs` for the list.", True),  # a lone quote in text
            ("Quote `\"/*\"` in a string. The list is in `hooks/lib.mjs`.", True),
            ("```", False),
            ("/* open comment", False),
            ("x = \"a // b\"  # don't", False),
            ("```", False),
            ("The list moved: see `hooks/lib.mjs`.", True),
            ("<!--", False),
            ("A note with no path.", False),
            ("-->", False),
            ("The list moved again: see `hooks/lib.mjs`.", True),
        ]
        text, lines = rows_text(rows)

        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, text)
            commit(repo)
        self.assert_flags(self.make_range(base_files(""), change), [(NOTES, n, "STALE001") for n in lines])


class SymbolTests(StaleCase):
    def test_symbol_moved_to_another_file_is_flagged_on_its_line_only(self):
        notes = ("# Notes\n\nSee (hooks/guard.py _process_start_ms) for timing.\n\n"
                 "See (hooks/git_reads.py _process_start_ms) now.\n")

        def change(repo):
            write(repo, "hooks/guard.py", "def keep():\n    return 1\n")
            write(repo, "hooks/git_reads.py", "def _process_start_ms(path):\n    return 0\n")
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes), change), [(NOTES, 3, "STALE002")])

    def test_renamed_file_names_its_new_home_in_each_finding(self):
        def change(repo):
            move(repo, "hooks/guard.py", "hooks/timing.py")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n(hooks/guard.py _process_start_ms)\n"), change)
        rc, out = self.run_check(rng)
        found = parse(out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(found, out)
        for path, line, code, text in found:
            self.assertEqual((path, line), (NOTES, 3), out)
            self.assertIn(code, ("STALE001", "STALE002"), out)
            self.assertIn("hooks/timing.py", text, out)

    def test_a_name_inside_a_string_at_head_is_not_a_def(self):
        head_guard = ('KEEP = "# def _process_start_ms"\n'
                      'DOC = """\ndef _process_start_ms():\n"""\n\n\n'
                      'def keep():\n    return 1\n')

        def change(repo):
            write(repo, "hooks/guard.py", head_guard)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n(hooks/guard.py _process_start_ms)\n"), change)
        self.assert_flags(rng, [(NOTES, 3, "STALE002")])

    def test_a_word_after_a_path_that_was_never_a_def_is_not_flagged(self):
        def change(repo):
            write(repo, "lint/x.py", "def run():\n    return 4\n")
            commit(repo)
        self.assert_passes(self.make_range(base_files("# Notes\n\n- (lint/x.py fixtures)\n"), change))

    def test_name_still_defined_in_the_same_file_is_not_flagged(self):
        def change(repo):
            write(repo, "hooks/guard.py", GUARD + "\n\ndef extra():\n    return 2\n")
            commit(repo)
        self.assert_passes(self.make_range(base_files("# Notes\n\n- (hooks/guard.py _process_start_ms)\n"), change))

    def test_name_that_was_only_a_comment_at_base_was_never_a_def(self):
        comment = "# _process_start_ms moved to hooks/git_reads.py\n"
        extra = {"hooks/guard.py": comment + "def keep():\n    return 1\n"}

        def change(repo):
            write(repo, "hooks/guard.py", comment + "def keep():\n    return 2\n")
            commit(repo)
        notes = "# Notes\n\n- (hooks/guard.py _process_start_ms)\n"
        self.assert_passes(self.make_range(base_files(notes, extra=extra), change))

    def test_file_and_name_on_different_lines_or_reversed_are_not_flagged(self):
        notes = ("# Notes\n\n- hooks/guard.py\n  _process_start_ms\n"
                 "- _process_start_ms hooks/guard.py\n")

        def change(repo):
            write(repo, "hooks/guard.py", "def keep():\n    return 1\n")
            write(repo, "hooks/git_reads.py", "def _process_start_ms(path):\n    return 0\n")
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes), change))

    def test_a_nested_def_in_a_test_method_is_not_a_module_level_name(self):
        # From a history replay: a test method's local def was read as a module-level name.
        base_sweep = ("import unittest\n\n\nclass SweepTests(unittest.TestCase):\n"
                      "    def test_two(self):\n        def stop(*a, **k):\n            return 1\n"
                      "        return stop\n")
        head_sweep = ("import unittest\n\n\nclass SweepTests(unittest.TestCase):\n"
                      "    def test_two(self):\n        return None\n")
        notes = "# Notes\n\ntwo tests in `janitor/test_sweep.py` stop with WinError 1314.\n"

        def change(repo):
            write(repo, "janitor/test_sweep.py", head_sweep)
            commit(repo)
        extra = {"janitor/test_sweep.py": base_sweep}
        self.assert_passes(self.make_range(base_files(notes, extra=extra), change))

    def test_a_module_level_def_removed_from_the_cited_file_is_flagged_on_the_same_line(self):
        base_sweep = "def stop(*a, **k):\n    return 1\n"
        head_sweep = "def keep():\n    return 2\n"
        notes = "# Notes\n\ntwo tests in `janitor/test_sweep.py` `stop` with WinError 1314.\n"

        def change(repo):
            write(repo, "janitor/test_sweep.py", head_sweep)
            commit(repo)
        extra = {"janitor/test_sweep.py": base_sweep}
        self.assert_flags(self.make_range(base_files(notes, extra=extra), change), [(NOTES, 3, "STALE002")])


    def test_a_module_level_def_under_if_or_try_still_counts_as_defined(self):
        notes = "# Notes\n\n(lib.py foo)\n"
        heads = {
            "if": "if True:\n    def foo():\n        return 1\n",
            "try": "try:\n    def foo():\n        return 1\nexcept ImportError:\n    pass\n",
        }
        for block, head_lib in heads.items():
            with self.subTest(block=block):
                def change(repo, head_lib=head_lib):
                    write(repo, "lib.py", head_lib)
                    commit(repo)
                extra = {"lib.py": "def foo():\n    return 1\n"}
                self.assert_passes(self.make_range(base_files(notes, extra=extra), change))

    def test_a_name_is_cited_only_in_backtick_or_paren_form(self):
        base_a = "def foo():\n    return 1\n\n\ndef read():\n    return 2\n"
        rows = [
            ("- `hooks/a.py` `foo`", True),
            ("- (hooks/a.py foo)", True),
            ("- (hooks/a.py read)", True),
            ("- `hooks/a.py` foo the rest", False),
            ("- hooks/a.py read more", False),
        ]
        text, lines = rows_text(rows)

        def change(repo):
            write(repo, "hooks/a.py", "def keep():\n    return 3\n")
            write(repo, NOTES, text)
            commit(repo)
        self.assert_flags(self.make_range(base_files("", extra={"hooks/a.py": base_a}), change),
                          [(NOTES, n, "STALE002") for n in lines])

    def test_a_removed_module_level_constant_cited_in_backticks_is_flagged(self):
        base_config = "LIMIT = 3\n\n\ndef keep():\n    return 1\n"
        head_config = "def keep():\n    return 1\n"
        notes = "# Notes\n\n- `hooks/config.py` `LIMIT`\n"
        self.assertEqual(binding_kind(base_config, "LIMIT"), "assign")  # scope: base binds LIMIT as a constant
        self.assertIsNone(binding_kind(head_config, "LIMIT"))  # scope: head no longer binds LIMIT

        def change(repo):
            write(repo, "hooks/config.py", head_config)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={"hooks/config.py": base_config}), change),
                          [(NOTES, 3, "STALE002")])

    def test_a_def_replaced_by_an_assignment_that_still_binds_the_name_is_not_flagged(self):
        base_lib = "def f():\n    return 1\n"
        head_lib = "def h():\n    return 2\n\n\nf = h\n"
        notes = "# Notes\n\n- `lib.py` `f`\n"
        self.assertEqual(binding_kind(base_lib, "f"), "def")  # scope: base defines f
        self.assertEqual(binding_kind(head_lib, "f"), "assign")  # scope: head binds f by assignment, no def

        def change(repo):
            write(repo, "lib.py", head_lib)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={"lib.py": base_lib}), change))

    def test_a_name_moved_away_but_re_imported_into_the_file_is_not_flagged(self):
        head_guard = "from hooks.git_reads import _process_start_ms\n\n\ndef keep():\n    return 1\n"
        head_reads = "def _process_start_ms(path):\n    return 0\n"
        notes = "# Notes\n\n- (hooks/guard.py _process_start_ms)\n"
        self.assertEqual(binding_kind(GUARD, "_process_start_ms"), "def")  # scope: base defines it in guard.py
        self.assertEqual(binding_kind(head_guard, "_process_start_ms"), "import")  # scope: head re-imports it

        def change(repo):
            write(repo, "hooks/guard.py", head_guard)
            write(repo, "hooks/git_reads.py", head_reads)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes), change))

    def test_a_constant_still_bound_under_a_module_level_if_is_not_flagged(self):
        base_config = "LIMIT = 3\n\n\ndef keep():\n    return 1\n"
        head_config = "if True:\n    LIMIT = 3\n\n\ndef keep():\n    return 1\n"
        notes = "# Notes\n\n- `hooks/config.py` `LIMIT`\n"
        self.assertEqual(binding_kind(base_config, "LIMIT"), "assign")  # scope: base binds LIMIT at module level
        self.assertEqual(binding_kind(head_config, "LIMIT"), "assign")  # scope: head binds it under the if

        def change(repo):
            write(repo, "hooks/config.py", head_config)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={"hooks/config.py": base_config}), change))

    def test_an_import_still_bound_inside_a_module_level_try_is_not_flagged(self):
        base_out = "from json import dumps\n\n\ndef keep():\n    return 1\n"
        head_out = ("try:\n    from json import dumps\nexcept ImportError:\n    pass\n\n\n"
                    "def keep():\n    return 1\n")
        notes = "# Notes\n\n- `hooks/out.py` `dumps`\n"
        self.assertEqual(binding_kind(base_out, "dumps"), "import")  # scope: base imports dumps at module level
        self.assertEqual(binding_kind(head_out, "dumps"), "import")  # scope: head imports it inside the try

        def change(repo):
            write(repo, "hooks/out.py", head_out)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={"hooks/out.py": base_out}), change))


class ValueTests(StaleCase):
    """STALE004: a Python value cite `file.py: NAME = literal` that quotes the value the range changed, or a line the
    range added whose cite is not the value at head. JSON and JavaScript values print unknown, never a finding. Each
    case asserts its fixture values first, so a probe never runs on a wrong fixture."""

    def change_config(self, base_cfg, head_cfg, notes):
        """Commit `notes` and `hooks/config.py` = `base_cfg` on main, then the head `head_cfg` on topic."""
        def change(repo):
            write(repo, "hooks/config.py", head_cfg)
            commit(repo)
        return self.make_range(base_files(notes, extra={"hooks/config.py": base_cfg}), change)

    def test_a_changed_value_still_quoted_by_an_untouched_line_is_flagged(self):
        base_cfg, head_cfg = "LIMIT = 4\n", "LIMIT = 5\n"
        notes = "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 4`\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(assigned_value(head_cfg, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        self.assert_flags(self.change_config(base_cfg, head_cfg, notes), [(NOTES, 3, "STALE004")])

    def test_the_same_line_rewritten_to_the_new_value_passes(self):
        base_cfg, head_cfg = "LIMIT = 4\n", "LIMIT = 5\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(assigned_value(head_cfg, "LIMIT"), 5)  # scope: the range changes LIMIT to 5

        def change(repo):
            write(repo, "hooks/config.py", head_cfg)
            write(repo, NOTES, "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 5`\n")
            commit(repo)
        notes = "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 4`\n"
        self.assert_passes(self.make_range(base_files(notes, extra={"hooks/config.py": base_cfg}), change))

    def test_a_cite_of_a_value_the_range_did_not_change_is_not_flagged(self):
        base_cfg, head_cfg = "LIMIT = 4\nRETRIES = 2\n", "LIMIT = 4\nRETRIES = 3\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), assigned_value(head_cfg, "LIMIT"))  # scope: LIMIT unchanged
        self.assertNotEqual(assigned_value(base_cfg, "RETRIES"), assigned_value(head_cfg, "RETRIES"))  # scope: range changed
        notes = "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 4`\n"
        self.assert_passes(self.change_config(base_cfg, head_cfg, notes))

    def test_a_line_already_wrong_at_base_and_untouched_is_not_flagged(self):
        base_cfg, head_cfg = "LIMIT = 4\n", "LIMIT = 5\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 3 is wrong at base
        self.assertEqual(assigned_value(head_cfg, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        notes = "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 3`\n"
        self.assert_passes(self.change_config(base_cfg, head_cfg, notes))

    def test_a_changed_value_that_no_line_cites_passes(self):
        base_cfg, head_cfg = "LIMIT = 4\n", "LIMIT = 5\n"
        self.assertEqual(assigned_value(head_cfg, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        notes = "# Notes\n\nThe retry limit lives in `hooks/config.py`.\n"  # the empty state: no value cite on any line
        self.assert_passes(self.change_config(base_cfg, head_cfg, notes))

    def test_a_changed_value_cited_on_the_last_line_of_a_full_page_is_flagged_on_that_line(self):
        lines = ["# Notes", ""] + ["Filler prose line %d." % i for i in range(297)] + ["- retry limit `hooks/config.py: LIMIT = 4`"]
        self.assertEqual(len(lines), 300)  # scope: a full page, the cite on line 300
        self.assertEqual(assigned_value("LIMIT = 4\n", "LIMIT"), 4)  # scope: base binds LIMIT to 4
        notes = "\n".join(lines) + "\n"
        self.assert_flags(self.change_config("LIMIT = 4\n", "LIMIT = 5\n", notes), [(NOTES, len(lines), "STALE004")])

    def test_a_new_line_whose_cite_is_not_the_head_value_is_flagged(self):
        base_cfg, head_cfg = "LIMIT = 4\n", "LIMIT = 5\n"
        self.assertNotEqual(assigned_value(head_cfg, "LIMIT"), 6)  # scope: the added cite's 6 is not the value at head
        def change(repo):
            write(repo, "hooks/config.py", head_cfg)
            write(repo, NOTES, "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 6`\n")
            commit(repo)
        self.assert_flags(self.make_range(base_files(extra={"hooks/config.py": base_cfg}), change), [(NOTES, 3, "STALE004")])

    def test_a_json_value_cite_prints_unknown_when_the_range_already_reads_markdown(self):
        # Only Python values are checked. A JSON value is read by no reader, so its cite prints unknown, and only in a
        # run that already reads Markdown. The Python literal below makes this run read Markdown; the JSON change alone
        # would not (see test_a_lone_json_touch_reads_no_markdown_and_starts_no_ls_tree).
        base_cfg, head_cfg = '{"retries": {"max": 4}}\n', '{"retries": {"max": 5}}\n'
        base_py, head_py = "RETRIES = 2\n", "RETRIES = 3\n"
        self.assertEqual(json_value(base_cfg, "retries.max"), 4)  # scope: base holds retries.max 4
        self.assertEqual(json_value(head_cfg, "retries.max"), 5)  # scope: the range changes retries.max to 5
        self.assertNotEqual(assigned_value(base_py, "RETRIES"), assigned_value(head_py, "RETRIES"))  # scope: a Python literal changes

        def change(repo):
            write(repo, "config.json", head_cfg)
            write(repo, "hooks/config.py", head_py)
            commit(repo)
        notes = "# Notes\n\n- retry cap `config.json: retries.max = 4`\n"
        base = base_files(notes, extra={"config.json": base_cfg, "hooks/config.py": base_py})
        rc, out = self.run_check(self.make_range(base, change))
        self.assertEqual(parse(out), [], "a JSON value cite must print unknown, not a STALE004 finding\n" + out)
        unknown = [line for line in out.splitlines() if line.startswith("stale-cites: unknown")]
        self.assertTrue(any("docs/debts/notes.md:3" in line and "config.json" in line for line in unknown),
                        "a JSON value cite on NOTES:3 must print a stale-cites unknown line that names config.json\n" + out)
        self.assertEqual(rc, 0, out)  # unknown never fails the run

    def test_a_cited_js_value_that_changed_prints_unknown_and_never_passes(self):
        base = {"hooks/config.py": "RETRIES = 2\n", "hooks/lib.mjs": "export const LIMIT = 4;\n",
                NOTES: "# Notes\n\n- limit `hooks/lib.mjs: LIMIT = 4`\n"}
        self.assertEqual(assigned_value(base["hooks/config.py"], "RETRIES"), 2)  # scope: the range also changes a .py literal
        self.assertIn("LIMIT = 4", base["hooks/lib.mjs"])  # scope: base holds the cited JS value

        def change(repo):
            write(repo, "hooks/config.py", "RETRIES = 3\n")
            write(repo, "hooks/lib.mjs", "export const LIMIT = 5;\n")
            commit(repo)
        rc, out = self.run_check(self.make_range(base, change))
        unknown = [line for line in out.splitlines() if line.startswith("stale-cites: unknown") and "hooks/lib.mjs" in line]
        self.assertTrue(unknown, "a cited .mjs value must print a stale-cites unknown line that names hooks/lib.mjs\n" + out)

    def test_a_wrong_cite_added_by_a_range_that_changes_no_literal_is_flagged(self):
        base_cfg = "LIMIT = 4\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base and head bind LIMIT to 4, the range changes no literal

        def change(repo):
            write(repo, NOTES, "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 6`\n")  # the added cite: 6 is not the value at head
            commit(repo)
        self.assert_flags(self.make_range(base_files(extra={"hooks/config.py": base_cfg}), change), [(NOTES, 3, "STALE004")])

    def test_a_correct_cite_added_by_a_range_that_changes_no_literal_passes(self):
        base_cfg = "LIMIT = 4\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base and head bind LIMIT to 4, the range changes no literal

        def change(repo):
            write(repo, NOTES, "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 4`\n")
            commit(repo)
        self.assert_passes(self.make_range(base_files(extra={"hooks/config.py": base_cfg}), change))

    def test_a_value_cite_of_a_module_name_the_range_removed_fires(self):
        base_cfg, head_cfg = "LIMIT = 4\nRETRIES = 2\n", "RETRIES = 2\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertIsNone(binding_kind(head_cfg, "LIMIT"))  # scope: head no longer binds LIMIT
        notes = "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 4`\n"

        def change(repo):
            write(repo, "hooks/config.py", head_cfg)
            commit(repo)
        rc, out = self.run_check(self.make_range(base_files(notes, extra={"hooks/config.py": base_cfg}), change))
        # A value cite is not a pair cite, so STALE002 never reads it; either code may own the finding.
        codes = [code for path, line, code, _ in parse(out) if (path, line) == (NOTES, 3)]
        self.assertTrue(codes, "a value cite of a name the range removed must fire on its line, but no finding names NOTES:3\n" + out)
        self.assertTrue(set(codes) <= {"STALE002", "STALE004"}, out)

    def test_a_second_copy_of_a_line_already_wrong_at_base_fires_on_the_copy(self):
        cite = "- retry limit `hooks/config.py: LIMIT = 6`"
        base_cfg = "LIMIT = 4\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 6 is wrong at base
        notes_base = "# Notes\n\n%s\n" % cite
        notes_head = "# Notes\n\n%s\n\n%s\n" % (cite, cite)  # the PR adds a second copy at line 5
        self.assertIn(cite, notes_base.split("\n"))  # scope: the copy is a line NOTES already holds at base

        def change(repo):
            write(repo, NOTES, notes_head)
            commit(repo)
        # The first copy is the base line, left alone. The added copy is a new wrong line, so it fires on its own line.
        self.assert_flags(self.make_range(base_files(notes_base, extra={"hooks/config.py": base_cfg}), change), [(NOTES, 5, "STALE004")])

    def test_a_wrong_line_at_base_left_alone_in_a_touched_md_does_not_fire(self):
        # Control for the added-line fix: the file is touched, but the wrong line is the base line, not a new one.
        cite = "- retry limit `hooks/config.py: LIMIT = 6`"
        base_cfg = "LIMIT = 4\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 6 is wrong at base

        def change(repo):
            write(repo, NOTES, "# Notes\n\n%s\n\nA new prose line.\n" % cite)  # the range touches NOTES, not the wrong line
            commit(repo)
        self.assert_passes(self.make_range(base_files("# Notes\n\n%s\n" % cite, extra={"hooks/config.py": base_cfg}), change))

    def test_a_wrong_line_moved_within_a_touched_md_does_not_fire(self):
        # Control for the added-line fix: a moved line keeps its text and its count, so it is no new line at any position.
        cite = "- retry limit `hooks/config.py: LIMIT = 6`"
        base_cfg = "LIMIT = 4\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 6 is wrong at base

        def change(repo):
            write(repo, NOTES, "# Notes\n\nA note.\n\n%s\n" % cite)  # the same wrong line, moved from line 3 to line 5
            commit(repo)
        self.assert_passes(self.make_range(base_files("# Notes\n\n%s\n\nA note.\n" % cite, extra={"hooks/config.py": base_cfg}), change))

    def test_an_added_cite_of_a_name_never_bound_fires_without_saying_the_range_removed_it(self):
        # The name was never bound at base or head, so the range removed nothing; the message must not say it did.
        base_cfg = "LIMIT = 4\n"
        self.assertEqual(assigned_value(base_cfg, "LIMIT"), 4)  # scope: base binds LIMIT, the one name the file has
        self.assertIsNone(binding_kind(base_cfg, "NOPE"))  # scope: base never binds NOPE

        def change(repo):
            write(repo, NOTES, "# Notes\n\n- retry limit `hooks/config.py: NOPE = 4`\n")  # the added cite of that name
            commit(repo)
        rc, out = self.run_check(self.make_range(base_files(extra={"hooks/config.py": base_cfg}), change))
        found = [text for path, line, code, text in parse(out) if (path, line) == (NOTES, 3)]
        self.assertTrue(found, "an added cite of a name the file never binds must fire on its line\n" + out)
        for text in found:
            self.assertNotIn("removed", text, "the message must not say the range removed a name it never bound: %s" % text)

    def test_a_ste_disable_line_mark_for_stale004_leaves_out_a_js_or_json_value_cite_line(self):
        # A JavaScript or JSON value cite prints unknown, and no STALE004 mark names an unknown. The mark still leaves
        # its own line out: the unknown names the line, so a mark on that line must keep it silent.
        cases = (
            ("hooks/lib.mjs", "export const LIMIT = 4;\n", "export const LIMIT = 5;\n", "hooks/lib.mjs: LIMIT = 4"),
            ("config.json", '{"retries": {"max": 4}}\n', '{"retries": {"max": 5}}\n', "config.json: retries.max = 4"),
        )
        for path, base_text, head_text, cite in cases:
            with self.subTest(file=path):
                self.assertNotEqual(base_text, head_text)  # scope: the range changes the cited file

                def run(line):
                    def change(repo):
                        write(repo, path, head_text)
                        write(repo, "hooks/config.py", "RETRIES = 3\n")  # a Python literal changes, so the run reads Markdown
                        commit(repo)
                    base = base_files("# Notes\n\n%s\n" % line, extra={path: base_text, "hooks/config.py": "RETRIES = 2\n"})
                    return self.run_check(self.make_range(base, change))[1]

                plain = run("- retry cap `%s`" % cite)
                self.assertTrue(any(l.startswith("stale-cites: unknown") and "docs/debts/notes.md:3" in l for l in plain.splitlines()),
                                "scope: without the mark, the cite line prints unknown\n" + plain)
                marked = run("- retry cap `%s` <!-- ste-disable-line STALE004 -->" % cite)
                named = [l for l in marked.splitlines() if l.startswith("stale-cites: unknown") and "docs/debts/notes.md:3" in l]
                self.assertEqual(named, [], "the STALE004 mark must leave the cite line out, so no unknown may name it\n" + marked)

    def test_every_parity_row_the_grammar_matches_is_flagged_when_its_value_changed(self):
        # Python rows only: a JSON row prints unknown, which the JSON cases hold.
        rows = [row for row in parity_rows() if row["match"] and row["file"].endswith(".py")]
        self.assertTrue(rows, "scope: the parity fixture holds matching rows")
        for row in rows:  # scope: each cited literal is the base value, and the range changes it
            symbol = row["match"]["symbol"]
            base_value = value_at(row, row["base"], symbol)
            self.assertEqual(base_value, ast.literal_eval(row["match"]["literal"]), "scope: base value of %s" % row["cite"])
            self.assertNotEqual(value_at(row, row["head"], symbol), base_value, "scope: head value of %s" % row["cite"])
        rng, lines = self.parity_range(rows)
        rc, out = self.run_check(rng)
        flagged = {line for _, line, code, _ in parse(out) if code == "STALE004"}
        missing = [row["cite"] for row, line in zip(rows, lines) if line not in flagged]
        self.assertEqual(missing, [], "STALE004 must flag each cited value that changed, on its own line:\n" + out)

    def test_every_parity_row_outside_the_grammar_stays_silent(self):
        rows = [row for row in parity_rows() if not row["match"]]
        self.assertTrue(rows, "scope: the parity fixture holds rows outside the grammar")
        for row in rows:  # scope: the range changes the row's file, so the check reads it
            self.assertNotEqual(row["base"], row["head"], "scope: the range changes the file of %s" % row["cite"])
        rng, _ = self.parity_range(rows)
        self.assert_passes(rng)

    def parity_range(self, rows):
        """One range that changes each row's file and cites each row on its own NOTES line. Returns the range and those lines."""
        base = {row["file"]: row["base"] for row in rows}
        base[NOTES] = "# Notes\n"
        notes = "# Notes\n\n" + "".join("- row %d: `%s`\n" % (i, row["cite"]) for i, row in enumerate(rows, 1))

        def change(repo):
            for row in rows:
                write(repo, row["file"], row["head"])
            write(repo, NOTES, notes)
            commit(repo)
        return self.make_range(base, change), [3 + k for k in range(len(rows))]  # row k sits on line 3 + k of NOTES


class StepTests(StaleCase):
    def test_code_only_pr_fails_the_step_on_the_stale_line(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        git(rng.repo, "update-ref", "refs/remotes/origin/main", rng.base)  # the base the step diffs against
        env = dict(os.environ, TMPDIR=rng.case, GITHUB_STEP_SUMMARY=os.path.join(rng.case, "summary.md"))
        done = subprocess.run([sys.executable, STEP, "main"], cwd=rng.repo, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        out = done.stdout + done.stderr
        self.assertNotEqual(done.returncode, 0, out)
        self.assertTrue(re.search(r"(?m)^%s:3: STALE001 " % re.escape(NOTES), out), out)


    def test_fail_false_prints_the_stale_line_and_exits_zero(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        git(rng.repo, "update-ref", "refs/remotes/origin/main", rng.base)
        done = subprocess.run([BASH, STEP_SH], cwd=rng.repo, env=direct_step_env(rng, "false"),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, out)
        self.assertTrue(re.search(r"(?m)^%s:3: STALE001 " % re.escape(NOTES), out), out)


class ReadAtHeadTests(StaleCase):
    """The check reads what HEAD commits, never the working tree, and never skips a file it cannot read."""

    def test_an_uncommitted_fix_in_the_tree_does_not_hide_a_stale_line_at_head(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, "# Notes\n\n- refusal list in `hooks/lib.mjs`\n")
            commit(repo)
            write(repo, NOTES, "# Notes\n\n- refusal list in `%s`\n" % MOVED)  # the fix, left uncommitted
        self.assert_flags(self.make_range(base_files(), change), [(NOTES, 3, "STALE001")])

    def test_a_tracked_file_deleted_from_the_tree_is_still_read_at_head(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, "# Notes\n\n- refusal list in `hooks/lib.mjs`\n")
            commit(repo)
            os.remove(os.path.join(repo, NOTES))
        self.assert_flags(self.make_range(base_files(), change), [(NOTES, 3, "STALE001")])

    def test_an_undecodable_markdown_file_is_named_not_passed_silently(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            os.makedirs(os.path.join(repo, "docs"), exist_ok=True)
            with open(os.path.join(repo, "docs", "bad.md"), "wb") as f:
                f.write(b"- refusal list in `hooks/lib.mjs`\n\xff\xfe not utf-8\n")
            commit(repo)
        rc, out = self.run_check(self.make_range(base_files(), change))
        self.assertNotIn("stale-cites: PASS", out)
        self.assertIn("docs/bad.md", out)


class UnknownTests(StaleCase):
    """A base the repo cannot resolve is unknown, not a finding: the check exits 0 and says so."""

    def test_an_unresolvable_base_prints_unknown_and_exits_zero(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files(), change)
        rc, out = self.run_check(rng, base="1" * 40)
        self.assertEqual(rc, 0, out)
        self.assertTrue(any(line.startswith("stale-cites: unknown") for line in out.splitlines()), out)

    def test_step_with_an_unresolvable_base_exits_zero(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        # A base with no shared history: origin/main resolves, but the three-dot range has no merge base.
        orphan = git(rng.repo, "commit-tree", EMPTY_TREE, "-m", "unrelated")
        git(rng.repo, "update-ref", "refs/remotes/origin/main", orphan)
        done = subprocess.run([sys.executable, STEP, "main"], cwd=rng.repo, env=direct_step_env(rng, "true"),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, out)
        self.assertIn("stale-cites: unknown", out)


class PinTests(unittest.TestCase):
    """bin/ste-changed LINT_FILES is the pin check's list of files the step runs. It must name each one."""

    def test_lint_files_holds_every_repo_file_the_check_imports(self):
        listed = tuple_named(os.path.join(ROOT, "bin", "ste-changed"), "LINT_FILES")
        needed = repo_modules_imported(MODULE) + paths_loaded_by_path(MODULE) + ["lint/stale_cites.py"]
        self.assertEqual([f for f in needed if f not in listed], [], "bin/ste-changed LINT_FILES lacks these")

    def test_the_py_facts_file_stale_cites_loads_by_path_is_in_lint_files(self):
        self.assertIn("skills/plain-english-map/scripts/lib/py-facts.py", paths_loaded_by_path(MODULE))  # scope
        listed = tuple_named(os.path.join(ROOT, "bin", "ste-changed"), "LINT_FILES")
        self.assertIn("skills/plain-english-map/scripts/lib/py-facts.py", listed,
                      "bin/ste-changed LINT_FILES lacks the py-facts file stale_cites loads by path")


class CostTests(StaleCase):
    """The check's cost is a contract: a few git starts, no markdown read when nothing was removed, no file written."""

    def run_traced(self, rng):
        trace = os.path.join(rng.case, "git-trace.txt")
        rc, out = self.run_check(rng, extra_env={"GIT_TRACE": trace})
        return rc, out, git_subcommands(trace)

    def test_a_range_that_removes_nothing_starts_three_git_reads_and_reads_no_markdown(self):
        def change(repo):
            write(repo, "hooks/new.py", "def fresh():\n    return 5\n")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertLessEqual(len(subs), 3, subs)
        self.assertTrue(set(subs) <= {"rev-parse", "merge-base", "diff"}, subs)

    def test_a_touched_py_that_removes_nothing_starts_four_git_processes_and_lists_no_tree(self):
        def change(repo):
            write(repo, "hooks/guard.py", GUARD.replace("return 1", "return 2"))
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(subs), ["cat-file", "diff", "merge-base", "rev-parse"], subs)
        # ls-tree lists the tracked Markdown, so a run without it reads no .md.
        self.assertNotIn("ls-tree", subs, subs)

    def test_a_lone_json_touch_reads_no_markdown_and_starts_no_ls_tree(self):
        # A JSON value is read by no reader, so a range that touches only a .json file reads no Markdown: it starts no
        # ls-tree, which lists the tracked Markdown. The stale JSON cite below is never read.
        base_cfg, head_cfg = '{"retries": {"max": 4}}\n', '{"retries": {"max": 5}}\n'
        self.assertEqual(json_value(head_cfg, "retries.max"), 5)  # scope: the range changes retries.max to 5
        notes = "# Notes\n\n- retry cap `config.json: retries.max = 4`\n"

        def change(repo):
            write(repo, "config.json", head_cfg)
            commit(repo)
        rc, out, subs = self.run_traced(self.make_range(base_files(notes, extra={"config.json": base_cfg}), change))
        self.assertNotIn("ls-tree", subs, "a range that only touches a .json file must start no ls-tree: %s" % subs)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out, out)

    def test_a_run_that_changes_no_literal_and_touches_no_markdown_reads_no_markdown(self):
        head_guard = GUARD.replace("return 1", "return 2")
        literals = [ast.dump(node) for node in ast.parse(GUARD).body if isinstance(node, ast.Assign)]
        self.assertEqual(literals, [ast.dump(node) for node in ast.parse(head_guard).body if isinstance(node, ast.Assign)],
                         "scope: the range changes no module-level literal")  # scope: head keeps every module-level assignment
        # The base holds a value cite that is wrong and untouched. A run that reads no Markdown never reads it.
        notes = "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 3`\n"

        def change(repo):
            write(repo, "hooks/guard.py", head_guard)
            commit(repo)
        rng = self.make_range(base_files(notes, extra={"hooks/config.py": "LIMIT = 4\n"}), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out, out)
        self.assertNotIn("ls-tree", subs, subs)  # no tracked Markdown is listed, so the untouched cite is never read

    def test_a_range_that_removes_a_path_starts_at_most_five_git_processes(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 1, out)
        self.assertLessEqual(len(subs), 5, subs)

    def test_a_module_assignment_changed_between_a_call_and_a_literal_reads_no_markdown(self):
        # The reader compares module-level literals. A call is no literal, so a change between a call and a literal
        # starts no ls-tree, in either direction. The scope asserts fix the two sides before the probe.
        calls, literal = 'FOO = os.path.join("a", "b")\n', 'FOO = "c"\n'
        self.assertIsInstance(ast.parse(calls).body[0].value, ast.Call)  # scope: one side is a call
        with self.assertRaises(ValueError):
            ast.literal_eval(ast.parse(calls).body[0].value)  # scope: a call is no literal
        self.assertEqual(ast.literal_eval(ast.parse(literal).body[0].value), "c")  # scope: the other side is a literal
        for base_src, head_src in ((calls, literal), (literal, calls)):
            with self.subTest(base=base_src, head=head_src):
                def change(repo, head_src=head_src):
                    write(repo, "hooks/paths.py", head_src)
                    commit(repo)
                rc, out, subs = self.run_traced(self.make_range(base_files(extra={"hooks/paths.py": base_src}), change))
                self.assertNotIn("ls-tree", subs, "a change between a call and a literal is no literal change, so no ls-tree: %s" % subs)
                self.assertEqual(rc, 0, out)

    def test_a_comment_only_python_change_starts_no_ls_tree(self):
        # A comment is not in the syntax tree, so a change to a comment moves no literal and starts no ls-tree.
        base_src = "LIMIT = 4  # the cap\n\n\ndef keep():\n    return 1\n"
        head_src = "LIMIT = 4  # the cap, reviewed\n\n\ndef keep():\n    return 1\n"
        self.assertNotEqual(base_src, head_src)  # scope: the file changed
        self.assertEqual(ast.dump(ast.parse(base_src)), ast.dump(ast.parse(head_src)))  # scope: only a comment differs

        def change(repo):
            write(repo, "hooks/config.py", head_src)
            commit(repo)
        rc, out, subs = self.run_traced(self.make_range(base_files(extra={"hooks/config.py": base_src}), change))
        self.assertNotIn("ls-tree", subs, "a comment-only change must start no ls-tree: %s" % subs)
        self.assertEqual(rc, 0, out)

    def test_a_touched_markdown_with_a_python_change_that_moves_no_literal_reads_only_that_markdown(self):
        # Only a changed literal or a removed name reads every tracked Markdown file. Here the Python change moves no
        # literal, so the run reads the touched NOTES and no other file. The untouched file cites a JavaScript value,
        # which prints unknown only in a run that reads that file. The JavaScript file is touched, so that cite is judged.
        other = "docs/other.md"
        config = "LIMIT = 4\n\n\ndef keep():\n    return 1\n"
        self.assertEqual(assigned_value(config, "LIMIT"), assigned_value(config.replace("return 1", "return 2"), "LIMIT"))  # scope: LIMIT holds
        base = base_files("# Notes\n", extra={"hooks/config.py": config, "hooks/lib.mjs": "export const LIMIT = 4;\n",
                                              other: "- limit `hooks/lib.mjs: LIMIT = 4`\n"})

        def change(repo):
            write(repo, "hooks/config.py", config.replace("return 1", "return 2"))
            write(repo, "hooks/lib.mjs", "export const LIMIT = 4; // reviewed\n")
            write(repo, NOTES, "# Notes\n\nA new prose line.\n")
            commit(repo)
        rc, out, subs = self.run_traced(self.make_range(base, change))
        self.assertNotIn("ls-tree", subs, "a Python change that moves no literal must start no ls-tree: %s" % subs)
        self.assertFalse(any(line.startswith("stale-cites: unknown") and other in line for line in out.splitlines()),
                         "the untouched %s must not be read, so no unknown may name it\n%s" % (other, out))
        self.assertEqual(rc, 0, out)

    def test_a_run_writes_no_file_in_the_repo_or_next_to_the_script(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        self.assert_run_writes_no_file(change)

    def test_a_touched_py_that_loads_py_facts_writes_no_file_next_to_it(self):
        def change(repo):
            write(repo, "hooks/guard.py", GUARD.replace("return 1", "return 2"))
            commit(repo)
        self.assert_run_writes_no_file(change)

    def assert_run_writes_no_file(self, change):
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        # Run a copy of the script's folders, so any file the run writes next to the script shows here.
        # skills/ holds py-facts, which a touched .py loads by path.
        scripts = os.path.join(rng.case, "scripts")
        tracked_tree.copy_tracked(scripts, "lint", "hooks", "skills")
        before = (paths_under(rng.repo), paths_under(scripts))
        env = dict(os.environ, TMPDIR=rng.case)
        env.pop("PYTHONDONTWRITEBYTECODE", None)  # a set variable would hide a .pyc the run writes
        env.pop("PYTHONPYCACHEPREFIX", None)
        done = subprocess.run([sys.executable, os.path.join(scripts, "lint", "stale_cites.py"),
                               "--range", "%s...%s" % (rng.base, rng.head)],
                              cwd=rng.repo, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = done.stdout + done.stderr
        self.assertIn(done.returncode, (0, 1), out)
        self.assertEqual((paths_under(rng.repo), paths_under(scripts)), before, out)


class UnknownFileTests(StaleCase):
    """A touched .py that does not parse cannot say which names it defines: unknown, named, never a silent pass."""

    def test_a_touched_py_that_does_not_parse_is_unknown_and_exits_zero(self):
        cases = (
            ("head", GUARD, "def keep(:\n    return 1\n"),
            ("base", "def keep(:\n    return 1\n", GUARD),
        )
        for side, base_src, head_src in cases:
            with self.subTest(unparseable_at=side):
                def change(repo, head_src=head_src):
                    write(repo, "hooks/guard.py", head_src)
                    commit(repo)
                rng = self.make_range(base_files(extra={"hooks/guard.py": base_src}), change)
                rc, out = self.run_check(rng)
                unknown = [line for line in out.splitlines() if line.startswith("stale-cites: unknown")]
                self.assertEqual(rc, 0, out)
                self.assertTrue(unknown, out)
                self.assertIn("hooks/guard.py", unknown[0], out)


class ExcludeFolderTests(StaleCase):
    """A bare folder line in .ste-lint-exclude leaves out the files under it, as `vendor/**` does."""

    def test_a_bare_folder_line_leaves_out_the_files_under_it(self):
        for line in ("vendor", "vendor/"):
            with self.subTest(line=line):
                def change(repo):
                    move(repo, "hooks/lib.mjs", MOVED)
                    commit(repo)
                extra = {".ste-lint-exclude": line + "\n", "vendor/a.md": "- refusal list in `hooks/lib.mjs`\n"}
                self.assert_passes(self.make_range(base_files(extra=extra), change))


if __name__ == "__main__":
    unittest.main()
