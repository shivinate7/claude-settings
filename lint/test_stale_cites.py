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
STALE005 (range mode only) reports an added governed line that states a capability by route with no backing. It is
report only: the exit code does not change (RouteClaimTests).


`--tree [REV]` reads every tracked Markdown file at REV instead of a range: STALE003 for a path cite that names
nothing tracked, STALE004 for a line anchor past the file's end (TreeTests, CostTests).

Each case makes a temp git repo: the base commit on `main`, the head commit on `topic`. The check runs
with the repo as cwd and the range as commit ids. The step cases run bin/ste-changed, which runs
actions/ste-lint/run.sh with the step's env. TMPDIR is the case folder, so temp files stay in the run folder.
"""
import ast
import atexit
import collections
import importlib.util
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
FINDING = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): (?P<code>STALE00[1-46]) (?P<text>.*)$")


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


SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)  # names inside are not module level


def module_bindings(source):
    """(kind, name) for each name a Python source binds at module level, under any statement that is no def or
    class: "def" for a def or class, "import", or "assign" for each name stored. Read with ast, never imported."""
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.append(("def", child.name))
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                found.extend(("import", alias.asname or alias.name.split(".")[0]) for alias in child.names)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                found.append(("assign", child.id))
            elif not isinstance(child, SCOPES):
                visit(child)
    visit(ast.parse(source))
    return found


def binding_kind(source, name):
    """How a Python source binds `name` at module level: "def", "assign", "import", or None. The last binding
    counts. A case asserts this on its fixtures before it probes the check on the name."""
    kinds = [kind for kind, bound in module_bindings(source) if bound == name]
    return kinds[-1] if kinds else None


def unknown_lines(out):
    """Each line the check printed as unknown."""
    return [line for line in out.splitlines() if line.startswith("stale-cites: unknown, ")]


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

    def run_traced_commands(self, rng):
        """(rc, out, the git commands a run started), read from a GIT_TRACE file."""
        trace = os.path.join(rng.case, "git-trace.txt")
        rc, out = self.run_check(rng, extra_env={"GIT_TRACE": trace})
        return rc, out, git_commands(trace)

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

    def run_tree(self, rng, rev=None, extra_env=None):
        """`--tree [rev]` in the repo: (exit code, output). EXCLUDE from the caller's environment is dropped, so
        only a case that sets EXCLUDE sees one."""
        env = dict(os.environ, TMPDIR=rng.case)
        env.pop("EXCLUDE", None)
        env.update(extra_env or {})
        args = [sys.executable, MODULE, "--tree"] + ([rev] if rev else [])
        done = subprocess.run(args, cwd=rng.repo, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        return done.returncode, done.stdout + done.stderr

    def tree(self, notes, extra=None):
        """A repo whose HEAD holds `notes` as the NOTES page, the CODE files and `extra`. Nothing is removed."""
        return self.make_range(base_files(notes, extra=extra), lambda repo: None)

    def assert_tree_flags(self, rng, expected, rev=None, extra_env=None):
        """The findings are exactly `expected`, as (path, line, code), the verdict is FAIL and the exit is 1.
        Returns the findings."""
        rc, out = self.run_tree(rng, rev, extra_env)
        found = parse(out)
        self.assertEqual(sorted((p, n, c) for p, n, c, _ in found), sorted(expected), out)
        self.assertIn("stale-cites: FAIL, %d finding(s)" % len(expected), out)
        self.assertEqual(rc, 1, out)
        return found

    def assert_tree_passes(self, rng, rev=None, extra_env=None):
        """The verdict is PASS, the exit is 0 and no finding prints."""
        rc, out = self.run_tree(rng, rev, extra_env)
        self.assertIn("stale-cites: PASS", out)
        self.assertEqual(rc, 0, out)
        self.assertEqual(parse(out), [], out)

    def run_copy_of_script(self, rng, args):
        """Run a copy of the script's folders with `args` in the repo. Returns (exit code, output, the files before,
        the files after), so a file the run writes in the repo or beside the script shows as a change."""
        scripts = os.path.join(rng.case, "scripts")
        tracked_tree.copy_tracked(scripts, "lint", "hooks", "skills")
        before = (paths_under(rng.repo), paths_under(scripts))
        env = dict(os.environ, TMPDIR=rng.case)
        env.pop("PYTHONDONTWRITEBYTECODE", None)  # a set variable would hide a .pyc the run writes
        env.pop("PYTHONPYCACHEPREFIX", None)
        done = subprocess.run([sys.executable, os.path.join(scripts, "lint", "stale_cites.py")] + args,
                              cwd=rng.repo, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        after = (paths_under(rng.repo), paths_under(scripts))
        return done.returncode, done.stdout + done.stderr, before, after


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
        self.assert_passes(self.make_range(base_files("# Notes\n\n- the guard is in `hooks/guard`\n"), change))

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

    def assert_bound_name_not_flagged(self, path, name, base_src, head_src):
        """Base and head both bind `name` at module level, so a note that cites it in `path` passes."""
        self.assertIsNotNone(binding_kind(base_src, name), "scope: base does not bind %s" % name)
        self.assertIsNotNone(binding_kind(head_src, name), "scope: head does not bind %s" % name)
        notes = "# Notes\n\n- `%s` `%s`\n" % (path, name)

        def change(repo):
            write(repo, path, head_src)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={path: base_src}), change))

    def test_a_name_moved_under_any_module_level_compound_statement_is_not_flagged(self):
        base_mod = "X = 1\n\n\ndef keep():\n    return 1\n"
        blocks = {
            "with": "with open(path) as fh:\n    X = 1\n",
            "for": "for item in items:\n    X = 1\n",
            "while": "while running:\n    X = 1\n",
            "match": "match mode:\n    case 1:\n        X = 1\n",
            "except": "try:\n    pass\nexcept ValueError:\n    X = 1\n",
            "for else": "for item in items:\n    pass\nelse:\n    X = 1\n",
            "finally": "try:\n    pass\nfinally:\n    X = 1\n",
        }
        for kind, block in blocks.items():
            with self.subTest(kind=kind):
                self.assert_bound_name_not_flagged("hooks/mod.py", "X", base_mod,
                                                   block + "\n\ndef keep():\n    return 1\n")

    def test_a_name_still_bound_by_a_tuple_for_with_or_walrus_target_is_not_flagged(self):
        base_mod = "X = 1\n\n\ndef keep():\n    return 1\n"
        forms = {
            "tuple": "X, Y = 1, 2\n",
            "for": "for X in range(2):\n    pass\n",
            "with": "with open(path) as X:\n    pass\n",
            "walrus": "(X := 3)\n",
        }
        for form, statement in forms.items():
            with self.subTest(form=form):
                self.assert_bound_name_not_flagged("hooks/mod.py", "X", base_mod,
                                                   statement + "\n\ndef keep():\n    return 1\n")


    def test_route_claim_node_id_cite_of_a_removed_test_is_flagged_stale002(self):
        base_src = "def case_y():\n    return 1\n\n\ndef keep():\n    return 2\n"
        head_src = "def keep():\n    return 2\n"

        def change(repo):
            write(repo, "lint/test_x.py", head_src)
            write(repo, NOTES, "# Notes\n\n- the case is `lint/test_x.py::case_y`\n"
                               "- the case is `lint/test_x.py::keep`\n")
            commit(repo)
        rng = self.make_range(base_files(extra={"lint/test_x.py": base_src}), change)
        self.assertEqual(binding_kind(base_src, "case_y"), "def")  # scope: bound at base, unbound at head
        self.assertIsNone(binding_kind(head_src, "case_y"))
        self.assert_flags(rng, [(NOTES, 3, "STALE002")])


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
    """The check's cost is a contract. A range that removes or renames no path, and changes only Markdown outside
    the rule files, starts three git processes and reads no blob, or one more when it adds a governed line: STALE005
    reads the added lines once. A removed or renamed path makes the check read the
    tracked Markdown files. So does a name that a touched .py no longer defines. A changed file that is not Markdown
    also reads the repo's decision records for its Home line, even when nothing was removed. No run writes a file."""

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

    def test_a_range_that_edits_only_a_non_rule_markdown_file_starts_exactly_three_git_processes_and_reads_no_blob(self):
        def change(repo):
            write(repo, NOTES, "# Notes\n\n- a debt note, edited\n")
            commit(repo)
        rng = self.make_range(base_files(), change)
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        subs = [command.split()[0] for command in commands]
        # No added line holds a claim candidate, so no blob is read: the three starts of the check, exactly.
        self.assertEqual(len(subs), 3, subs)
        self.assertNotIn("cat-file", subs, subs)
        self.assertTrue(set(subs) <= {"diff", "merge-base", "rev-parse"}, subs)

    def test_a_touched_py_that_removes_nothing_starts_five_git_processes_with_one_ls_tree_of_the_decisions(self):
        """Guards the code-only pin: the report's backing scan reuses the reads home_report already makes (the decisions
        ls-tree and cat-file), so this range starts no git process beyond the pinned five. The exact pin stays."""
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
        """Guards the code-only pin: the report's backing scan reuses the reads home_report already makes (the decisions
        ls-tree and cat-file), so this range starts no git process beyond the pinned five. The exact pin stays."""
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

    def test_a_lone_touched_mjs_starts_four_git_processes_with_the_reports_ls_tree_and_prints_no_unknown_line(self):
        """Guards the code-only pin: the report's backing scan reuses the reads home_report already makes (the decisions
        ls-tree and cat-file), so this range starts no git process beyond the pinned four. The exact pin stays."""
        def change(repo):
            write(repo, "hooks/lib.mjs", LIB + "export const more = 1;\n")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- `hooks/lib.mjs` `refusals`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(unknown_lines(out), [], out)
        # The three starts of the check, plus the one ls-tree the report's Home half adds for a changed code file.
        self.assertEqual(sorted(subs), ["diff", "ls-tree", "merge-base", "rev-parse"], subs)

    def test_a_range_that_removes_a_path_starts_at_most_five_git_processes(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 1, out)
        self.assertLessEqual(len(subs), 5, subs)

    def test_route_claim_markdown_only_range_with_a_claim_candidate_starts_exactly_four_git_processes(self):
        text, flagged = rows_text([
            ("# Notes", False),
            ("- The cloud cannot push to main (route cloud-push).", False),  # backed by a row: silent
            ("- The classifier cannot push to main.", True),
        ])

        def change(repo):
            write(repo, NOTES, text)
            commit(repo)
        rng = self.make_range(base_files(extra={ROUTE_ROWS: route_rows_text("cloud-push")}), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(stale005_lines(out, NOTES), flagged, out)  # the check ran: the unbacked line prints
        # The three starts of a Markdown-only range, and one cat-file that reads the added lines' blob.
        self.assertEqual(len(subs), 4, subs)

    def test_route_claim_read_backing_checks_its_file_in_the_same_git_start(self):
        text, flagged = rows_text([
            ("# Notes", False),
            ("- The cloud cannot push to main (read hooks/guard.py:2).", False),  # the file exists at head: silent
            ("- The cloud cannot merge to main.", True),
        ])

        def change(repo):
            write(repo, NOTES, text)
            commit(repo)
        rng = self.make_range(base_files(), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(stale005_lines(out, NOTES), flagged, out)  # the check ran: the unbacked line prints
        # The existence of hooks/guard.py is read from the same cat-file as the line: no extra git start.
        self.assertEqual(len(subs), 4, subs)

    def test_route_claim_with_a_removed_path_and_a_claim_candidate_starts_exactly_five_git_processes(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, "# Notes\n\n- The cloud cannot push to main (route cloud-push).\n"
                               "- The classifier cannot push to main.\n")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n", extra={ROUTE_ROWS: route_rows_text("cloud-push")}), change)
        self.assertIn(MOVED, touched(rng))  # scope: the range renames hooks/lib.mjs away, so a path is removed
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(stale005_lines(out, NOTES), [4], out)  # the check read the candidate: the unbacked line fires
        # The removed path makes the check read the Markdown at head (one ls-tree, one cat-file). The candidate line
        # reads its backing from that same cat-file, so the count is five and no more.
        self.assertEqual(len(subs), 5, subs)

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
        rc, out, before, after = self.run_copy_of_script(rng, ["--range", "%s...%s" % (rng.base, rng.head)])
        self.assertIn(rc, (0, 1), out)
        self.assertEqual(after, before, out)

    def run_tree_traced(self, rng):
        """(exit code, output, the git subcommands started). No trace file means no git start at all."""
        trace = os.path.join(rng.case, "git-trace-tree.txt")
        rc, out = self.run_tree(rng, extra_env={"GIT_TRACE": trace})
        return rc, out, git_subcommands(trace) if os.path.exists(trace) else []

    def test_a_tree_run_starts_rev_parse_ls_tree_and_one_cat_file(self):
        rng = self.tree("# Notes\n\n- see `hooks/gone.py`\n- see `hooks/guard.py:3`\n")
        rc, out, subs = self.run_tree_traced(rng)
        self.assertEqual(collections.Counter(subs), collections.Counter(["rev-parse", "ls-tree", "cat-file"]), subs)
        self.assertEqual(rc, 1, out)

    def test_a_tree_run_writes_no_file_in_the_repo_or_next_to_the_script(self):
        rng = self.tree("# Notes\n\n- see `hooks/gone.py`\n")
        rc, out, before, after = self.run_copy_of_script(rng, ["--tree"])
        self.assertIn("stale-cites: FAIL, 1 finding(s)", out)
        self.assertEqual(after, before, out)


class ForeignFileTests(StaleCase):
    """A cite of a JavaScript or shell name prints as unknown, not as a finding, and only when Markdown is already
    read. A lone touched .mjs passes silently."""

    def mjs_and_removal(self, notes):
        def change(repo):
            write(repo, "hooks/lib.mjs", LIB + "export const more = 1;\n")
            os.remove(os.path.join(repo, "hooks", "guard_core.py"))  # a second removal, so Markdown is read
            commit(repo)
        return self.make_range(base_files(notes), change)

    def test_a_touched_mjs_cited_beside_another_removal_prints_one_unknown_line(self):
        rng = self.mjs_and_removal("# Notes\n\n- `hooks/lib.mjs` `refusals`\n")
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(unknown_lines(out), [
            "stale-cites: unknown, docs/debts/notes.md:3: hooks/lib.mjs refusals: "
            "JavaScript and shell names are not checked",
        ], out)

    def test_a_line_marked_ste_disable_line_stale002_prints_no_unknown_line(self):
        rng = self.mjs_and_removal("# Notes\n\n- `hooks/lib.mjs` `refusals` <!-- ste-disable-line STALE002 -->\n")
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(unknown_lines(out), [], out)

    def test_an_anchor_only_edit_starts_exactly_four_git_processes_and_no_ls_tree_of_hooks(self):
        # No code file changed, so the report reads the rule file's blobs and the mechanisms file through one cat-file,
        # and no ls-tree names hooks/. The added line holds no claim candidate, so it adds no start.
        base_claude = "Main moves only by pull request. <!-- rule:git-main-only-by-pr -->\n"
        head_claude = "Main moves only by a reviewed pull request. <!-- rule:git-main-only-by-pr -->\n"
        mech = mechanisms({"git-main-only-by-pr": {"kind": "guard", "ref": "main-moves-by-pull-request"}})

        def change(repo):
            write(repo, CLAUDE, head_claude)
            commit(repo)
        rng = self.make_range(base_files(extra={CLAUDE: base_claude, MECH: mech}), change)
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(commands), 4, commands)
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


    def test_route_claim_changed_code_file_lists_each_prose_line_its_backing_points_at(self):
        # The prose is a decision record: the backing scan reads only what home_report already reads, the decisions.
        record = "docs/decisions/route-backing.md"
        decision = ("# Route backing\n\n"
                    "- the gate is read at (read hooks/guard.py:2)\n"  # line 3
                    "- the case is checked at (test lint/test_x.py::keep)\n"  # line 4
                    "- the other gate is read at (read hooks/other.py:1)\n")  # line 5: its file is not changed
        base_test = "def keep():\n    return 1\n"

        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            write(repo, "lint/test_x.py", "def keep():\n    return 2\n")
            commit(repo)
        rng = self.make_range(base_files(extra={"lint/test_x.py": base_test, record: decision}), change)
        self.assertTrue({"hooks/guard.py", "lint/test_x.py"} <= touched(rng))  # scope: both files changed
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn(record + ":3", report_prose(out, "hooks/guard.py"), out)
        self.assertIn(record + ":4", report_prose(out, "lint/test_x.py"), out)
        self.assertNotIn(record + ":5", report_prose(out, "hooks/guard.py") | report_prose(out, "lint/test_x.py"), out)


# A guard module whose refuse() call names the rule: rule_audit reads the rule id from the third argument.
GUARD_REFUSE = GUARD + "\n\ndef gate(ctx):\n    return refuse(ctx, 'no push to main', 'main-moves-by-pull-request')\n"
STREAM = "def stream():\n    return 4\n"


class TreeTests(StaleCase):
    """`--tree` reads each tracked Markdown file as committed at HEAD, or at REV. A path cite that names nothing
    tracked is STALE003. A line anchor past the file's end, or a range that ends before it starts, is STALE004.
    The guard.py in CODE has six lines; the cases below use that count."""

    def test_a_dead_path_cite_is_flagged_stale003(self):
        found = self.assert_tree_flags(self.tree("# Notes\n\n- the guard is in `hooks/gone.py`\n"),
                                       [(NOTES, 3, "STALE003")])
        self.assertIn("hooks/gone.py", found[0][3])
        self.assertNotIn("did you mean", found[0][3])

    def test_a_trailing_dot_or_dash_is_stripped_before_the_check(self):
        notes = "# Notes\n\n- see `hooks/gone.py.`\n- see hooks/gone.py-\n"
        self.assert_tree_flags(self.tree(notes), [(NOTES, 3, "STALE003"), (NOTES, 4, "STALE003")])

    def test_a_live_path_cite_is_silent(self):
        self.assert_tree_passes(self.tree("# Notes\n\n- the guard is in `hooks/guard.py`\n- and `lint/x.py`\n"))

    def test_a_path_resolved_from_the_md_file_folder_is_silent(self):
        extra = {"mods/session-board/notes.md": "- see `hooks/tool.py`\n",
                 "mods/session-board/hooks/tool.py": "def tool():\n    return 1\n"}
        # The same cite in docs/debts/ names no file from either folder, so only that line is flagged.
        self.assert_tree_flags(self.tree("# Notes\n\n- see `hooks/tool.py`\n", extra=extra), [(NOTES, 3, "STALE003")])

    def test_a_line_anchor_inside_the_file_is_silent(self):
        notes = "# Notes\n\n- `hooks/guard.py:1`\n- `hooks/guard.py:6`\n- `hooks/guard.py:2-6`\n"
        self.assert_tree_passes(self.tree(notes))

    def test_a_line_anchor_past_the_end_of_the_file_is_stale004(self):
        self.assert_tree_flags(self.tree("# Notes\n\n- `hooks/guard.py:7`\n"), [(NOTES, 3, "STALE004")])

    def test_a_line_anchor_below_one_is_stale004(self):
        self.assert_tree_flags(self.tree("# Notes\n\n- `hooks/guard.py:0`\n"), [(NOTES, 3, "STALE004")])

    def test_a_line_range_that_ends_past_the_end_of_the_file_is_stale004(self):
        self.assert_tree_flags(self.tree("# Notes\n\n- `hooks/guard.py:2-9`\n"), [(NOTES, 3, "STALE004")])

    def test_a_line_range_that_ends_before_it_starts_is_stale004(self):
        self.assert_tree_flags(self.tree("# Notes\n\n- `hooks/guard.py:5-2`\n"), [(NOTES, 3, "STALE004")])

    def test_a_tree_with_no_markdown_passes(self):
        rng = self.make_range({"hooks/guard.py": GUARD}, lambda repo: None)
        self.assert_tree_passes(rng)

    def test_a_line_anchor_on_the_last_line_of_a_long_file_is_read_to_its_end(self):
        extra = {"hooks/long.py": "x = 1\n" * 400}
        self.assert_tree_flags(self.tree("- `hooks/long.py:400`\n- `hooks/long.py:401`\n", extra=extra),
                               [(NOTES, 2, "STALE004")])

    def test_an_anchor_on_a_dead_path_gives_stale003_only(self):
        # lint/guard.py is dead. Its basename matches hooks/guard.py, which has six lines: :99 is no STALE004 here.
        self.assert_tree_flags(self.tree("# Notes\n\n- `lint/guard.py:99`\n"), [(NOTES, 3, "STALE003")])

    def test_a_dead_path_with_one_same_basename_file_gets_a_did_you_mean_hint(self):
        found = self.assert_tree_flags(self.tree("# Notes\n\n- `lint/guard.py`\n"), [(NOTES, 3, "STALE003")])
        self.assertIn("did you mean hooks/guard.py", found[0][3])

    def test_a_dead_path_with_two_same_basename_files_gets_no_hint(self):
        extra = {"mods/a/guard.py": "def other():\n    return 1\n"}
        found = self.assert_tree_flags(self.tree("# Notes\n\n- `lint/guard.py`\n", extra=extra),
                                       [(NOTES, 3, "STALE003")])
        self.assertNotIn("did you mean", found[0][3])

    def test_a_path_with_placeholder_characters_is_silent(self):
        notes = ("# Notes\n\n- `hooks/<name>.py`\n- `hooks/*.py`\n- `hooks/guard_?.py`\n- `hooks/{a,b}.py`\n"
                 "- `hooks/[ab].py`\n- `$HOME/hooks/x.py`\n- `hooks/gone-*.py`\n")
        self.assert_tree_passes(self.tree(notes))

    def test_an_extensionless_or_folder_cite_is_silent(self):
        self.assert_tree_passes(self.tree("# Notes\n\n- `hooks/gone`\n- `docs/gone/`\n- `hooks/`\n- `vendor/`\n"))

    def test_a_path_whose_first_segment_is_not_a_tracked_top_folder_is_silent(self):
        self.assert_tree_passes(self.tree("# Notes\n\n- `vendor/x.py`\n- `debts/gone.py`\n"))

    def test_a_file_named_by_ste_lint_exclude_is_left_out(self):
        extra = {".ste-lint-exclude": "# Third-party prose.\nthird_party/**\n",
                 "third_party/notes.md": "- see `hooks/gone.py`\n"}
        self.assert_tree_passes(self.tree("# Notes\n", extra=extra))

    def test_a_file_named_by_the_exclude_env_is_left_out(self):
        extra = {"vendor/notes.md": "- see `hooks/gone.py`\n"}
        self.assert_tree_passes(self.tree("# Notes\n", extra=extra), extra_env={"EXCLUDE": "vendor"})

    def test_a_disable_line_mark_leaves_out_only_its_own_code(self):
        rows = [
            ("- see `hooks/gone.py` <!-- ste-disable-line STALE003 -->", False),
            ("- see `hooks/gone.py` <!-- ste-disable-line STALE004 -->", True),
            ("- see `hooks/guard.py:99` <!-- ste-disable-line STALE004 -->", False),
            ("- see `hooks/guard.py:99`", True),
            ("- see `hooks/gone.py`", True),
        ]
        text, _ = rows_text(rows)
        self.assert_tree_flags(self.tree(text),
                               [(NOTES, 2, "STALE003"), (NOTES, 4, "STALE004"), (NOTES, 5, "STALE003")])

    def test_the_records_page_is_never_read(self):
        self.assert_tree_passes(self.tree("# Notes\n", extra={"docs/records.md": "- see `hooks/gone.py`\n"}))

    def test_a_cite_inside_a_fenced_block_is_counted(self):
        self.assert_tree_flags(self.tree("# Notes\n\n```\n- see `hooks/gone.py`\n```\n"), [(NOTES, 4, "STALE003")])

    def test_comment_openers_and_lone_quotes_do_not_hide_a_later_dead_cite(self):
        rows = [
            ("# Dead `hooks/gone.py`", True),  # a heading opens with `#`
            ("Use `#` to start a comment. See `hooks/gone.py`.", True),
            ("Open a comment with `<!--`. See `hooks/gone.py`.", True),
            ("Don't read `hooks/gone.py` for the list.", True),  # a lone quote in text
            ("Quote `\"/*\"` in a string. See `hooks/gone.py`.", True),
            ("```", False),
            ("/* open comment `hooks/gone.py`", True),  # inside a fence: still prose
            ("x = \"a // b\"  # don't `hooks/gone.py`", True),
            ("```", False),
            ("See `hooks/gone.py` again.", True),
            ("<!--", False),
            ("No path here.", False),
            ("-->", False),
            ("See `hooks/gone.py` once more.", True),
        ]
        text, lines = rows_text(rows)
        self.assert_tree_flags(self.tree(text), [(NOTES, n, "STALE003") for n in lines])

    def test_a_working_tree_only_file_is_not_live_and_uncommitted_markdown_is_not_read(self):
        rng = self.tree("# Notes\n\n- see `hooks/gone.py`\n- see `hooks/new_tool.py`\n")
        write(rng.repo, NOTES, "# Notes\n\n- see `hooks/guard.py`\n- see `hooks/guard.py`\n")  # a fix, uncommitted
        write(rng.repo, "hooks/new_tool.py", "def tool():\n    return 1\n")  # a file, uncommitted
        write(rng.repo, "docs/scratch.md", "- see `hooks/gone.py`\n")  # a page, uncommitted
        # HEAD holds the first version of the notes, and no new_tool.py: both lines are dead at HEAD.
        self.assert_tree_flags(rng, [(NOTES, 3, "STALE003"), (NOTES, 4, "STALE003")])

    def test_range_mode_still_flags_only_what_the_range_removed(self):
        # The dead cite on line 4 is a tree finding. --range must not name it.
        notes = "# Notes\n\n- refusal list in `hooks/lib.mjs`\n- see `hooks/gone.py`\n"

        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes), change), [(NOTES, 3, "STALE001")])

    def test_tree_and_range_together_are_refused(self):
        rng = self.tree("# Notes\n")
        done = subprocess.run([sys.executable, MODULE, "--tree", "--range", "%s...%s" % (rng.base, rng.head)],
                              cwd=rng.repo, env=dict(os.environ, TMPDIR=rng.case), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 2, out)
        self.assertIn("not allowed with", out)

    def test_rev_reads_that_commit_and_the_default_is_head(self):
        def change(repo):
            write(repo, "hooks/tool.py", "def tool():\n    return 1\n")
            commit(repo)
            git(repo, "rm", "-q", "hooks/tool.py")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- see `hooks/tool.py`\n"), change)
        self.assert_tree_flags(rng, [(NOTES, 3, "STALE003")])  # HEAD: the file is gone
        self.assert_tree_passes(rng, rev="HEAD~1")  # HEAD~1: the file is tracked


