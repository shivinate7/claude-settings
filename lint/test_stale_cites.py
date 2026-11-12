#!/usr/bin/env python3
"""Cases for lint/stale_cites.py. Standard library only.

    python3 lint/test_stale_cites.py

The merge check refuses stale prose. A tracked Markdown line that names a repo path the range deleted
or renamed is STALE001. A `<file.py> <name>` pair on one line is STALE002 when the name was bound at module
level in that file at base (a def, class, assignment or import) and is not bound there at head. A `--flag` in one
code span with its script path is STALE007 when the range removed that flag from that script. Each finding
is one line, `path:line: CODE message`.
A clean run prints `stale-cites: PASS` and exits 0.
The report (decision stale-cites-at-merge) prints after the findings and never changes the exit code. It names
each anchor whose sentence changed in CLAUDE.md or the output style, with its rule_mechanisms.json row and the changed
files under hooks/, lint/, bin/, actions/ and .github/ (no touched or untouched verdict), and each changed code file
with the decisions whose Home names it and the rows that name it.
STALE005 (range mode only) reports an added governed line that states a capability by route with no backing. It is
report only: the exit code does not change (RouteClaimTests).
STALE009 (range mode only) reports an added decision-record line that states what code does, with no cite of a bound
name. It is report only too (CodeClaimTests).
STALE010 (range mode) is a finding: an added line that cites a Python name the head does not bind, or a file absent at
head in a tracked top folder, in a STALE002 form or a node id. A cite into an untracked top folder is no cite here
(NameCiteTests). A cite is judged on added lines only.


`--tree [REV]` reads every tracked Markdown file at REV instead of a range: STALE003 for a path cite that names
nothing tracked, STALE004 for a line anchor past the file's end (TreeTests, CostTests).

STALE008 (range mode) reads a Python value cite, `file.py: NAME = literal` in backticks (ValueCiteTests): a line that
quotes the value the range changed or removed, or a line the range adds that does not match the value at head. A
JavaScript cite prints unknown, and a JSON cite is not read. The parity rows in
skills/plain-english-map/tests/value-cite-parity.json hold this grammar to the map's (ValueCiteTests, and F2f in
fact-lines.test.mjs).

Each case makes a temp git repo: the base commit on `main`, the head commit on `topic`. The check runs
with the repo as cwd and the range as commit ids. The step cases run bin/ste-changed, which runs
actions/ste-lint/run.sh with the step's env. TMPDIR is the case folder, so temp files stay in the run folder.
"""
import ast
import atexit
import collections
import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
MODULE = os.environ.get("STALE_CITES_UNDER_TEST") or os.path.join(HERE, "stale_cites.py")
STEP = os.path.join(ROOT, "bin", "ste-changed")
STEP_SH = os.path.join(ROOT, "actions", "ste-lint", "run.sh")
BASH = "/bin/bash" if os.path.exists("/bin/bash") else (shutil.which("bash") or "bash")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree, for a base with no shared history
PARITY = os.path.join(ROOT, "skills", "plain-english-map", "tests", "value-cite-parity.json")  # the rows both suites read
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  removes a fixture tree, read-only git objects included (testing/tracked_tree.py)
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)

RUN_FOLDER = _test_temp.run_folder()
atexit.register(tracked_tree.rm_tree, RUN_FOLDER)

NOTES = "docs/debts/notes.md"
MOVED = "mods/session-board/hooks/lib.mjs"
REPORT, OTHER, MERGE_PY, PUSH = "tools/report.py", "tools/other.py", "merge/merge.py", "hooks/push.sh"
COMMON = "tools/common_args.py"  # a shared parent parser that a script can take its flags from
PAGES = "tools/stale_pages.py"  # the script that the bare basename `stale_pages.py` names
SAME_NAME = "hooks/report.py"  # a second report.py, in another folder than REPORT
SCRIPT_A, SCRIPT_B = "lint/a.py", "lint/b.py"  # two scripts that one code span can cite, in order
LIB = "export const refusals = [\n  'a',\n  'b',\n  'c',\n  'd',\n];\n"  # long enough that git pairs a move as a rename
GUARD = "def _process_start_ms(path):\n    return 0\n\n\ndef keep():\n    return 1\n"
CODE = {
    "hooks/lib.mjs": LIB,
    "hooks/guard.py": GUARD,
    "hooks/guard_core.py": "def core():\n    return 2\n",
    "lint/x.py": "def check():\n    return 3\n",
}
Range = collections.namedtuple("Range", "case repo base head")
FINDING = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): (?P<code>STALE00[1-478]|STALE010) (?P<text>.*)$")  # not STALE005 or STALE009: report lines


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


def module_value(source, name):
    """The literal the last module-level assignment of `name` binds, read with ast and never run. None when no such
    assignment is at module level, so a name bound only inside a def gives None. Scope only: a case asserts its
    fixture values with this before it probes the check."""
    found = None
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            found = ast.literal_eval(node.value)
    return found


def whole_tree_listings(commands):
    """The `ls-tree` commands that list the whole tree at a rev: the listing that finds every tracked Markdown file.
    The report's Home half lists decision paths after ` -- `, so its listing is no listing of Markdown."""
    return [command for command in commands if command.startswith("ls-tree") and " -- " not in command]


def parity_rows():
    """The rows of the value-cite parity fixture, which the Python suite and tests/fact-lines.test.mjs both read."""
    with open(PARITY, encoding="utf-8") as f:
        return json.load(f)["rows"]


def unknown_lines(out):
    """Each line the check printed as unknown."""
    return [line for line in out.splitlines() if line.startswith("stale-cites: unknown, ")]


def parser_script(flags, parents=(), table=(), rebound=False, starred=(), single=()):
    """A Python script that declares each of `flags` with add_argument, as a CLI does. Each name in `parents` is a
    parent parser that COMMON defines: the script imports it and takes it as `parents=[name()]`. Each row of `table`
    is a (flag, metavar, help) row of a CHECK_FLAGS tuple, which a loop declares, as a CLI's table does. `rebound`
    binds CHECK_FLAGS a second time, with a plain assignment, so no reader takes its rows. `starred` is a list that
    one `add_argument(*STARRED)` call declares. `single` is a list that a single-target loop, `for flag in SINGLE`,
    declares one flag per row. Never run."""
    module = os.path.splitext(os.path.basename(COMMON))[0]
    imports = "".join("from %s import %s\n" % (module, name) for name in parents)
    takes = "parents=[%s]" % ", ".join(name + "()" for name in parents) if parents else ""
    rebind = "CHECK_FLAGS = CHECK_FLAGS[:]\n" if rebound else ""
    constant = ("CHECK_FLAGS = (%s\n)\n%s\n" % ("".join('\n    ("%s", "%s", "%s"),' % row for row in table), rebind)
                if table else "")
    loop = "for flag, _, text in CHECK_FLAGS:\n    parser.add_argument(flag, help=text)\n" if table else ""
    star = ("STARRED = [%s]\nparser.add_argument(*STARRED)\n" % ", ".join('"%s"' % f for f in starred)) if starred else ""
    single_loop = ("SINGLE = [%s]\nfor flag in SINGLE:\n    parser.add_argument(flag)\n" % ", ".join('"%s"' % f for f in single)
                   if single else "")
    return ("import argparse\n" + imports + "\n" + constant + "parser = argparse.ArgumentParser(%s)\n" % takes
            + "".join('parser.add_argument("%s")\n' % flag for flag in flags) + loop + star + single_loop)


def shared_parser(flags):
    """COMMON's source: `window_parser()`, a parent parser that declares each of `flags`."""
    return ("import argparse\n\n\ndef window_parser():\n    parser = argparse.ArgumentParser(add_help=False)\n"
            + "".join('    parser.add_argument("%s")\n' % flag for flag in flags) + "    return parser\n")


def subparser_script(flags, window=False, keyword=False):
    """A Python script with two subcommands, `a` and `b`. Subcommand `a` declares each of `flags` with add_argument, as
    a CLI does, or takes the helper `add_window` from COMMON when `window` is set, passing `a` by keyword when `keyword`
    is set. `b` always takes `add_window`. Never run."""
    module = os.path.splitext(os.path.basename(COMMON))[0]
    lines = ["import argparse", "from %s import add_window" % module, "", "parser = argparse.ArgumentParser()",
             "sub = parser.add_subparsers()", 'a = sub.add_parser("a")']
    call = ["add_window(parser=a)" if keyword else "add_window(a)"] if window else []
    lines += ['a.add_argument("%s")' % flag for flag in flags] + call
    lines += ['b = sub.add_parser("b")', "add_window(b)"]
    return "\n".join(lines) + "\n"


