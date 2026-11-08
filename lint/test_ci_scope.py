#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/ci-scope.sh) and the mod test runner (.github/scripts/mod-tests.sh).

Each scope case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT and BASE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
CI_SCOPE overrides the script path (for a successor). Needs bash on PATH. The mod runner cases build a
scratch tree with a copy of mod-tests.sh and run it there; they need node on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per check job except the lint job `checks`: checks_windows, checks_windows_merge,
             checks_windows_rest, checks_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep, mods, shoot (the suite flags; shoot turns on the whole checks-shoot job)

Run with:  python3 lint/test_ci_scope.py -v
"""
import ast
import itertools
import os
import posixpath
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies the script under test into a scratch tree; rm_tree removes the run folder
SCRIPT = os.environ.get("CI_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")
JOB_FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep", "mods", "shoot"]
# Flags derived from others, kept out of JOB_FLAGS so the exact-set cases below stay about the base flags:
# checks_windows_sweep is set with checks_windows_rest. checks_guard is set when both `code` and `guard` are set, or
# directly by the arm for actions/playwright-setup and .github/shoot (the paths checks-guard installs from).
DERIVED_FLAGS = ["checks_windows_sweep", "checks_guard"]
ALL = JOB_FLAGS + STEP_FLAGS
BASH = shutil.which("bash")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(paths, event="pull_request", base="auto", existing=(), landed=None, head_ref=""):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit. `head_ref` is HEAD_REF,
    empty when not given, so no HEAD_REF of the caller's environment reaches the script."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q")
        git(d, "config", "user.email", "t@t")
        git(d, "config", "user.name", "t")
        git(d, "config", "commit.gpgsign", "false")
        # No background gc or maintenance after a commit: it can write into .git while the temp dir is removed.
        git(d, "config", "gc.auto", "0")
        git(d, "config", "maintenance.auto", "false")
        open(os.path.join(d, "seed.txt"), "w").write("seed\n")
        # The base holds landed-dirs.txt: the repo's own, or `landed` (a list of dir names) in its place.
        with open(os.path.join(HERE, "..", "landed-dirs.txt")) as f:
            real = f.read()
        open(os.path.join(d, "landed-dirs.txt"), "w").write(real if landed is None else chr(10).join(landed) + chr(10))
        for p in existing:  # in the base commit, so the head commit modifies them
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write("old\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        sha = git(d, "rev-parse", "HEAD")
        for p in paths:
            full = os.path.join(d, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write("changed\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        out = os.path.join(d, "..", f"out-{os.getpid()}.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out, HEAD_REF=head_ref,
                   BASE_SHA=sha if base == "auto" else base)
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = open(out).read().split()
        os.remove(out)
        return dict(l.split("=", 1) for l in lines)


MERGE_PY = os.path.join(HERE, "..", "merge", "merge.py")
LOADER = "_load_hooks_module"  # merge.py's by-path loader: _load_hooks_module("git_reads") loads hooks/git_reads.py
# The folders whose .py files a load can name: the folders that merge.py, or a file it loads, puts on sys.path, and skills/,
# where merge.py loads skills/roadmap/build.py by path.
LOAD_ROOTS = ("hooks", "lint", "janitor", "merge", "actions", "skills", "testing", "bin")


def repo_files(*dirs):
    """-> the repo-relative paths of every file under the dirs, spelled as the scope script names them."""
    root = os.path.join(HERE, "..")
    out = set()
    for d in dirs:
        for dp, dns, fns in os.walk(os.path.join(root, d)):
            dns[:] = [x for x in dns if x != "__pycache__"]
            out.update(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/") for f in fns)
    return out


def repo_load_files():
    """-> the repo-relative paths a load can name: every .py file under LOAD_ROOTS, and every file under bin/, where a by-path
    load names a script with no .py name (bin/sim-lease)."""
    return {p for p in repo_files(*LOAD_ROOTS) if p.endswith(".py") or p.startswith("bin/")}


def read_repo(rel):
    with open(os.path.join(HERE, "..", rel), encoding="utf-8") as f:
        return f.read()


def consts(node):
    """-> the string constants in the subtree of `node`."""
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)


def scopes_of(tree):
    """-> (parents, values): each node's parent, and {scope: {name: [value]}} for every `name = value` in the file, keyed by the
    function or module the assignment sits in. Module-level and function-level names are both read here."""
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            scope = node
            while not isinstance(scope, SCOPES):
                scope = parents[scope]
            for t in node.targets:
                if isinstance(t, ast.Name):
                    values.setdefault(scope, {}).setdefault(t.id, []).append(node.value)
    return parents, values


def dotted(node):
    """-> the dotted name of a Name or an Attribute chain (`os.path`), or '' for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + "." + node.attr if base else ""
    return ""