ROUTE_ROWS = "hooks/route_rows.json"  # a route id is a row of this file at head
PREMISE_HOME = os.path.join(ROOT, "hooks", "precompact_handoff.py")  # PREMISE_KINDS is read here, never copied
FIXTURE = os.path.join(HERE, "route_claims_labelled.json")
LABELS = ("STALE", "PARTLY_STALE", "HALF", "TRUE", "HISTORY", "UNKNOWN")


def route_rows_text(*ids):
    """hooks/route_rows.json as a linted repo holds it: {"rows": [...]}, one row per route id, in the row shape the
    route-claims lane uses (id, act, route, surface, outcome, measured, cc_version, evidence, by)."""
    rows = [{"id": route, "act": "push", "route": "cloud", "surface": "cloud", "outcome": "refused",
             "measured": "2026-11-06", "cc_version": "2.1.0", "evidence": "fixture", "by": "test-author"}
            for route in ids]
    return json.dumps({"rows": rows}, indent=2) + "\n"


def read_repo_file(repo, path):
    with open(os.path.join(repo, *path.split("/")), encoding="utf-8") as f:
        return f.read()


def stale005_hits(out):
    """(path, line, text) for each output line that carries STALE005 and names a Markdown `path:line`. A finding line
    and a report line both count, so a case pins the lines a reader gets, never the form they print in."""
    hits = []
    for line in out.splitlines():
        if "STALE005" in line:
            hits.extend((path, int(number), line) for path, number in re.findall(r"([\w./@+~-]+\.md):(\d+)", line))
    return hits