def add_window_source(flags):
    """COMMON's source: `add_window(parser)`, a helper that a subcommand calls to declare each of `flags`."""
    return "def add_window(parser):\n" + "".join('    parser.add_argument("%s")\n' % flag for flag in flags)


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
    def make_range(self, base, change, history=()):
        """Commit each `history` step on main, one commit per step, then `base`, then run `change(repo)` on topic. A
        step runs before the base, so the range does not touch the paths it made. `change` makes its own commit, so a
        case can leave a file untracked after it."""
        case = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, case)
        repo = os.path.join(case, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q")
        git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        for step in history:
            step(repo)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "history")
        for path, text in base.items():
            write(repo, path, text)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        base_sha = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "topic")
        change(repo)
        return Range(case, repo, base_sha, git(repo, "rev-parse", "HEAD"))

    def route_range(self, rows, extra=None, base_notes="# Notes\n", head_extra=None, history=()):
        """A range that rewrites NOTES as `rows`, given as (line, flagged) pairs. `extra` is committed at base and
        `head_extra` ({path: text}) at head. `history` steps are committed before the base (see make_range). Returns
        (range, flagged lines)."""
        text, flagged = rows_text(rows)

        def change(repo):
            write(repo, NOTES, text)
            for path, body in (head_extra or {}).items():
                write(repo, path, body)
            commit(repo)
        return self.make_range(base_files(base_notes, extra=extra), change, history=history), flagged

    def rows_range(self, rows, head_extra=None):
        """A range that rewrites the decision record DECISION as `rows` ((text, flagged) pairs) over a base of a heading
        and the merge/merge.py fixture. `head_extra` ({path: text}) is written at head too. Returns (range, flagged)."""
        text, flagged = rows_text(rows)

        def change(repo):
            write(repo, DECISION, text)
            for path, body in (head_extra or {}).items():
                write(repo, path, body)
            commit(repo)
        return self.make_range(base_files(extra={DECISION: "# Heading\n", MERGE_PY: LANE_LINT}), change), flagged

    def run_check(self, rng, base=None, extra_env=None, spec=None):
        """(exit code, output) of `--range`. `spec` gives the range text when a case needs another shape."""
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/stale_cites.py")
        env = dict(os.environ, TMPDIR=rng.case, **(extra_env or {}))
        if spec is None:
            spec = "%s...%s" % (rng.base if base is None else base, rng.head)
        done = subprocess.run([sys.executable, MODULE, "--range", spec],
                              cwd=rng.repo, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        return done.returncode, done.stdout + done.stderr

    def run_traced_commands(self, rng, spec=None):
        """(rc, out, the git commands a run started), read from a GIT_TRACE file. `spec` is the range text, as run_check takes it."""
        trace = os.path.join(rng.case, "git-trace.txt")
        rc, out = self.run_check(rng, spec=spec, extra_env={"GIT_TRACE": trace})
        return rc, out, git_commands(trace)

    def assert_starts_after_failed_read(self, rng, spec, failed_read, rc, expected):
        """Pin the git commands a failing `spec` starts after its one `failed_read`, with its exit code `rc`. The
        count and the order of `expected` are both checked, so a change shows which start moved."""
        code, out, traced = self.run_traced_commands(rng, spec=spec)
        self.assertEqual(code, rc, "%s exited %d, expected %d\n%s" % (spec, code, rc, out))
        commands = [" ".join(shlex.split(command)) for command in traced]  # the trace quotes `^{...}` arguments
        reads = [i for i, command in enumerate(commands) if command.split()[0] == failed_read]
        self.assertEqual(len(reads), 1, "scope: %s ran the %s read %d times, not once\n%s"
                         % (spec, failed_read, len(reads), commands))
        after = commands[reads[0] + 1:]
        self.assertEqual(len(after), len(expected), "%s starts %d git processes after its failed %s, expected %d\n%s"
                         % (spec, len(after), failed_read, len(expected), after))
        self.assertEqual(after, expected, "%s starts other git processes after its failed %s than the pinned list\n%s"
                         % (spec, failed_read, after))

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

    def depth_one_clone(self, rng):
        """A depth-1 clone of the range's repo: the head is in it and the base is cut away. Asserts the clone is
        shallow and the base is out before a case reads it. Returns the clone's folder."""
        clone = os.path.join(rng.case, "shallow")
        self.assertEqual(shallow_clone.make(rng.repo, clone, rng.head), "", "scope: the depth-1 clone was made")
        self.assertTrue(shallow_clone.facts(clone, rng.head)["shallow"], "scope: the clone is shallow")
        self.assertFalse(has_object(clone, rng.base), "scope: the base is cut from the clone")
        return clone

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


class FlagTests(StaleCase):
    """STALE007: a `script --flag` pair in one code span, where the range removed that flag from that script. A flag is
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
                                  [(NOTES, 3, "STALE007")])
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
                          [(NOTES, 3, "STALE007")])

    def test_removed_shell_flag_cited_in_one_code_span_is_flagged(self):
        base_sh, head_sh = "#!/bin/sh\ngit push --force origin HEAD\n", "#!/bin/sh\ngit push origin HEAD\n"
        self.assertIn("--force", base_sh)  # scope: base has the token
        self.assertNotIn("--force", head_sh)  # scope: head has no token
        notes = "# Notes\n\n- push: `hooks/push.sh --force origin`\n"

        def change(repo):
            write(repo, PUSH, head_sh)
            commit(repo)
        found = self.assert_flags(self.make_range(base_files(notes, extra={PUSH: base_sh}), change),
                                  [(NOTES, 3, "STALE007")])
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
                          [(NOTES, 3, "STALE007")])

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
                          [(NOTES, n, "STALE007") for n in lines])

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

    def range_drops_json_from_a(self, notes, others=None):
        """A range that removes --json from SCRIPT_A and keeps --check there. `notes` and `others` ({path: text}) are
        committed at base, and only SCRIPT_A changes at head."""
        base_src, head_src = parser_script(["--check", "--json"]), parser_script(["--check"])
        self.assertEqual(argument_flags(base_src), {"--check", "--json"})  # scope: base declares --json in a.py
        self.assertEqual(argument_flags(head_src), {"--check"})  # scope: head removes only --json from a.py

        def change(repo):
            write(repo, SCRIPT_A, head_src)
            commit(repo)
        return self.make_range(base_files(notes, extra={SCRIPT_A: base_src, **(others or {})}), change)

    def test_a_flag_after_a_later_script_in_one_span_is_not_read_for_the_earlier_script(self):
        b_src = parser_script(["--json"])
        self.assertEqual(argument_flags(b_src), {"--json"})  # scope: b.py keeps --json, and the range leaves b.py alone
        notes = "# Notes\n\n- check: `python3 lint/a.py --check && python3 lint/b.py --json`\n"
        self.assert_passes(self.range_drops_json_from_a(notes, others={SCRIPT_B: b_src}))

    def test_a_flag_before_its_script_in_one_span_is_not_read_for_that_script(self):
        notes = "# Notes\n\n- verdict: `bin/verdict --json python3 lint/a.py`\n"
        self.assert_passes(self.range_drops_json_from_a(notes))

    def test_a_flag_after_a_pipe_is_not_read_for_the_script_before_the_pipe(self):
        notes = "# Notes\n\n- check: `lint/a.py --check | jq --json`\n"
        self.assert_passes(self.range_drops_json_from_a(notes))

    def assert_b_json_after_span_passes(self, span):
        """`span` cites lint/a.py --check, then lint/b.py --json. a.py loses --json and b.py keeps it, so nothing is flagged."""
        b_src = parser_script(["--json"])
        self.assertEqual(argument_flags(b_src), {"--json"})  # scope: b.py keeps --json, and the range leaves b.py alone
        self.assert_passes(self.range_drops_json_from_a("# Notes\n\n- check: `%s`\n" % span, others={SCRIPT_B: b_src}))

    def test_a_flag_after_a_semicolon_glued_to_a_flag_is_not_read_for_the_script_before_it(self):
        self.assert_b_json_after_span_passes("lint/a.py --check; lint/b.py --json")

    def test_a_flag_after_a_spaced_semicolon_is_not_read_for_the_script_before_it(self):
        self.assert_b_json_after_span_passes("lint/a.py --check ; lint/b.py --json")

    def test_a_flag_after_a_double_pipe_is_not_read_for_the_script_before_it(self):
        self.assert_b_json_after_span_passes("lint/a.py --check || lint/b.py --json")

    def test_a_flag_after_a_single_ampersand_is_not_read_for_the_script_before_it(self):
        self.assert_b_json_after_span_passes("lint/a.py --check & lint/b.py --json")

    def test_a_flag_right_after_its_own_script_is_still_flagged(self):
        notes = "# Notes\n\n- json: `lint/a.py --json`\n"
        found = self.assert_flags(self.range_drops_json_from_a(notes), [(NOTES, 3, "STALE007")])
        self.assertIn("--json", found[0][3])

    def test_the_same_script_after_a_separator_is_still_flagged_for_its_own_flag(self):
        notes = "# Notes\n\n- check: `python3 lint/a.py --check && python3 lint/a.py --json`\n"
        found = self.assert_flags(self.range_drops_json_from_a(notes), [(NOTES, 3, "STALE007")])
        self.assertIn("--json", found[0][3])

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
                                  [(NOTES, 3, "STALE007")])
        self.assertIn("--between", found[0][3])

    def assert_moved_flag_passes(self, cite, base_extra, change):
        """No STALE007 for `cite` when `change` moves its flag to a file the range touches."""
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
                          [(NOTES, 3, "STALE007")])

    def test_ste_disable_line_names_stale007_and_no_other(self):
        rows = [
            ("- report: `tools/report.py --between START END` <!-- ste-disable-line STALE007 -->", False),
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
                          [(NOTES, n, "STALE007") for n in lines])

    def test_removed_py_flag_cited_by_bare_basename_is_flagged_beside_its_full_path_cite(self):
        base_src, head_src = parser_script(["--items"]), parser_script([])
        self.assertEqual(argument_flags(base_src), {"--items"})  # scope: base declares --items
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no flag
        notes = "# Notes\n\n- pages: `tools/stale_pages.py --items START`\n- pages: `stale_pages.py --items`\n"

        def change(repo):
            write(repo, PAGES, head_src)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={PAGES: base_src}), change),
                          [(NOTES, 3, "STALE007"), (NOTES, 4, "STALE007")])

    def test_removed_shell_flag_cited_by_dot_slash_path_is_flagged_beside_its_bare_cite(self):
        base_sh, head_sh = "#!/bin/sh\nsetup --cloud \"$@\"\n", "#!/bin/sh\nsetup \"$@\"\n"
        self.assertIn("--cloud ", base_sh)  # scope: base has --cloud as a whole word
        self.assertNotIn("--cloud", head_sh)  # scope: head has no --cloud
        notes = "# Notes\n\n- install: `install.sh --cloud`\n- install: `./install.sh --cloud`\n"

        def change(repo):
            write(repo, "install.sh", head_sh)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={"install.sh": base_sh}), change),
                          [(NOTES, 3, "STALE007"), (NOTES, 4, "STALE007")])

    def test_bare_basename_naming_two_scripts_is_not_flagged_while_its_full_path_cite_is(self):
        base_src, head_src = parser_script(["--between"]), parser_script([])
        same_src = parser_script(["--between"])  # the other report.py keeps --between, and the range does not touch it
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base REPORT declares --between
        self.assertEqual(argument_flags(head_src), set())  # scope: head REPORT declares no flag
        self.assertEqual(argument_flags(same_src), {"--between"})  # scope: SAME_NAME keeps --between
        notes = ("# Notes\n\n- report: `tools/report.py --between START END`\n"
                 "- report: `report.py --between START END`\n")

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_flags(self.make_range(base_files(notes, extra={REPORT: base_src, SAME_NAME: same_src}), change),
                          [(NOTES, 3, "STALE007")])

    def test_flag_taken_from_an_untouched_shared_parent_is_not_flagged(self):
        base_src = parser_script(["--between"])
        head_src = parser_script([], parents=("window_parser",))
        shared_src = shared_parser(["--between"])  # COMMON declares --between at base, and the range leaves it alone
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base REPORT declares --between itself
        self.assertEqual(argument_flags(head_src), set())  # scope: head REPORT declares no flag of its own
        self.assertIn("parents=[window_parser()]", head_src)  # scope: head REPORT takes its parser from COMMON
        self.assertEqual(argument_flags(shared_src), {"--between"})  # scope: the shared parent declares --between
        notes = "# Notes\n\n- report: `tools/report.py --between START END`\n"

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_passes(self.make_range(base_files(notes, extra={REPORT: base_src, COMMON: shared_src}), change))

    def assert_control_fires_and_subject_does_not(self, rng, control, subject, flag):
        """Line `control` cites a flag the range really removed, and STALE007 flags it. Line `subject` cites `flag`, which
        the script still declares in a form the reader does not take as a literal, and STALE007 must not flag it. The
        control is asserted first, so the subject is judged on a run the reader really made."""
        rc, out = self.run_check(rng)
        self.assertNotIn("Traceback", out, out)  # a crash is not a read
        self.assertIn("stale-cites: FAIL", out, out)
        found = [(p, n, c) for p, n, c, _ in parse(out)]
        self.assertIn((NOTES, control, "STALE007"), found, out)  # control: a removed literal still fires
        self.assertNotIn((NOTES, subject, "STALE007"), found,
                         "line %d cites %s, which the script still declares, yet STALE007 flagged it:\n%s"
                         % (subject, flag, out))

    def test_flag_declared_through_a_loop_over_a_constant_is_not_flagged(self):
        rows = (("--root", "<repo>", "repo root"), ("--page-url", "<url>", "the page URL"),
                ("--item", "<id>", "the item id"), ("--fetched", "<dir>", "the fetch folder"))
        base_src = parser_script(["--pick", "--old"], table=rows)
        head_src = parser_script([], table=rows + (("--pick", "<key>", "the pick a peer relayed"),))
        self.assertEqual(argument_flags(base_src), {"--pick", "--old"})  # scope: base declares both as literals
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no literal flag
        self.assertIn("for flag, _, text in CHECK_FLAGS:", head_src)  # scope: head declares through the loop
        self.assertIn("--pick", [row[0] for row in module_value(head_src, "CHECK_FLAGS")])  # scope: head's table holds --pick
        notes = ("# Notes\n\n- report: `tools/report.py --pick KEY`\n"  # line 3: still declared
                 "- report: `tools/report.py --old 5`\n")  # line 4: really removed

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_control_fires_and_subject_does_not(
            self.make_range(base_files(notes, extra={REPORT: base_src}), change), control=4, subject=3, flag="--pick")

    def test_flag_declared_by_an_untouched_helper_called_from_a_subparser_is_not_flagged(self):
        base_src, head_src = subparser_script(["--between", "--old"]), subparser_script([], window=True)
        helper_src = add_window_source(["--between"])  # COMMON, untouched by the range, declares --between
        self.assertEqual(argument_flags(base_src), {"--between", "--old"})  # scope: base declares both as literals
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no literal flag
        self.assertIn("add_window(a)", head_src)  # scope: head's subcommand a takes its flags from the helper
        self.assertEqual(argument_flags(helper_src), {"--between"})  # scope: the untouched helper declares --between
        notes = ("# Notes\n\n- report: `tools/report.py --between START END`\n"  # line 3: declared by the helper
                 "- report: `tools/report.py --old 5`\n")  # line 4: really removed

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_control_fires_and_subject_does_not(
            self.make_range(base_files(notes, extra={REPORT: base_src, COMMON: helper_src}), change),
            control=4, subject=3, flag="--between")

    def test_flag_named_as_a_constant_in_a_table_bound_twice_reads_unknown_not_removed(self):
        """A removed flag that head still names as a string constant, in a table bound twice, is unknown for its cite.
        No reader takes that table's rows, so the flag is never called removed. Control: the same shape with the flag
        gone entirely still fires."""
        base_src = parser_script(["--x"])
        kept_src = parser_script([], table=(("--x", "<n>", "the x flag"),), rebound=True)
        gone_src = parser_script([], table=(("--y", "<n>", "the y flag"),), rebound=True)
        notes = "# Notes\n\n- report: `tools/report.py --x 5`\n"  # line 3 cites --x
        self.assertEqual(argument_flags(base_src), {"--x"})  # scope: base declares --x as a literal
        self.assertEqual(module_bindings(kept_src).count(("assign", "CHECK_FLAGS")), 2)  # scope: the table is bound twice
        self.assertEqual(argument_flags(kept_src), set())  # scope: no reader takes the table's rows
        self.assertIn('"--x"', kept_src)  # scope: head still names --x as a string constant
        self.assertNotIn("--x", gone_src)  # scope: the control's head names --x nowhere

        def change_to(head):
            def change(repo):
                write(repo, REPORT, head)
                commit(repo)
            return change

        self.assert_flags(self.make_range(base_files(notes, extra={REPORT: base_src}), change_to(gone_src)),
                          [(NOTES, 3, "STALE007")])  # control: --x gone entirely still fires
        rc, out = self.run_check(self.make_range(base_files(notes, extra={REPORT: base_src}), change_to(kept_src)))
        self.assertNotIn("Traceback", out, out)  # a crash is not a read
        self.assertNotIn((NOTES, 3, "STALE007"), [(p, n, c) for p, n, c, _ in parse(out)],
                         "line 3 cites --x, which head still names as a string constant in a table bound twice; "
                         "the reader does not take that form, so the cite must read unknown, not removed:\n%s" % out)
        self.assertEqual(rc, 0, out)
        unknown = unknown_lines(out)
        self.assertEqual(len(unknown), 1, "one cite, one unknown line:\n%s" % out)
        self.assertTrue(unknown[0].startswith("stale-cites: unknown, %s:3: " % NOTES), out)

    def test_flag_declared_by_a_starred_list_is_not_flagged_while_a_removed_one_is(self):
        base_src = parser_script([], starred=("--between", "--old"))
        head_src = parser_script([], starred=("--between",))
        self.assertIn('"--old"', base_src)  # scope: base declares --old through the starred list
        self.assertIn("parser.add_argument(*STARRED)", head_src)  # scope: head declares through *STARRED
        self.assertEqual(module_value(head_src, "STARRED"), ["--between"])  # scope: head's list keeps --between
        notes = ("# Notes\n\n- report: `tools/report.py --between START END`\n"  # line 3: still declared
                 "- report: `tools/report.py --old 5`\n")  # line 4: really removed

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_control_fires_and_subject_does_not(
            self.make_range(base_files(notes, extra={REPORT: base_src}), change),
            control=4, subject=3, flag="--between")

    def test_flag_declared_by_a_single_target_loop_over_a_table_is_not_flagged_while_a_removed_one_is(self):
        base_src = parser_script(["--between", "--old"])
        head_src = parser_script([], single=("--between",))
        self.assertEqual(argument_flags(base_src), {"--between", "--old"})  # scope: base declares both as literals
        self.assertIn("for flag in SINGLE:", head_src)  # scope: head declares through a single-target loop
        self.assertEqual(module_value(head_src, "SINGLE"), ["--between"])  # scope: head's table keeps --between
        notes = ("# Notes\n\n- report: `tools/report.py --between START END`\n"  # line 3: still declared
                 "- report: `tools/report.py --old 5`\n")  # line 4: really removed

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_control_fires_and_subject_does_not(
            self.make_range(base_files(notes, extra={REPORT: base_src}), change),
            control=4, subject=3, flag="--between")

    def test_flag_declared_by_an_untouched_helper_passed_by_keyword_is_not_flagged(self):
        base_src, head_src = subparser_script(["--between", "--old"]), subparser_script([], window=True, keyword=True)
        helper_src = add_window_source(["--between"])  # COMMON, untouched by the range, declares --between
        self.assertEqual(argument_flags(base_src), {"--between", "--old"})  # scope: base declares both as literals
        self.assertEqual(argument_flags(head_src), set())  # scope: head declares no literal flag
        self.assertIn("add_window(parser=a)", head_src)  # scope: head's subcommand a passes its parser by keyword
        self.assertEqual(argument_flags(helper_src), {"--between"})  # scope: the untouched helper declares --between
        notes = ("# Notes\n\n- report: `tools/report.py --between START END`\n"  # line 3: declared by the helper
                 "- report: `tools/report.py --old 5`\n")  # line 4: really removed

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        self.assert_control_fires_and_subject_does_not(
            self.make_range(base_files(notes, extra={REPORT: base_src, COMMON: helper_src}), change),
            control=4, subject=3, flag="--between")


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
    """A base a shallow clone cannot resolve is unknown, not a finding: the check exits 0 and says so. A base that
    does not resolve in a full clone is a read that could not run (UnreadableReadTests), except a root commit's
    parent (HEAD~1, HEAD^1): a first push to the default branch reads that range by design (actions/ste-lint/run.sh),
    so it exits 0 as on main. The root commit's cases sit here for that reason."""

    def test_an_unresolvable_base_in_a_depth_one_clone_prints_unknown_and_exits_zero(self):
        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        rng = self.make_range(base_files(), change)
        clone = self.depth_one_clone(rng)
        rc, out = self.run_check(rng._replace(repo=clone))
        self.assertEqual(rc, 0, out)
        self.assertTrue(unknown_lines(out), out)
        self.assertIn("fetch-depth", out, "the shallow clone's unknown line does not name fetch-depth\n" + out)

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

    def root_repo(self):
        """A full clone whose one commit is the root. Its base, HEAD~1, names nothing."""
        rng = self.tree("# Notes\n")._replace(base="HEAD~1")
        self.assertFalse(has_object(rng.repo, "HEAD~1"), "scope: the root commit has no parent")
        self.assertEqual(git(rng.repo, "rev-parse", "--is-shallow-repository"), "false", "scope: the repo is a full clone")
        return rng

    def assert_root_range_exits_zero(self, rng, spec):
        rc, out = self.run_check(rng, spec=spec)
        self.assertNotIn("stale-cites: UNKNOWN,", out, "a root commit's first push printed the exit-2 read failure\n" + out)
        self.assertEqual(rc, 0, "a root commit's first push (%s) in a full clone did not exit 0 as on main\n%s" % (spec, out))
        self.assertIn("stale-cites: unknown, the base of %s does not resolve" % spec, out,
                      "a root commit's first push (%s) did not print its unknown line\n%s" % (spec, out))
        self.assertNotIn("stale-cites: PASS", out, "a root commit's first push (%s) printed PASS\n%s" % (spec, out))

    def assert_root_range_exits_two(self, rng, spec):
        """A base past the root commit's first parent, such as its grandparent, stays unread: the range exits 2."""
        rc, out = self.run_check(rng, spec=spec)
        self.assertEqual(rc, 2, "a base past the root commit's first parent (%s) did not exit 2\n%s" % (spec, out))
        self.assertNotIn("stale-cites: PASS", out,
                         "a base past the root commit's first parent (%s) printed PASS\n%s" % (spec, out))
        self.assertRegex(out, "(?i)unknown", out)

    def test_a_root_commit_range_in_a_full_clone_exits_zero_as_on_main(self):
        self.assert_root_range_exits_zero(self.root_repo(), "HEAD~1..HEAD")

    def test_a_failing_two_dot_root_range_starts_five_git_processes_after_its_failed_diff(self):
        """The root form `HEAD~1..HEAD`, whose base is the first parent of a root commit: after its failed `diff`, five
        git processes start, in this order, and it exits 0 as on main."""
        self.assert_starts_after_failed_read(self.root_repo(), "HEAD~1..HEAD", "diff", 0, [
            "rev-parse --verify --quiet HEAD^{commit}",
            "rev-parse --verify --quiet HEAD~1^{commit}",
            "rev-parse --is-shallow-repository",
            "rev-list --parents -n 1 HEAD",
            "rev-parse --verify --quiet HEAD^{commit}",
        ])

    def test_a_failing_three_dot_root_range_starts_six_git_processes_after_its_failed_merge_base(self):
        """The root form `HEAD~1...HEAD`: after its failed `merge-base`, six git processes start, in this order, and it
        exits 0 as on main."""
        self.assert_starts_after_failed_read(self.root_repo(), "HEAD~1...HEAD", "merge-base", 0, [
            "rev-parse --verify --quiet HEAD^{commit}",
            "rev-parse --verify --quiet HEAD~1^{commit}",
            "rev-parse --verify --quiet HEAD~1^{commit}",
            "rev-parse --is-shallow-repository",
            "rev-list --parents -n 1 HEAD",
            "rev-parse --verify --quiet HEAD^{commit}",
        ])

    def test_a_root_commit_range_with_its_parent_spelled_caret_one_exits_zero_as_on_main(self):
        rng = self.root_repo()
        head = git(rng.repo, "rev-parse", "HEAD")
        for spec in ("HEAD^1..HEAD", "%s^1..%s" % (head, head)):
            with self.subTest(spec=spec):
                self.assert_root_range_exits_zero(rng, spec)

    def test_a_root_commit_range_with_its_parent_spelled_tilde_one_and_the_head_as_a_sha_exits_zero_as_on_main(self):
        rng = self.root_repo()
        self.assert_root_range_exits_zero(rng, "HEAD~1..%s" % rng.head)

    def test_a_root_commit_three_dot_range_with_its_parent_spelled_tilde_one_exits_zero_as_on_main(self):
        rng = self.root_repo()
        self.assert_root_range_exits_zero(rng, "HEAD~1...%s" % rng.head)

    def test_a_root_commit_range_with_the_head_spelled_at_sign_exits_zero_as_on_main(self):
        self.assert_root_range_exits_zero(self.root_repo(), "@~1..HEAD")

    def test_a_root_commit_range_with_its_parent_spelled_zero_padded_exits_zero_as_on_main(self):
        self.assert_root_range_exits_zero(self.root_repo(), "HEAD~01..HEAD")

    def test_a_root_commit_range_with_its_parent_spelled_bare_tilde_or_caret_exits_zero_as_on_main(self):
        """A bare `~` or `^` is the first parent, as `~1` and `^1` are. A first-parent suffix that needs its digit
        exits 2 here, while the digit forms above stay green."""
        rng = self.root_repo()
        for spec in ("HEAD~..HEAD", "HEAD^..HEAD"):
            with self.subTest(spec=spec):
                self.assertFalse(has_object(rng.repo, spec.split("..")[0]), "scope: the root commit has no parent")
                self.assert_root_range_exits_zero(rng, spec)

    def test_a_root_commit_range_whose_base_is_two_back_exits_two(self):
        rng = self.root_repo()
        self.assertFalse(has_object(rng.repo, "HEAD~2"), "scope: the root commit has no grandparent")
        self.assert_root_range_exits_two(rng, "HEAD~2..HEAD")

    def test_a_root_commit_range_whose_base_is_caret_caret_exits_two(self):
        rng = self.root_repo()
        self.assertFalse(has_object(rng.repo, "HEAD^^"), "scope: the root commit has no grandparent")
        self.assert_root_range_exits_two(rng, "HEAD^^..HEAD")

    def test_a_root_commit_range_whose_base_is_tilde_one_then_tilde_zero_exits_two(self):
        rng = self.root_repo()
        self.assertFalse(has_object(rng.repo, "HEAD~1~0"), "scope: the root commit has no parent")
        self.assert_root_range_exits_two(rng, "HEAD~1~0..HEAD")

    def test_the_first_parent_of_a_different_root_commit_exits_two_as_before(self):
        """A control: a base that is the first parent of another root commit is not the first parent of HEAD, so
        the range stays unread and exits 2."""
        rng = self.root_repo()
        other = git(rng.repo, "commit-tree", EMPTY_TREE, "-m", "a second root")
        git(rng.repo, "update-ref", "refs/heads/orphan-root", other)
        self.assertFalse(has_object(rng.repo, "orphan-root^1"), "scope: the orphan branch's root commit has no parent")
        self.assertNotEqual(other, rng.head, "scope: the orphan root is not HEAD")
        rc, out = self.run_check(rng, spec="orphan-root^1..HEAD")
        self.assertEqual(rc, 2, "the first parent of a different root commit exited %d, not 2\n%s" % (rc, out))
        self.assertNotIn("stale-cites: PASS", out, "the first parent of a different root commit printed PASS\n" + out)
        self.assertRegex(out, "(?i)unknown", out)

    def test_a_root_commit_range_in_a_depth_one_clone_prints_unknown_and_exits_zero(self):
        rng = self.tree("# Notes\n")._replace(base="HEAD~1")
        clone = self.depth_one_clone(rng)
        rc, out = self.run_check(rng._replace(repo=clone), spec="HEAD~1..HEAD")
        self.assertEqual(rc, 0, "a depth-1 clone's root-commit range exited non-zero, the carve-out is lost\n" + out)
        self.assertTrue(unknown_lines(out), out)
        self.assertIn("fetch-depth", out, "the shallow clone's unknown line does not name fetch-depth\n" + out)

    def parent_gone_range(self):
        """A full clone whose head is no root, and whose parent commit object is gone, so the base names nothing readable."""
        def change(repo):
            write(repo, NOTES, "# Notes\n\n- one more line\n")
            commit(repo)
        rng = self.make_range(base_files(), change)
        drop_loose_object(rng.repo, rng.base)
        self.assertFalse(has_object(rng.repo, rng.base), "scope: the parent commit is gone")
        self.assertTrue(has_object(rng.repo, "HEAD"), "scope: the head resolves")
        self.assertEqual(git(rng.repo, "rev-parse", "--is-shallow-repository"), "false", "scope: the repo is a full clone")
        return rng

    def test_a_non_root_range_whose_parent_object_is_gone_exits_two_in_both_spellings(self):
        rng = self.parent_gone_range()
        for spec in ("HEAD~1..HEAD", "HEAD^1..HEAD"):
            with self.subTest(spec=spec):
                rc, out = self.run_check(rng, spec=spec)
                self.assertEqual(rc, 2, "a non-root head whose parent is gone did not exit 2 (%s)\n%s" % (spec, out))
                self.assertNotIn("stale-cites: PASS", out, "a non-root head whose parent is gone printed PASS\n" + out)
                self.assertRegex(out, "(?i)unknown", out)

    def main_in_process(self, stale, rng, spec):
        """(exit code, output) of the loaded module's main on `spec`, run in this process with the repo as cwd."""
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(rng.repo)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = stale.main(["--range", spec])
        return rc, buf.getvalue()

    def test_a_rev_list_that_prints_the_head_then_exits_nonzero_is_unknown_and_not_a_root(self):
        rng = self.parent_gone_range()
        stale = load_module_under_test()
        real_run = stale._nowindow.run
        starts = []

        def rev_list_prints_head_then_fails(argv, *args, **kwargs):
            if "rev-list" not in argv:
                return real_run(argv, *args, **kwargs)
            starts.append(argv)
            text = "text" in kwargs or "encoding" in kwargs
            shown = rng.head + "\n"
            return subprocess.CompletedProcess(argv, 1, stdout=shown if text else shown.encode(), stderr="" if text else b"")

        rc, out = self.main_in_process(stale, rng, "HEAD~1..HEAD")
        self.assertEqual(rc, 2, "scope: the in-process run with the real rev-list does not exit 2\n" + out)
        with mock.patch.object(stale._nowindow, "run", rev_list_prints_head_then_fails):
            rc, out = self.main_in_process(stale, rng, "HEAD~1..HEAD")
        self.assertTrue(starts, "the mocked rev-list never ran, so the case did not reach the rev-list it names\n" + out)
        self.assertEqual(rc, 2, "a rev-list that printed the head then exited non-zero was read as a root commit "
                         "(rev-list starts: %d)\n%s" % (len(starts), out))
        self.assertNotIn("stale-cites: PASS", out, "a rev-list that failed printed PASS\n" + out)
        self.assertRegex(out, "(?i)unknown", out)


class ResolveTests(StaleCase):
    """resolves reads whether a rev names a commit. Each pinned input states its answer here, so a change to what
    resolves returns shows as the input that moved."""

    @classmethod
    def setUpClass(cls):
        cls.stale = load_module_under_test()

    def test_resolves_names_a_commit_for_each_pinned_rev(self):
        def topic_commit(repo):
            write(repo, "topic.md", "topic\n")
            commit(repo)
        rng = self.make_range(base_files(), topic_commit)   # HEAD has a parent, so HEAD^1 and HEAD~1 name a commit
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(rng.repo)
        branches = git(rng.repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
        self.assertEqual(sorted(branches), ["main", "topic"],
                         "scope: the case repo does not hold the two branches the pins name")
        names_commit = {"HEAD": True, "main": True, "topic": True, "HEAD^1": True, "HEAD~1": True,
                        "HEAD~5": False, "nope": False, "nope^1": False, EMPTY_TREE: False}
        for rev, expected in names_commit.items():
            with self.subTest(rev=rev):
                self.assertEqual(self.stale.resolves(rev), expected, "%s does not resolve as pinned" % rev)


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
    reads the added lines once. A decision line that states what code does (STALE009) reads its blob the same way, and
    so does a folder .py name cite (STALE010, pinned at four starts in NameCiteTests). A removed or renamed path makes the check read the
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

    def test_a_markdown_only_range_that_adds_a_python_value_cite_starts_exactly_four_git_processes_with_one_cat_file(self):
        def change(repo):
            write(repo, NOTES, cite_page(["%s: LIMIT = 4" % CONFIG]))
            commit(repo)
        rng = self.make_range(base_files(extra={CONFIG: LIMIT_BASE}), change)
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: the range changes Markdown only
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        subs = [command.split()[0] for command in commands]
        # The added line holds a .py value cite, so the one cat-file the check opens reads the page: the three starts
        # of a Markdown-only range, and that cat-file, exactly.
        self.assertEqual(sorted(subs), ["cat-file", "diff", "merge-base", "rev-parse"], subs)
        self.assertEqual(whole_tree_listings(commands), [], commands)

    def test_a_js_value_cite_on_an_added_markdown_line_starts_no_process_past_the_one_cat_file(self):
        def change(repo):
            write(repo, NOTES, cite_page(["hooks/lib.mjs: LIMIT = 4"]))
            commit(repo)
        rng = self.make_range(base_files(extra={"hooks/lib.mjs": MJS_BASE}), change)
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: the range changes Markdown only
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        subs = [command.split()[0] for command in commands]
        # A .mjs value cite may read the page, but only through the one cat-file: no ls-tree, and no fifth start.
        self.assertLessEqual(len(subs), 4, subs)
        self.assertTrue(set(subs) <= {"rev-parse", "merge-base", "diff", "cat-file"}, subs)
        self.assertLessEqual(subs.count("cat-file"), 1, subs)
        self.assertEqual(whole_tree_listings(commands), [], commands)

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
        rc, out, commands = self.run_traced_commands(rng)
        subs = [command.split()[0] for command in commands]
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(subs), ["cat-file", "diff", "ls-tree", "merge-base", "rev-parse"], subs)
        # The one ls-tree is the report's, of the decisions folder: no ls-tree of the whole tree, so no .md is read.
        # The one cat-file reads the script.
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

    def test_a_decision_line_stating_what_code_does_starts_one_cat_file_and_the_same_line_elsewhere_starts_none(self):
        """STALE009 reads an added decision line that states what code does, so its head blob is read: four starts, not
        three. The same line on a page outside the decisions folder reads no blob, which pins the extra start to the
        decision reader. The line has no STALE005 verb or route word, so only STALE009 can read it."""
        line = "- The check runs weekly."
        module = load_module_under_test()
        self.assertIsNone(module.VERB.search(line))  # scope: no STALE005 verb in the line
        self.assertIsNone(module.ROUTE_WORD.search(line))  # scope: no route word in the line
        rng, _ = self.rows_range([(line, False)])
        self.assertIn(DECISION, touched(rng))  # scope: the added line is in a decision record
        rc, out, subs = self.run_traced(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(subs), 4, subs)  # the three starts of a Markdown range, and one cat-file that reads the line
        elsewhere, _ = self.route_range([(line, False)])
        rc, out, subs = self.run_traced(elsewhere)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(subs), 3, subs)
        self.assertNotIn("cat-file", subs, subs)

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

    def test_a_flag_read_through_an_untouched_helper_starts_no_git_process_beyond_the_five(self):
        notes = ("# Notes\n\n- report: `tools/report.py --between START END`\n"  # line 3: declared by the helper
                 "- report: `tools/report.py --old 5`\n")  # line 4: really removed
        base_src, head_src = subparser_script(["--between", "--old"]), subparser_script([], window=True)

        def change(repo):
            write(repo, REPORT, head_src)
            commit(repo)
        rng = self.make_range(base_files(notes, extra={REPORT: base_src, COMMON: add_window_source(["--between"])}), change)
        rc, out, commands = self.run_traced_commands(rng)
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(rc, 1, out)  # scope: line 4 is really removed, so the run fails on it
        subs = [command.split()[0] for command in commands]
        self.assertEqual(sorted(subs), ["cat-file", "diff", "ls-tree", "merge-base", "rev-parse"], commands)
        listing = [command for command in commands if command.startswith("ls-tree")]
        self.assertEqual(len(listing), 1, commands)  # the helper read reuses the one whole-tree listing

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