def path_fn(func):
    """-> f when a call's `func` is os.path.f, posixpath.f or a bare f, else ''."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and dotted(func.value) in ("os.path", "posixpath"):
        return func.attr
    return ""


def read_values(node, rel, scopes, depth=0):
    """-> the path strings `node` can be, read from this file alone: a string literal; `__file__`, the file's own path `rel`; a
    name the file assigns, in the nearest function or module that holds it; os.path.join, dirname, realpath and abspath; Path(x)
    with .resolve(), .absolute(), .parent or .parents[N]; and `/`. [] when a part cannot be read: such a load is not guessed."""
    parents, values = scopes
    if depth > 8:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return [rel]
        cur = parents.get(node)
        while cur is not None:
            if isinstance(cur, SCOPES):
                if node.id in values.get(cur, {}):
                    return [s for v in values[cur][node.id] for s in read_values(v, rel, scopes, depth + 1)]
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                        isinstance(a, ast.arg) and a.arg == node.id for a in ast.walk(cur.args)):
                    return []  # a parameter: its value is the caller's, not this file's
            cur = parents.get(cur)
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return join_all([node.left, node.right], rel, scopes, depth)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return [posixpath.dirname(s) for s in read_values(node.value, rel, scopes, depth + 1)]
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents" \
            and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
        out = read_values(node.value.value, rel, scopes, depth + 1)
        for _ in range(node.slice.value + 1):  # parents[0] is the folder of the path, parents[1] its parent
            out = [posixpath.dirname(s) for s in out]
        return out
    if isinstance(node, ast.Call):
        if node.args:
            fn = path_fn(node.func)
            if fn == "join":
                return join_all(node.args, rel, scopes, depth)
            if fn == "dirname" and len(node.args) == 1:
                return [posixpath.dirname(s) for s in read_values(node.args[0], rel, scopes, depth + 1)]
            if fn in ("realpath", "abspath") and len(node.args) == 1:
                return read_values(node.args[0], rel, scopes, depth + 1)
            if dotted(node.func) in ("Path", "pathlib.Path") and len(node.args) == 1:
                return read_values(node.args[0], rel, scopes, depth + 1)
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ("resolve", "absolute"):
            return read_values(node.func.value, rel, scopes, depth + 1)
    return []


def join_all(parts, rel, scopes, depth):
    """-> posixpath.join over every combination of the paths each part can be; [] when any part cannot be read."""
    options = [read_values(p, rel, scopes, depth + 1) for p in parts]
    if not all(options):
        return []
    return [posixpath.join(*combo) for combo in itertools.product(*options)]


class UnresolvedLoad(Exception):
    """A load the closure reader cannot follow. It is raised, never dropped: a dropped load leaves its file out of the closure, and a
    change to that file then gets no merge flag."""


# A by-path load whose path the reader cannot read, allowed by naming the module constant that holds the path. The reader reads the
# value from the file that holds the constant, so a constant it cannot read is still a failure. A constant is named here, not copied.
ALLOWED_CONSTANT_LOADS = {
    "hooks/guard_merge.py": ("MERGE_TOOL_REL",),  # the merge tool under a settings root; the constant names merge/merge.py
    "hooks/decision_watch.py": ("_GUARD_PATH",),  # GUARD_UNDER_TEST, an environment override; the default branch imports guard by name
}
PACKAGE_WHY = "a package-qualified load; the reader follows a load only by the name of a file in the closure"
COMPUTED_WHY = "a by-path load whose path it cannot read; name the file, or allow-list the constant the path names"


def unresolved(rel, node, why):
    return UnresolvedLoad(f"{rel}: cannot follow the load {ast.unparse(node)}: {why}")


def package_qualified(dotted, by_name):
    """-> True when `dotted` starts with a folder the loads live in, and no file of that name is in the closure."""
    top = dotted.split(".")[0]
    return top in LOAD_ROOTS and top not in by_name


def is_parameter(name_node, parents):
    """-> True when the name is a parameter of a function that holds it."""
    cur = parents.get(name_node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(a, ast.arg) and a.arg == name_node.id for a in ast.walk(cur.args)):
            return True
        cur = parents.get(cur)
    return False


def reached_names(node, scopes, depth=0):
    """-> the Name nodes `node` reads, and the Name nodes of the values its local names are assigned from, to depth 8. A path such as
    `path` reads the names its own assignment reads, so a constant named in that assignment is reached from the path."""
    parents, values = scopes
    out = []
    if depth > 8:
        return out
    for n in ast.walk(node):
        if not isinstance(n, ast.Name):
            continue
        out.append(n)
        cur = parents.get(n)
        while cur is not None:
            if isinstance(cur, SCOPES) and n.id in values.get(cur, {}):
                for v in values[cur][n.id]:
                    out.extend(reached_names(v, scopes, depth + 1))
                break
            cur = parents.get(cur)
    return out


def mentions_parameter(node, scopes):
    """-> True when `node` reads a parameter, directly or through a local name. A path built from a parameter is the caller's value.
    The caller's load is read where the caller passes it, so the reader takes that path as no load."""
    parents, _ = scopes
    return any(is_parameter(n, parents) for n in reached_names(node, scopes))


def allowed_constant(rel, node, scopes):
    """-> the name node of a constant ALLOWED_CONSTANT_LOADS names for the file `rel`, which `node` reads, or None."""
    names = ALLOWED_CONSTANT_LOADS.get(rel, ())
    return next((n for n in reached_names(node, scopes) if n.id in names), None)


# A subprocess target (bin/ci-job, run as a child process) is no load and stays out of the closure (decision ci-scope-merge-closure).
def file_loads(rel, source, files):
    """-> the files in `files` that the file `rel`, with this `source`, loads when it runs. A load is: an import at any depth
    (`import x`, `import x.y`, `from x import y`, `from . import y`) that names a file x.py in `files`; LOADER("<name>") as
    hooks/<name>.py; `__import__("x")` and `importlib.import_module("x")` with a literal name; and a by-path load,
    `spec_from_file_location(name, path)` or `SourceFileLoader(name, path)`, whose path names a file in `files`, by a string
    constant in the call, or by a path read from this file (read_values). module_from_spec takes no path: its load is read where
    its spec or loader is made. A name in a comment or a string is no load. A load the reader cannot follow raises UnresolvedLoad:
    a package-qualified load, or a by-path load whose path it cannot read, unless the path is built from a parameter or allow-listed
    by the constant it names (ALLOWED_CONSTANT_LOADS)."""
    tree = ast.parse(source)
    by_name = {}
    for p in files:
        if p.endswith(".py"):
            by_name.setdefault(posixpath.basename(p)[:-3], set()).add(p)
    scopes = scopes_of(tree)
    module_strings = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    module_strings.setdefault(t.id, []).extend(consts(node.value))
    here = posixpath.dirname(rel)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if package_qualified(a.name, by_name):
                    raise unresolved(rel, node, PACKAGE_WHY)
                out |= by_name.get(a.name.split(".")[0], set())
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                if package_qualified(node.module, by_name):
                    raise unresolved(rel, node, PACKAGE_WHY)
                out |= by_name.get(node.module.split(".")[0], set())
            elif node.level:  # a sibling of this file
                for name in ([node.module] if node.module else [a.name for a in node.names]):
                    out.add(posixpath.normpath(posixpath.join(here, name.replace(".", "/") + ".py")))
        elif isinstance(node, ast.Call):
            func = node.func
            fn = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            first = node.args[0] if node.args else None
            literal = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else ""
            if fn == LOADER and literal:
                out.add(f"hooks/{literal}.py")
            elif fn in ("__import__", "import_module") and literal:
                if package_qualified(literal, by_name):
                    raise unresolved(rel, node, PACKAGE_WHY)
                out |= by_name.get(literal.split(".")[0], set())
            elif fn in ("spec_from_file_location", "SourceFileLoader"):
                strings = []
                for arg in [*node.args, *(k.value for k in node.keywords)]:
                    strings += consts(arg)
                    strings += [s for n in ast.walk(arg) if isinstance(n, ast.Name) for s in module_strings.get(n.id, [])]
                for s in strings:
                    if s.endswith(".py"):
                        out.add(posixpath.normpath(s))
                        out.add(posixpath.normpath(posixpath.join(here, s)))
                # The path is the second argument (location, or path as a keyword), read as repo-relative: __file__ is rel.
                path_arg = node.args[1] if len(node.args) > 1 else next(
                    (k.value for k in node.keywords if k.arg in ("location", "path")), None)
                if path_arg is not None:
                    got = read_values(path_arg, rel, scopes)
                    named = allowed_constant(rel, path_arg, scopes)
                    if got:
                        out |= {posixpath.normpath(s) for s in got}
                    elif named is not None:
                        out |= {posixpath.normpath(s) for s in read_values(named, rel, scopes)}
                    elif not mentions_parameter(path_arg, scopes):
                        raise unresolved(rel, node, COMPUTED_WHY)
    return out & files


