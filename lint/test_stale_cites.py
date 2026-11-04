#!/usr/bin/env python3
"""Cases for lint/stale_cites.py. Standard library only.

    python3 lint/test_stale_cites.py

The merge check refuses stale prose. A tracked Markdown line that names a repo path the range deleted
or renamed is STALE001. A `<file.py> <name>` pair on one line is STALE002 when the name was bound at module
level in that file at base (a def, class, assignment or import) and is not bound there at head. Each finding
is one line, `path:line: CODE message`.
A clean run prints `stale-cites: PASS` and exits 0.
The report (decision stale-cites-at-merge) prints after the findings and never changes the exit code. It names
each anchor whose sentence changed in CLAUDE.md or the output style, with its rule_mechanisms.json row and the changed
files under hooks/, lint/, bin/, actions/ and .github/ (no touched or untouched verdict), and each changed code file
with the decisions whose Home names it and the rows that name it.

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
FINDING = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): (?P<code>STALE00[12]) (?P<text>.*)$")


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


def git_commands(trace_path):
    """The git commands a run started, read from a GIT_TRACE file: each `built-in: git <args>` line, args only."""
    commands = []
    with open(trace_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            found = re.search(r"trace: built-in: git (.+)$", line)
            if found:
                commands.append(found.group(1).strip())
    return commands


def git_subcommands(trace_path):
    """The git subcommands a run started: the first word of each command in the GIT_TRACE file."""
    return [command.split()[0] for command in git_commands(trace_path)]


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

    def run_traced_commands(self, rng):
        """(rc, out, the git commands a run started), read from a GIT_TRACE file."""
        trace = os.path.join(rng.case, "git-trace.txt")
        rc, out = self.run_check(rng, extra_env={"GIT_TRACE": trace})
        return rc, out, git_commands(trace)

    def run_traced(self, rng):
        rc, out, commands = self.run_traced_commands(rng)
        return rc, out, [command.split()[0] for command in commands]

    def test_a_range_that_removes_nothing_starts_at_most_four_git_reads_with_one_ls_tree(self):
        def change(repo):
            write(repo, "hooks/new.py", "def fresh():\n    return 5\n")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        # A changed code file also reads its Home lines: one ls-tree of docs/decisions, the only start it adds.
        # No decision blob is read here, so the cat-file the .py cases open is not started.
        self.assertEqual(subs.count("ls-tree"), 1, subs)
        self.assertLessEqual(len(subs), 4, subs)
        self.assertTrue(set(subs) <= {"rev-parse", "merge-base", "diff", "ls-tree"}, subs)

    def test_a_touched_py_that_removes_nothing_starts_five_git_processes_with_one_ls_tree_of_the_decisions(self):
        def change(repo):
            write(repo, "hooks/guard.py", GUARD.replace("return 1", "return 2"))
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        subs = [command.split()[0] for command in commands]
        # The one start a code change adds is the ls-tree of docs/decisions, never of the whole tree: it lists no .md
        # beyond the decision folder. The cat-file is the one the .py already opened, so it adds no start.
        self.assertEqual(sorted(subs), ["cat-file", "diff", "ls-tree", "merge-base", "rev-parse"], subs)
        listing = [command for command in commands if command.startswith("ls-tree")]
        self.assertTrue(listing, commands)
        self.assertIn("docs/decisions", listing[0], commands)

    def test_a_changed_non_python_non_markdown_file_starts_one_ls_tree_and_one_cat_file_for_its_decisions(self):
        extra = decisions(("tool-home-record", "config/tool.toml"))

        def change(repo):
            write(repo, "config/tool.toml", "mode = 2\n")
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        # Pins the count for a changed file that is neither Markdown nor Python: the Home half starts one ls-tree of
        # docs/decisions and one cat-file that reads each decision's blob, and no other git start.
        subs = [command.split()[0] for command in commands]
        self.assertEqual(sorted(subs), ["cat-file", "diff", "ls-tree", "merge-base", "rev-parse"], subs)
        listing = [command for command in commands if command.startswith("ls-tree")]
        self.assertTrue(listing, commands)
        self.assertIn("docs/decisions", listing[0], commands)

    def test_a_range_that_removes_a_path_starts_at_most_five_git_processes(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 1, out)
        self.assertLessEqual(len(subs), 5, subs)

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

    def test_an_anchor_only_edit_starts_a_pinned_count_of_git_processes_and_no_ls_tree_of_hooks(self):
        # Pinned to the count the report starts today for an edit to CLAUDE.md alone, measured with GIT_TRACE. No code
        # file changed, so the report reads the rule file's blobs and the mechanisms file, and no ls-tree names hooks/.
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        mech = mechanisms({"git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"}})

        def change(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: mech}), change)
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(commands), 4, commands)  # PINNED: today's count for this edit
        self.assertFalse(any(command.startswith("ls-tree") and "hooks/" in command for command in commands), commands)

    def test_an_anchor_edit_with_a_code_change_starts_at_most_one_more_git_process(self):
        # The code change may add one start on top of the anchor-only count: the ls-tree of the decisions folder.
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        mech = mechanisms({"git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"}})
        extra = {CLAUDE: base_claude, MECH: mech}

        def anchor_only(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)

        def anchor_and_code(repo):
            write(repo, CLAUDE, head_claude)
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        _, _, alone = self.run_traced_commands(self.make_range(base_files(extra=extra), anchor_only))
        rc, out, commands = self.run_traced_commands(self.make_range(base_files(extra=extra), anchor_and_code))
        self.assertEqual(rc, 0, out)
        self.assertLessEqual(len(commands), len(alone) + 1, "%s\nanchor only: %s" % (commands, alone))


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


CLAUDE = "CLAUDE.md"
MECH = "lint/rule_mechanisms.json"
GUARD_EDIT = GUARD.replace("return 1", "return 2")  # a status M change to hooks/guard.py
TOUCHED = re.compile(r"(?<!un)touched")
UNTOUCHED = re.compile(r"\buntouched\b")
GUARD_KIND = re.compile(r"(?<![\w/.-])guard(?![\w/.-])")  # the word, never a part of a path such as hooks/guard.py


def named(text, token):
    """True when `token` appears whole: no word character or hyphen on either side of it."""
    return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(token), text) is not None


def slug_lines(out, slug):
    """Each report line that names the anchor slug or the decision stem `slug`."""
    return [line for line in out.splitlines() if named(line, slug)]


def mechanisms(rows):
    """lint/rule_mechanisms.json in the repo's shape: {"rules": {slug: {"mechanism": {...}}}}."""
    return json.dumps({"rules": {slug: {"mechanism": m} for slug, m in rows.items()}}, indent=2) + "\n"