UNRESOLVED = "3" * 40  # a commit id that no test repo holds


def has_object(repo, spec):
    """True when git can read the object `spec` names in `repo`."""
    return subprocess.run(["git", "cat-file", "-e", spec], cwd=repo, capture_output=True).returncode == 0


def drop_loose_object(repo, spec):
    """Remove the loose object `spec` names, so a read of it cannot run. A packed object stays readable, so a case
    that dropped one would break nothing: this refuses that case instead of passing it."""
    sha = git(repo, "rev-parse", spec)
    path = os.path.join(repo, ".git", "objects", sha[:2], sha[2:])
    if not os.path.isfile(path):
        raise AssertionError("scope: %s is not a loose object, so dropping it breaks no read" % spec)
    os.chmod(path, 0o644)  # git writes objects read-only, and Windows removes no read-only file
    os.remove(path)


class UnreadableReadTests(StaleCase):
    """A read the check makes that cannot run exits 2 and says unknown beside the read's name. It never exits 0 and
    never prints PASS. Each case breaks one read on a fixture; its control runs the same fixture with nothing broken."""

    def moved_lib(self, cited):
        """A range that moves hooks/lib.mjs. NOTES names it on line 3 when `cited`, and names no path otherwise."""
        notes = "# Notes\n\n- refusal list in `hooks/lib.mjs`\n" if cited else "# Notes\n\n- no path cite here\n"

        def change(repo):
            move(repo, "hooks/lib.mjs", MOVED)
            write(repo, NOTES, notes)
            commit(repo)
        return self.make_range(base_files(), change)

    def assert_healthy_moved_lib(self):
        """The same fixture read whole: a clean range exits 0, and a real stale cite exits 1."""
        self.assert_passes(self.moved_lib(cited=False))
        self.assert_flags(self.moved_lib(cited=True), [(NOTES, 3, "STALE001")])

    def assert_read_failed(self, rc, out, read):
        """Exit 2, no PASS verdict, the output says unknown and names `read`."""
        self.assertEqual(rc, 2, "a read that could not run did not exit 2\n" + out)
        self.assertNotIn("stale-cites: PASS", out, "a read that could not run printed a PASS verdict\n" + out)
        self.assertRegex(out, "(?i)unknown", "the output does not say unknown\n" + out)
        self.assertIn(read, out, "the output does not name the read that failed (%s)\n%s" % (read, out))

    def test_a_head_that_does_not_resolve_exits_two_and_names_the_merge_base(self):
        rng = self.moved_lib(cited=True)
        self.assertTrue(has_object(rng.repo, rng.base), "scope: the base resolves")
        self.assertFalse(has_object(rng.repo, UNRESOLVED), "scope: the head does not resolve")
        rc, out = self.run_check(rng, spec="%s...%s" % (rng.base, UNRESOLVED))
        self.assert_read_failed(rc, out, "merge-base")
        self.assertNotIn("fetch-depth", out, "a missing head was blamed on a shallow clone of the base\n" + out)

    def test_a_three_dot_range_with_a_resolving_head_is_read_whole(self):
        self.assert_healthy_moved_lib()

    def test_a_two_dot_range_whose_head_does_not_resolve_exits_two_and_names_the_diff(self):
        rng = self.moved_lib(cited=True)
        self.assertFalse(has_object(rng.repo, UNRESOLVED), "scope: the head does not resolve")
        rc, out = self.run_check(rng, spec="%s..%s" % (rng.base, UNRESOLVED))
        self.assert_read_failed(rc, out, "git diff")
        self.assertNotIn("fetch-depth", out, "a missing head was blamed on a shallow clone of the base\n" + out)

    def assert_base_missing_from_full_clone(self, spec):
        """A base that names nothing in a full clone is a read that could not run, in either range form: exit 2, and
        the output names the base and does not blame a shallow clone."""
        rng = self.moved_lib(cited=True)
        self.assertEqual(git(rng.repo, "rev-parse", "--is-shallow-repository"), "false", "scope: the repo is not shallow")
        self.assertFalse(has_object(rng.repo, "nosuchbase"), "scope: the base does not resolve")
        self.assertTrue(has_object(rng.repo, "HEAD"), "scope: the head resolves")
        rc, out = self.run_check(rng, spec=spec)
        self.assert_read_failed(rc, out, "nosuchbase")
        self.assertNotIn("fetch-depth", out, "a base missing from a full clone was blamed on a shallow clone\n" + out)

    def test_an_unresolvable_base_in_a_full_clone_exits_two_and_names_it(self):
        self.assert_base_missing_from_full_clone("nosuchbase...HEAD")

    def test_an_unresolvable_base_in_a_full_clone_two_dot_range_exits_two_and_names_it(self):
        self.assert_base_missing_from_full_clone("nosuchbase..HEAD")

    def test_a_failing_range_with_a_suffixed_base_starts_the_measured_git_processes_after_its_failed_read(self):
        """A failing range whose base has a first-parent suffix (`nope^1`) starts one `rev-list` more than a plain base
        does after its failed read: four git processes after `diff` for `..`, five after `merge-base` for `...`."""
        cases = (
            ("nope^1..HEAD", "diff", [
                "rev-parse --verify --quiet HEAD^{commit}",
                "rev-parse --verify --quiet nope^1^{commit}",
                "rev-parse --is-shallow-repository",
                "rev-list --parents -n 1 HEAD",
            ]),
            ("nope^1...HEAD", "merge-base", [
                "rev-parse --verify --quiet HEAD^{commit}",
                "rev-parse --verify --quiet nope^1^{commit}",
                "rev-parse --verify --quiet nope^1^{commit}",
                "rev-parse --is-shallow-repository",
                "rev-list --parents -n 1 HEAD",
            ]),
        )
        for spec, failed_read, expected in cases:
            with self.subTest(spec=spec):
                rng = self.moved_lib(cited=True)
                self.assertEqual(git(rng.repo, "rev-parse", "--is-shallow-repository"), "false", "scope: the repo is not shallow")
                self.assertFalse(has_object(rng.repo, "nope^1"), "scope: the base names nothing")
                self.assertTrue(has_object(rng.repo, "HEAD^1"), "scope: HEAD has a parent, so it is not a root")
                self.assert_starts_after_failed_read(rng, spec, failed_read, 2, expected)

    def test_a_failing_three_dot_range_with_a_plain_base_starts_four_git_processes_after_its_failed_merge_base(self):
        """A plain base that names nothing: after its failed `merge-base`, four git processes start, in this order."""
        rng = self.moved_lib(cited=True)
        self.assertFalse(has_object(rng.repo, "nope"), "scope: the base names nothing")
        self.assert_starts_after_failed_read(rng, "nope...HEAD", "merge-base", 2, [
            "rev-parse --verify --quiet HEAD^{commit}",
            "rev-parse --verify --quiet nope^{commit}",
            "rev-parse --verify --quiet nope^{commit}",
            "rev-parse --is-shallow-repository",
        ])

    def test_a_failing_two_dot_range_with_a_plain_base_starts_three_git_processes_after_its_failed_diff(self):
        """A plain base that names nothing: after its failed `diff`, three git processes start, in this order."""
        rng = self.moved_lib(cited=True)
        self.assertFalse(has_object(rng.repo, "nope"), "scope: the base names nothing")
        self.assert_starts_after_failed_read(rng, "nope..HEAD", "diff", 2, [
            "rev-parse --verify --quiet HEAD^{commit}",
            "rev-parse --verify --quiet nope^{commit}",
            "rev-parse --is-shallow-repository",
        ])

    def test_an_unresolvable_base_in_a_depth_one_clone_two_dot_range_prints_unknown_and_exits_zero(self):
        rng = self.moved_lib(cited=True)
        clone = self.depth_one_clone(rng)
        rc, out = self.run_check(rng._replace(repo=clone), spec="%s..%s" % (rng.base, rng.head))
        self.assertEqual(rc, 0, "a depth-1 clone's two-dot base read exited non-zero, the carve-out is lost\n" + out)
        self.assertTrue(unknown_lines(out), out)
        self.assertIn("fetch-depth", out, "the shallow clone's unknown line does not name fetch-depth\n" + out)

    def test_a_two_dot_range_with_a_resolving_head_flags_the_stale_cite_and_passes_when_clean(self):
        rng = self.moved_lib(cited=True)
        rc, out = self.run_check(rng, spec="%s..%s" % (rng.base, rng.head))
        self.assertEqual(rc, 1, "a resolving two-dot range did not flag the stale cite\n" + out)
        self.assertEqual([(p, n, c) for p, n, c, _ in parse(out)], [(NOTES, 3, "STALE001")], out)
        clean = self.moved_lib(cited=False)
        rc, out = self.run_check(clean, spec="%s..%s" % (clean.base, clean.head))
        self.assertEqual(rc, 0, "a clean two-dot range did not exit 0\n" + out)

    def test_an_exclude_file_that_cannot_be_read_exits_two_and_names_it(self):
        rng = self.moved_lib(cited=False)
        self.assertIn(MOVED, touched(rng), "scope: the range renames a path, so the check reads the excludes")
        os.mkdir(os.path.join(rng.repo, ".ste-lint-exclude"))  # a folder under the file's name: open() cannot read it
        rc, out = self.run_check(rng)
        self.assert_read_failed(rc, out, ".ste-lint-exclude")

    def link_exclude(self, rng, target):
        """Make .ste-lint-exclude in the repo a symlink to `target`. A platform that makes no symlink skips the case."""
        link = os.path.join(rng.repo, ".ste-lint-exclude")
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("this platform cannot make a symlink: %s" % exc)
        self.assertTrue(os.path.islink(link), "scope: the exclude is a link")

    def test_a_dangling_exclude_symlink_exits_two_and_names_it(self):
        rng = self.moved_lib(cited=False)
        self.assertIn(MOVED, touched(rng), "scope: the range renames a path, so the check reads the excludes")
        target = os.path.join(rng.case, "no-such-excludes")
        self.assertFalse(os.path.exists(target), "scope: the link's target is missing")
        self.link_exclude(rng, target)
        rc, out = self.run_check(rng)
        self.assert_read_failed(rc, out, ".ste-lint-exclude")

    def test_an_exclude_symlink_to_a_readable_file_still_passes(self):
        rng = self.moved_lib(cited=False)
        target = os.path.join(rng.case, "readable-excludes")
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write("# no excludes\n")
        self.link_exclude(rng, target)
        self.assert_passes(rng)

    def test_a_non_utf8_exclude_file_exits_two_without_a_traceback(self):
        rng = self.moved_lib(cited=False)
        self.assertIn(MOVED, touched(rng), "scope: the range renames a path, so the check reads the excludes")
        raw = b"\xff\xfe bad\n"
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("utf-8")  # scope: the bytes are not UTF-8
        with open(os.path.join(rng.repo, ".ste-lint-exclude"), "wb") as f:
            f.write(raw)
        rc, out = self.run_check(rng)
        self.assert_read_failed(rc, out, ".ste-lint-exclude")
        self.assertNotIn("Traceback", out, "a non-UTF-8 exclude file printed a traceback, not an unknown line\n" + out)

    def test_a_utf8_exclude_file_with_non_ascii_text_still_passes(self):
        rng = self.moved_lib(cited=False)
        write(rng.repo, ".ste-lint-exclude", "# café excludes\n")
        self.assert_passes(rng)

    def assert_only_adds_a_page(self, rng):
        """The range adds one Markdown page and removes, renames and changes nothing else. A case asserts this before
        it reads the result, so an add-only case has the add-only range it names."""
        self.assertEqual(git(rng.repo, "diff", "--name-status", "-M", rng.base, rng.head).split(),
                         ["A", "docs/added.md"], "scope: the range does not only add one page")

    def add_only_range(self, unreadable):
        """A range that adds one page with no cite and no route word. `.ste-lint-exclude` is a folder when `unreadable`
        (open() cannot read it), and a file that leaves out nothing otherwise."""
        def change(repo):
            write(repo, "docs/added.md", "# Added\n\n- a plain note\n")
            commit(repo)
        rng = self.make_range(base_files(), change)
        if unreadable:
            os.mkdir(os.path.join(rng.repo, ".ste-lint-exclude"))
        else:
            write(rng.repo, ".ste-lint-exclude", "# no excludes\n")
        self.assert_only_adds_a_page(rng)
        return rng

    def test_an_add_only_range_whose_exclude_file_cannot_be_read_exits_two_and_names_it(self):
        rng = self.add_only_range(unreadable=True)
        self.assertTrue(os.path.isdir(os.path.join(rng.repo, ".ste-lint-exclude")), "scope: the exclude is a folder")
        rc, out = self.run_check(rng)
        self.assert_read_failed(rc, out, ".ste-lint-exclude")

    def test_an_add_only_range_with_a_readable_exclude_file_exits_zero(self):
        self.assert_passes(self.add_only_range(unreadable=False))

    def test_no_exclude_file_is_read_whole(self):
        self.assert_healthy_moved_lib()

    def test_a_line_anchor_whose_cited_file_cannot_be_read_exits_two_and_names_it(self):
        rng = self.tree("# Notes\n\n- `hooks/guard.py:99`\n")
        self.assertIn("hooks/guard.py", git(rng.repo, "ls-tree", "-r", "--name-only", "HEAD").split(),
                      "scope: the cited file is tracked at HEAD")
        drop_loose_object(rng.repo, "HEAD:hooks/guard.py")
        rc, out = self.run_tree(rng)
        self.assert_read_failed(rc, out, "hooks/guard.py")

    def test_a_readable_cited_file_flags_an_anchor_past_its_end_and_passes_one_inside(self):
        self.assert_tree_flags(self.tree("# Notes\n\n- `hooks/guard.py:99`\n"), [(NOTES, 3, "STALE004")])
        self.assert_tree_passes(self.tree("# Notes\n\n- `hooks/guard.py:6`\n"))

    def pymod_range(self, drop_head_blob):
        """A range whose head adds lint/pymod_probe.py, read through the branch `pymod`. With `drop_head_blob`, that
        file's blob is removed, so `git diff` cannot read the head while the base and the history still resolve."""
        def change(repo):
            write(repo, "lint/pymod_probe.py", "def probe_only_here():\n    return 17\n")
            commit(repo)
        rng = self.make_range(base_files(), change)
        git(rng.repo, "branch", "pymod", rng.head)
        if drop_head_blob:
            drop_loose_object(rng.repo, "%s:lint/pymod_probe.py" % rng.head)
        return rng

    def assert_head_blob_unreadable(self, spec):
        """A head blob the diff cannot read, in a full clone whose base resolves: exit 2 and the output names the diff.
        It never blames the base or a shallow clone."""
        rng = self.pymod_range(drop_head_blob=True)
        self.assertEqual(git(rng.repo, "rev-parse", "--is-shallow-repository"), "false", "scope: the repo is not shallow")
        self.assertTrue(has_object(rng.repo, "main"), "scope: the base resolves")
        self.assertTrue(has_object(rng.repo, rng.head), "scope: the head commit resolves")
        self.assertFalse(has_object(rng.repo, "%s:lint/pymod_probe.py" % rng.head), "scope: the head blob is gone")
        rc, out = self.run_check(rng, spec=spec)
        self.assert_read_failed(rc, out, "git diff")
        self.assertNotIn("does not resolve", out, "a head blob the diff cannot read blamed the base, which resolves\n" + out)
        self.assertNotIn("fetch-depth", out, "a head blob the diff cannot read was blamed on a shallow clone\n" + out)

    def test_a_head_blob_the_diff_cannot_read_in_a_full_clone_exits_two_for_a_three_dot_range(self):
        self.assert_head_blob_unreadable("main...pymod")

    def test_a_head_blob_the_diff_cannot_read_in_a_full_clone_exits_two_for_a_two_dot_range(self):
        self.assert_head_blob_unreadable("main..pymod")

    def test_a_full_clone_with_every_head_blob_present_passes_both_range_forms(self):
        rng = self.pymod_range(drop_head_blob=False)
        self.assertTrue(has_object(rng.repo, "%s:lint/pymod_probe.py" % rng.head), "scope: the head blob is present")
        for spec in ("main...pymod", "main..pymod"):
            with self.subTest(spec=spec):
                rc, out = self.run_check(rng, spec=spec)
                self.assertEqual(rc, 0, "a full clone with its head blob present did not exit 0\n" + out)
                self.assertIn("stale-cites: PASS", out)

    def test_a_depth_one_clone_with_an_unresolvable_base_keeps_exit_zero_for_both_range_forms(self):
        rng = self.pymod_range(drop_head_blob=False)
        clone = self.depth_one_clone(rng)
        for spec in ("%s...%s", "%s..%s"):
            with self.subTest(spec=spec):
                rc, out = self.run_check(rng._replace(repo=clone), spec=spec % (rng.base, rng.head))
                self.assertEqual(rc, 0, "a depth-1 clone's unresolvable base exited non-zero, the carve-out is lost\n" + out)
                self.assertTrue(unknown_lines(out), out)
                self.assertIn("fetch-depth", out, "the shallow clone's unknown line does not name fetch-depth\n" + out)


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