def closure(start, files, read):
    """-> the files in `files` that `start` loads, directly or through the files they load, to closure. read(rel) is a file's
    source. `start` is not in the result, even when a file loads it back."""
    found, todo = set(), [start]
    while todo:
        cur = todo.pop()
        for dep in file_loads(cur, read(cur), files) - found - {start}:
            found.add(dep)
            todo.append(dep)
    return found


def defines_function(source, name):
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in ast.parse(source).body)


class FileLoads(unittest.TestCase):
    """The reader on fixtures: each kind of load, a name in a comment or a string, a relative import, and the closure. These test
    the reader in this file, not product code, so they are controls, not product claims."""

    FILES = {"hooks/_nowindow.py", "hooks/required_check.py", "hooks/git_reads.py", "lint/hook_catalog.py",
             "lint/check_silent_undo.py", "hooks/in_class.py", "hooks/deep.py", "janitor/sweep.py", "bin/sim-lease"}

    def loads(self, source, rel="merge/merge.py"):
        return file_loads(rel, source, self.FILES)

    def test_empty_module_loads_nothing(self):
        self.assertEqual(self.loads(""), set())

    def test_module_level_imports_and_the_loader_count(self):
        src = (
            "import json\n"  # no file of that name in FILES: no load
            "try:\n    import _nowindow\nexcept ImportError:\n    _nowindow = None\n"  # a top-level try block counts
            "from required_check import REQUIRED_CHECK\n"
            "from hook_catalog import RECORDS_PAGE\n"
            "_git_reads = _load_hooks_module(\"git_reads\")\n"
        )
        self.assertEqual(self.loads(src), {"hooks/_nowindow.py", "hooks/required_check.py", "lint/hook_catalog.py", "hooks/git_reads.py"},
                         "file_loads misses a module-level load, or counts one that is no load")

    def test_function_level_and_class_level_imports_count(self):
        src = ("def inside():\n    import check_silent_undo\n    _load_hooks_module(\"in_class\")\n"
               "class Holder:\n    import deep\n")
        self.assertEqual(self.loads(src), {"lint/check_silent_undo.py", "hooks/in_class.py", "hooks/deep.py"},
                         "file_loads misses a load below module level")

    def test_a_name_in_a_comment_or_a_string_is_no_load(self):
        self.assertEqual(self.loads("# import sweep\nNOTE = \"import check_silent_undo\"\n"), set())

    def test_relative_imports_name_a_sibling(self):
        self.assertEqual(self.loads("from . import deep\nfrom .in_class import X\n", rel="hooks/guard.py"),
                         {"hooks/deep.py", "hooks/in_class.py"})

    def test_by_path_and_importlib_loads_count(self):
        src = ("import importlib.util, pathlib\n"
               "SWEEP = pathlib.Path(__file__).resolve().parents[1] / \"janitor/sweep.py\"\n"
               "def load():\n"
               "    importlib.util.spec_from_file_location(\"sweep_under_test\", SWEEP)\n"
               "    return importlib.import_module(\"deep\")\n")
        self.assertEqual(self.loads(src), {"janitor/sweep.py", "hooks/deep.py"})

    def test_a_source_file_loader_reads_a_script_named_through_file(self):
        # hooks/guard.py loads bin/sim-lease this way: a local name joined from __file__'s folder and two literals.
        src = ("import importlib.machinery, os\n"
               "def sim_lease():\n"
               "    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), \"..\", \"bin\", \"sim-lease\")\n"
               "    return importlib.machinery.SourceFileLoader(\"sim_lease\", path)\n")
        self.assertEqual(self.loads(src, rel="hooks/guard.py"), {"bin/sim-lease"},
                         "file_loads misses a SourceFileLoader load of a script named through __file__'s folder")

    def test_a_by_path_load_reads_a_module_constant(self):
        src = ("import importlib.util, os\n"
               "HOOKS = os.path.join(\"hooks\", \"..\")\n"
               "def load():\n"
               "    return importlib.util.spec_from_file_location(\"sweep\", os.path.join(HOOKS, \"janitor\", \"sweep.py\"))\n")
        self.assertEqual(self.loads(src), {"janitor/sweep.py"},
                         "file_loads misses a by-path load whose path joins a module constant")

    def test_a_by_path_load_reads_a_local_name_in_its_own_function(self):
        src = ("import importlib.util, os\n"
               "def other():\n    path = \"janitor/sweep.py\"\n    return path\n"
               "def load():\n"
               "    path = os.path.join(\"hooks\", \"deep.py\")\n"
               "    return importlib.util.spec_from_file_location(\"deep\", path)\n")
        self.assertEqual(self.loads(src), {"hooks/deep.py"},
                         "file_loads does not resolve a by-path load through a local name in its own function")

    def test_a_by_path_load_reads_a_parent_folder_of_this_file(self):
        # merge.py loads skills/roadmap/build.py as pathlib's parents[1] of __file__, joined with a split literal.
        src = ("import importlib.util, pathlib\n"
               "IDLE_BUILD = pathlib.Path(__file__).resolve().parents[1] / \"janitor\" / \"sweep.py\"\n"
               "def load():\n"
               "    return importlib.util.spec_from_file_location(\"roadmap_build\", IDLE_BUILD)\n")
        self.assertEqual(self.loads(src, rel="merge/merge.py"), {"janitor/sweep.py"},
                         "file_loads does not read a by-path load's path through parents[N] of __file__")

    def test_a_path_built_from_a_parameter_is_no_load(self):
        # Control: the caller passes root, which this file cannot read. A reader that guessed would add janitor/sweep.py.
        src = ("import importlib.util, os\n"
               "def load(root):\n"
               "    return importlib.util.spec_from_file_location(\"sweep\", os.path.join(root, \"janitor\", \"sweep.py\"))\n")
        self.assertEqual(self.loads(src), set(), "file_loads guesses a by-path load from a path part it cannot read")

    def test_the_closure_follows_loads_to_the_end_and_stops_at_its_start(self):
        files = {"merge/merge.py", "hooks/mid.py", "hooks/leaf.py", "hooks/unused.py"}
        source = {"merge/merge.py": "def f():\n    import mid\n", "hooks/mid.py": "import leaf\n",
                  "hooks/leaf.py": "import merge\n", "hooks/unused.py": "import leaf\n"}
        self.assertEqual(closure("merge/merge.py", files, source.__getitem__), {"hooks/mid.py", "hooks/leaf.py"})