def decisions(*pairs, folder="docs/decisions"):
    """Decision records under `folder`, one per (stem, Home) pair, each with the one Home line the repo writes."""
    return {"%s/%s.md" % (folder, stem): "# %s\n\n## The ruling\n\nA fixture ruling.\n\nKind: build\nHome: %s\n"
            % (stem, home) for stem, home in pairs}


def touched(rng):
    """The paths the range changed. A case asserts this first, so the scope it probes is the one it claims."""
    return set(git(rng.repo, "diff", "--name-only", rng.base, rng.head).split())


NONE = re.compile(r"\bnone\b")


class ReportTests(StaleCase):
    """The report: an anchor edit names its guard or check row and the changed files under the rule dirs; a changed
    code file lists the decisions whose Home names it. A repo with no mechanisms file gets the Home half only."""

    def test_anchor_edit_prints_its_guard_row_and_none_when_no_rule_dir_changed(self):
        # Re-pointed from "holder untouched": a guard row's logic can sit in another module (guard_kill.py and similar),
        # so the report prints no verdict. It prints the row, then the changed files under the rule dirs: none here.
        base_claude = ("Never merge failing CI. <!-- rule:git-never-merge-failing-ci --> "
                       "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n")
        head_claude = ("Never merge failing CI. <!-- rule:git-never-merge-failing-ci --> "
                       "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n")
        mech = mechanisms({
            "git-never-merge-failing-ci": {"kind": "check", "ref": "lint/x.py", "test": "lint/test_x.py::test_check"},
            "git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"},
        })

        def change(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: mech}), change)
        self.assertEqual(touched(rng), {CLAUDE}, "scope: only CLAUDE.md changed, so the guard's holder is untouched")
        rc, out = self.run_check(rng)
        lines = slug_lines(out, "git-main-only-by-pr")
        ref_lines = [line for line in lines if "main-moves-by-pull-request" in line]
        self.assertTrue(ref_lines, "the report names no guard for the edited anchor git-main-only-by-pr\n" + out)
        self.assertTrue(any(GUARD_KIND.search(line) for line in ref_lines),
                        "the guard line for git-main-only-by-pr does not say its kind is guard\n" + out)
        self.assertFalse(any("touched" in line for line in ref_lines),
                         "the guard line for git-main-only-by-pr gives a touched verdict\n" + out)
        self.assertTrue(any(NONE.search(line) for line in ref_lines),
                        "the guard line for git-main-only-by-pr does not say no rule dir changed\n" + out)
        self.assertEqual(slug_lines(out, "git-never-merge-failing-ci"), [],
                         "an anchor whose sentence did not change is named\n" + out)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)

    def test_anchor_edit_lists_the_changed_rule_dir_file_and_prints_no_verdict(self):
        # Re-pointed from "says touched" for a check row whose ref is the changed file. The row's ref now names
        # lint/x.py, which this range does not change, so a hooks/ file in the anchor line can only come from the
        # changed-files list, not from the row.
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        mech = mechanisms({"git-main-only-by-pr": {"kind": "check", "ref": "lint/x.py",
                                                   "test": "lint/test_x.py::test_check"}})

        def change(repo):
            write(repo, CLAUDE, head_claude)
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: mech}), change)
        self.assertEqual(touched(rng), {CLAUDE, "hooks/guard.py"},
                         "scope: the range changes the anchor's file and a file under hooks/")
        rc, out = self.run_check(rng)
        lines = slug_lines(out, "git-main-only-by-pr")
        self.assertTrue(any("hooks/guard.py" in line for line in lines),
                        "the anchor line does not list the changed file under hooks/\n" + out)
        self.assertFalse(any("touched" in line for line in lines),
                         "the anchor line gives a touched or untouched verdict\n" + out)
        self.assertEqual(rc, 0, out)

    def test_code_change_lists_each_decision_whose_home_names_the_file(self):
        extra = decisions(("guard-home-first", "hooks/guard.py"), ("guard-home-second", "hooks/guard.py"))

        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        self.assertEqual(touched(rng), {"hooks/guard.py"}, "scope: only the code file changed")
        rc, out = self.run_check(rng)
        for stem in ("guard-home-first", "guard-home-second"):
            self.assertTrue(named(out, stem), "the report does not list %s, whose Home names hooks/guard.py\n%s"
                            % (stem, out))
        self.assertEqual(rc, 0, out)

    def test_a_home_on_a_longer_path_or_another_file_does_not_list_the_file(self):
        extra = decisions(("guard-home-exact", "hooks/guard.py"),
                          ("guard-home-longer", "mods/session-board/hooks/guard.py"),
                          ("guard-home-core", "hooks/guard_core.py"))

        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        self.assertEqual(touched(rng), {"hooks/guard.py"}, "scope: only the code file changed")
        rc, out = self.run_check(rng)
        self.assertTrue(named(out, "guard-home-exact"),
                        "the report does not list guard-home-exact, Home hooks/guard.py\n" + out)
        self.assertFalse(named(out, "guard-home-longer"),
                         "a Home on mods/session-board/hooks/guard.py lists hooks/guard.py\n" + out)
        self.assertFalse(named(out, "guard-home-core"), "a Home on hooks/guard_core.py lists hooks/guard.py\n" + out)
        self.assertEqual(rc, 0, out)

    def test_a_check_row_whose_ref_is_the_changed_file_is_listed_and_another_ref_is_not(self):
        mech = mechanisms({
            "guard-row-listed": {"kind": "check", "ref": "hooks/guard.py", "test": "hooks/test_guard.py::test_main"},
            "guard-row-other": {"kind": "check", "ref": "lint/x.py", "test": "lint/test_x.py::test_check"},
        })

        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra={MECH: mech}), change)
        self.assertEqual(touched(rng), {"hooks/guard.py"}, "scope: only the code file changed")
        rc, out = self.run_check(rng)
        self.assertTrue(named(out, "guard-row-listed"), "the report does not list the row whose ref is hooks/guard.py\n"
                        + out)
        self.assertFalse(named(out, "guard-row-other"), "the report lists a row whose ref is lint/x.py\n" + out)
        self.assertEqual(rc, 0, out)

    def test_child_repo_without_a_mechanisms_file_lists_the_home_decisions_and_no_error(self):
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        extra = {CLAUDE: base_claude, **decisions(("guard-home-first", "hooks/guard.py"))}

        def change(repo):
            write(repo, CLAUDE, head_claude)
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        self.assertEqual(touched(rng), {CLAUDE, "hooks/guard.py"}, "scope: the anchor's file and a code file changed")
        rc, out = self.run_check(rng)
        self.assertTrue(named(out, "guard-home-first"),
                        "the Home half is not printed in a repo with no rule_mechanisms.json\n" + out)
        self.assertFalse(named(out, "git-main-only-by-pr"),
                         "an anchor section prints in a repo with no mechanisms file\n" + out)
        self.assertNotIn("UNKNOWN", out, out)
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(rc, 0, out)

    def test_child_repo_anchor_edit_with_no_mechanisms_file_prints_no_anchor_section_and_no_error(self):
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"

        def change(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude}), change)
        self.assertEqual(touched(rng), {CLAUDE}, "scope: only the anchor's file changed")
        rc, out = self.run_check(rng)
        self.assertFalse(named(out, "git-main-only-by-pr"),
                         "an anchor section prints in a repo with no mechanisms file\n" + out)
        self.assertNotIn("UNKNOWN", out, out)
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)

    def test_report_lines_leave_the_finding_list_and_the_exit_code_as_they_were(self):
        extra = decisions(("guard-home-first", "hooks/guard.py"))

        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n", extra=extra), change)
        self.assertIn("hooks/guard.py", touched(rng), "scope: the range removes a path and changes the code file")
        rc, out = self.run_check(rng)
        self.assertTrue(named(out, "guard-home-first"),
                        "the report does not list guard-home-first beside a finding\n" + out)
        self.assertEqual(rc, 1, out)
        self.assertEqual([(p, n, c) for p, n, c, _ in parse(out)], [(NOTES, 3, "STALE001")],
                         "the finding list changed: report lines must not match a finding\n" + out)
        self.assertIn("FAIL, 1 finding(s)", out)

    def test_step_summary_lists_the_home_decisions_on_a_code_only_pr(self):
        extra = decisions(("guard-home-first", "hooks/guard.py"))

        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        git(rng.repo, "update-ref", "refs/remotes/origin/main", rng.base)  # the base the step diffs against
        done = subprocess.run([BASH, STEP_SH], cwd=rng.repo, env=direct_step_env(rng, "true"),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = done.stdout + done.stderr
        summary_path = os.path.join(rng.case, "summary.md")
        summary = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
        self.assertTrue(named(summary, "guard-home-first"), "the step summary does not list guard-home-first\n"
                        + summary + out)
        self.assertEqual(done.returncode, 0, out)

    def test_a_code_span_anchor_and_a_lone_quote_do_not_hide_the_real_anchor(self):
        base_claude = ("Write `<!-- rule:fake -->` here. Don't stop there. Main moves only by pull request. "
                       "<!-- rule:git-main-only-by-pr -->\n")
        head_claude = ("Write `<!-- rule:fake -->` here. Don't stop there. Main moves only by a reviewed pull request. "
                       "<!-- rule:git-main-only-by-pr -->\n")
        mech = mechanisms({"git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"}})

        def change(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: mech}), change)
        self.assertEqual(touched(rng), {CLAUDE}, "scope: only CLAUDE.md changed")
        rc, out = self.run_check(rng)
        ref_lines = [line for line in slug_lines(out, "git-main-only-by-pr") if "main-moves-by-pull-request" in line]
        # Re-pointed from "named as untouched": the report prints no verdict, only the changed rule-dir files, and
        # this range changes none of them, so the line says none.
        self.assertTrue(any(NONE.search(line) for line in ref_lines),
                        "the real anchor git-main-only-by-pr is not named past a code span and a quote, "
                        "with none changed\n" + out)
        self.assertFalse(named(out, "fake"), "the unchanged anchor in a code span is named\n" + out)
        self.assertEqual(rc, 0, out)

    def test_a_backticked_anchor_is_a_mention_and_only_a_real_anchor_is_named(self):
        base_claude = ("Write `<!-- rule:fake -->` to cite an anchor.\n"
                       "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n")
        head_claude = ("Write `<!-- rule:fake -->` to cite an anchor in prose.\n"
                       "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n")
        mech = mechanisms({
            "fake": {"kind": "guard", "ref": "fake-guard"},
            "git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"},
        })

        def change(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: mech}), change)
        self.assertEqual(touched(rng), {CLAUDE}, "scope: only CLAUDE.md changed; the mention's sentence changed too")
        rc, out = self.run_check(rng)
        ref_lines = [line for line in slug_lines(out, "git-main-only-by-pr") if "main-moves-by-pull-request" in line]
        # Re-pointed from "named as untouched": no verdict is printed, so the line is checked for its changed-files list.
        self.assertTrue(any(NONE.search(line) for line in ref_lines),
                        "the real anchor git-main-only-by-pr is not named with none changed\n" + out)
        self.assertFalse(named(out, "fake") or "fake-guard" in out,
                         "a backticked mention, `<!-- rule:fake -->`, is named as an anchor\n" + out)
        self.assertEqual(rc, 0, out)

    def test_a_malformed_mechanisms_file_prints_one_unknown_line_and_keeps_the_exit_code(self):
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        base_mech = mechanisms({"git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"}})
        malformed = (
            ("a top-level list", "[]\n"),
            ("a row that is a string", json.dumps({"rules": {"git-main-only-by-pr": "guard"}}) + "\n"),
            ("a row that is null", json.dumps({"rules": {"git-main-only-by-pr": None}}) + "\n"),
        )
        for label, text in malformed:
            with self.subTest(malformed=label):
                def change(repo, text=text):
                    write(repo, CLAUDE, head_claude)
                    write(repo, "hooks/guard.py", GUARD_EDIT)
                    write(repo, MECH, text)
                    commit(repo)
                rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: base_mech}), change)
                self.assertEqual(touched(rng), {CLAUDE, "hooks/guard.py", MECH},
                                 "scope: the anchor, a code file and the mechanisms file changed")
                rc, out = self.run_check(rng)
                unknown = [line for line in out.splitlines() if line.startswith("stale-cites: unknown")]
                self.assertEqual(len(unknown), 1, "a malformed mechanisms file must print one unknown line\n" + out)
                self.assertIn(MECH, unknown[0], "the unknown line does not name the mechanisms file\n" + out)
                self.assertEqual(rc, 0, "a malformed mechanisms file changed the exit code\n" + out)
                self.assertNotIn("Traceback", out, out)

    def test_a_reworded_guard_anchor_lists_only_its_changed_hooks_file(self):
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        mech = mechanisms({"git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"}})
        extra = {CLAUDE: base_claude, MECH: mech, "hooks/guard.py": GUARD_REFUSE, "hooks/guard_stream.py": STREAM}

        def change(repo):
            write(repo, CLAUDE, head_claude)
            write(repo, "hooks/guard_stream.py", STREAM.replace("return 4", "return 5"))
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        self.assertEqual(touched(rng), {CLAUDE, "hooks/guard_stream.py"},
                         "scope: hooks/guard.py, which holds the refuse() call, is untouched")
        rc, out = self.run_check(rng)
        lines = slug_lines(out, "git-main-only-by-pr")
        # Re-pointed from "names hooks/guard.py untouched as the holder": the report names no holder. Its changed-files
        # list holds the changed hooks/ file, and it does not list the unchanged module that holds the refuse() call.
        self.assertTrue(any("hooks/guard_stream.py" in line for line in lines),
                        "the anchor line does not list the changed hooks/ file\n" + out)
        self.assertFalse(any("hooks/guard.py" in line for line in lines),
                         "the anchor line lists hooks/guard.py, which this range does not change\n" + out)
        self.assertFalse(any("touched" in line or "holder" in line for line in lines),
                         "the anchor line gives a holder or touched verdict\n" + out)
        self.assertEqual(rc, 0, out)

    def test_child_repo_with_decisions_in_a_decisions_folder_prints_the_home_line_for_a_changed_file(self):
        # A repo not rolled out to the layout keeps its decisions at decisions/, the layout's legacy path.
        extra = decisions(("guard-home-first", "hooks/guard.py"), folder="decisions")

        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        self.assertEqual(touched(rng), {"hooks/guard.py"}, "scope: only the code file changed")
        rc, out = self.run_check(rng)
        self.assertTrue(named(out, "guard-home-first"),
                        "the report does not list a decision in decisions/ whose Home names hooks/guard.py\n" + out)
        self.assertEqual(rc, 0, out)


# A guard module whose refuse() call names the rule: rule_audit reads the rule id from the third argument.
GUARD_REFUSE = GUARD + "\n\ndef gate(ctx):\n    return refuse(ctx, 'no push to main', 'main-moves-by-pull-request')\n"
STREAM = "def stream():\n    return 4\n"


if __name__ == "__main__":
    unittest.main()