class UnreadableReportTests(StaleCase):
    """A report read that cannot run prints an unknown line that names it, never a silent gap. The report keeps the
    exit code, as a malformed mechanisms file does (its case ends _and_keeps_the_exit_code), so these keep it too."""

    def guard_edit(self, extra):
        """A range that changes hooks/guard.py only. Nothing is removed, so only the report reads the repo's files."""
        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            commit(repo)
        return self.make_range(base_files(extra=extra), change)

    def test_a_decision_record_that_cannot_be_read_prints_an_unknown_line_naming_it(self):
        record = "docs/decisions/guard-home-first.md"
        rng = self.guard_edit(decisions(("guard-home-first", "hooks/guard.py")))
        self.assertEqual(touched(rng), {"hooks/guard.py"}, "scope: only the code file changed")
        self.assertIn(record, git(rng.repo, "ls-tree", "-r", "--name-only", "HEAD").split(),
                      "scope: the record is tracked at HEAD")
        drop_loose_object(rng.repo, "HEAD:" + record)
        rc, out = self.run_check(rng)
        self.assertTrue([line for line in unknown_lines(out) if record in line],
                        "a record that cannot be read printed no unknown line naming it\n" + out)
        self.assertEqual(rc, 0, "an unreadable record changed the exit code\n" + out)

    def test_a_readable_decision_record_prints_its_home_line_and_no_unknown_line(self):
        rng = self.guard_edit(decisions(("guard-home-first", "hooks/guard.py")))
        rc, out = self.run_check(rng)
        self.assertIn("Home of decision guard-home-first", out, out)
        self.assertEqual(unknown_lines(out), [], out)
        self.assertEqual(rc, 0, out)

    def test_a_readable_decision_record_beside_a_real_stale_cite_still_exits_one(self):
        def change(repo):
            write(repo, "hooks/guard.py", GUARD_EDIT)
            move(repo, "hooks/lib.mjs", MOVED)
            commit(repo)
        extra = decisions(("guard-home-first", "hooks/guard.py"))
        rng = self.make_range(base_files("# Notes\n\n- refusal list in `hooks/lib.mjs`\n", extra=extra), change)
        self.assert_flags(rng, [(NOTES, 3, "STALE001")])

    def test_a_mechanisms_file_that_cannot_be_read_prints_an_unknown_line_naming_it(self):
        rng = self.guard_edit({MECH: mechanisms({"guard-row": {"kind": "guard", "ref": "hooks/guard.py"}})})
        self.assertEqual(touched(rng), {"hooks/guard.py"}, "scope: only the code file changed")
        self.assertIn(MECH, git(rng.repo, "ls-tree", "-r", "--name-only", "HEAD").split(),
                      "scope: the mechanisms file is tracked at HEAD")
        drop_loose_object(rng.repo, "HEAD:" + MECH)
        rc, out = self.run_check(rng)
        self.assertTrue([line for line in unknown_lines(out) if MECH in line],
                        "a mechanisms file that cannot be read printed no unknown line naming it\n" + out)
        self.assertEqual(rc, 0, "an unreadable mechanisms file changed the exit code\n" + out)

    def test_a_readable_mechanisms_file_names_its_row_and_prints_no_unknown_line(self):
        rng = self.guard_edit({MECH: mechanisms({"guard-row": {"kind": "guard", "ref": "hooks/guard.py"}})})
        rc, out = self.run_check(rng)
        self.assertTrue(named(out, "guard-row"), "the mechanisms row does not name the changed file\n" + out)
        self.assertEqual(unknown_lines(out), [], out)
        self.assertEqual(rc, 0, out)


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
        self.assertIn(NOTES, touched(rng))  # scope: the range adds the three claim lines
        # The node id names a file absent in a tracked top folder (`lint`), so STALE010 finds it on its line and the exit
        # is 1. The two dead backings still print as STALE005 report lines.
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 1, out)
        self.assertEqual([(p, n, c) for p, n, c, _ in parse(out)], [(NOTES, flagged[1], "STALE010")], out)
        self.assertEqual(stale005_lines(out, NOTES), sorted(flagged), out)
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


