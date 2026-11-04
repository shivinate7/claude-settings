#!/usr/bin/env python3
"""Cases for lint/stale_cites.py. Standard library only.

    python3 lint/test_stale_cites.py

The merge check refuses stale prose. A tracked Markdown line that names a repo path the range deleted
or renamed is STALE001. A `<file.py> <name>` pair on one line is STALE002 when the name was bound at module
level in that file at base (a def, class, assignment or import) and is not bound there at head. A `--flag` in one
code span with its script path is STALE003 when the range removed that flag from that script. Each finding
is one line, `path:line: CODE message`.
A clean run prints `stale-cites: PASS` and exits 0.

Each case makes a temp git repo: the base commit on `main`, the head commit on `topic`. The check runs
with the repo as cwd and the range as commit ids. The step cases run bin/ste-changed, which runs
actions/ste-lint/run.sh with the step's env. TMPDIR is the case folder, so temp files stay in the run folder.
"""
import ast
import atexit
import collections
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
REPORT, OTHER, MERGE_PY, PUSH = "tools/report.py", "tools/other.py", "merge/merge.py", "hooks/push.sh"
COMMON = "tools/common_args.py"  # a shared parent parser that a script can take its flags from
LIB ="export const refusals = [\n  'a',\n  'b',\n  'c',\n  'd',\n];\n"  # long enough that git pairs a move as a rename
GUARD = "def _process_start_ms(path):\n    return 0\n\n\ndef keep():\n    return 1\n"
CODE = {
    "hooks/lib.mjs": LIB,
    "hooks/guard.py": GUARD,
    "hooks/guard_core.py": "def core():\n    return 2\n",
    "lint/x.py": "def check():\n    return 3\n",
}
Range = collections.namedtuple("Range", "case repo base head")
FINDING = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): (?P<code>STALE00[1-3]) (?P<text>.*)$")


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


def parser_script(flags):
    """A Python script that declares each of `flags` with add_argument, as a CLI does. Never run."""
    return "import argparse\n\nparser = argparse.ArgumentParser()\n" + "".join(
        'parser.add_argument("%s")\n' % flag for flag in flags)