class UnresolvedLoads(unittest.TestCase):
    """A load the reader cannot resolve fails the closure loudly, and the failure names the file and the load. The reader must not
    drop it: a dropped load leaves its file out of the closure, so a change to that file gets no merge flag. Each case puts the load
    in hooks/mid.py, which merge/merge.py imports, so the failure comes through closure(), the walk the check runs."""

    def closure_of(self, mid_src, allowed=()):
        """The closure from merge/merge.py over the fixture files. `allowed` are the constants allow-listed for hooks/mid.py."""
        files = {"merge/merge.py", "hooks/mid.py", "hooks/deep.py"}
        source = {"merge/merge.py": "import mid\n", "hooks/mid.py": mid_src, "hooks/deep.py": "X = 1\n"}
        with mock.patch.dict(ALLOWED_CONSTANT_LOADS, {"hooks/mid.py": tuple(allowed)}):
            return closure("merge/merge.py", files, source.__getitem__)

    def assert_fails_loud(self, mid_src, load, allowed=()):
        """The closure raises UnresolvedLoad, and its message names hooks/mid.py and the load's text."""
        with self.assertRaises(UnresolvedLoad, msg=f"the closure drops the unresolvable load {load!r} without a failure") as cm:
            self.closure_of(mid_src, allowed)
        self.assertIn("hooks/mid.py", str(cm.exception), f"the failure for {load!r} does not name the file hooks/mid.py")
        self.assertIn(load, str(cm.exception), f"the failure does not name the load {load!r}")

    def test_a_package_qualified_from_import_fails_loud(self):
        self.assert_fails_loud("from hooks import deep\n", "from hooks import deep")

    def test_a_package_qualified_dotted_import_fails_loud(self):
        self.assert_fails_loud("import hooks.deep\n", "import hooks.deep")

    def test_an_importlib_load_of_a_package_qualified_name_fails_loud(self):
        self.assert_fails_loud('import importlib\nimportlib.import_module("hooks.deep")\n', "hooks.deep")

    def test_a_by_path_load_with_a_concatenated_path_fails_loud(self):
        self.assert_fails_loud('import importlib.util, os\n'
                               'SPEC = importlib.util.spec_from_file_location("deep", os.environ["X"] + ".py")\n',
                               "spec_from_file_location")

    def test_a_by_path_load_with_an_f_string_path_fails_loud(self):
        self.assert_fails_loud('import importlib.util, os\n'
                               'SPEC = importlib.util.spec_from_file_location("deep", f"hooks/{os.environ[\'X\']}.py")\n',
                               "spec_from_file_location")

    def test_a_by_path_load_with_a_format_path_fails_loud(self):
        self.assert_fails_loud('import importlib.util, os\n'
                               'SPEC = importlib.util.spec_from_file_location("deep", "hooks/{}.py".format(os.environ["X"]))\n',
                               "spec_from_file_location")

    # An allow-listed constant that reads to nothing. The allow list names the constant that holds the path, so the reader must
    # fail on an empty read of it, not pass the load with no file. Named failure: an allow-listed load passes with no file added.
    def test_an_allow_listed_constant_that_reads_to_nothing_fails_loud(self):
        # The decision_watch.py shape: a module constant holds an environment read, and a by-path load names it.
        self.assert_fails_loud('import importlib.util, os\n'
                               'MID_PATH = os.environ.get("MID_UNDER_TEST")\n'
                               'SPEC = importlib.util.spec_from_file_location("deep", MID_PATH)\n',
                               "MID_PATH", allowed=("MID_PATH",))

    # An allow-listed constant that reads to a file no closure holds. The merge_module shape: a local path joins a loop variable
    # and the constant. Named failure: the read file is dropped by the closure filter, and no failure names it.
    def test_an_allow_listed_constant_that_reads_to_no_closure_file_fails_loud(self):
        self.assert_fails_loud('import importlib.util, os\n'
                               'MID_PATH = os.path.join("hooks", "nope.py")\n'
                               'def load(roots):\n'
                               '    for root in roots:\n'
                               '        path = os.path.join(root, MID_PATH)\n'
                               '        return importlib.util.spec_from_file_location("nope", path)\n',
                               "MID_PATH", allowed=("MID_PATH",))

    # Green controls: the same call shapes with a path or a name the reader can read, and loads it must ignore.

    def test_an_allow_listed_constant_that_reads_to_a_closure_file_still_resolves(self):
        src = ('import importlib.util, os\n'
               'MID_PATH = os.path.join("hooks", "deep.py")\n'
               'def load(roots):\n'
               '    for root in roots:\n'
               '        path = os.path.join(root, MID_PATH)\n'
               '        return importlib.util.spec_from_file_location("deep", path)\n')
        # Scope first: without the allow list this load is unreadable, so the case below tests the allow-listed path.
        with self.assertRaises(UnresolvedLoad, msg="the load reads without the allow list, so this control tests nothing"):
            self.closure_of(src)
        self.assertEqual(self.closure_of(src, allowed=("MID_PATH",)), {"hooks/mid.py", "hooks/deep.py"},
                         "an allow-listed constant that reads to a closure file no longer resolves")

    def test_a_literal_by_path_load_still_resolves(self):
        src = 'import importlib.util\nSPEC = importlib.util.spec_from_file_location("deep", "hooks/deep.py")\n'
        self.assertEqual(self.closure_of(src), {"hooks/mid.py", "hooks/deep.py"}, "a literal by-path load stopped resolving")

    def test_stdlib_loads_are_no_load(self):
        src = "import os.path\nimport json\nfrom collections import abc\nimport importlib\nimportlib.import_module('json')\n"
        self.assertEqual(self.closure_of(src), {"hooks/mid.py"}, "a stdlib load was read as a load of a closure file, or raised")

    def test_a_load_text_in_a_comment_or_a_string_is_no_load(self):
        src = ("# don't import hooks.deep\n"
               'NOTE = "from hooks import deep"\n'
               'DOC = """\n'
               "import hooks.deep\n"
               'importlib.import_module("hooks.deep")\n'
               '"""\n')
        self.assertEqual(self.closure_of(src), {"hooks/mid.py"}, "a load named in a comment or a string was read as a load")

    def test_the_real_merge_closure_reads_without_an_unresolved_load(self):
        # Green on base. It stays green only once each known computed load is resolved or allow-listed by the constant it names.
        loads = closure("merge/merge.py", repo_load_files(), read_repo)
        missing = [p for p in REACHED if p not in loads]
        self.assertFalse(missing, f"the closure from merge.py misses {missing}")


# The files the closure must reach, one per kind of load the reader sorts: a module-level import, a by-path load, a load through a
# module-level path, a function-level import, a transitive load, guard.py, and bin/sim-lease, a script with no .py name that
# guard.py loads by a path built from __file__'s folder. A reader that stops short fails the scope check first.
REACHED = ["hooks/_nowindow.py", "hooks/git_reads.py", "skills/roadmap/build.py", "janitor/sweep.py", "hooks/shared_names.py",
           "hooks/guard.py", "hooks/guard_core.py", "hooks/git_bash.py", "hooks/decision_watch.py", "lint/hook_catalog.py",
           "lint/workflow_steps.py", "lint/stale_cites.py", "lint/check_debt_retire.py", "lint/check_skill_model_rows.py",
           "actions/ci-alarm/clear_rule.py", "bin/sim-lease"]