EVIDENCE_SHAPE = r"^[0-9a-f]{40}: \S.*\.$"  # an optional row's evidence: the fix commit's sha, then a sentence


def repo_relative_md(path):
    """A full repo-relative path to a Markdown file: no leading slash, and no empty, `.` or `..` segment."""
    return (path.endswith(".md") and not any(part in ("", ".", "..") for part in path.split("/"))
            and not re.search(r"\s", path))


def known_commit(sha):
    return subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], cwd=ROOT, capture_output=True).returncode == 0


class RouteClaimFixtureTests(unittest.TestCase):
    """The labelled route claims, hand-judged stale or true, that measure the judge's false alarms: one entry per labelled line.
    A span is one entry at its first line, and `line` is a string, such as "16" or "16-20"."""

    def test_route_claims_fixture_has_the_audited_shape(self):
        self.assertTrue(os.path.isfile(FIXTURE), "fixture absent: %s" % FIXTURE)
        with open(FIXTURE, encoding="utf-8") as f:
            rows = json.load(f)
        self.assertIsInstance(rows, list)
        for row in rows:
            self.assertIn("rev", row, row)  # the commit the row was judged at, or null
            keys = sorted(set(row) - {"evidence"})  # evidence is optional: the fix commit that made the line false, and why
            if row["rev"] is None:
                self.assertEqual(keys, ["file", "label", "line", "note", "rev", "text_summary"], row)
                self.assertTrue(row["note"].strip(), row)  # a null rev says why
            else:
                self.assertEqual(keys, ["file", "label", "line", "rev", "text", "text_summary"], row)
                self.assertRegex(row["rev"], r"^[0-9a-f]{7,40}$", row)
                self.assertIsInstance(row["text"], str, row)
            if "evidence" in row:
                self.assertRegex(row["evidence"], EVIDENCE_SHAPE, row)
            self.assertTrue(repo_relative_md(row["file"]), row)  # a full repo-relative path to a Markdown file
            self.assertRegex(row["line"], r"^[1-9][0-9]*(?:-[1-9][0-9]*)?$", row)
            self.assertIn(row["label"], LABELS, row)
            self.assertTrue(row["text_summary"].strip(), row)
        self.assertEqual(len({(row["file"], row["line"], row["rev"]) for row in rows}), len(rows),
                         "a (file, line, rev) repeats")  # one line judged at two revs is two rows
        # The pinned label mix. Adding or removing a row changes this pin, on purpose.
        self.assertEqual(collections.Counter(row["label"] for row in rows),
                         collections.Counter({"STALE": 19, "PARTLY_STALE": 1, "HALF": 1, "TRUE": 13,
                                              "HISTORY": 1, "UNKNOWN": 3}),
                         "the label mix of the labelled file moved: pin it here if the change is on purpose")
        unknown = [row["evidence"][:40] for row in rows if "evidence" in row and not known_commit(row["evidence"][:40])]
        if unknown and git(ROOT, "rev-parse", "--is-shallow-repository") == "true":
            self.skipTest("evidence sha missing from this shallow clone: %s" % ", ".join(unknown))
        self.assertEqual(unknown, [], "evidence sha is not a commit of this repo")


def fixture_rows():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def line_span(line):
    """The first and last line numbers of a row's `line`: "16" gives (16, 16), "16-20" gives (16, 20)."""
    first, _, last = line.partition("-")
    return int(first), int(last or first)


class RouteClaimRevTests(unittest.TestCase):
    """Each row replays at its `rev`: the lines its `line` names, at that commit, join to its `text`. A null `rev` has none."""

    def test_each_row_holds_its_text_at_its_rev(self):
        rows = fixture_rows()
        self.assertEqual([row["file"] + ":" + row["line"] for row in rows if "rev" not in row], [],
                         "rows with no rev key")
        self.assertTrue(any(row["rev"] for row in rows), "no row has a non-null rev, so none replays")
        shallow = git(ROOT, "rev-parse", "--is-shallow-repository") == "true"
        for row in rows:
            if row["rev"] is None:
                continue
            with self.subTest(row=row["file"] + ":" + row["line"]):
                known = known_commit(row["rev"])
                if not known and shallow:
                    self.skipTest("rev %s is missing from this shallow clone" % row["rev"])
                self.assertTrue(known, "rev %s is not a commit of this repo" % row["rev"])
                shown = subprocess.run(["git", "show", "%s:%s" % (row["rev"], row["file"])], cwd=ROOT,
                                       capture_output=True)
                self.assertEqual(shown.returncode, 0, "%s is absent at rev %s" % (row["file"], row["rev"]))
                first, last = line_span(row["line"])
                lines = shown.stdout.decode("utf-8").split("\n")
                self.assertEqual("\n".join(lines[first - 1:last]), row["text"],
                                 "%s line %s at rev %s is not the text" % (row["file"], row["line"], row["rev"]))


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


CONFIG = "hooks/config.py"  # the Python file the value cites name
LIMIT_BASE = "LIMIT = 4\n\n\ndef keep():\n    return 1\n"
LIMIT_HEAD = "LIMIT = 5\n\n\ndef keep():\n    return 1\n"
REMOVED = "def keep():\n    return 1\n"  # LIMIT_BASE with LIMIT taken out
CITE_4 = "- retry limit `hooks/config.py: LIMIT = 4`"  # quotes LIMIT_BASE's value
DOC_BASE = 'DOC = """\nLIMIT = 9\n"""\n\nLIMIT = 4\n\n\ndef keep():\n    return 1\n'  # a string spells a binding
DOC_HEAD = DOC_BASE.replace("LIMIT = 4", "LIMIT = 5")
MJS_BASE, MJS_HEAD = "export const LIMIT = 4;\n", "export const LIMIT = 5;\n"
NO_JSON_VALUES = ("'a'", "True", "None", "0x4", "1_000", ".5", "4 seconds")  # values MAP9 reads as no JSON literal
UNTRACKED_CITES = ("hooks/confg.py", "config.py")  # a typo of a tracked path, and a bare basename no tracked file has
NONLIT_CONFIG = "LIMIT = 30 * 86400\nGATE = compute()\n\n\ndef keep():\n    return 1\n"  # names bound to no literal
NONLIT_CITES = ("%s: LIMIT = 4" % CONFIG, "%s: GATE = 1" % CONFIG)  # cites of those names, with JSON literals


def cite_page(cites):
    """A Markdown page: a heading, a blank line, then one bulleted line per cite, the first cite on line 3."""
    return "# Notes\n\n" + "".join("- retry limit `%s`\n" % cite for cite in cites)


def unknown_counts(out, numbers):
    """How many `stale-cites: unknown` lines name each NOTES line in `numbers`: {number: count}."""
    return {n: sum("%s:%d: " % (NOTES, n) in line for line in unknown_lines(out)) for n in numbers}


def value_file(name, literal):
    """A Python file that binds `name` to the literal text `literal` at module level, beside one def the check keeps."""
    return "%s = %s\n\n\ndef keep():\n    return 1\n" % (name, literal)