def stale005_lines(out, path):
    """The line numbers of `path` that STALE005 names in the output, sorted."""
    return sorted(number for hit, number, _ in stale005_hits(out) if hit == path)


def report_prose(out, changed):
    """The `path.md:line` cites on each report line that names the changed file `changed`."""
    cites = set()
    for line in out.splitlines():
        if line.startswith("stale-cites: report, ") and changed in line:
            cites.update(re.findall(r"[\w./@+~-]+\.md:\d+", line))
    return cites


class RouteClaimTests(StaleCase):
    """STALE005, range mode only, report only. An ADDED line of governed prose states a capability by route when it
    holds a capability verb and a route word. It is backed by a premise kind from PREMISE_KINDS with its source, or by a
    route id that is a row of hooks/route_rows.json. The exit code never changes."""

    def route_range(self, rows, extra=None, base_notes="# Notes\n"):
        """A range that rewrites NOTES as `rows`, given as (line, flagged) pairs. Returns (range, flagged lines)."""
        text, flagged = rows_text(rows)

        def change(repo):
            write(repo, NOTES, text)
            commit(repo)
        return self.make_range(base_files(base_notes, extra=extra), change), flagged

    def assert_route_claims(self, rng, expected, path=NOTES):
        """Scope first: the range touched `path`. Then the exit is 0, the verdict is PASS, and the STALE005 lines that
        name `path` are exactly `expected`. Returns the output."""
        self.assertIn(path, touched(rng))
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)
        self.assertEqual(stale005_lines(out, path), sorted(expected), out)
        return out

    def test_route_claim_fires_on_each_verb_and_route_word_and_not_on_a_part_of_a_word(self):
        rows = [
            ("- The cloud cannot push to main.", True),
            ("- The cloud can't push to main.", True),
            ("- The cloud refuses pushes to main.", True),
            ("- Pushes to main are refused by the cloud.", True),
            ("- The cloud blocks pushes to main.", True),
            ("- Auto mode is not available for this branch.", True),
            ("- The cloud works for read-only tasks.", True),
            ("- Local sessions cannot push to main.", True),
            ("- Auto mode cannot push to main.", True),
            ("- The classifier cannot push to main.", True),
            ("- gh cannot push to main.", True),
            ("- gh api cannot push to main.", True),
            ("- The MCP server cannot push to main.", True),
            ("- The proxy cannot push to main.", True),
            ("- The harness cannot push to main.", True),
            ("- The cloud runs the nightly job.", False),  # a route word and no verb
            ("- The sandbox cannot push to main.", False),  # a verb and no route word
            ("- The local networks are fine.", False),  # `works` sits inside `networks`
            ("- The highway cannot be used.", False),  # `gh` sits inside `highway`
            ("- The cloud runs the job.", False),  # two sentences: the route word in one, the verb in the other
            ("  The job cannot push to main.", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_is_silent_in_a_heading_a_quote_a_fence_and_a_span_that_holds_the_whole_claim(self):
        rows = [
            ("## The cloud cannot push to main.", False),  # a heading
            ("> The cloud cannot push to main.", False),  # a quote line
            ("```", False),
            ("The cloud cannot push to main.", False),  # inside a fence
            ("```", False),
            ("The cloud cannot push to main, after the fence.", True),  # prose again after the closing fence
            ("- `The cloud cannot push to main.`", False),  # a code span holds the whole claim
            ("- Use `cannot` and `cloud` only in code.", False),  # a verb in a span is a mention (lane ruling 12:47 CST)
            ("- The cloud cannot push to main; see `hooks/guard.py`.", True),  # the words sit outside the span
            ("- Open a fence with `` ``` `` and the cloud cannot push to main.", True),  # no fence opens in a span
            ("- Open a comment with `<!--`. The cloud cannot push to main.", True),  # a comment opener in a span
            ("- Don't read `hooks/guard.py` for this. The cloud cannot push to main.", True),  # a lone quote
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_in_a_fence_four_spaces_deep_under_a_list_item_is_silent(self):
        # Any indent opens a fence in this module, so the claim inside the four-space fence is no claim. The claim after
        # the fence is read: the scope control. This pins the verdict as it stands.
        rows = [
            ("- Run the step:", False),
            ("    ```", False),
            ("    The cloud cannot push to main.", False),  # inside a fence four spaces deep
            ("    ```", False),
            ("- The cloud cannot push to main.", True),  # the scope control: the same claim outside the fence
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_in_a_tilde_fence_four_spaces_deep_under_a_list_item_is_silent(self):
        # CODE_SPAN pairs backtick rows across lines and blanks the claim between them, so a backtick fence pins nothing
        # about FENCE. A tilde fence has no such pairing: only FENCE keeps its claim out of the scan.
        rows = [
            ("- Run the step:", False),
            ("    ~~~", False),
            ("    The cloud cannot push to main.", False),  # inside a tilde fence four spaces deep
            ("    ~~~", False),
            ("- The cloud cannot push to main.", True),  # the scope control: the same claim outside the fence
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_fires_on_a_code_span_used_as_the_subject_and_skips_only_a_span_holding_the_whole_claim(self):
        rows = [
            ("- `gh` cannot close a pull request.", True),  # the span is the subject; the claim is outside the span
            ("- `The cloud` cannot push to main.", True),
            ("- The cloud cannot push to `main`.", True),  # the span is an object; the claim is outside it
            ("- `gh cannot close a pull request.`", False),  # the whole claim sits in the span
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_is_silent_on_a_local_branch_because_local_alone_is_no_route_word(self):
        rows = [
            ("- A local branch cannot hold the record.", False),  # `local` alone names no route
            ("- Local runs cannot push to main.", False),  # `local runs` is no route word (lane ruling 12:47 CST)
            ("- The cloud cannot hold the record.", True),  # the same verb with a route word fires
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_reads_locally_on_the_owners_computer_and_a_local_session_as_route_words(self):
        sentences = [
            "- Locally, the push cannot reach main.",
            "- On the owner's computer, the push cannot reach main.",
            "- On the owner’s computer, the push cannot reach main.",
            "- A local session cannot hold the record.",
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                rng, flagged = self.route_range([("# Notes", False), ("", False), (sentence, True)])
                self.assert_route_claims(rng, flagged)

    def test_route_claim_past_tense_incident_is_silent_beside_a_present_claim(self):
        rows = [
            ("- The cloud refused the push on 2026-10-30.", False),  # a dated incident
            ("- The cloud refuses pushes to main.", True),  # the same route in the present tense
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_fires_on_each_capability_verb_it_names(self):
        sentences = [  # each holds one verb and the route word `cloud` (or `classifier`, `proxy`): the verb decides
            "- The cloud isn't available for merges.",
            "- The cloud isn’t available for merges.",
            "- The cloud does not work for pushes to main.",
            "- The cloud doesn't work for pushes to main.",
            "- The classifier won't merge to main.",
            "- Pushes to main are blocked by the proxy.",
            "- The proxy denies pushes to main.",
            "- The cloud gets a 403 on pushes to main.",
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                rng, flagged = self.route_range([("# Notes", False), ("", False), (sentence, True)])
                self.assert_route_claims(rng, flagged)

    def test_route_claim_counts_a_hyphenated_auto_mode_as_a_route_word(self):
        sentences = [  # the verb `cannot` decides; `Auto-mode` is the route word
            "- Auto-mode cannot push to main.",
            "- auto-mode cannot push to main.",
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                rng, flagged = self.route_range([("# Notes", False), ("", False), (sentence, True)])
                self.assert_route_claims(rng, flagged)

    def test_route_claim_wrapped_over_two_lines_fires_on_its_first_line(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- The cloud", True),  # the route word on this row, the verb on the next: one sentence
            ("  cannot close a pull request.", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_wrapped_with_the_verb_on_the_first_line_fires_on_its_first_line(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- Pushes to main are refused", True),
            ("  by the cloud.", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_backing_on_the_next_line_of_its_sentence_silences_it(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- The cloud cannot close a pull request", False),  # the claim and its backing: one sentence, silent
            ("  (read hooks/guard.py:2).", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_backing_in_another_sentence_of_the_paragraph_does_not_silence_it(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- The cloud cannot close a pull request. It is recorded (read hooks/guard.py:2).", True),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_split_by_a_blank_line_is_two_paragraphs_and_stays_silent(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- The cloud", False),
            ("", False),
            ("  cannot close a pull request.", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_code_span_crossing_a_line_break_that_holds_the_claim_is_silent(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- `The cloud", False),  # the whole claim sits in a code span that crosses the line break
            ("  cannot close a pull request.`", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_wrapped_after_a_lone_quote_and_a_comment_opener_in_a_span_fires(self):
        rows = [
            ("# Notes", False),
            ("", False),
            ("- Don't read `<!--` as a comment. The cloud", True),  # a lone quote, an opener in a span, then the claim
            ("  cannot close a pull request.", False),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_disable_mark_names_stale005_and_no_other_code(self):
        rows = [
            ("- The cloud cannot push to main. <!-- ste-disable-line STALE005 -->", False),
            ("- The cloud cannot push to main. <!-- ste-disable-line STALE001 -->", True),
            ("- The cloud cannot push to main.", True),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_is_backed_by_a_strong_premise_kind_with_its_source_and_a_weak_one_is_not(self):
        kinds = tuple_named(PREMISE_HOME, "PREMISE_KINDS")
        weak = {"notes", "assumed"}
        self.assertTrue({"ruling", "measured", "read"} <= kinds, kinds)  # scope: the strong kinds this check reads
        self.assertTrue(weak <= kinds, kinds)  # scope: the weak kinds are premise kinds the home file names
        self.assertNotIn("guess", kinds)
        rows = [("- The cloud cannot push to main (%s hooks/guard.py:12)." % kind, False)
                for kind in sorted(kinds - weak)]
        rows += [("- The cloud cannot push to main (%s hooks/guard.py:12)." % kind, True) for kind in sorted(weak)]
        rows += [
            ("- The cloud cannot push to main (measured 2026-11-06, hooks/guard.py:12).", False),
            ("- The cloud cannot push to main (guess hooks/guard.py:12).", True),  # a kind outside PREMISE_KINDS
            ("- The cloud cannot push to main (measured 2026-11-06).", True),  # a kind with no source
            ("- The cloud cannot push to main.", True),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_is_backed_by_a_test_node_id_and_stays_silent(self):
        rows = [
            ("- The cloud cannot push to main (test lint/test_x.py::keep).", False),  # backed by a test node id
            ("- The cloud cannot push to main (test lint/test_x.py::keep) and merge.", False),
            ("- The cloud cannot merge to main.", True),  # no backing at all
        ]
        rng, flagged = self.route_range(rows, extra={"lint/test_x.py": "def keep():\n    return 1\n"})  # the file exists
        self.assert_route_claims(rng, flagged)

    def test_route_claim_read_or_test_backing_naming_a_file_absent_at_head_is_a_dead_backing(self):
        rows = [
            ("- The cloud cannot push to main (read hooks/guard.py:12).", False),  # the file exists at head: backed
            ("- The cloud cannot push to main (read hooks/gone.py:12).", True),  # no such file: a dead backing
            ("- The cloud cannot push to main (test lint/test_gone.py::keep).", True),  # no such file: a dead backing
        ]
        rng, flagged = self.route_range(rows)
        tracked = git(rng.repo, "ls-tree", "-r", "--name-only", rng.head).split()
        self.assertIn("hooks/guard.py", tracked, "scope: the backing that exists is tracked at head")
        self.assertNotIn("hooks/gone.py", tracked, "scope: the read backing is absent at head")
        self.assertNotIn("lint/test_gone.py", tracked, "scope: the test backing is absent at head")
        out = self.assert_route_claims(rng, flagged)
        texts = {number: text for path, number, text in stale005_hits(out) if path == NOTES}
        self.assertIn("hooks/gone.py", texts.get(flagged[0], ""), out)  # the report names the file it cannot find
        self.assertIn("lint/test_gone.py", texts.get(flagged[1], ""), out)

    def test_route_claim_cites_a_route_id_that_is_a_row_at_head_and_names_a_dead_one(self):
        rows = [
            ("- The cloud cannot push to main (route cloud-push).", False),
            ("- The cloud cannot merge to main (route gone).", True),  # no such row: a dead route
        ]
        rng, flagged = self.route_range(rows, extra={ROUTE_ROWS: route_rows_text("cloud-push")})
        out = self.assert_route_claims(rng, flagged)
        texts = [text for path, number, text in stale005_hits(out) if path == NOTES and number == flagged[0]]
        self.assertTrue(texts and "gone" in texts[0] and "dead route" in texts[0], out)

    def test_route_claim_with_an_empty_rows_file_makes_every_route_cite_a_dead_route(self):
        rows = [("- The cloud cannot push to main (route cloud-push).", True)]
        rng, flagged = self.route_range(rows, extra={ROUTE_ROWS: route_rows_text()})
        self.assertEqual(json.loads(read_repo_file(rng.repo, ROUTE_ROWS))["rows"], [])  # scope: the file holds no row
        out = self.assert_route_claims(rng, flagged)
        texts = [text for path, number, text in stale005_hits(out) if path == NOTES and number == flagged[0]]
        self.assertTrue(texts and "cloud-push" in texts[0] and "dead route" in texts[0], out)

    def test_route_claim_with_no_rows_file_at_head_reads_unknown_once_and_names_no_dead_route(self):
        rows = [
            ("- The cloud cannot push to main (route cloud-push).", True),
            ("- The cloud cannot merge to main (route cloud-other).", True),
        ]
        rng, flagged = self.route_range(rows)  # no rows file in the fixture
        tracked = git(rng.repo, "ls-tree", "-r", "--name-only", rng.head).split()
        self.assertNotIn(ROUTE_ROWS, tracked, "scope: the rows file is absent at head")
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)
        self.assertFalse([line for line in out.splitlines() if "dead route" in line], out)  # an absent file is not dead
        named = [line for line in out.splitlines() if ROUTE_ROWS in line]
        self.assertEqual(len(named), 1, out)  # one report line for the absent file, however many claims cite a route
        self.assertIn("absent", named[0], out)

    def test_route_claim_reads_the_route_rows_at_head_not_at_base(self):
        text, flagged = rows_text([
            ("# Notes", False),
            ("", False),
            ("- The cloud cannot push to main (route cloud-push).", False),  # the row is added in this range
            ("- The classifier cannot push to main.", True),
        ])

        def change(repo):
            write(repo, ROUTE_ROWS, route_rows_text("cloud-push"))
            write(repo, NOTES, text)
            commit(repo)
        rng = self.make_range(base_files(extra={ROUTE_ROWS: route_rows_text()}), change)
        self.assertEqual([row["id"] for row in json.loads(read_repo_file(rng.repo, ROUTE_ROWS))["rows"]], ["cloud-push"])
        self.assertIn(ROUTE_ROWS, touched(rng))  # scope: the rows file changed in this range
        self.assert_route_claims(rng, flagged)

    def test_route_row_removed_in_the_range_reports_each_prose_line_at_head_that_cites_it(self):
        notes = ("# Notes\n\n- The cloud cannot push to main (route cloud-push).\n"
                 "- The cloud cannot merge to main (route cloud-other).\n")
        record = "# Decision\n\n## The ruling\n\nThe cloud cannot push to main (route cloud-push).\n"
        extra = {ROUTE_ROWS: route_rows_text("cloud-push", "cloud-other"), "docs/decisions/route-note.md": record}

        def change(repo):
            write(repo, ROUTE_ROWS, route_rows_text("cloud-other"))  # the range removes the cloud-push row
            commit(repo)
        rng = self.make_range(base_files(notes, extra=extra), change)
        self.assertIn(ROUTE_ROWS, touched(rng))  # scope: the rows file changed in this range
        self.assertNotIn(NOTES, touched(rng))  # scope: the prose that cites the row is not in the range
        ids_at_base = {row["id"] for row in json.loads(git(rng.repo, "show", "%s:%s" % (rng.base, ROUTE_ROWS)))["rows"]}
        ids_at_head = {row["id"] for row in json.loads(read_repo_file(rng.repo, ROUTE_ROWS))["rows"]}
        self.assertEqual(ids_at_base - ids_at_head, {"cloud-push"}, "scope: the range removes one row id")
        rc, out, commands = self.run_traced_commands(rng)
        subs = [command.split()[0] for command in commands]
        self.assertEqual(rc, 0, out)  # report only: the exit code does not change
        self.assertIn("stale-cites: PASS", out)
        self.assertEqual(stale005_lines(out, NOTES), [3], out)  # the prose line that cites the removed id
        self.assertEqual(stale005_lines(out, "docs/decisions/route-note.md"), [5], out)  # and a decision record's line
        self.assertLessEqual(len(subs), 5, subs)  # within the pin for a range that removes a path

    def test_route_claim_fires_only_on_a_line_the_range_adds(self):
        base = "# Notes\n\n- The cloud cannot push to main.\n- Auto mode cannot merge.\n"

        def change(repo):
            write(repo, NOTES, "# Notes\n\n- The cloud cannot push to main.\n- The classifier refuses merges.\n")
            commit(repo)
        rng = self.make_range(base_files(base), change)
        # Line 3 was on main and the range does not touch it, so it is silent. Line 4 is added.
        self.assert_route_claims(rng, [4])

    def test_route_claim_fires_in_a_markdown_file_the_range_adds(self):
        def change(repo):
            write(repo, "docs/new-note.md", "# New note\n\n- The cloud cannot push to main.\n")
            commit(repo)
        self.assert_route_claims(self.make_range(base_files(), change), [3], path="docs/new-note.md")

    def test_route_claim_is_not_reported_in_the_records_page_or_an_excluded_file(self):
        extra = {".ste-lint-exclude": "third_party/**\n"}
        page = "# Page\n\n- The cloud cannot push to main.\n"

        def change(repo):
            write(repo, NOTES, "# Notes\n\n- The cloud cannot push to main.\n")
            write(repo, "docs/records.md", page)
            write(repo, "third_party/notes.md", page)
            commit(repo)
        rng = self.make_range(base_files(extra=extra), change)
        self.assertTrue({"docs/records.md", "third_party/notes.md"} <= touched(rng))  # scope: both files changed
        out = self.assert_route_claims(rng, [3])
        self.assertEqual([path for path, _, _ in stale005_hits(out) if path != NOTES], [], out)

    def test_route_claim_leaves_the_exit_code_to_the_other_findings(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, "# Notes\n\n- refusal list in `hooks/lib.mjs`\n- The classifier refuses merges.\n")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        self.assertIn(NOTES, touched(rng))  # scope
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 1, out)
        self.assertIn("stale-cites: FAIL, 1 finding(s)", out)
        self.assertEqual([(path, n, code) for path, n, code, _ in parse(out)], [(NOTES, 3, "STALE001")], out)
        self.assertEqual(stale005_lines(out, NOTES), [4], out)

    def test_route_claim_is_reported_on_an_added_line_and_not_when_the_range_adds_none(self):
        def add(repo):
            write(repo, NOTES, "# Notes\n\n- The cloud cannot push to main.\n")
            commit(repo)
        self.assert_route_claims(self.make_range(base_files(), add), [3])  # the range adds the claim

        def drop(repo):
            write(repo, NOTES, "# Notes\n")
            commit(repo)
        self.assert_route_claims(self.make_range(base_files("# Notes\n\n- The cloud cannot push to main.\n"), drop), [])

    def test_route_claim_full_size_file_reports_each_unbacked_claim_by_its_own_line(self):
        rows = [("- The cloud cannot push to main.", True) if n % 100 == 0 else ("- Filler line %d." % n, False)
                for n in range(1, 1201)]
        rng, flagged = self.route_range(rows)
        self.assertEqual(len(flagged), 12)  # scope: twelve claim lines in 1,200
        self.assert_route_claims(rng, flagged)

    def test_route_claim_is_not_reported_by_tree_mode(self):
        rng, flagged = self.route_range([("# Notes", False), ("- The cloud cannot push to main.", True)])
        self.assert_route_claims(rng, flagged)  # the range run reports the added line
        _, out = self.run_tree(rng)
        self.assertEqual(stale005_hits(out), [], out)

    def test_route_claim_is_silent_on_a_claim_in_straight_or_curly_double_quotes(self):
        rows = [
            ('- The old rule said "The cloud cannot close a pull request".', False),  # a quoted old claim
            ("- The old rule said “The cloud cannot close a pull request”.", False),  # the same, in curly quotes
            ('- The grant "Acts the cloud refuses" stays in force.', False),  # a quoted grant title
            ('- The old rule said "The cloud cannot', False),  # a quote wrapped over two lines of one sentence
            ('  close a pull request" and it is gone.', False),
            ('- A lone " is no quote, and the cloud cannot push to main.', True),  # an unclosed quote opens nothing
            ('- The "<!--" marker is quoted, and the cloud cannot push to main.', True),  # a comment opener in quotes
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_is_silent_on_a_file_path_that_holds_a_route_word_and_a_verb(self):
        rows = [
            ("- See docs/decisions/cloud-cannot-send.md for the ruling.", False),  # a bare path names a file, no claim
            ("- The ruling docs/decisions/cloud-cannot-send.md is kept.", False),  # the same path mid-sentence
            ("- See `docs/decisions/cloud-cannot-send.md` for the ruling.", False),  # a span, already silent
            ("- See docs/decisions/cloud-cannot-send.md. The cloud cannot push to main.", True),  # a real claim fires
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_fires_on_an_unquoted_claim_beside_a_quote_and_a_verb_inside_a_quote_is_a_mention(self):
        rows = [
            ('- The cloud is the subject; the rule "cannot close a pull request" is old.', False),  # the verb is quoted
            ('- The cloud cannot push to main; the rule "Acts the cloud refuses" is old.', True),  # the unquoted claim
            ('- The old rule said "The cloud cannot close a pull request", and the cloud cannot push to main.', True),
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_apostrophe_opens_no_quote_so_a_claim_after_it_still_fires(self):
        rows = [
            ("- Don't rely on the cloud; it cannot push to main.", True),  # a straight apostrophe before the claim
            ("- Don’t rely on the cloud; it cannot push to main.", True),  # a curly apostrophe before the claim
            ("- Don't rely on the cloud; it cannot push to main. The cloud can't push either.", True),  # two apostrophes
            ('- The old rule said "The cloud can\'t push to main".', False),  # an apostrophe inside a quote
            ('- Don\'t cite "The cloud cannot close a pull request" as current.', False),  # a quote after an apostrophe
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_unclosed_quote_in_a_table_row_does_not_hide_the_next_row(self):
        rows = [
            ("| Route | Claim |", False),
            ("|---|---|", False),
            ('| a | "doesn\'t this mean |', False),  # an unclosed straight quote; its run ends at the next `|` row
            ("| b | the auto-mode classifier refuses a tool call |", True),  # the claim the quote must not hide
            ('| c | "quoted" |', False),  # a later quote, which an open run would pair with across rows
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)

    def test_route_claim_header_row_of_a_table_does_not_flag_for_a_claim_in_a_data_row(self):
        rows = [
            ("| Route | Claim |", False),  # a header row names columns; it states no claim
            ("|---|---|", False),
            ("| a | the auto-mode classifier refuses a tool call |", True),  # the claim is flagged on its own row
        ]
        rng, flagged = self.route_range(rows)
        self.assert_route_claims(rng, flagged)


class RouteClaimFixtureTests(unittest.TestCase):
    """The labelled route claims, hand-judged stale or true, that measure the judge's false alarms: one entry per labelled line.
    A span is one entry at its first line, and `line` is a string, such as "16" or "16-20"."""

    def test_route_claims_fixture_has_the_audited_shape(self):
        self.assertTrue(os.path.isfile(FIXTURE), "fixture absent: %s" % FIXTURE)
        with open(FIXTURE, encoding="utf-8") as f:
            rows = json.load(f)
        self.assertIsInstance(rows, list)
        for row in rows:
            self.assertEqual(sorted(row), ["file", "label", "line", "text_summary"], row)
            self.assertRegex(row["file"], r"^(?:docs|\.claude)/\S+\.md$", row)  # a full repo-relative path
            self.assertRegex(row["line"], r"^[1-9][0-9]*(?:-[1-9][0-9]*)?$", row)
            self.assertIn(row["label"], LABELS, row)
            self.assertTrue(row["text_summary"].strip(), row)
        self.assertEqual(len({(row["file"], row["line"]) for row in rows}), len(rows), "a (file, line) repeats")
        self.assertEqual(collections.Counter(row["label"] for row in rows),
                         collections.Counter({"STALE": 2, "PARTLY_STALE": 1, "HALF": 1, "TRUE": 13,
                                              "HISTORY": 1, "UNKNOWN": 3}))


def load_module_under_test():
    """The module under test, loaded from MODULE, so STALE_CITES_UNDER_TEST can point a run at another copy."""
    spec = importlib.util.spec_from_file_location("stale_cites_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CitedExcerptTests(unittest.TestCase):
    """cited_excerpt: the numbered lines of a backing file that a cite points at. A prose judge sends them beside the line."""
    TEXT = "a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n"

    @classmethod
    def setUpClass(cls):
        cls.stale = load_module_under_test()

    def test_a_line_range_gives_those_lines(self):
        shown = self.stale.cited_excerpt("read src/widget.py:2-3", self.TEXT)
        self.assertEqual(shown, "2: b = 2\n3: c = 3", "a read cite of lines 2-3 gives those two lines, numbered")

    def test_a_test_cite_starts_at_the_def_of_its_name(self):
        text = "import os\n\n\ndef helper():\n    pass\n\n\ndef test_add():\n    assert 1\n"
        shown = self.stale.cited_excerpt("test tests/test_widget.py::test_add", text)
        self.assertEqual(shown.split("\n")[0], "8: def test_add():", "a test cite does not start at the def of its name")

    def test_a_lone_quote_in_a_comment_does_not_move_the_start(self):
        # The def scan reads source text. A quote in a comment is text, and must not move where the scan starts.
        text = "# don't touch this\ndef target():\n    return 1\n"
        shown = self.stale.cited_excerpt("test lint/widget.py::target", text)
        self.assertEqual(shown.split("\n")[0], "2: def target():", "a lone quote in a comment moved the start off the def")

    def test_a_def_name_inside_a_string_literal_is_not_the_start(self):
        # The string opens with '#', so a scan that drops comments first would still see a def name inside it.
        text = 'MSG = "# see def target below"\n\ndef target():\n    return 1\n'
        shown = self.stale.cited_excerpt("test lint/widget.py::target", text)
        self.assertEqual(shown.split("\n")[0], "3: def target():", "the excerpt starts at a string that names the def, not at the def")

    def test_a_def_name_inside_a_docstring_is_not_the_start(self):
        text = '"""\nNotes: def target() moved.\n"""\ndef target():\n    return 1\n'
        shown = self.stale.cited_excerpt("test lint/widget.py::target", text)
        self.assertEqual(shown.split("\n")[0], "4: def target():", "the excerpt starts inside a docstring that names the def, not at the def")

    def test_a_def_name_in_a_comment_is_not_the_start(self):
        text = "# def target moved below\n\ndef target():\n    return 1\n"
        shown = self.stale.cited_excerpt("test lint/widget.py::target", text)
        self.assertEqual(shown.split("\n")[0], "3: def target():", "the excerpt starts at a comment that names the def, not at the def")

    def test_a_cite_that_names_no_backing_path_gives_none(self):
        shown = self.stale.cited_excerpt("read the top of the file", self.TEXT)
        self.assertIsNone(shown, "a read cite with no backing path gives %r, want None" % (shown,))


# Reword check (plan part b, owner item 340). A rule sentence removed or changed in a RULE_FILES file leaves a finding
# on each tracked Markdown line at head that holds a 5-word run of it, unless that line's paragraph names the rule id.
# The retired phrase is split in source, so this file never holds it whole (lint/test_retired_names.py).
REWORD = "STALE006"  # the reword code; STALE001-005 are taken
OLD_STE = "Write in Simplified " + "Technical English"
OLD_RULE = ("**Output.** " + OLD_STE + " by default, to me and between agents,\n"
            "unless told otherwise.<!-- rule:output-write-in-ste -->\n")
NEW_RULE = "**Output.** Write plainly: short sentences, one term per meaning, no filler.<!-- rule:output-write-in-ste -->\n"
# The eight agent lines and the debt line, verbatim from origin/main 5a5f081e (grep "Technical English"), one line per
# file. Each is at line 1 here, where it sat at lines 18 to 510 there. The old phrase is the %s.
NINE = {
    "agents/builder.md": "that does not apply. %s. Start with the point. No preamble.\n",
    "agents/claude-code-guide.md": "Report once. Start with the point. %s. Report in under 25\n",
    "agents/designer.md": "Input Needed, list each `Owner grant: yes` item. %s. Report in\n",
    "agents/explore.md": "Report once. Start with the point. %s. Report in under 25\n",
    "agents/plan.md": "Report once. Start with the point. %s. Report in under 25\n",
    "agents/record-writer.md": "now). %s.\n",
    "agents/reviewer.md": "label that does not apply. %s. Start with the point. No\n",
    "agents/test-author.md": "that does not apply. %s. Start with the point. No preamble.\n",
    NOTES: "- ste-into-agent-briefs: move the STE writing standard from CLAUDE.md into agent briefs; agents/*.md still "
           "say \"%s\". Owner's grant, or 30 days after the plain-prose lint merges to main, counted by date (agents/*.md). "
           "Decision: plain-prose-lint\n",
}
NINE_PATHS = sorted(NINE)
PLAN = "agents/plan.md"


class RewordCase(StaleCase):
    def reworded(self, head_rule=NEW_RULE, base_rule=OLD_RULE, copies=True, extra=None):
        """A range whose CLAUDE.md changes from base_rule to head_rule. With copies, the nine lines are at base too."""
        notes, files = "# Notes\n", {"CLAUDE.md": base_rule}
        if copies:
            notes = NINE[NOTES] % OLD_STE
            files.update({path: text % OLD_STE for path, text in NINE.items() if path != NOTES})
        files.update(extra or {})

        def change(repo):
            write(repo, "CLAUDE.md", head_rule)
            commit(repo)
        return self.make_range(base_files(notes, extra=files), change)

    def fix(self, rng, files):
        """A new commit on the topic branch of rng that writes `files`. Returns the range to the new head."""
        for path, text in files.items():
            write(rng.repo, path, text)
        commit(rng.repo)
        return Range(rng.case, rng.repo, rng.base, git(rng.repo, "rev-parse", "HEAD"))

    @staticmethod
    def listed(out):
        return sorted((path, number) for path, number, code, _ in parse(out) if code == REWORD)


class RewordTests(RewordCase):
    def test_the_nine_copies_are_listed_when_the_rule_is_reworded(self):
        rng = self.reworded()
        rc, out = self.run_check(rng)
        self.assertEqual(self.listed(out), [(path, 1) for path in NINE_PATHS], out)
        self.assertEqual(rc, 1, out)
        for path, number, code, text in parse(out):
            if code == REWORD:
                self.assertIn("output-write-in-ste", text, out)

    def test_the_nine_copies_pass_once_each_is_fixed(self):
        rng = self.reworded()
        fixed = {path: text % "Write plainly." for path, text in NINE.items() if path != PLAN}
        # The plan line names the rule id in its paragraph, so the rule id exempts the copy.
        fixed[PLAN] = "Per rule output-write-in-ste: report once. Start with the point. %s. Report in under 25\n" % OLD_STE
        fixed["agents/four.md"] = "in Simplified Technical English\n"  # a 4-word run is under the floor
        rc, out = self.run_check(self.fix(rng, fixed))
        self.assertEqual(self.listed(out), [], out)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)

    def test_fixing_eight_leaves_only_the_ninth_listed(self):
        rng = self.reworded()
        fixed = {path: text % "Write plainly." for path, text in NINE.items() if path != PLAN}
        rc, out = self.run_check(self.fix(rng, fixed))
        self.assertEqual(self.listed(out), [(PLAN, 1)], out)
        self.assertEqual(rc, 1, out)

    def test_an_untracked_copy_is_not_read(self):
        def change(repo):
            write(repo, "CLAUDE.md", NEW_RULE)
            commit(repo)
            write(repo, "agents/builder.md", "that does not apply. %s. Start with the point.\n" % OLD_STE)
        rng = self.make_range(base_files(extra={"CLAUDE.md": OLD_RULE}), change)
        self.assert_passes(rng)

    def test_a_removed_sentence_with_no_copy_passes(self):
        self.assert_passes(self.reworded(copies=False))

    def test_a_reflowed_or_re_emphasised_rule_is_no_change(self):
        head = "*Output.* Write plainly: short sentences,\none term per meaning, no filler.<!-- rule:output-write-in-ste -->\n"
        self.assert_passes(self.reworded(head_rule=head, base_rule=NEW_RULE))

    def test_a_quoted_old_sentence_is_not_a_rule_sentence(self):
        base = "Quote it as `**Output.** " + OLD_STE + " by default, to me and between agents, unless told otherwise." \
               "<!-- rule:output-write-in-ste -->` only.\n"
        head = "Quote it as `**Output.** Write plainly: short sentences, one term per meaning, no filler." \
               "<!-- rule:output-write-in-ste -->` only.\n"
        self.assert_passes(self.reworded(head_rule=head, base_rule=base))

    def test_a_comment_opener_in_a_code_span_does_not_hide_the_rule_sentence(self):
        base = "**Output.** Write the `<!--` opener as text. " + OLD_STE + " by default, to me and between agents,\n" \
               "unless told otherwise.<!-- rule:output-write-in-ste -->\n"
        head = "**Output.** Write the `<!--` opener as text. Write plainly: short sentences, one term per meaning, " \
               "no filler.<!-- rule:output-write-in-ste -->\n"
        rng = self.reworded(head_rule=head, base_rule=base)
        rc, out = self.run_check(rng)
        self.assertEqual(self.listed(out), [(path, 1) for path in NINE_PATHS], out)

    def test_a_change_to_a_file_outside_the_rule_files_is_no_trigger(self):
        rng = self.make_range(base_files(NINE[NOTES] % OLD_STE, extra={"CLAUDE.md": NEW_RULE}), lambda repo: (
            write(repo, NOTES, "# Notes\n\n- the debt is closed\n"), commit(repo)))
        self.assert_passes(rng)


class RewordCostTests(RewordCase):
    """The reword check reads the tree only when a rule sentence changed. A rule change lists the tree once and reads
    the blobs in one cat-file batch, and a reflow reads no tree. No run writes a file."""

    def run_traced(self, rng):
        rc, out, commands = self.run_traced_commands(rng)
        return rc, out, [command.split()[0] for command in commands]

    def test_a_rule_sentence_change_starts_one_tree_listing_and_one_blob_batch(self):
        rc, out, subs = self.run_traced(self.reworded())
        self.assertIn(rc, (0, 1), out)  # the verdict is not the subject here; the starts are
        self.assertEqual(sorted(subs), ["cat-file", "diff", "ls-tree", "merge-base", "rev-parse"], subs)

    def test_a_reflow_only_rule_change_lists_no_tree(self):
        head = "*Output.* Write plainly: short sentences,\none term per meaning, no filler.<!-- rule:output-write-in-ste -->\n"
        rc, out, subs = self.run_traced(self.reworded(head_rule=head, base_rule=NEW_RULE, copies=False))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("ls-tree", subs, subs)

    def test_a_rule_sentence_change_writes_no_file(self):
        rng = self.reworded()
        rc, out, before, after = self.run_copy_of_script(rng, ["--range", "%s...%s" % (rng.base, rng.head)])
        self.assertEqual(before, after, out)


# Review round 2, F5: a head sentence that only gained words used to skip the reword check. The skip was checked against
# every rule's head sentences, and it ignored a negator in the added words. Now a negator ends the skip, and a rule is
# compared with its own head sentences only.
MERGE_BASE = "**Merge.** Main may merge only by pull request.<!-- rule:merge-by-pr -->\n"
MERGE_MOVED = "**Merge.** Main moves only by pull request.<!-- rule:merge-by-pr -->\n"
MERGE_NEGATED = "**Merge.** Main may not merge only by pull request.<!-- rule:merge-by-pr -->\n"
CAN_BASE = "**Merge.** Main can merge only by pull request.<!-- rule:merge-by-pr -->\n"
CAN_CONTRACTED = "**Merge.** Main can't merge only by pull request.<!-- rule:merge-by-pr -->\n"
MERGE_LINE = "Main may merge only by pull request. Start with the point.\n"
CAN_LINE = "Main can merge only by pull request. Start with the point.\n"
BRIEF_BASE = "**Brief.** Write the brief to the task and the files only.<!-- rule:brief-scope -->\n"
BRIEF_GROWN = "**Brief.** Write the brief, for each lane, to the task and the files only.<!-- rule:brief-scope -->\n"
BRIEF_LINE = "Write the brief to the task and the files only. Start with the point.\n"
BATCH_BASE = "**Batch.** Main may merge only by a pull request.<!-- rule:batch-merge -->\n"
BATCH_GROWN = "**Batch.** Main, when the checks pass, may merge only by a pull request.<!-- rule:batch-merge -->\n"
# Growth that adds an exception changes what the rule allows, so it is a reword. Each word is its own case.
BRIEF_UNLESS = "**Brief.** Write the brief, unless the owner asks, to the task and the files only.<!-- rule:brief-scope -->\n"
BRIEF_EXCEPT = "**Brief.** Write the brief, except when the owner asks, to the task and the files only.<!-- rule:brief-scope -->\n"
BRIEF_WITHOUT = ("**Brief.** Write the brief, without a note from the owner, to the task and the files only."
                 "<!-- rule:brief-scope -->\n")


class RewordSkipTests(RewordCase):
    def reword(self, base, head, line):
        """A range whose CLAUDE.md changes from base to head, with `line` in agents/notes.md at both ends."""
        def change(repo):
            write(repo, "CLAUDE.md", head)
            commit(repo)
        return self.make_range(base_files(extra={"CLAUDE.md": base, "agents/notes.md": line}), change)

    def test_a_rule_reworded_with_no_growth_lists_its_copy(self):
        # The control: with no growth to skip, the same copy line is listed.
        rc, out = self.run_check(self.reword(MERGE_BASE, MERGE_MOVED, MERGE_LINE))
        self.assertEqual(self.listed(out), [("agents/notes.md", 1)], out)
        self.assertEqual(rc, 1, out)

    def test_a_negator_added_to_a_rule_sentence_is_listed(self):
        rc, out = self.run_check(self.reword(MERGE_BASE, MERGE_NEGATED, MERGE_LINE))
        self.assertEqual(self.listed(out), [("agents/notes.md", 1)], out)
        self.assertEqual(rc, 1, out)

    def test_a_contraction_added_to_a_rule_sentence_is_listed(self):
        rc, out = self.run_check(self.reword(CAN_BASE, CAN_CONTRACTED, CAN_LINE))
        self.assertEqual(self.listed(out), [("agents/notes.md", 1)], out)
        self.assertEqual(rc, 1, out)

    def test_growth_with_no_negator_still_skips(self):
        self.assert_passes(self.reword(BRIEF_BASE, BRIEF_GROWN, BRIEF_LINE))

    def test_growth_in_another_rule_does_not_hide_a_removed_sentence(self):
        rng = self.reword(MERGE_BASE + "\n" + BATCH_BASE, MERGE_MOVED + "\n" + BATCH_GROWN, MERGE_LINE)
        rc, out = self.run_check(rng)
        self.assertEqual(self.listed(out), [("agents/notes.md", 1)], out)
        self.assertEqual(rc, 1, out)

    def test_a_rule_grown_by_an_exception_word_is_listed(self):
        # The exception is in the middle of the sentence, so the old runs across it are lost, as a reword's are.
        for word, head in (("unless", BRIEF_UNLESS), ("except", BRIEF_EXCEPT), ("without", BRIEF_WITHOUT)):
            with self.subTest(word=word):
                rc, out = self.run_check(self.reword(BRIEF_BASE, head, BRIEF_LINE))
                self.assertEqual(self.listed(out), [("agents/notes.md", 1)], out)
                self.assertEqual(rc, 1, out)


if __name__ == "__main__":
    unittest.main()