@unittest.skipUnless(BASH, "bash not on PATH")
class MergeFlagFiles(unittest.TestCase):
    """The merge flag (checks_windows_merge) against the files merge/merge.py loads, directly or through imports, to closure."""

    def merge_closure(self):
        """-> the files merge.py loads, to closure, read from this checkout."""
        with open(MERGE_PY, encoding="utf-8") as f:
            src = f.read()
        self.assertTrue(defines_function(src, LOADER), f"merge.py no longer defines {LOADER}, so its by-path loads are not read")
        loads = closure("merge/merge.py", repo_load_files(), read_repo)
        # Scope before subject: the reader reached each named file, so the case below tests the whole closure.
        missing = [p for p in REACHED if p not in loads]
        self.assertFalse(missing, f"the closure from merge.py misses {missing}: the reader does not follow those loads")
        return loads

    # Named failure: a file that merge.py loads, directly or through imports, gets no merge flag from the script, so a change to
    # it runs no merge suite. Ruling (decision ci-scope-merge-closure): the merge flag covers the whole closure.
    def test_every_file_merge_py_loads_gets_the_merge_flag(self):
        loads = self.merge_closure()
        no_flag = sorted(p for p in loads if run([p], existing=[p]).get("checks_windows_merge") != "true")
        self.assertFalse(no_flag, f"ci-scope.sh gives no merge flag to {len(no_flag)} of the {len(loads)} files merge.py loads: {no_flag}")


@unittest.skipUnless(BASH, "bash not on PATH")
class DerivedFlags(unittest.TestCase):
    PATHS = [["hooks/guard.py"], ["hooks/test_guard.py"], ["janitor/sweep.py"], ["hooks/test_config_watch.py"], ["merge/merge.py"],
             ["README.md"], ["skills/ci-hygiene/SKILL.md"], ["bin/ios-ship"], ["lint/layout.json"], ["actions/stamp/stamp.mjs"],
             ["install.ps1"], ["unlisted/new-file.txt"], ["bin/verdict"], ["settings.json"], ["bin/shoot"]]

    def check(self, got):
        for n in DERIVED_FLAGS:
            self.assertIn(n, got, f"output {n} missing: {got}")
        self.assertEqual(got["checks_windows_sweep"], got["checks_windows_rest"], got)
        # PATHS touch neither direct arm, so the both-flags rule is the whole rule for them.
        both = got["code"] == "true" and got["guard"] == "true"
        self.assertEqual(got["checks_guard"], "true" if both else "false", got)

    def test_sweep_flag_follows_rest_and_guard_flag_needs_code_and_guard(self):
        seen = set()
        for paths in self.PATHS:
            for event in ("pull_request", "push"):
                with self.subTest(paths=paths, event=event):
                    got = run(paths, event=event)
                    self.check(got)
                    seen.add((got["checks_windows_rest"], got["checks_guard"]))
        # The sample reaches both ends: everything on, and a docs-only change with everything off.
        self.assertTrue({("true", "true"), ("false", "false")} <= seen, seen)

    def test_unreadable_diff_turns_the_derived_flags_on(self):
        self.check(run(["hooks/guard.py"], base="0" * 40))
        self.assertEqual(run(["hooks/guard.py"], base="0" * 40)["checks_guard"], "true")