class ValueCiteTests(StaleCase):
    """STALE008 (decision stale-cites-at-merge): a Python value cite `file.py: NAME = literal` in backticks quotes the
    value the range changed or removed, or a line the range adds does not match the value at head. A JavaScript cite
    prints unknown, and a JSON cite is not read. Each case asserts its fixture values before it probes the check."""

    def value_range(self, base, head):
        """The range from `base` ({path: text}, over base_files, so NOTES defaults) on main to `head` ({path: text},
        written over it) on topic. NOTES is a path too, so a case that edits its prose puts NOTES in `head`."""
        def change(repo):
            for path, text in head.items():
                write(repo, path, text)
            commit(repo)
        return self.make_range(base_files(extra=base), change)

    def parity_range(self, rows):
        """One range that changes each row's file and cites each row on its own NOTES line: row k sits on line 3 + k."""
        base = {row["file"]: row["base"] for row in rows}
        base[NOTES] = "# Notes\n"
        head = {row["file"]: row["head"] for row in rows}
        head[NOTES] = "# Notes\n\n" + "".join("- row %d: `%s`\n" % (k + 1, row["cite"]) for k, row in enumerate(rows))
        return self.value_range(base, head)

    # Fires: the range changed or removed the value a line quotes, or added a line that does not match head.

    def test_a_changed_value_still_quoted_by_an_untouched_line_is_flagged(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: LIMIT_HEAD})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_changed_value_quoted_on_an_untouched_line_of_a_touched_page_is_flagged(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        notes = "# Notes\n\n%s\n" % CITE_4
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: notes}, {CONFIG: LIMIT_HEAD, NOTES: notes + "\nA new line.\n"})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_removed_value_still_quoted_by_a_line_is_flagged_and_says_removed(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertIsNone(binding_kind(REMOVED, "LIMIT"))  # scope: head no longer binds LIMIT
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: REMOVED})
        found = self.assert_flags(rng, [(NOTES, 3, "STALE008")])
        self.assertIn("removed", found[0][3], "a name the range removed must say so: %s" % found[0][3])

    def test_an_added_line_citing_a_value_head_does_not_hold_is_flagged_when_no_literal_changed(self):
        head_cfg = LIMIT_BASE + "\n\ndef extra():\n    return 2\n"
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), module_value(head_cfg, "LIMIT"))  # scope: the range changes no literal
        self.assertNotEqual(module_value(head_cfg, "LIMIT"), 6)  # scope: the added cite's 6 is not the value at head
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"},
                               {CONFIG: head_cfg, NOTES: "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 6`\n"})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_second_copy_of_a_line_already_wrong_at_base_fires_on_the_copy_only(self):
        cite = "- retry limit `hooks/config.py: LIMIT = 6`"
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 6 is wrong at base
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % cite},
                               {NOTES: "# Notes\n\n%s\n\n%s\n" % (cite, cite)})  # the range adds a second copy on line 5
        self.assert_flags(rng, [(NOTES, 5, "STALE008")])

    def test_an_added_cite_of_a_name_the_file_never_binds_is_flagged_without_saying_removed(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT, the one name the file has
        self.assertIsNone(binding_kind(LIMIT_BASE, "NOPE"))  # scope: base never binds NOPE
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"},
                               {NOTES: "# Notes\n\n- retry limit `hooks/config.py: NOPE = 4`\n"})
        found = self.assert_flags(rng, [(NOTES, 3, "STALE008")])
        self.assertNotIn("removed", found[0][3], "a name the file never bound must not read as removed: %s" % found[0][3])

    def test_a_changed_value_cited_on_the_last_line_of_a_full_page_is_flagged_on_that_line(self):
        lines = ["# Notes", ""] + ["Filler prose line %d." % i for i in range(297)] + [CITE_4]
        self.assertEqual(len(lines), 300)  # scope: a full page, the cite on line 300
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "\n".join(lines) + "\n"}, {CONFIG: LIMIT_HEAD})
        self.assert_flags(rng, [(NOTES, 300, "STALE008")])

    def test_a_changed_value_cited_inside_a_fenced_block_is_flagged(self):
        notes = "# Notes\n\n```\n%s\n```\n" % CITE_4
        self.assertEqual(notes.split("\n")[3], CITE_4)  # scope: the cite is on line 4, inside the fence
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: notes}, {CONFIG: LIMIT_HEAD})
        self.assert_flags(rng, [(NOTES, 4, "STALE008")])

    def test_a_hash_inside_a_string_value_is_part_of_the_value(self):
        base_cfg = 'NAME = "a # b"\n\n\ndef keep():\n    return 1\n'
        head_cfg = 'NAME = "a # c"\n\n\ndef keep():\n    return 1\n'
        self.assertEqual(module_value(base_cfg, "NAME"), "a # b")  # scope: base binds NAME to a string that holds a hash
        self.assertEqual(module_value(head_cfg, "NAME"), "a # c")  # scope: the range changes NAME
        rng = self.value_range({CONFIG: base_cfg, NOTES: '# Notes\n\n- label `hooks/config.py: NAME = "a # b"`\n'},
                               {CONFIG: head_cfg})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_name_that_a_string_also_spells_is_read_from_the_binding(self):
        self.assertEqual(module_value(DOC_BASE, "DOC"), "\nLIMIT = 9\n")  # scope: a string holds the text LIMIT = 9
        self.assertEqual(module_value(DOC_BASE, "LIMIT"), 4)  # scope: the binding is 4
        self.assertEqual(module_value(DOC_HEAD, "LIMIT"), 5)  # scope: the range changes the binding to 5
        rng = self.value_range({CONFIG: DOC_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: DOC_HEAD})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_an_added_cite_of_the_value_only_a_string_spells_is_flagged(self):
        self.assertEqual(module_value(DOC_HEAD, "LIMIT"), 5)  # scope: head binds LIMIT to 5
        self.assertEqual(module_value(DOC_HEAD, "DOC"), "\nLIMIT = 9\n")  # scope: a string at head holds the text LIMIT = 9
        rng = self.value_range({CONFIG: DOC_BASE, NOTES: "# Notes\n\n"},
                               {CONFIG: DOC_HEAD, NOTES: "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 9`\n"})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_lone_quote_in_the_prose_before_the_cite_does_not_hide_it(self):
        notes = '# Notes\n\n- don\'t use the 5" limit, see `hooks/config.py: LIMIT = 4`\n'
        self.assertEqual(notes.split("\n")[2].count('"'), 1)  # scope: one lone double quote in the prose
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: notes}, {CONFIG: LIMIT_HEAD})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_hash_in_the_prose_before_the_cite_does_not_hide_it(self):
        notes = "# Notes\n\n- see issue #12 for the cap: `hooks/config.py: LIMIT = 4`\n"
        self.assertIn("#12", notes)  # scope: the prose holds a hash mark before the cite
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: notes}, {CONFIG: LIMIT_HEAD})
        self.assert_flags(rng, [(NOTES, 3, "STALE008")])

    def test_a_js_value_cite_of_a_touched_file_prints_unknown_when_the_range_reads_markdown(self):
        self.assertNotEqual(MJS_BASE, MJS_HEAD)  # scope: the range changes the cited JavaScript file
        self.assertEqual(module_value("RETRIES = 2\n", "RETRIES"), 2)  # scope: a Python literal changes too, so Markdown is read
        self.assertEqual(module_value("RETRIES = 3\n", "RETRIES"), 3)
        rng = self.value_range({"hooks/lib.mjs": MJS_BASE, CONFIG: "RETRIES = 2\n", NOTES: "# Notes\n\n- retry limit `hooks/lib.mjs: LIMIT = 4`\n"},
                               {"hooks/lib.mjs": MJS_HEAD, CONFIG: "RETRIES = 3\n"})
        rc, out = self.run_check(rng)
        named = [line for line in unknown_lines(out) if "%s:3" % NOTES in line and "hooks/lib.mjs" in line]
        self.assertTrue(named, "a value cite of a .mjs file must print an unknown line that names %s:3 and the file\n%s" % (NOTES, out))
        self.assertEqual(parse(out), [], out)
        self.assertEqual(rc, 0, out)

    def test_a_ste_disable_line_mark_leaves_a_js_value_cite_line_out_of_the_unknown(self):
        def run(line):
            rng = self.value_range({"hooks/lib.mjs": MJS_BASE, CONFIG: "RETRIES = 2\n", NOTES: "# Notes\n\n%s\n" % line},
                                   {"hooks/lib.mjs": MJS_HEAD, CONFIG: "RETRIES = 3\n"})
            return self.run_check(rng)[1]

        def named(out):
            return [line for line in unknown_lines(out) if "%s:3" % NOTES in line]
        plain = run("- retry limit `hooks/lib.mjs: LIMIT = 4`")
        self.assertTrue(named(plain), "scope: without the mark, the cite line prints unknown\n%s" % plain)
        marked = run("- retry limit `hooks/lib.mjs: LIMIT = 4` <!-- ste-disable-line STALE008 -->")
        self.assertEqual(named(marked), [], "the STALE008 mark must leave the cite line out of the unknown\n%s" % marked)

    def test_a_ste_disable_line_mark_leaves_a_python_value_cite_line_out_of_the_finding(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        self.assert_flags(self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: LIMIT_HEAD}),
                          [(NOTES, 3, "STALE008")])  # scope: without the mark, the cite line is flagged
        marked = "# Notes\n\n%s <!-- ste-disable-line STALE008 -->\n" % CITE_4
        self.assert_passes(self.value_range({CONFIG: LIMIT_BASE, NOTES: marked}, {CONFIG: LIMIT_HEAD}))

    def test_a_changed_literal_reads_the_untouched_markdown_in_full(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: the range changes a module-level literal
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: LIMIT_HEAD})
        rc, out, commands = self.run_traced_commands(rng)
        self.assertTrue(whole_tree_listings(commands),
                        "a changed literal must read every tracked Markdown file, so the run lists the whole tree: %s" % commands)

    def test_every_fire_parity_row_is_flagged_on_its_own_line(self):
        rows = parity_rows()
        fire = [(row, 3 + k) for k, row in enumerate(rows) if row["expect"] == "fire"]
        self.assertTrue(fire, "scope: the fixture holds fire rows")
        for row, _ in fire:  # scope: the cited literal is the base value, and the range changes it
            base_value = module_value(row["base"], row["match"]["symbol"])
            self.assertEqual(base_value, ast.literal_eval(row["match"]["literal"]), "scope: base value of %s" % row["cite"])
            self.assertNotEqual(module_value(row["head"], row["match"]["symbol"]), base_value, "scope: head value of %s" % row["cite"])
        rc, out = self.run_check(self.parity_range(rows))
        flagged = {(path, line) for path, line, code, _ in parse(out) if code == "STALE008"}
        missing = [row["cite"] for row, line in fire if (NOTES, line) not in flagged]
        self.assertEqual(missing, [], "STALE008 must flag each changed value on its own line:\n%s" % out)

    # Fires on a value no JSON literal can hold, or on a path no tracked file has. The line is added, so each is a finding.

    def test_an_added_python_cite_whose_value_is_no_json_literal_is_flagged_on_its_own_line(self):
        for value in NO_JSON_VALUES:  # scope: each value is no JSON literal
            self.assertRaises(ValueError, json.loads, value)
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cited name exists
        cites = ["%s: LIMIT = %s" % (CONFIG, value) for value in NO_JSON_VALUES]
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"}, {NOTES: cite_page(cites)})
        rc, out = self.run_check(rng)
        found = sorted((p, n, c) for p, n, c, _ in parse(out))
        expected = sorted((NOTES, 3 + k, "STALE008") for k in range(len(cites)))
        self.assertEqual(found, expected, "each added cite whose value is no JSON literal must print one STALE008 on its line\n%s" % out)
        self.assertEqual(rc, 1, out)

    def test_an_added_python_cite_naming_no_tracked_file_is_flagged_on_its_own_line(self):
        for path in UNTRACKED_CITES:  # scope: no tracked file has the path
            self.assertNotIn(path, base_files(extra={CONFIG: LIMIT_BASE}))
        cites = ["%s: LIMIT = 4" % path for path in UNTRACKED_CITES]
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"}, {NOTES: cite_page(cites)})
        rc, out = self.run_check(rng)
        found = sorted(parse(out))
        self.assertEqual([(p, n, c) for p, n, c, _ in found], [(NOTES, 3 + k, "STALE008") for k in range(len(cites))],
                         "each added cite of a path no tracked file has must print one STALE008 on its line\n%s" % out)
        for (_, _, _, text), path in zip(found, UNTRACKED_CITES):
            self.assertIn(path, text, "a finding must name the path it could not find: %s" % text)
        self.assertEqual(rc, 1, out)

    def test_an_added_non_json_value_after_a_lone_quote_or_holding_a_hash_is_flagged(self):
        notes = "# Notes\n\n- don't trust `hooks/config.py: LIMIT = 'a'`\n- label `hooks/config.py: LIMIT = 'a # b'`\n"
        self.assertEqual(notes.split("\n")[2].split("`")[0].count("'"), 1)  # scope: one lone single quote in the prose before the cite
        self.assertIn("'a # b'", notes.split("\n")[3])  # scope: a hash inside the non-JSON value
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"}, {NOTES: notes})
        rc, out = self.run_check(rng)
        self.assertEqual(sorted((p, n, c) for p, n, c, _ in parse(out)), [(NOTES, 3, "STALE008"), (NOTES, 4, "STALE008")],
                         "a lone quote in the prose and a hash in the value must not hide either added cite\n%s" % out)
        self.assertEqual(rc, 1, out)

    # Unknown, never a finding: a cite the check cannot read prints one `stale-cites: unknown` line per cite, and the exit stays 0.

    def test_an_untouched_non_json_or_untracked_cite_prints_one_unknown_line_on_a_whole_tree_read(self):
        cites = (["%s: LIMIT = %s" % (CONFIG, value) for value in NO_JSON_VALUES]
                 + ["%s: LIMIT = 4" % path for path in UNTRACKED_CITES])
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)  # scope: the range changes LIMIT, so the whole tree is read
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: cite_page(cites)}, {CONFIG: LIMIT_HEAD})
        rc, out = self.run_check(rng)
        counts = unknown_counts(out, range(3, 3 + len(cites)))
        self.assertEqual({n: c for n, c in counts.items() if c != 1}, {},
                         "each untouched cite that is no JSON literal or names no tracked file must print one unknown line\n%s" % out)
        self.assertEqual(parse(out), [], "an untouched cite the check cannot read is no finding\n%s" % out)
        self.assertEqual(rc, 0, out)

    def test_an_added_js_value_cite_in_a_markdown_only_range_prints_one_unknown_line_naming_its_line(self):
        rng = self.value_range({"hooks/lib.mjs": MJS_BASE, CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"},
                               {NOTES: cite_page(["hooks/lib.mjs: LIMIT = 4"])})
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: the range changes Markdown only
        rc, out = self.run_check(rng)
        named = [line for line in unknown_lines(out) if "%s:3: " % NOTES in line]
        self.assertEqual(len(named), 1, "an added .mjs value cite must print one unknown line that names its line\n%s" % out)
        self.assertIn("hooks/lib.mjs", named[0], out)
        self.assertEqual(parse(out), [], out)
        self.assertEqual(rc, 0, out)

    def test_an_added_python_cite_of_a_name_bound_to_no_literal_at_head_prints_one_unknown_line_each(self):
        for line in NONLIT_CONFIG.split("\n")[:2]:  # scope: each name is bound at module level to a value no literal reads
            name, value = line.split(" = ")
            self.assertEqual(binding_kind(NONLIT_CONFIG, name), "assign")
            self.assertRaises(ValueError, ast.literal_eval, value)
        rng = self.value_range({CONFIG: NONLIT_CONFIG, NOTES: "# Notes\n\n"}, {NOTES: cite_page(NONLIT_CITES)})
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: the range changes Markdown only
        rc, out = self.run_check(rng)
        counts = unknown_counts(out, (3, 4))
        self.assertEqual({n: c for n, c in counts.items() if c != 1}, {},
                         "each added cite of a name bound to no literal must print one unknown line\n%s" % out)
        self.assertEqual(parse(out), [], "a cite of a name bound to no literal at head is no finding\n%s" % out)
        self.assertEqual(rc, 0, out)

    def test_an_untouched_python_cite_of_a_name_bound_to_no_literal_at_head_prints_one_unknown_line_each(self):
        base_cfg = "LIMIT = 30 * 86400\nGATE = compute()\nRETRIES = 2\n\n\ndef keep():\n    return 1\n"
        head_cfg = base_cfg.replace("RETRIES = 2", "RETRIES = 3")
        self.assertEqual(module_value(base_cfg, "RETRIES"), 2)  # scope: base binds RETRIES to 2
        self.assertEqual(module_value(head_cfg, "RETRIES"), 3)  # scope: the range changes RETRIES, so the whole tree is read
        for name in ("LIMIT", "GATE"):  # scope: head binds each name at module level to no literal
            self.assertEqual(binding_kind(head_cfg, name), "assign")
        self.assertRaises(ValueError, ast.literal_eval, "30 * 86400")
        rng = self.value_range({CONFIG: base_cfg, NOTES: cite_page(NONLIT_CITES)}, {CONFIG: head_cfg})
        rc, out = self.run_check(rng)
        counts = unknown_counts(out, (3, 4))
        self.assertEqual({n: c for n, c in counts.items() if c != 1}, {},
                         "each untouched cite of a name bound to no literal must print one unknown line on a whole-tree read\n%s" % out)
        self.assertEqual(parse(out), [], "an untouched cite of a name bound to no literal is no finding\n%s" % out)
        self.assertEqual(rc, 0, out)

    # Controls: no fire. Each one is green on the old code, because the old code never reads a value cite.

    def test_an_untouched_non_json_or_untracked_cite_prints_no_unknown_when_no_literal_changed(self):
        head_cfg = LIMIT_BASE + "\n\ndef extra():\n    return 2\n"
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), module_value(head_cfg, "LIMIT"))  # scope: no module-level literal changes
        cites = (["%s: LIMIT = %s" % (CONFIG, value) for value in NO_JSON_VALUES]
                 + ["%s: LIMIT = 4" % path for path in UNTRACKED_CITES])
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: cite_page(cites)}, {CONFIG: head_cfg})
        rc, out = self.run_check(rng)
        self.assertEqual(unknown_lines(out), [], "an untouched cite prints unknown only when the range changes a literal\n%s" % out)
        self.assertEqual(parse(out), [], out)
        self.assertEqual(rc, 0, out)

    def parent_parser_range(self, moved):
        """The range on main to topic over one script, its shared parent parser and one page. The page keeps line 3, an
        untouched cite of a value no JSON literal reads, and gains line 4, a cite of `Z = 2`. With `moved`, the range moves
        the script's `--between` flag into the parent parser `window_parser()`, which the script takes as `parents=[...]`.
        Without it, the script keeps its flag and only Z is added."""
        base = {REPORT: parser_script(["--between"]), NOTES: cite_page(["%s: X = not json" % REPORT])}
        head_page = cite_page(["%s: X = not json" % REPORT, "%s: Z = 2" % REPORT])
        if moved:
            head = {REPORT: parser_script([], parents=("window_parser",)) + "Z = 2\n",
                    COMMON: shared_parser(["--between"]), NOTES: head_page}
        else:
            head = {REPORT: parser_script(["--between"]) + "Z = 2\n", NOTES: head_page}
        return self.value_range(base, head)

    def test_a_flag_read_through_a_parent_parser_does_not_make_an_untouched_cite_unknown(self):
        base_src = parser_script(["--between"])
        head_src = parser_script([], parents=("window_parser",))
        self.assertEqual(argument_flags(base_src), {"--between"})  # scope: base REPORT declares --between itself
        self.assertEqual(argument_flags(head_src), set())  # scope: head REPORT declares no flag of its own
        self.assertIn("parents=[window_parser()]", head_src)  # scope: head REPORT takes its parser from COMMON
        self.assertEqual(argument_flags(shared_parser(["--between"])), {"--between"})  # scope: COMMON declares --between at head
        self.assertEqual(module_value(head_src + "Z = 2\n", "Z"), 2)  # scope: the added cite's Z = 2 holds at head
        self.assertRaises(ValueError, json.loads, "not json")  # scope: the untouched cite's value is no JSON literal

        control = self.parent_parser_range(moved=False)
        rc, out = self.run_check(control)
        self.assertEqual(rc, 0, out)
        self.assertEqual(parse(out), [], out)
        self.assertEqual(unknown_counts(out, (3,)), {3: 0},
                         "control: a range that moves no flag must print no unknown line for line 3\n%s" % out)

        rng = self.parent_parser_range(moved=True)
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(parse(out), [], out)
        self.assertEqual(unknown_counts(out, (3,)), {3: 0},
                         "a flag read through a parent parser must not make the untouched cite on line 3 unknown\n%s" % out)

    def test_an_untouched_js_value_cite_in_a_markdown_only_range_prints_no_unknown_line(self):
        base_page = cite_page(["hooks/lib.mjs: LIMIT = 4"])
        rng = self.value_range({"hooks/lib.mjs": MJS_BASE, CONFIG: LIMIT_BASE, NOTES: base_page},
                               {NOTES: base_page + "\nA new line.\n"})
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: the range changes Markdown only
        rc, out = self.run_check(rng)
        self.assertEqual(unknown_lines(out), [], "an untouched .mjs cite prints unknown only on a whole-tree read\n%s" % out)
        self.assertEqual(parse(out), [], out)
        self.assertEqual(rc, 0, out)

    def test_an_unchanged_value_quoted_by_a_line_passes(self):
        base_cfg, head_cfg = "LIMIT = 4\nRETRIES = 2\n", "LIMIT = 4\nRETRIES = 3\n"
        self.assertEqual(module_value(base_cfg, "LIMIT"), module_value(head_cfg, "LIMIT"))  # scope: LIMIT is unchanged
        self.assertNotEqual(module_value(base_cfg, "RETRIES"), module_value(head_cfg, "RETRIES"))  # scope: the range changes RETRIES
        self.assert_passes(self.value_range({CONFIG: base_cfg, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: head_cfg}))

    def test_a_line_wrong_at_base_and_left_alone_does_not_fire(self):
        cite = "- retry limit `hooks/config.py: LIMIT = 3`"
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 3 is wrong at base
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        for label, head in (("page untouched", {CONFIG: LIMIT_HEAD}),
                            ("page touched below the cite", {CONFIG: LIMIT_HEAD, NOTES: "# Notes\n\n%s\n\nA new line.\n" % cite})):
            with self.subTest(page=label):
                self.assert_passes(self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % cite}, head))

    def test_a_wrong_line_moved_within_a_touched_page_does_not_fire(self):
        cite = "- retry limit `hooks/config.py: LIMIT = 6`"
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4, so the cite's 6 is wrong at base
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n\nA note.\n" % cite},
                               {NOTES: "# Notes\n\nA note.\n\n%s\n" % cite})  # the same wrong line, moved from line 3 to line 5
        self.assert_passes(rng)

    def test_a_changed_value_with_no_cite_on_any_line_passes(self):
        for label, notes in (("empty page", ""), ("prose only", "# Notes\n\nThe retry limit lives in `hooks/config.py`.\n")):
            with self.subTest(page=label):
                self.assertNotIn("= ", notes)  # scope: no line holds a value cite
                self.assert_passes(self.value_range({CONFIG: LIMIT_BASE, NOTES: notes}, {CONFIG: LIMIT_HEAD}))

    def test_a_cite_rewritten_to_the_head_value_in_the_same_range_passes(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base binds LIMIT to 4
        self.assertEqual(module_value(LIMIT_HEAD, "LIMIT"), 5)  # scope: the range changes LIMIT to 5
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4},
                               {CONFIG: LIMIT_HEAD, NOTES: "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 5`\n"})
        self.assert_passes(rng)

    def test_an_added_cite_of_the_head_value_passes_when_no_literal_changed(self):
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), 4)  # scope: base and head bind LIMIT to 4, so no literal changes
        self.assert_passes(self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n"}, {NOTES: "# Notes\n\n%s\n" % CITE_4}))

    def test_a_literal_inside_a_def_is_no_module_value(self):
        base_cfg = "def build():\n    LIMIT = 4\n    return LIMIT\n\n\ndef keep():\n    return 1\n"
        head_cfg = base_cfg.replace("LIMIT = 4", "LIMIT = 5")
        self.assertIsNone(module_value(base_cfg, "LIMIT"))  # scope: base binds LIMIT only inside a def
        self.assertIsNone(module_value(head_cfg, "LIMIT"))  # scope: head binds it only inside a def too
        self.assertNotEqual(base_cfg, head_cfg)  # scope: the range changes the function's literal
        self.assert_passes(self.value_range({CONFIG: base_cfg, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: head_cfg}))

    def test_a_comment_only_python_change_reads_no_markdown(self):
        base_cfg = "LIMIT = 4  # the cap\n\n\ndef keep():\n    return 1\n"
        head_cfg = "LIMIT = 4  # the cap, reviewed\n\n\ndef keep():\n    return 1\n"
        self.assertEqual(ast.dump(ast.parse(base_cfg)), ast.dump(ast.parse(head_cfg)))  # scope: the trees match, so no literal changes
        self.assertNotEqual(base_cfg, head_cfg)  # scope: the file changes, in a comment
        rng = self.value_range({CONFIG: base_cfg, NOTES: "# Notes\n\n%s\n" % CITE_4}, {CONFIG: head_cfg})
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(whole_tree_listings(commands), [], commands)

    def test_a_range_that_changes_no_literal_and_touches_no_markdown_lists_no_markdown(self):
        head_cfg = "LIMIT = 4\n\n\ndef keep():\n    return 2\n"
        self.assertEqual(module_value(LIMIT_BASE, "LIMIT"), module_value(head_cfg, "LIMIT"))  # scope: no module-level literal changes
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n- retry limit `hooks/config.py: LIMIT = 3`\n"}, {CONFIG: head_cfg})
        rc, out, commands = self.run_traced_commands(rng)  # the untouched cite is wrong at base, so it is never read
        self.assertEqual(rc, 0, out)
        self.assertEqual(whole_tree_listings(commands), [], commands)

    def test_a_range_that_touches_only_markdown_lists_no_markdown_in_full(self):
        rng = self.value_range({CONFIG: LIMIT_BASE, NOTES: "# Notes\n\n%s\n" % CITE_4},
                               {NOTES: "# Notes\n\n%s\n\nA new line.\n" % CITE_4})
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(whole_tree_listings(commands), [], commands)

    def test_a_json_value_cite_is_not_read(self):
        base_json, head_json = '{"retries": {"max": 4}}\n', '{"retries": {"max": 5}}\n'
        self.assertEqual(json.loads(base_json)["retries"]["max"], 4)  # scope: base holds retries.max 4
        self.assertEqual(json.loads(head_json)["retries"]["max"], 5)  # scope: the range changes retries.max to 5
        self.assertEqual(module_value("RETRIES = 3\n", "RETRIES"), 3)  # scope: a Python literal changes too, so Markdown is read
        rng = self.value_range({"config.json": base_json, CONFIG: "RETRIES = 2\n",
                                NOTES: "# Notes\n\n- retry cap `config.json: retries.max = 4`\n"},
                               {"config.json": head_json, CONFIG: "RETRIES = 3\n"})
        rc, out = self.run_check(rng)
        self.assertEqual(parse(out), [], out)
        self.assertEqual([line for line in unknown_lines(out) if "config.json" in line], [], out)
        self.assertEqual(rc, 0, out)

    def test_a_range_that_touches_only_a_json_file_lists_no_markdown(self):
        base_json, head_json = '{"retries": {"max": 4}}\n', '{"retries": {"max": 5}}\n'
        self.assertEqual(json.loads(head_json)["retries"]["max"], 5)  # scope: the range changes retries.max to 5
        rng = self.value_range({"config.json": base_json, NOTES: "# Notes\n\n- retry cap `config.json: retries.max = 4`\n"},
                               {"config.json": head_json})
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertEqual(whole_tree_listings(commands), [], commands)

    def test_every_silent_parity_row_stays_silent(self):
        rows = parity_rows()
        silent = [(row, 3 + k) for k, row in enumerate(rows) if row["expect"] == "silent"]
        self.assertTrue(silent, "scope: the fixture holds silent rows")
        for row, _ in silent:  # scope: a row with a match keeps its value, and a row with none changes its file
            if row["match"]:
                self.assertEqual(module_value(row["base"], row["match"]["symbol"]), module_value(row["head"], row["match"]["symbol"]),
                                 "scope: the value of %s is unchanged" % row["cite"])
            else:
                self.assertNotEqual(row["base"], row["head"], "scope: the range changes the file of %s" % row["cite"])
        rc, out = self.run_check(self.parity_range(rows))
        flagged = {(path, line) for path, line, _, _ in parse(out)}
        loud = [row["cite"] for row, line in silent if (NOTES, line) in flagged]
        self.assertEqual(loud, [], "a silent parity row must not be flagged:\n%s" % out)

    # Type and set cites. A value is compared by value, a boolean is no number, 1 and 1.0 are one number as JSON reads
    # them, and a set cite pins no member order.
    # py-facts reads a set as a sorted list, so a set cite compares to it as a set.

    def added_cite_range(self, code, cite):
        """A Markdown-only range: CONFIG holds `code` on main and on topic, and the topic adds one line on NOTES
        line 3 that cites `cite`. No literal changes, so the check judges the added line alone."""
        rng = self.value_range({CONFIG: code, NOTES: "# Notes\n\n"}, {NOTES: cite_page([cite])})
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: the range changes Markdown only
        return rng

    def assert_cite_flagged(self, rng, cause):
        """Exactly one STALE008 finding, on NOTES line 3, and exit 1. A failure names `cause`."""
        rc, out = self.run_check(rng)
        self.assertEqual([(p, n, c) for p, n, c, _ in parse(out)], [(NOTES, 3, "STALE008")], "%s\n%s" % (cause, out))
        self.assertEqual(rc, 1, out)

    def assert_cite_matches(self, rng, cause):
        """No finding and exit 0. A failure names `cause`."""
        rc, out = self.run_check(rng)
        self.assertEqual(parse(out), [], "%s\n%s" % (cause, out))
        self.assertEqual(rc, 0, out)

    def test_an_added_number_cite_of_a_true_value_is_flagged_on_its_line(self):
        self.assertIs(module_value(value_file("LIMIT", "True"), "LIMIT"), True)  # scope: the code binds LIMIT to True
        self.assertIs(type(json.loads("1")), int)  # scope: the cite reads as the number 1
        self.assert_cite_flagged(self.added_cite_range(value_file("LIMIT", "True"), "hooks/config.py: LIMIT = 1"),
                                 "the cite 1 matched the value True: a boolean is no number, so the cite must match its type")

    def test_an_added_boolean_cite_of_a_number_value_is_flagged_on_its_line(self):
        self.assertIs(type(module_value(value_file("LIMIT", "1"), "LIMIT")), int)  # scope: the code binds LIMIT to the int 1
        self.assertIs(json.loads("true"), True)  # scope: the cite reads as the boolean true
        self.assert_cite_flagged(self.added_cite_range(value_file("LIMIT", "1"), "hooks/config.py: LIMIT = true"),
                                 "the cite true matched the value 1: a boolean is no number, so the cite must match its type")

    def test_an_added_int_cite_of_an_int_value_passes(self):
        self.assertIs(type(module_value(value_file("LIMIT", "1"), "LIMIT")), int)  # scope: the code binds LIMIT to an int
        self.assertIs(type(json.loads("1")), int)  # scope: the cite is an int too
        self.assert_cite_matches(self.added_cite_range(value_file("LIMIT", "1"), "hooks/config.py: LIMIT = 1"),
                                 "the int cite 1 must match the int value 1")

    def test_an_added_float_cite_of_a_float_value_passes(self):
        self.assertIs(type(module_value(value_file("LIMIT", "1.0"), "LIMIT")), float)  # scope: the code binds LIMIT to a float
        self.assertIs(type(json.loads("1.0")), float)  # scope: the cite is a float too
        self.assert_cite_matches(self.added_cite_range(value_file("LIMIT", "1.0"), "hooks/config.py: LIMIT = 1.0"),
                                 "the float cite 1.0 must match the float value 1.0")

    def test_an_added_float_cite_of_an_int_value_passes(self):
        self.assertIs(type(module_value(value_file("LIMIT", "1"), "LIMIT")), int)  # scope: the code binds LIMIT to the int 1
        self.assertIs(type(json.loads("1.0")), float)  # scope: the cite reads as the float 1.0
        self.assert_cite_matches(self.added_cite_range(value_file("LIMIT", "1"), "hooks/config.py: LIMIT = 1.0"),
                                 "the float cite 1.0 must match the int value 1: JSON reads both as one number")

    def test_an_added_int_cite_of_a_float_value_passes(self):
        self.assertIs(type(module_value(value_file("LIMIT", "1.0"), "LIMIT")), float)  # scope: the code binds LIMIT to the float 1.0
        self.assertIs(type(json.loads("1")), int)  # scope: the cite reads as the int 1
        self.assert_cite_matches(self.added_cite_range(value_file("LIMIT", "1.0"), "hooks/config.py: LIMIT = 1"),
                                 "the int cite 1 must match the float value 1.0: JSON reads both as one number")

    def test_an_added_cite_of_a_float_with_a_trailing_zero_passes(self):
        self.assertEqual(module_value(value_file("RATE", "0.9"), "RATE"), 0.9)  # scope: the code binds RATE to 0.9
        self.assertEqual(json.loads("0.90"), 0.9)  # scope: the cite 0.90 reads as the same float
        self.assert_cite_matches(self.added_cite_range(value_file("RATE", "0.9"), "hooks/config.py: RATE = 0.90"),
                                 "0.90 is the float 0.9, so the cite must pass: a value is compared by value, not by text")

    def test_an_added_set_cite_matches_a_set_value_in_any_member_order(self):
        self.assertEqual(module_value(value_file("TAGS", '{"a", "b"}'), "TAGS"), {"a", "b"})  # scope: the code binds TAGS to a set
        self.assertRaises(ValueError, json.loads, '{"b", "a"}')  # scope: a set is no JSON literal, so the cite takes the set form
        self.assert_cite_matches(self.added_cite_range(value_file("TAGS", '{"a", "b"}'), 'hooks/config.py: TAGS = {"b", "a"}'),
                                 'the set {"b", "a"} has the members of {"a", "b"}, so it must pass in any member order')

    def test_an_added_set_cite_with_a_wrong_member_is_flagged_on_its_line(self):
        self.assertEqual(module_value(value_file("TAGS", '{"a", "b"}'), "TAGS"), {"a", "b"})  # scope: the code binds TAGS to a set
        self.assert_cite_flagged(self.added_cite_range(value_file("TAGS", '{"a", "b"}'), 'hooks/config.py: TAGS = {"a", "c"}'),
                                 'the set {"a", "c"} holds c, which the set {"a", "b"} lacks: the cite must be flagged')

    def test_an_added_set_cite_of_single_quoted_members_is_flagged_as_no_json_literal(self):
        self.assertEqual(module_value(value_file("TAGS", '{"a", "b"}'), "TAGS"), {"a", "b"})  # scope: the code binds TAGS to a set
        self.assertRaises(ValueError, json.loads, "['a', 'b']")  # scope: single-quoted members are no JSON
        rc, out = self.run_check(self.added_cite_range(value_file("TAGS", '{"a", "b"}'), "hooks/config.py: TAGS = {'a', 'b'}"))
        found = parse(out)
        self.assertEqual([(p, n, c) for p, n, c, _ in found], [(NOTES, 3, "STALE008")], out)
        self.assertIn("no JSON literal", found[0][3], "a set cite that is no JSON literal must print that reason: %s" % found[0][3])
        self.assertEqual(rc, 1, out)


DECISION = "docs/decisions/pr-ledger.md"  # a decision record: STALE009 reads its added lines
GUIDE = "docs/guide.md"  # a page outside the decisions folder: STALE009 never reads it
MERGE_PY = "merge/merge.py"
LANE_LINT = "def lane_lint(lane):\n    return lane\n"  # the one name merge/merge.py binds
LEDGER = "The ledger reads no CI state; a batch line is a done record for the live head."
CITED_PAREN = LEDGER.replace("reads no CI state;", "reads no CI state (merge/merge.py lane_lint);")
CITED_TICK = LEDGER.replace("reads no CI state;", "reads no CI state, as `merge/merge.py` `lane_lint` shows;")
DEAD_PAREN = LEDGER.replace("reads no CI state;", "reads no CI state (merge/merge.py no_such_name);")
UNCITED = "The guard refuses a push to main."  # a code claim with no cite: STALE009 reports it
CLAIM = re.compile(r"^stale-cites: report, (?P<path>[^\s:]+):(?P<line>\d+): STALE009 (?P<text>.*)$", re.M)


def code_claims(out):
    """(path, line, text) of each report line the check printed for STALE009, in output order."""
    return [(m.group("path"), int(m.group("line")), m.group("text")) for m in CLAIM.finditer(out)]


def top_folders(rng, rev=None):
    """The first folder of each tracked path at `rev` (head by default): the folders a cite's first segment is tested
    against. A symlink at the root has no folder part, so it is in none."""
    listed = git(rng.repo, "ls-tree", "-r", "--name-only", rev or rng.head).split()
    return {p.split("/", 1)[0] for p in listed if "/" in p}


def tracked_history(rng):
    """The paths the commits before the base add or delete, renames not followed: the history a folder is read from."""
    return set(git(rng.repo, "log", "--no-renames", "--name-only", "--format=", rng.base).split())


def track_debts_guard(repo):
    write(repo, "debts/guard.py", GUARD)


def move_debts_guard(repo):
    move(repo, "debts/guard.py", "docs/debts/guard.py")


DEBTS_MOVED_HISTORY = (track_debts_guard, move_debts_guard)  # `debts/` tracked, then moved out, before the base


def track_root_link(repo):
    os.symlink("lint", os.path.join(repo, "link"))  # a root symlink to a tracked folder: an entry of mode 120000


def git_failing_log(case):
    """A folder holding a `git` that fails every `log` and runs each other command as the real git does. A case puts
    it first on PATH for the check's run only, so the history read fails and nothing else changes."""
    real = shutil.which("git")
    folder = os.path.join(case, "shim")
    os.makedirs(folder)
    script = os.path.join(folder, "git")
    with open(script, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\n"
                "for arg in \"$@\"; do\n"
                "  if [ \"$arg\" = log ]; then\n"
                "    echo 'git log refused by the test shim' >&2\n"
                "    exit 1\n"
                "  fi\n"
                "done\n"
                "exec %s \"$@\"\n" % shlex.quote(real))
    os.chmod(script, 0o755)
    return folder


class CodeClaimTests(StaleCase):
    """STALE009, range mode, report only. An ADDED line of a decision record that states what code does (a code
    subject and a behaviour verb) must carry a cite of a bound name, in a STALE002 form or a node id. A line that does
    not is a report line. The exit code never changes, and a line the range does not add is never reported. A dead
    cite is STALE010, not a report (NameCiteTests)."""

    def assert_code_claims(self, rng, expected):
        """The exit is 0, the verdict is PASS and no finding prints. The STALE009 report lines are exactly `expected`,
        as (path, line) pairs. Returns the output."""
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)
        self.assertEqual(parse(out), [], out)
        self.assertEqual(sorted((p, n) for p, n, _ in code_claims(out)), sorted(expected), out)
        return out

    def test_an_added_decision_line_stating_what_code_does_with_no_cite_is_reported_and_the_exit_stays_zero(self):
        rng, flagged = self.rows_range([("- " + LEDGER, True)])
        self.assertIn(DECISION, touched(rng))  # scope: the range adds a decision line
        self.assert_code_claims(rng, [(DECISION, n) for n in flagged])

    def test_a_bound_name_cited_in_either_form_silences_its_sentence_and_the_uncited_twin_still_fires(self):
        rows = [("- " + LEDGER, True), ("- " + CITED_TICK, False), ("- " + CITED_PAREN, False)]
        rng, _ = self.rows_range(rows)
        self.assertEqual(binding_kind(LANE_LINT, "lane_lint"), "def")  # scope: the cited name is bound at head
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, 1)])

    def test_a_node_id_of_a_name_bound_at_head_is_a_cite_and_the_uncited_twin_still_fires(self):
        rows = [("- The check refuses a push to main, as `lint/x.py::check` shows.", False), ("- " + UNCITED, True)]
        rng, _ = self.rows_range(rows)
        self.assertEqual(binding_kind(CODE["lint/x.py"], "check"), "def")  # scope: the cited name is bound at head
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, 2)])

    def test_a_claim_outside_the_decisions_folder_is_not_reported_and_the_same_claim_in_a_decision_is(self):
        guide_text, _ = rows_text([("- " + UNCITED, False)])
        decision_text, flagged = rows_text([("- " + UNCITED, True)])

        def change(repo):
            write(repo, GUIDE, guide_text)
            write(repo, DECISION, decision_text)
            commit(repo)
        rng = self.make_range(base_files(extra={GUIDE: "# Guide\n", DECISION: "# Heading\n", MERGE_PY: LANE_LINT}), change)
        self.assertIn(GUIDE, touched(rng))  # scope: the same claim is added on a page outside decisions
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, n) for n in flagged])

    def test_a_mark_for_stale009_leaves_its_line_out_and_a_mark_for_another_code_does_not(self):
        rows = [
            ("- " + UNCITED + " <!-- ste-disable-line STALE009 -->", False),
            ("- " + UNCITED + " <!-- ste-disable-line STALE005 -->", True),
            ("- " + UNCITED, True),
        ]
        rng, flagged = self.rows_range(rows)
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, n) for n in flagged])

    def test_a_claim_inside_a_fenced_block_is_not_reported_and_the_same_claim_after_the_fence_is(self):
        rows = [
            ("```", False),
            ("- " + UNCITED, False),  # an example inside a fence: a mention, as STALE005 reads it
            ("```", False),
            ("", False),
            ("- " + UNCITED, True),
        ]
        rng, flagged = self.rows_range(rows)
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, n) for n in flagged])

    def test_a_comment_opener_in_a_code_span_a_lone_apostrophe_and_a_span_closed_on_the_next_row_do_not_hide_a_claim(self):
        rows = [
            ("- Open a comment with `<!--`.", False),
            ("- Open a comment with `//`, `/*` and `#`, then the guard refuses a push to main.", True),
            ("- Don't count on it: the ledger reads no CI state.", True),
            ("- Keep `x", False),
            ("  y`. The guard refuses a push to main.", True),  # the span closes here; the claim sentence starts here
        ]
        rng, flagged = self.rows_range(rows)
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, n) for n in flagged])

    def test_a_sentence_on_a_line_the_range_does_not_add_is_not_reported_even_in_the_same_paragraph(self):
        base = LEDGER + "\n"  # no bullet: the old line and the added line are one paragraph
        head = base + "The hook refuses a push to main.\n"

        def change(repo):
            write(repo, DECISION, head)
            commit(repo)
        rng = self.make_range(base_files(extra={DECISION: base, MERGE_PY: LANE_LINT}), change)
        self.assertEqual(git(rng.repo, "show", "%s:%s" % (rng.base, DECISION)).split("\n")[0], LEDGER)  # scope: line 1 at base
        self.assertIn(DECISION, touched(rng))
        self.assert_code_claims(rng, [(DECISION, 2)])

    def test_a_dead_cite_is_stale010_and_no_stale009_report_while_the_uncited_claim_beside_it_still_reports(self):
        rows = [("- " + DEAD_PAREN, False), ("- " + UNCITED, True)]
        rng, _ = self.rows_range(rows)
        self.assertIsNone(binding_kind(LANE_LINT, "no_such_name"))  # scope: the head file never binds the name
        self.assertIn(DECISION, touched(rng))
        rc, out = self.run_check(rng)
        self.assertEqual(rc, 1, out)  # the dead cite is a finding, so the exit is 1
        self.assertEqual([(p, n, c) for p, n, c, _ in parse(out)], [(DECISION, 1, "STALE010")], out)
        self.assertEqual(sorted((p, n) for p, n, _ in code_claims(out)), [(DECISION, 2)], out)  # the uncited claim only