def argument_flags(source):
    """The string literals passed to add_argument in a Python source, read with ast. A flag that only appears in
    a docstring or a comment is not declared."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument":
            found.update(arg.value for arg in node.args
                         if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"))
    return found


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


class FlagTests(StaleCase):
    """STALE003: a `script --flag` pair in one code span, where the range removed that flag from that script. A flag is
    an add_argument literal in a Python script (read with ast) and a whole-word token in any other script."""

    def test_removed_py_flag_cited_in_one_code_span_is_flagged(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base declares --between
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no flag
        notes = "# Notes\n\n- report: `tools/report.py --between START END`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        found = self.assert_flags(self.make_range(base_files(notes, extra={REPORT: base_src}), change),
                                  [(NOTES, 3, "STALE003")])
        self.assertIn("--between", found[0][3])

    def test_a_flag_still_named_in_a_docstring_or_comment_is_removed_once_its_call_goes(self):
        base_src = parser_script(["--between"])
        head_src = ('"""Use --between to pick a window."""\n' + parser_script([])
                    + '# parser.add_argument("--between")\n')
        self.assertIn("--between", head_src)  # scope: head still names --between in its text
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no flag
        notes = "# Notes\n\n- report: `tools/report.py --between START END`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={REPORT: base_src}), change),
                          [(NOTES, 3, "STALE003")])

    def test_removed_shell_flag_cited_in_one_code_span_is_flagged(self):
        base_sh, head_sh = "#!/bin/sh\ngit push --force origin HEAD\n", "#!/bin/sh\ngit push origin HEAD\n"
        self.assertIn("--force", base_sh)  # scope: base has the token
        self.assertNotIn("--force", head_sh)  # scope: head has no token
        notes = "# Notes\n\n- push: `hooks/push.sh --force origin`\n"

        def change(repo):
            write(repo, PUSH, head_sh)
            commit(repo)
        found = self.assert_flags(self.make_range(base_files(notes, extra={PUSH: base_sh}), change),
                                  [(NOTES, 3, "STALE003")])
        self.assertIn("--force", found[0][3])

    def test_a_shell_flag_counts_as_removed_only_when_its_whole_word_goes(self):
        base_sh = "#!/bin/sh\nreport --between A\nreport --between-x B\n"
        head_sh = "#!/bin/sh\nreport --between-x B\n"
        self.assertIn("--between ", base_sh)  # scope: base has --between as a whole word
        self.assertNotIn("--between ", head_sh)  # scope: head keeps only --between-x, a longer token
        notes = "# Notes\n\n- run: `hooks/report.sh --between A`\n"

        def change(repo):
            write(repo, "hooks/report.sh", head_sh)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={"hooks/report.sh": base_sh}), change),
                          [(NOTES, 3, "STALE003")])

    def test_one_span_fires_past_comment_openers_and_a_lone_quote_and_a_split_cite_does_not(self):
        rows = [
            ("# Flags: `tools/report.py --between`", True),  # a heading opens with `#`
            ("Use `#` to start a comment: `tools/report.py --between`.", True),
            ("Open a comment with `<!--`: `tools/report.py --between`.", True),
            ("Don't run `tools/report.py --between` by hand.", True),  # a lone quote in text
            ("```", False),
            ("/* open comment: `tools/report.py --between`", True),  # a fenced block counts as prose
            ("```", False),
            ("tools/report.py --between START END", False),  # no code span, so no cite
            ("- report: `tools/report.py`", False),
            ("  `--between START END`", False),  # the path and the flag sit on two lines
            ("- report: `tools/report.py` and `--between START END`", False),  # two spans on one line
            ("- report: `tools/report.py --between START END`", True),
        ]
        text, lines = rows_text(rows)
        base_src = parser_script(["--between"])
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base declares --between

        def change(repo):
            write(repo, REPORT, parser_script([]))
            write(repo, NOTES, text)
            commit(repo)
        self.assert_flags(self.make_range(base_files("", extra={REPORT: base_src}), change),
                          [(NOTES, n, "STALE003") for n in lines])

    def test_a_flag_the_script_still_declares_is_not_flagged_in_a_full_size_script(self):
        kept = ["--flag-%02d" % i for i in range(40)]
        base_src, head_src = parser_script(kept + ["--between"]), parser_script(kept)
        removed = argument_flags(base_src) - argument_flags(head_src)
        self.assertEqual(removed, {"--between"})  # scope: only --between goes
        notes = "# Notes\n\n- report: `tools/report.py --flag-07 5`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={REPORT: base_src}), change))

    def test_git_push_force_names_no_script_so_it_is_not_flagged(self):
        base_sh, head_sh = "#!/bin/sh\ngit push --force origin HEAD\n", "#!/bin/sh\ngit push origin HEAD\n"
        self.assertIn("--force", base_sh)  # scope: the base script has --force
        self.assertNotIn("--force", head_sh)  # scope: the range removes --force from it
        notes = "# Notes\n\n- never force: `git push --force`\n"

        def change(repo):
            write(repo, PUSH, head_sh)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={PUSH: base_sh}), change))

    def test_a_flag_cited_on_another_scripts_span_is_not_flagged(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        other_src = parser_script(["--between"])
        self.assertEqual(argument_flags(other_src), {"--between"})  # scope: OTHER keeps --between
        notes = "# Notes\n\n- rerun: `tools/other.py --between START END`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={REPORT: base_src, OTHER: other_src}), change))

    def test_a_shim_path_is_not_flagged_for_a_flag_its_target_removes(self):
        shim = ('#!/usr/bin/env python3\n# Shim for the merge tool. Starts merge/merge.py; no merge logic lives here.\n'
                'import subprocess, sys\nsubprocess.run([sys.executable, "merge/merge.py", *sys.argv[1:]])\n')
        base_merge, head_merge = parser_script(["--base", "--dry-run"]), parser_script(["--dry-run"])
        self.assertNotIn("--base", shim)  # scope: the shim declares no --base
        removed = argument_flags(base_merge) - argument_flags(head_merge)
        self.assertEqual(removed, {"--base"})  # scope: merge.py removes --base
        notes = "# Notes\n\n- merge: `bin/merge --base origin/main`\n"

        def change(repo):
            write(repo, "bin/merge", shim.replace("no merge logic", "no merge code"))  # the range touches the shim
            write(repo, MERGE_PY, head_merge)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={"bin/merge": shim, MERGE_PY: base_merge}), change))

    def test_a_flag_named_only_in_a_docstring_at_base_was_never_declared(self):
        base_src = '"""Use --between to pick a window."""\n' + parser_script(["--old"])
        head_src = parser_script([])
        self.assertEqual(argument_flags(base_src), {"--old"})  # scope: --between is only in the docstring
        self.assertEqual(argument_flags(head_src), set())  # scope: the range removes --old
        notes = "# Notes\n\n- report: `tools/report.py --between START END`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={REPORT: base_src}), change))

    def test_a_shell_flag_is_not_removed_by_a_longer_flag_going(self):
        base_sh, head_sh = "#!/bin/sh\ngit push --force-with-lease origin HEAD\n", "#!/bin/sh\ngit push origin HEAD\n"
        self.assertNotIn("--force ", base_sh)  # scope: base has no whole-word --force
        self.assertIn("--force-with-lease", base_sh)  # scope: the range removes --force-with-lease
        notes = "# Notes\n\n- push: `hooks/push.sh --force origin`\n"

        def change(repo):
            write(repo, PUSH, head_sh)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={PUSH: base_sh}), change))

    def test_a_claude_home_cite_resolves_to_the_repo_path_and_fires(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base declares --between
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no flag
        notes = "# Notes\n\n- report: `python3 ~/.claude/lint/x.py --between START END`\n"

        def change(repo):
            write(repo, "lint/x.py", head_src)
            commit(repo)
        found = self.assert_flags(self.make_range(base_files(notes, extra={"lint/x.py": base_src}), change),
                                  [(NOTES, 3, "STALE003")])
        self.assertIn("--between", found[0][3])

    def assert_moved_flag_passes(self, cite, base_extra, change):
        """No STALE003 for `cite` when `change` moves its flag to a file the range touches."""
        self.assert_passes(self.make_range(base_files("# Notes\n\n- run: `%s`\n" % cite, extra=base_extra), change))

    def test_a_flag_moved_to_a_py_file_the_range_adds_is_not_flagged(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        shared_src = parser_script(["--between"])  # a shared parent parser takes the flag, in a file added here
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base report declares --between
        self.assertEqual(argument_flags(head_src), set())  # scope: head report declares no flag
        self.assertEqual(argument_flags(shared_src), {"--between"})  # scope: the touched file declares --between

        def change(repo):
            write(repo, REPORT, head_src)
            write(repo, COMMON, shared_src)
            commit(repo)
        self.assert_moved_flag_passes("tools/report.py --between START END", {REPORT: base_src}, change)

    def test_a_flag_moved_to_a_py_file_the_range_modifies_is_not_flagged(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        base_common, head_common = parser_script(["--other"]), parser_script(["--other", "--between"])
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base report declares --between
        self.assertEqual(argument_flags(head_src), set())  # scope: head report declares no flag
        self.assertEqual(argument_flags(base_common), {"--other"})  # scope: base common does not declare --between
        self.assertEqual(argument_flags(head_common), {"--other", "--between"})  # scope: head common declares it

        def change(repo):
            write(repo, REPORT, head_src)
            write(repo, COMMON, head_common)
            commit(repo)
        self.assert_moved_flag_passes("tools/report.py --between START END",
                                      {REPORT: base_src, COMMON: base_common}, change)

    def test_a_shell_flag_moved_to_a_sh_file_the_range_adds_is_not_flagged(self):
        base_sh, head_sh = "#!/bin/sh\nreport --between A\n", "#!/bin/sh\nreport A\n"
        shared_sh = '#!/bin/sh\nparse_window --between "$@"\n'  # a shared helper takes the flag, in a file added here
        self.assertIn("--between ", base_sh)  # scope: base script has --between as a whole word
        self.assertNotIn("--between", head_sh)  # scope: head script has no --between
        self.assertIn("--between ", shared_sh)  # scope: the touched shell file has --between as a whole word

        def change(repo):
            write(repo, "hooks/report.sh", head_sh)
            write(repo, "hooks/common.sh", shared_sh)
            commit(repo)
        self.assert_moved_flag_passes("hooks/report.sh --between A", {"hooks/report.sh": base_sh}, change)

    def test_a_shell_flag_moved_to_a_sh_file_the_range_modifies_is_not_flagged(self):
        base_sh, head_sh = "#!/bin/sh\nreport --between A\n", "#!/bin/sh\nreport A\n"
        base_common = '#!/bin/sh\nparse_window --other "$@"\n'
        head_common = '#!/bin/sh\nparse_window --other --between "$@"\n'
        self.assertIn("--between ", base_sh)  # scope: base script has --between as a whole word
        self.assertNotIn("--between", head_sh)  # scope: head script has no --between
        self.assertNotIn("--between", base_common)  # scope: base shared file does not have --between
        self.assertIn("--between ", head_common)  # scope: head shared file has --between as a whole word

        def change(repo):
            write(repo, "hooks/report.sh", head_sh)
            write(repo, "hooks/common.sh", head_common)
            commit(repo)
        self.assert_moved_flag_passes("hooks/report.sh --between A",
                                      {"hooks/report.sh": base_sh, "hooks/common.sh": base_common}, change)

    def test_a_flag_removed_with_no_new_home_still_fires_beside_a_touched_file(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        other_src = parser_script(["--other"])  # a file the range touches, with no --between in it
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base report declares --between
        self.assertEqual(argument_flags(head_src), set())  # scope: head report declares no flag
        self.assertNotIn("--between", argument_flags(other_src))  # scope: the range gives --between no new home
        notes = "# Notes\n\n- report: `tools/report.py --between START END`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            write(repo, COMMON, other_src)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={REPORT: base_src}), change),
                          [(NOTES, 3, "STALE003")])

    def test_ste_disable_line_names_stale003_and_no_other(self):
        rows = [
            ("- report: `tools/report.py --between START END` <!-- ste-disable-line STALE003 -->", False),
            ("- report: `tools/report.py --between START END` <!-- ste-disable-line STALE001 -->", True),
            ("- report: `tools/report.py --between START END`", True),
        ]
        text, lines = rows_text(rows)
        base_src = parser_script(["--between"])
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base declares --between

        def change(repo):
            write(repo, REPORT, parser_script([]))
            write(repo, NOTES, text)
            commit(repo)
        self.assert_flags(self.make_range(base_files("", extra={REPORT: base_src}), change),
                          [(NOTES, n, "STALE003") for n in lines])


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

    def test_a_touched_sh_that_removes_no_flag_starts_one_cat_file_and_reads_no_markdown(self):
        base_sh = "#!/bin/sh\nreport --between A\n"
        head_sh = base_sh + "echo done\n"
        self.assertIn("--between ", head_sh)  # scope: the range keeps the script's flag, so it removes none
        self.assertEqual(head_sh.replace("echo done\n", ""), base_sh)  # scope: the only change is one added line

        def change(repo):
            write(repo, "hooks/report.sh", head_sh)
            commit(repo)
        notes = "# Notes\n\n- refusal list in `hooks/lib.mjs`\n"
        rng = self.make_range(base_files(notes, extra={"hooks/report.sh": base_sh}), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(subs), ["cat-file", "diff", "merge-base", "rev-parse"], subs)
        # ls-tree lists the tracked Markdown, so a run without it reads no .md; the one cat-file reads the script.
        self.assertNotIn("ls-tree", subs, subs)

    def test_a_lone_touched_mjs_starts_three_git_processes_and_prints_no_unknown_line(self):
        def change(repo):
            write(repo, "hooks/lib.mjs", LIB + "export const more = 1;\n")
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- `hooks/lib.mjs` `refusals`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(unknown_lines(out), [], out)
        self.assertEqual(sorted(subs), ["diff", "merge-base", "rev-parse"], subs)

    def test_a_range_that_removes_a_path_starts_at_most_five_git_processes(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n"), change)
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 1, out)
        self.assertLessEqual(len(subs), 5, subs)

    def test_a_range_that_removes_a_flag_starts_at_most_five_git_processes(self):
        def change(repo):
            write(repo, REPORT, parser_script([]))
            commit(repo)
        notes = "# Notes\n\n- report: `tools/report.py --between START END`\n"
        rng = self.make_range(base_files(notes, extra={REPORT: parser_script(["--between"])}), change)
        rc, out, subs = self.run_traced(rng)
        self.assertIn(rc, (0, 1), out)
        self.assertNotIn("Traceback", out)
        self.assertLessEqual(len(subs), 5, subs)
        self.assertTrue(set(subs) <= {"rev-parse", "merge-base", "diff", "cat-file", "ls-tree"}, subs)

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