@unittest.skipUnless(BASH, "bash not on PATH")
class Scope(unittest.TestCase):
    def assertFlags(self, got, want_true=(), want_false=()):
        for n in ALL:
            self.assertIn(n, got, f"output {n} missing: {got}")
        for n in want_true:
            self.assertEqual(got[n], "true", f"{n}: {got}")
        for n in want_false:
            self.assertEqual(got[n], "false", f"{n}: {got}")

    def test_docs_only_pr_turns_every_job_off(self):
        got = run(["README.md", "decisions/some-record.md"])
        self.assertFlags(got, want_false=ALL)

    def test_merge_change_turns_the_merge_job_on(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_true=["checks_windows_merge", "code"])

    def test_guard_change_turns_the_guard_suites_on(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_macos", "guard", "sweep", "code"])
        # The selector's test
        # and mutation test also turn `guard` on. Named failure: the guard suite runs in no job.
        for p in ("hooks/test_guard.py", "hooks/mutate_guard.py"):
            with self.subTest(path=p):
                self.assertFlags(run([p]), want_true=["guard"])

    def test_a_merge_change_leaves_a_job_that_never_runs_merge_suites_off(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_false=["pointer_windows", "shell_macos"])

    def test_workflow_or_scope_script_change_runs_everything(self):
        for p in (".github/workflows/checks.yml", ".github/scripts/ci-scope.sh"):
            self.assertFlags(run([p]), want_true=ALL)

    def test_a_test_run_signing_helper_change_runs_everything(self):
        # Every suite loads the helper, so a change to any of its three twins runs every job.
        for p in ("lint/_test_git.py", "lint/_test_git.sh", "lint/_test_git.mjs"):
            with self.subTest(path=p):
                self.assertFlags(run([p]), want_true=ALL + DERIVED_FLAGS)

    def test_unmapped_path_runs_everything(self):
        self.assertFlags(run(["zz-unmapped/blob.bin"]), want_true=ALL)

    def test_unreadable_diff_runs_everything(self):
        bogus = "f" * 40
        self.assertFlags(run(["README.md"], base=bogus), want_true=ALL)
        self.assertFlags(run(["README.md"], base=""), want_true=ALL)

    def test_push_schedule_and_dispatch_run_everything_even_for_docs(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            self.assertFlags(run(["README.md"], event=ev), want_true=ALL)

    # Map gaps found in review: each path is read by a suite in another job.
    def test_merge_tool_change_turns_on_the_suites_that_load_it(self):
        self.assertFlags(run(["merge/merge.py"]), want_true=["checks_windows", "checks_macos", "guard", "checks_windows_merge"])

    def test_layout_change_turns_on_the_guard_and_merge_suites(self):
        for path in ("lint/layout.json", "lint/layout.py"):
            self.assertFlags(run([path]), want_true=["checks_windows", "checks_macos", "guard", "code", "checks_windows_merge"])

    def test_janitor_launcher_change_turns_on_the_install_suite(self):
        # `guard` too: the janitor launcher turns the guard suite on.
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["checks_windows", "shell_macos", "guard"])

    def test_windows_install_test_change_turns_on_the_windows_install_job(self):
        # The file is in the base, so an edit to it is no new file in a landed dir; the job that runs it must start.
        self.assertFlags(run(["hooks/test_install_windows.sh"], existing=["hooks/test_install_windows.sh"]),
                         want_true=["checks_windows", "code"])

    def test_silent_undo_checker_change_turns_on_the_merge_job(self):
        self.assertFlags(run(["lint/check_silent_undo.py"]), want_true=["checks_windows_merge"])

    def test_session_start_change_turns_on_the_unknown_read_contract_job(self):
        self.assertFlags(run(["hooks/session_start.sh"]), want_true=["checks_windows_rest"])

    def test_a_new_file_in_a_landed_dir_turns_on_the_install_suite(self):
        for p in ("agents/new.md", "skills/new/SKILL.md", "output-styles/new.md", "lint/new.py"):
            self.assertFlags(run([p]), want_true=["checks_windows", "shell_macos"])
        # Named failure: review
        # finding on #305. The guard suite reads this path; if `guard` stays off, cut F runs it in no job.
        self.assertFlags(run(["lint/zz_new.py"]), want_true=["guard"])

    def test_a_modified_md_under_skills_turns_on_nothing(self):
        self.assertFlags(run(["skills/old/SKILL.md"], existing=["skills/old/SKILL.md"]), want_false=ALL)

    def test_a_new_file_in_hooks_or_janitor_turns_on_the_install_suite(self):
        for p in ("hooks/new.py", "janitor/new.py"):
            self.assertFlags(run([p]), want_true=["checks_windows", "shell_macos"])

    def test_the_landed_dirs_come_from_landed_dirs_txt(self):
        # A made-up dir in the scratch repo's landed-dirs.txt: the script reads the file, it does not copy the list.
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up"]), want_true=["checks_windows", "shell_macos"])

    def test_an_empty_or_comment_only_landed_list_turns_everything_on(self):
        for landed in ([], ["# only a comment", ""]):
            self.assertFlags(run(["docs/new.md"], landed=landed), want_true=ALL)

    def test_a_trailing_slash_in_landed_dirs_is_read_as_the_dir(self):
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up/"]), want_true=["checks_windows", "shell_macos"])

    # Cut F: checks-windows-guard and checks-mutate-guard skip on the `guard` flag. The slice selector
    # (GUARD_TESTS) is read from hooks/test_guard.py, so an edit to that file must turn `guard` on,
    # or a pull request that changes the slice would run no guard job at all.
    # Control: a docs-only path must keep `guard` off, or the new rules over-trigger (false red).
    def test_a_docs_only_path_keeps_the_guard_flag_off(self):
        for p in ("README.md", "decisions/some-record.md"):
            self.assertFlags(run([p]), want_false=["guard"])

    # lint/guard_log_report.py imports hooks/guard_core.py at load, and decision_watch
    # reads guard.log through it at run time. So a change to it must select the same jobs as
    # lint/_transcript.py, the other module the decision watch loads (the rules at its line 36, 51).
    def test_guard_log_reader_change_selects_the_jobs_of_the_transcript_reader(self):
        reader = self.true_set(run(["lint/guard_log_report.py"]))
        self.assertEqual(reader, self.true_set(run(["lint/_transcript.py"])))
        self.assertTrue({"checks_windows_rest", "checks_macos", "code", "guard"} <= reader, reader)

    # Guard family: hooks/guard_<anything>.py is split out of hooks/guard.py. Each sibling must set
    # exactly the flags guard.py sets, as a new file and as an edit. Today the generic hooks/* rule
    # gives a new sibling no sweep flag, and an edited one no Windows or shell job.
    GUARD_SIBLINGS = ["hooks/guard_core.py", "hooks/guard_merge.py", "hooks/guard_rules.py"]

    def true_set(self, got):
        return {n for n in ALL if got[n] == "true"}

    def test_guard_sibling_new_file_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"])
        self.assertFlags(want, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep"],
                         want_false=["pointer_windows"])  # the merge flag is read by the closure case, not pinned here
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p]), want)

    def test_guard_sibling_edit_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"], existing=["hooks/guard.py"])
        self.assertFlags(want, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep"],
                         want_false=["shell_macos", "pointer_windows"])  # the merge flag is read by the closure case, not pinned here
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p], existing=[p]), want)

    def test_shared_names_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and config_watch.py import it, so the guard mutation tests must run on it.
        want = run(["hooks/guard.py"])
        self.assertEqual(run(["hooks/shared_names.py"]), want)
        self.assertEqual(run(["hooks/shared_names.py"], existing=["hooks/shared_names.py"]),
                         run(["hooks/guard.py"], existing=["hooks/guard.py"]))

    # Ruling (decision ci-scope-merge-closure): the merge flag covers every file in the closure merge/merge.py loads.
    # merge.py imports hooks/git_reads.py by path, so a change to it sets the merge flag. The guard and sweep flags stay as
    # guard.py's: guard_core.py and the janitor's sweep.py import it, so the guard and sweep suites run on it.
    def test_git_reads_change_sets_the_guard_flags_and_the_merge_flag(self):
        # Scope: hooks/test_guard.py is no load of merge.py, so its merge flag is off and the flag read below is git_reads' own.
        self.assertEqual(run(["hooks/test_guard.py"])["checks_windows_merge"], "false")
        for edit in (False, True):
            with self.subTest(edit=edit):
                got = run(["hooks/git_reads.py"], existing=["hooks/git_reads.py"] if edit else ())
                want = run(["hooks/guard.py"], existing=["hooks/guard.py"] if edit else ())
                self.assertEqual(got["checks_windows_merge"], "true",
                                 f"git_reads sets no merge flag, though merge.py imports it: {got}")
                # The other flags match guard.py's; the merge flag is compared in the closure case.
                self.assertEqual(dict(got, checks_windows_merge=want["checks_windows_merge"]), want, got)

    # Control: the guard test file keeps today's flags. A family rule must not catch it.
    def test_guard_test_file_keeps_its_current_flags(self):
        p = "hooks/guard_test_x.py"
        self.assertEqual(self.true_set(run([p])),
                         {"checks_windows", "checks_windows_rest", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows_rest", "checks_macos", "code", "guard"})

    # Control: the guard selector test keeps today's flags.
    def test_test_guard_keeps_its_current_flags(self):
        p = "hooks/test_guard.py"
        self.assertEqual(self.true_set(run([p])), {"checks_windows", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows", "checks_macos", "code", "guard"})

    # Mod and map-skill tests run as a step of the checks, checks-windows and checks-macos jobs, run only on the
    # `mods` flag. A job runs on its own flag, so a path that turns on `mods` must turn on checks_windows and
    # checks_macos too, or a mod-only pull request starts neither job and the step never runs there.
    # `mods` is in ALL, so every fail-safe case in the Scope class carries the mods check.
    MOD_JOBS = ["checks_windows", "checks_macos"]
    def test_a_mods_path_sets_the_mods_flag(self):
        for p in ("mods/plain-diff/check.mjs", "mods/session-board/session-board.test.mjs"):
            with self.subTest(path=p):
                self.assertEqual(run([p]).get("mods"), "true")
        self.assertEqual(run(["README.md", "mods/plain-diff/check.mjs"]).get("mods"), "true")

    def test_a_mods_only_diff_sets_the_mod_jobs_and_no_other_flag(self):
        got = run(["mods/plain-diff/check.mjs"])
        self.assertFlags(got, want_true=["mods"] + self.MOD_JOBS,
                         want_false=[n for n in ALL if n not in ["mods"] + self.MOD_JOBS])

    def test_a_docs_only_diff_leaves_the_mods_flag_off(self):
        self.assertEqual(run(["README.md", "decisions/some-record.md"]).get("mods"), "false")

    # mods/decision-watch/decision-watch.test.mjs imports lint/test_scanner_traps.mjs,
    # and the mod-tests.sh step runs that test. The lint/* rule sets `code` only, so a diff naming only the lint
    # file would skip its test.
    def test_a_scanner_trap_lint_change_sets_the_mods_flag(self):
        self.assertFlags(run(["lint/test_scanner_traps.mjs"]), want_true=["mods", "code"] + self.MOD_JOBS)

    # Each arm that turns `mods` on starts both mod jobs, as a new file and as an edit. An edit leaves every
    # other job flag off, so the set is exact. A new file under lint/ or skills/ is in a landed dir, which adds
    # shell_macos and guard by its own rule, so a new file is checked for the jobs it must not start.
    # `.gitignore` is an arm too: skills/plain-english-map/tests/typescript-home.test.mjs reads it, so a .gitignore-only
    # pull request must run the CI step. It keeps `code`, which its lint suites read.
    MOD_ARMS = ["mods/zz-new/a.mjs", "lint/test_scanner_traps.mjs", "skills/plain-english-map/README.md", ".gitignore"]

    def test_each_mods_arm_starts_the_windows_and_macos_jobs(self):
        for p in self.MOD_ARMS:
            with self.subTest(path=p, edit=True):
                code_arm = p.startswith("lint/") or p == ".gitignore"
                want = {"mods", "checks_windows", "checks_macos"} | ({"code"} if code_arm else set())
                self.assertEqual(self.true_set(run([p], existing=[p])), want,
                                 msg=f"{p}: the mods arm must start the CI step and both mod jobs, and keep code")
            with self.subTest(path=p, edit=False):
                self.assertFlags(run([p]), want_true=["mods"] + self.MOD_JOBS,
                                 want_false=["checks_windows_merge", "checks_windows_rest", "pointer_windows"])

    # Any path under the map skill turns `mods` on, .md files included, as a new file or an edit.
    # The checks job runs the skill's tests only when `mods` is on. Those tests read SKILL.md and
    # .md fixtures, so a .md path with no flag would skip them. The skill and its tests live in
    # this repo (ruling `map-skill-lives-here`: the tests run in the checks workflow).
    MAP_SKILL = "skills/plain-english-map/"

    def test_a_map_skill_md_change_turns_on_mods(self):
        for p in (self.MAP_SKILL + "SKILL.md", self.MAP_SKILL + "tests/fixture/docs/map/core.md",
                  self.MAP_SKILL + "tests/fixture/docs/map/traces/home.md"):
            for existing in ((), (p,)):
                with self.subTest(path=p, edit=bool(existing)):
                    got = run([p], existing=existing)
                    self.assertFlags(got, want_true=["mods"] + self.MOD_JOBS)

    # Control: the fix must not narrow the skill's non-.md paths. They stay on the fail-safe arm.
    def test_a_map_skill_script_change_still_turns_everything_on(self):
        p = self.MAP_SKILL + "scripts/map-check.mjs"
        for existing in ((), (p,)):
            with self.subTest(edit=bool(existing)):
                self.assertFlags(run([p], existing=existing), want_true=ALL)

    # Control: another skill's .md keeps today's flags. The new rule must name the map skill only.
    def test_another_skills_md_keeps_its_current_flags(self):
        p = "skills/ci-hygiene/SKILL.md"
        self.assertFlags(run([p], existing=[p]), want_false=ALL)
        self.assertEqual(self.true_set(run([p])), {"checks_windows", "shell_macos", "code", "guard"})

    # The rm shim suite also runs in checks-macos: BSD rm and the /var symlink change what the shim reads,
    # and a Linux pass proves neither. ci-scope.sh maps bin/rm and the suite to that job ahead of
    # the lint/* rule, which sets `code` only, so a diff that names the suite alone still reaches it.
    def test_an_rm_shim_suite_change_turns_on_the_macos_job(self):
        self.assertFlags(run(["lint/test_rm_shim.py"], existing=["lint/test_rm_shim.py"]), want_true=["checks_macos", "code"])

    # bin/ios-ship and its suite run in the shell-macos job only (macOS /bin/bash 3.2). An edit to either turns on that
    # job and `code`, and no other flag. Without the arm, an unmapped path turns every flag on, so this goes red.
    # Only the edit is exact: a new file under bin/ also sets the install-suite flags (the landed-dirs rule).
    def test_ios_ship_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/ios-ship", "lint/test_ios_ship.sh"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/sim-test and its suite run in the shell-macos job only, like bin/ios-ship. The suite runs the real bin/sim-lease
    # beside the script. bin/sim-lease has its own case below, since merge.py loads it.
    def test_sim_test_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/sim-test", "lint/test_sim_test.sh"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/sim-lease is in merge.py's load closure (decision ci-scope-merge-closure: the
    # merge flag covers that closure), so an edit to it also sets checks_windows_merge.
    def test_sim_lease_edit_turns_on_the_macos_shell_job_and_the_merge_check(self):
        p = "bin/sim-lease"
        self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code", "checks_windows_merge"})

    # bin/shoot's suite installs a browser, so its own paths and the browser installers turn `shoot` on. An edit sets
    # `code` and `shoot` and no other flag in true_set (checks_guard is outside ALL; the cases below pin it).
    # An unrelated code change leaves `shoot` off.
    def test_shoot_edit_turns_on_only_the_shoot_suite(self):
        for p in ("bin/shoot", "lint/test_shoot.mjs", "testing/skip-locally-fail-in-ci.mjs", ".github/shoot/package-lock.json",
                  "actions/playwright-setup/action.yml"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"code", "shoot"})
        self.assertFlags(run(["lint/test_verdict.py"], existing=["lint/test_verdict.py"]), want_false=["shoot"])

    # checks-guard and checks-shoot both install actions/playwright-setup, and checks-guard gates on checks_guard
    # alone (checks.yml). An edit to the action must set checks_guard directly, with `shoot` for checks-shoot.
    # Named failure: the action arm sets code and shoot only, so checks-guard skips its install and guard suite.
    def test_playwright_action_edit_turns_on_the_checks_guard_job(self):
        p = "actions/playwright-setup/action.yml"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # Control: a bin/shoot edit keeps checks_guard off, so the action's arm must not widen to bin/shoot.
    def test_shoot_edit_keeps_checks_guard_off(self):
        p = "bin/shoot"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "false", f"checks_guard: {got}")

    # checks-guard installs the Playwright that .github/shoot pins, so a change to that pin must start the job.
    # Named failure: the pin path sets code and shoot only, and checks-guard installs the old browser.
    def test_shoot_package_lock_edit_turns_on_the_checks_guard_job(self):
        p = ".github/shoot/package-lock.json"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # pin.sh is the install script checks-guard runs from actions/playwright-setup. Named failure: an edit that
    # starts checks-shoot alone leaves the checks-guard install on the old script.
    def test_playwright_pin_script_edit_turns_on_the_checks_guard_job(self):
        p = "actions/playwright-setup/pin.sh"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # A .md edit under the action is docs, so neither job starts. Named failure: without the *.md carve-out, the
    # action arm starts checks-shoot and checks-guard for a README edit.
    def test_playwright_readme_edit_turns_on_no_job(self):
        p = "actions/playwright-setup/README.md"
        got = run([p], existing=[p])
        self.assertFlags(got, want_false=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "false", f"checks_guard: {got}")


# The mod phase must run each mods check script (mods/**/check.mjs), not only *.test.mjs. The script cds to its own
# root, so each case runs a copy of it inside a scratch tree under the run folder.
@unittest.skipUnless(BASH, "bash not on PATH")
class ModTestsRunsEveryCheck(unittest.TestCase):
    SENTINEL = "zz-mod-check-ran"
    # Candidate names for the passing test file. find lists by the filesystem's directory order, which depends on
    # the names, so a case tries these until one lists check.mjs where it needs it.
    TEST_NAMES = ["plain-diff.test.mjs"] + [f"{c}.test.mjs" for c in "abcdefghijklmnop"]

    @classmethod
    def setUpClass(cls):
        cls.run_dir = _test_temp.run_folder()

    @classmethod
    def tearDownClass(cls):
        tracked_tree.rm_tree(cls.run_dir)

    def setUp(self):
        # In CI a missing node is a red run, never a skip: the mod phase cannot run without it.
        if shutil.which("node") is None:
            if os.environ.get("CI"):
                self.fail("node is not on PATH in CI, so the mod phase cannot run")
            self.skipTest("node not on PATH")

    @staticmethod
    def node_script(exit_code, say=None):
        """A node file that prints `say` to stderr, then exits with `exit_code`."""
        printed = f"console.error({say!r});\n" if say else ""
        return printed + f"process.exit({exit_code});\n"

    def make_tree(self, name, test=None, check=None, test_name="plain-diff.test.mjs"):
        """A scratch tree: mod-tests.sh, one mod test file (passing by default), and mods/plain-diff/check.mjs if `check` is given."""
        tree = os.path.join(self.run_dir, name)
        tracked_tree.copy_tracked(tree, ".github/scripts")
        plain = os.path.join(tree, "mods", "plain-diff")
        os.makedirs(plain)
        with open(os.path.join(plain, test_name), "w") as f:
            f.write(test or self.node_script(0))
        if check is not None:
            with open(os.path.join(plain, "check.mjs"), "w") as f:
                f.write(check)
        return tree

    def run_phase(self, tree):
        """The mods phase of the copied script, run from `tree`, which holds every file the phase can see."""
        return subprocess.run([BASH, os.path.join(tree, ".github", "scripts", "mod-tests.sh"), "mods"],
                              cwd=tree, capture_output=True, text=True)

    def listing(self, tree):
        """The .mjs files under mods/ in the order find lists them. The mod phase lists a subset of these in the same order."""
        r = subprocess.run(["find", "mods", "-type", "f", "-name", "*.mjs"], cwd=tree, capture_output=True, text=True, check=True)
        return r.stdout.split()

    def tree_listing_check(self, name, check_last):
        """A scratch tree with one passing test file and the red check, listed last (check_last) or first."""
        for i, test_name in enumerate(self.TEST_NAMES):
            tree = self.make_tree(f"{name}-{i}", check=self.node_script(1, self.SENTINEL), test_name=test_name)
            listed = self.listing(tree)
            if len(listed) == 2 and listed[-1].endswith("check.mjs") == check_last:
                return tree
        self.fail(f"no candidate test name lists check.mjs {'last' if check_last else 'first'} on this filesystem")

    # Scope first: the phase ran at all. The asserts after it say what the phase did with the check file. Both orders run,
    # because a phase that takes only the last file's exit code hides a red check listed before a passing file.
    def test_a_red_check_script_fails_the_mod_phase_in_either_order(self):
        for check_last in (True, False):
            with self.subTest(check_last=check_last):
                r = self.run_phase(self.tree_listing_check(f"red-check-{check_last}", check_last))
                self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
                # Named failure: check.mjs never runs, because the phase globs *.test.mjs only.
                self.assertIn(self.SENTINEL, r.stdout + r.stderr, "mods/plain-diff/check.mjs did not run: the mod phase skips it")
                self.assertNotEqual(r.returncode, 0, "mods/plain-diff/check.mjs failed, and the mod phase still exited 0")

    # Green control: a passing check file leaves the phase green, so the fix cannot turn it red.
    def test_a_green_check_script_leaves_the_mod_phase_green(self):
        r = self.run_phase(self.make_tree("green-check", check=self.node_script(0, self.SENTINEL)))
        self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
        self.assertEqual(r.returncode, 0, f"a passing mods/plain-diff/check.mjs turned the mod phase red:\n{r.stdout}{r.stderr}")

    # Green control: a red *.test.mjs already fails the phase.
    def test_a_red_test_file_fails_the_mod_phase(self):
        r = self.run_phase(self.make_tree("red-test", test=self.node_script(1)))
        self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
        self.assertNotEqual(r.returncode, 0, "a red *.test.mjs passed the mod phase")


@unittest.skipUnless(BASH, "bash not on PATH")
class MutationReport(unittest.TestCase):
    """The mutation_report output: on a pull request only from a `batch-` branch, and on every other event."""

    # Named failure: the mutation-report job starts on every pull request, or on none, not only the batch ones.
    def test_only_a_batch_pull_request_turns_it_on_and_a_push_always_does(self):
        feature = run(["README.md"], head_ref="feature-x")
        self.assertIn("mutation_report", feature, feature)
        self.assertEqual(feature["mutation_report"], "false", f"a pull request from feature-x: {feature}")
        batch = run(["README.md"], head_ref="batch-11")
        self.assertEqual(batch["mutation_report"], "true", f"a pull request from batch-11: {batch}")
        push = run(["README.md"], event="push")
        self.assertEqual(push["mutation_report"], "true", f"a push: {push}")


if __name__ == "__main__":
    unittest.main()