class NameCiteTests(StaleCase):
    """STALE010, range mode, a finding. An ADDED line that cites a Python name in a STALE002 form or a node id is
    flagged when its file is absent at head or the name is not bound there. A cite into a top folder is judged only
    when head tracks that folder, or history tracked it and head does not: one git log per range, started only when an
    added cite names an absent folder. A folder never tracked is no cite. A failed log prints one unknown line and
    flags nothing. Only added lines are judged, so the check is never red on work the range did not do."""

    def test_a_cite_to_an_unbound_name_is_flagged_and_the_bound_name_beside_it_is_silent(self):
        rows = [("- (lint/x.py CODE_CLAIM)", True), ("- (lint/x.py check)", False)]
        rng, _ = self.route_range(rows)
        self.assertIsNone(binding_kind(CODE["lint/x.py"], "CODE_CLAIM"))  # scope: lint/x.py binds no such name
        self.assertEqual(binding_kind(CODE["lint/x.py"], "check"), "def")  # scope: the name it does bind
        self.assertIn(NOTES, touched(rng))
        self.assert_flags(rng, [(NOTES, 1, "STALE010")])

    def test_a_dead_cite_on_an_added_line_is_flagged_and_the_same_cite_already_at_base_is_not(self):
        old = "- old `lint/x.py` `gone_one`"
        rng, _ = self.route_range([(old, False), ("- new `lint/x.py` `gone_two`", True)], base_notes=old + "\n")
        self.assertEqual(git(rng.repo, "show", "%s:%s" % (rng.base, NOTES)).split("\n")[0], old)  # scope: line 1 at base
        self.assertIn(NOTES, touched(rng))
        self.assert_flags(rng, [(NOTES, 2, "STALE010")])

    def test_each_cite_form_into_an_absent_file_is_flagged_and_a_bound_name_beside_them_is_silent(self):
        rows = [
            ("- (lint/gone.py lane_lint)", True),
            ("- `lint/gone.py` `lane_lint`", True),
            ("- `lint/gone.py::lane_lint`", True),
            ("- (lint/x.py check)", False),
            ("- Open a comment with `<!--` and cite `lint/gone.py` `lane_lint`.", True),
            ("- Open a comment with `//`, `/*` and `#`, as `lint/gone.py` `lane_lint` shows.", True),
            ("- Don't count on `lint/gone.py` `lane_lint`.", True),
        ]
        rng, flagged = self.route_range(rows)
        self.assertNotIn("lint/gone.py", git(rng.repo, "ls-tree", "-r", "--name-only", rng.head).split())  # scope
        self.assertEqual(binding_kind(CODE["lint/x.py"], "check"), "def")  # scope: the present file binds the name
        self.assert_flags(rng, [(NOTES, n, "STALE010") for n in flagged])

    def test_a_name_bound_only_in_a_comment_or_a_string_is_flagged_and_a_def_the_range_adds_is_bound(self):
        head = ('# CODE_CLAIM is named in this comment\n'
                'NOTE = "# CODE_CLAIM"\n'
                'DOC = """\nCODE_CLAIM\n"""\n\n\n'
                'def check():\n    return 3\n\n\n'
                'def new_one():\n    return 5\n')
        rows = [
            ("- `lint/x.py` `CODE_CLAIM`", True),
            ("- `lint/x.py` `check`", False),
            ("- `lint/x.py` `new_one`", False),
        ]
        rng, _ = self.route_range(rows, head_extra={"lint/x.py": head})
        self.assertIsNone(binding_kind(head, "CODE_CLAIM"))  # scope: a comment and strings name it, nothing binds it
        self.assertEqual(binding_kind(head, "new_one"), "def")  # scope: a def the range adds
        self.assertIn("lint/x.py", touched(rng))
        self.assert_flags(rng, [(NOTES, 1, "STALE010")])

    def test_src_layout_and_django_cites_are_silent_and_a_cite_into_a_tracked_folder_beside_them_is_flagged(self):
        foo_src = "def foo():\n    return 1\n"
        rows = [("- (mypkg/x.py foo)", False), ("- (django/db/models.py Model)", False), ("- (lint/x.py missing)", True)]
        rng, flagged = self.route_range(rows, extra={"src/mypkg/x.py": foo_src})
        self.assertEqual(binding_kind(foo_src, "foo"), "def")  # scope: the file under src binds the cited name
        self.assertIn("src", top_folders(rng))  # scope: src is a tracked top folder
        self.assertNotIn("mypkg", top_folders(rng))  # scope: mypkg is no tracked top folder
        self.assertNotIn("django", top_folders(rng))  # scope: django is no tracked top folder
        self.assertFalse(any(p.startswith(("mypkg/", "django/")) for p in tracked_history(rng)),
                         "scope: a folder the cites name was tracked in the history")
        self.assertIn("lint", top_folders(rng))  # scope: lint is a tracked top folder
        self.assertIsNone(binding_kind(CODE["lint/x.py"], "missing"))  # scope: lint/x.py binds no such name
        self.assert_flags(rng, [(NOTES, n, "STALE010") for n in flagged])

    def test_a_top_folder_tracked_only_in_history_is_judged_and_its_cite_is_flagged(self):
        rng, flagged = self.route_range([("- (debts/guard.py main)", True)], history=DEBTS_MOVED_HISTORY)
        self.assertNotIn("debts", top_folders(rng))  # scope: debts/ is absent at head
        self.assertIn("debts/guard.py", tracked_history(rng))  # scope: the history tracked debts/guard.py
        self.assert_flags(rng, [(NOTES, n, "STALE010") for n in flagged])

    def test_a_folder_never_tracked_beside_a_history_of_another_folder_is_silent_and_the_history_cite_is_flagged(self):
        rows = [("- (django/db/models.py Model)", False), ("- (debts/guard.py main)", True)]
        rng, flagged = self.route_range(rows, history=DEBTS_MOVED_HISTORY)
        self.assertNotIn("django", top_folders(rng))  # scope: django is absent at head
        self.assertTrue(any(p.startswith("debts/") for p in tracked_history(rng)), "scope: the history tracks debts/")
        self.assertFalse(any(p.startswith("django/") for p in tracked_history(rng)),
                         "scope: a folder the cite names was tracked in the history")
        self.assert_flags(rng, [(NOTES, n, "STALE010") for n in flagged])

    @unittest.skipUnless(os.name == "posix", "the shim is a POSIX shell script")
    def test_a_failed_history_log_prints_one_unknown_line_exits_zero_and_flags_nothing(self):
        rows = [("- (debts/guard.py main)", True), ("- (debts/guard.py keep)", True)]
        rng, _ = self.route_range(rows, history=DEBTS_MOVED_HISTORY)
        self.assertNotIn("debts", top_folders(rng))  # scope: debts/ is absent at head
        self.assertIn("debts/guard.py", tracked_history(rng))  # scope: the history tracks it, so the log is needed
        shim = git_failing_log(rng.case)
        refused = subprocess.run([os.path.join(shim, "git"), "log", "--format=", rng.base], cwd=rng.repo,
                                 capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0, "scope: the shim does not fail git log")
        served = subprocess.run([os.path.join(shim, "git"), "rev-parse", "--verify", "HEAD"], cwd=rng.repo,
                                capture_output=True, text=True)
        self.assertEqual(served.returncode, 0, "scope: the shim does not pass git rev-parse through")
        rc, out = self.run_check(rng, extra_env={"PATH": shim + os.pathsep + os.environ["PATH"]})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("stale-cites: UNKNOWN", out, out)  # a failed log is unknown, not a read that stops the run
        self.assertEqual(parse(out), [], out)
        self.assertEqual(len(unknown_lines(out)), 1, "one unknown line for the range, not one per cite\n" + out)

    @unittest.skipUnless(os.name == "posix", "a symlink entry needs a POSIX checkout")
    def test_a_root_symlink_top_folder_is_silent_and_a_tracked_folder_cite_beside_it_is_flagged(self):
        rows = [("- (link/x.py foo)", False), ("- (lint/x.py missing)", True)]
        rng, flagged = self.route_range(rows, history=(track_root_link,))
        self.assertTrue(git(rng.repo, "ls-tree", rng.head, "--", "link").startswith("120000 "), "scope: link is a symlink")
        self.assertNotIn("link", top_folders(rng))  # scope: a symlink is no tracked top folder
        self.assertIn("lint", top_folders(rng))  # scope: lint is a tracked top folder
        self.assert_flags(rng, [(NOTES, n, "STALE010") for n in flagged])

    def test_a_name_cited_in_an_empty_py_file_or_a_full_size_one_is_judged_by_what_the_file_binds(self):
        big = "".join("def f%d():\n    return %d\n\n\n" % (i, i) for i in range(300))
        rows = [
            ("- (lint/empty.py gone_eight)", True),
            ("- (lint/big.py f299)", False),
            ("- (lint/big.py f300)", True),
        ]
        rng, _ = self.route_range(rows, extra={"lint/empty.py": "", "lint/big.py": big})
        self.assertGreater(len(big), 8192)  # scope: the full-size file
        self.assertEqual(binding_kind(big, "f299"), "def")  # scope: the last def the file binds
        self.assertIsNone(binding_kind(big, "f300"))
        self.assertIsNone(binding_kind("", "gone_eight"))  # scope: the empty file binds nothing
        self.assert_flags(rng, [(NOTES, 1, "STALE010"), (NOTES, 3, "STALE010")])

    def test_a_markdown_range_that_adds_one_folder_py_cite_starts_exactly_four_git_processes_with_one_cat_file(self):
        rng, _ = self.route_range([("- (lint/x.py check)", False)])
        self.assertEqual(git(rng.repo, "diff", "--name-only", rng.base, rng.head), NOTES)  # scope: Markdown only
        self.assertEqual(binding_kind(CODE["lint/x.py"], "check"), "def")  # scope: the cited name is bound at head
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)
        subs = [command.split()[0] for command in commands]
        # The three starts of a Markdown-only range, and one cat-file that reads lint/x.py for the cite: four in all.
        self.assertEqual(sorted(subs), ["cat-file", "diff", "merge-base", "rev-parse"], subs)
        self.assertEqual(whole_tree_listings(commands), [], commands)

    def test_a_cite_into_a_folder_never_tracked_starts_one_git_log_for_the_range(self):
        """`mypkg` is no tracked top folder: its package lives under `src/`. `django` is no folder of the repo. Both
        cited files are absent at head and neither folder is in the history, so neither cite is judged. Both folders
        are absent at head, so one git log reads the history for the whole range."""
        foo_src = "def foo():\n    return 1\n"
        rows = [("- (mypkg/x.py foo)", False), ("- (django/db/models.py Model)", False)]
        rng, _ = self.route_range(rows, extra={"src/mypkg/x.py": foo_src})
        self.assertEqual(binding_kind(foo_src, "foo"), "def")  # scope: the file under src binds the cited name
        self.assertNotIn("mypkg", top_folders(rng))  # scope: mypkg is no tracked top folder
        self.assertNotIn("django", top_folders(rng))  # scope: django is no tracked top folder
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 0, out)
        self.assertIn("stale-cites: PASS", out)
        subs = [command.split()[0] for command in commands]
        # The four starts of a Markdown range, and one git log for the two absent folders: five, with one log.
        self.assertEqual(sorted(subs), ["cat-file", "diff", "log", "merge-base", "rev-parse"], subs)
        self.assertEqual(subs.count("log"), 1, subs)

    def test_a_cite_into_a_folder_tracked_in_history_starts_one_git_log_beyond_the_four(self):
        rng, _ = self.route_range([("- (debts/guard.py main)", True)], history=DEBTS_MOVED_HISTORY)
        self.assertNotIn("debts", top_folders(rng))  # scope: debts/ is absent at head
        rc, out, commands = self.run_traced_commands(rng)
        self.assertEqual(rc, 1, out)  # the history cite is judged and flagged, so the run exits 1
        subs = [command.split()[0] for command in commands]
        self.assertEqual(sorted(subs), ["cat-file", "diff", "log", "merge-base", "rev-parse"], subs)
        self.assertEqual(subs.count("log"), 1, subs)


if __name__ == "__main__":
    unittest.main()
