#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/ci-scope.sh).

Each case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT and BASE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
CI_SCOPE overrides the script path (for a successor). Needs bash on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per check job except the lint job `checks`: checks_windows, checks_windows_merge,
             checks_windows_rest, checks_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep, mods, shoot (the suite flags; shoot turns on the whole checks-shoot job)
  GUARD_SPLIT guard_windows_full, guard_windows_slice (the Windows guard split; GuardWindowsSplit pins them)
  MERGE_SPLIT merge_windows_full, merge_windows_slice (the Windows merge split; MergeWindowsSplit pins them)
  LIST_SPLIT guard_windows_shards, merge_windows_shards (the JSON leg lists each sharded suite's matrix reads;
             WindowsShardLists pins them, and lint/test_windows_split.py holds the rule they must meet)

Run with:  python3 lint/test_ci_scope.py -v
"""
import ast
import functools
import json
import os
import posixpath
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from unittest import mock

import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder (lint/_test_temp.py)
import test_windows_split as windows_split  # noqa: E402  the one home of the shard list rule and the expected lists
RUN_FOLDER = _test_temp.run_folder()
SCRIPT = os.environ.get("CI_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")
REPO = os.path.abspath(os.path.join(HERE, ".."))
REPO_REAL = os.path.realpath(REPO)  # the root the derivation reads paths against: __file__ resolves to this too
JOB_FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep", "mods", "shoot"]
# Flags derived from others, kept out of JOB_FLAGS so the exact-set cases below stay about the base flags:
# checks_windows_sweep is set with checks_windows_rest. checks_guard is set when both `code` and `guard` are set, or
# directly by the arm for actions/playwright-setup and .github/shoot (the paths checks-guard installs from).
DERIVED_FLAGS = ["checks_windows_sweep", "checks_guard"]
ALL = JOB_FLAGS + STEP_FLAGS
# The Windows guard split. Kept out of ALL and DERIVED_FLAGS: those lists are checked in every case, and the cases that
# predate the split would then fail on the old script for a missing output. GuardWindowsSplit pins both names.
GUARD_FULL = "guard_windows_full"
GUARD_SLICE = "guard_windows_slice"
GUARD_SPLIT = (GUARD_FULL, GUARD_SLICE)
# The Windows merge split, the same shape: the full shards (the matrix legs of checks-windows-merge) and the slice.
MERGE_FULL = "merge_windows_full"
MERGE_SLICE = "merge_windows_slice"
MERGE_SPLIT = (MERGE_FULL, MERGE_SLICE)
# The leg lists each sharded suite's matrix reads: ci-scope.sh writes them, and their names are one home in test_windows_split.py.
GUARD_LIST = windows_split.MATRIX_OUT[windows_split.GUARD_JOB]
MERGE_LIST = windows_split.MATRIX_OUT[windows_split.MERGE_JOB]
LIST_SPLIT = (GUARD_LIST, MERGE_LIST)
GUARD_LEGS, MERGE_LEGS, SLICE_ONLY = windows_split.GUARD_LEGS, windows_split.MERGE_LEGS, windows_split.SLICE_ONLY
BASH = shutil.which("bash")


def pre_split(got):
    """The outputs the script wrote before the splits: every output but GUARD_SPLIT, MERGE_SPLIT and LIST_SPLIT."""
    return {n: v for n, v in got.items() if n not in GUARD_SPLIT + MERGE_SPLIT + LIST_SPLIT}


def family_files():
    """hooks/<module>.py for each module in hooks/guard.py's _FAMILY_MODULES. The tuple is read from the file's syntax tree,
    so guard.py is not imported (its load starts the guard's own reads)."""
    with open(os.path.join(HERE, "..", "hooks", "guard.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_FAMILY_MODULES" for t in node.targets):
            return [f"hooks/{elt.value}.py" for elt in node.value.elts]
    raise AssertionError("hooks/guard.py has no _FAMILY_MODULES tuple")


# The files the guard suite loads, derived from the code of GUARD_SEEDS, not listed by hand. A file is in the closure when
# a file in it imports it, or loads it by a path (_refs reads each file's syntax tree):
#   import x, from x import y, importlib.import_module("x"): x is the basename of a repo .py file;
#   a run-time root that is a folder of the repo (_path_of reads __file__ and the os.path or pathlib calls on it, .parent,
#   and a module-level name bound once to one of these), then its literals, as os.path.join(root, "lit") or a `/` chain,
#   root / "a" / "b": the file at that folder plus the literals (_repo_load);
#   os.path.join whose literal segments have a `..`, or whose run-time root is the file's own folder (__file__, _HERE):
#     the file of that name in that folder;
#   os.path.join of literal segments with no run-time root: a repo path, from the repo root;
#   a spec_from_file_location or SourceFileLoader path: its Name read through to the path assigned to it.
# Not followed: a product module's join with a run-time root and several literals, when its path is a repo file: it is named
# in LOAD_EXCEPTIONS. A test module's such join is read when its root is the repo, and is not named otherwise: its root is a
# fixture path in a temp folder. A run-time root that is not a folder of the repo is not read. A loader path with no literal
# repo file is named. A string or a comment holds no load: the syntax tree is read.
GUARD_SEEDS = ("hooks/guard.py", "hooks/test_guard.py")
# The merge suite's closure has one seed, its own file. merge/test_merge.py imports decision_watch, which imports guard, so the
# merge closure holds the guard closure's files too (closure_of reads them from the code, once per seed set).
MERGE_SEEDS = ("merge/test_merge.py",)
# Each load guard_closure finds but does not follow, as "file:scope:source": why. The scope is the enclosing function (or
# <module>) and the source is the load's text as ast.unparse writes it, so a line added above a load keeps its entry.
# An entry names a load of either closure (the guard's or the merge suite's), so the check reads the union of both.
LOAD_EXCEPTIONS = {
    "hooks/config_watch.py:_load_guard:path": "GUARD_UNDER_TEST, a test override of guard.py's path, as decision_watch's (guard.py is in the closure by import)",
    "hooks/decision_watch.py:<module>:_GUARD_PATH": "GUARD_UNDER_TEST, a test override of guard.py's path (guard.py is in the closure by import)",
    "hooks/guard_merge.py:merge_module:path": "the merge tool at a clone root, MERGE_TOOL_REL (guard_merge.py): merge/merge.py is in the closure",
    "hooks/guard_merge.py:_merge_config_at:os.path.join(root, '.github', 'stamp.json')": "a stamp read from a clone root found by walking up: a fixture root in the suite, the checkout in a real run",
    "hooks/precompact_handoff.py:prompt_path:os.path.join(config_dir(), 'hooks', 'precompact_handoff_prompt.md')": "the installed prompt under config_dir(), the installer's copy, not the repo's file",
    "hooks/test_guard.py:_load_git_reads:os.path.join(os.path.dirname(GUARD), 'git_reads.py')": "a sibling of GUARD, hooks/ by default: git_reads.py is in the closure by import",
    "hooks/test_guard.py:rm_var_taint_reader_case:path": "a sibling of GUARD: guard_rm_var.py is in the closure by import",
    "hooks/test_guard.py:_load_own_session:os.path.join(os.path.dirname(GUARD), 'own_session.py')": "a sibling of GUARD: own_session.py is in the closure by import",
    "hooks/test_guard.py:_load_guard_module:GUARD": "GUARD itself: guard.py, or the GUARD_UNDER_TEST copy, which is in the closure by import",
    "hooks/test_guard.py:_hu_reread:READ_CHECK": "READ_CHECK: reread_check.py by default, which is in the closure by import",
    "hooks/test_guard.py:_shared_names_under_test:os.path.join(os.path.dirname(GUARD), 'shared_names.py')": "a sibling of GUARD: shared_names.py is in the closure by import",
    "lint/check_silent_undo.py:generated_page:os.path.join(base, 'lint', 'hook_catalog.py')": "a checkout's hook_catalog.py, the oracle of the silent-undo check: in the closure by merge.py's import",
    "lint/rule_audit.py:<module>:os.path.join(ROOT, 'lint', 'rule_mechanisms.json')": "ROOT, the repo root by definition, a fixture root in the suite: lint/rule_mechanisms.json is not in the closure",
    "lint/rule_audit.py:<module>:os.path.join(ROOT, '.github', 'workflows', 'checks.yml')": "ROOT: .github/workflows/checks.yml, already a fail-safe path in ci-scope.sh",
    "lint/rule_audit.py:emitted_rule_ids:os.path.join(root, 'hooks', 'config_watch.py')": "ROOT: hooks/config_watch.py is not in the closure",
    "merge/merge.py:hit_suites:os.path.join(root, '.github', 'workflows', 'checks.yml')": "the checkout's own workflow, .github/workflows/checks.yml, already a fail-safe path in ci-scope.sh",
    "skills/waiting-page/stale_pages.py:pointer_checkout:os.path.join(os.path.expanduser('~'), '.claude', 'CLAUDE.md')": "the user's ~/.claude/CLAUDE.md, not this repo's .claude/CLAUDE.md",
}
_CLOSURE = {}  # closure_of's cache: seed tuple -> (files, unfollowed)


def _repo_files():
    """Every file under the repo, as '/' paths. Skips .git, build folders, and .claude/worktrees (each worktree copies the repo)."""
    return list(_files_under(REPO))


@functools.lru_cache(maxsize=None)
def _files_under(root):
    """The files under `root`, walked once per root. A tuple, so no caller can change the cached list."""
    out = []
    worktrees = os.path.join(root, ".claude", "worktrees")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")
                       and os.path.join(dirpath, d) != worktrees]
        out += [os.path.relpath(os.path.join(dirpath, n), root).replace(os.sep, "/") for n in filenames if n != ".git"]
    return tuple(out)


def _callee(call):
    """The dotted name a call is made through, such as `importlib.import_module`; '' when it is not a plain name."""
    parts, f = [], call.func
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if not isinstance(f, ast.Name):
        return ""
    return ".".join([f.id] + parts[::-1])


def _join_segments(call):
    """The literal segments of an os.path.join call after its last run-time argument, split on '/', and whether a
    run-time argument came before them (a run-time root)."""
    segs, lead = [], False
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            segs.append(a.value)
        else:
            segs, lead = [], True
    return [p for s in segs for p in s.split("/") if p], lead


def _is_str(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_path_expr(node):
    """An os.path.join call, or a `/` with a string literal on its right (pathlib): a path built from parts."""
    return (isinstance(node, ast.Call) and _callee(node) == "os.path.join") or (
        isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and _is_str(node.right))


def _loader_joins(arg, call, tree, parents, bound):
    """The path expressions a loader's path argument can hold: the argument itself, or the ones assigned to its Name in
    the enclosing function (the module when there is none), or the module-level value of the Name."""
    if _is_path_expr(arg):
        return [arg]
    if not isinstance(arg, ast.Name):
        return []
    scope, node = tree, call
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = node
            break
    found = [n.value for n in ast.walk(scope) if isinstance(n, ast.Assign) and _is_path_expr(n.value)
             and any(isinstance(t, ast.Name) and t.id == arg.id for t in n.targets)]
    if not found and _is_path_expr(bound.get(arg.id)):
        found = [bound[arg.id]]
    return found


def _uses_file(node):
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node))


@functools.lru_cache(maxsize=None)
def _bound_names(tree):
    """The module-level names bound once in the file, with their values. A name bound anywhere else in the file (a
    parameter, a local, an import, a second assignment) is not read through: its value is not the module's."""
    stores = Counter()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            stores[n.id] += 1
        elif isinstance(n, ast.arg):
            stores[n.arg] += 1
        elif isinstance(n, ast.alias):
            stores[(n.asname or n.name).split(".")[0]] += 1
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stores[n.name] += 1
    return {st.targets[0].id: st.value for st in tree.body
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
            and stores[st.targets[0].id] == 1}


def _path_of(node, f, bound, depth=0):
    """The absolute path a path expression reads to, or None. Only these are read: __file__ (the loading file), the os.path
    functions dirname, abspath, realpath, normpath and join, pathlib.Path(...), .resolve(), .parent, .parents[N], a `/` with a
    literal, and a module-level name bound once to one of these. Nothing is called beyond them: no environment, no read."""
    if depth > 20:
        return None
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return os.path.realpath(os.path.join(REPO_REAL, f))
        return _path_of(bound[node.id], f, bound, depth + 1) if node.id in bound else None
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        p = _path_of(node.value, f, bound, depth + 1)
        return None if p is None else os.path.dirname(p)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents" \
            and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
        p = _path_of(node.value.value, f, bound, depth + 1)
        if p is None:
            return None
        for _ in range(node.slice.value + 1):  # parents[N] is N + 1 dirnames up
            p = os.path.dirname(p)
        return p
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and _is_str(node.right):
        base = _path_of(node.left, f, bound, depth + 1)
        return None if base is None else os.path.join(base, node.right.value)
    if not isinstance(node, ast.Call):
        return None
    name = _callee(node)
    if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve" and not node.args:
        p = _path_of(node.func.value, f, bound, depth + 1)
        return None if p is None else os.path.realpath(p)
    if name in ("os.path.dirname", "os.path.abspath", "os.path.realpath", "os.path.normpath", "pathlib.Path", "Path") \
            and len(node.args) == 1:
        p = _path_of(node.args[0], f, bound, depth + 1)
        fn = {"os.path.dirname": os.path.dirname, "os.path.abspath": os.path.abspath, "os.path.realpath": os.path.realpath,
              "os.path.normpath": os.path.normpath}.get(name, os.path.normpath)
        return None if p is None else fn(p)
    if name == "os.path.join" and node.args and all(_is_str(a) for a in node.args[1:]):
        base = _path_of(node.args[0], f, bound, depth + 1)
        return None if base is None else os.path.join(base, *(a.value for a in node.args[1:]))
    return None


def _is_test(f):
    return posixpath.basename(f).startswith("test_")


def _div_chain(expr):
    """The root of a pathlib `/` chain and its literal segments in order: root / "a" / "b" -> (root, ["a", "b"]). The chain
    ends at the first `/` whose right side is not a literal."""
    lits = []
    while isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div) and _is_str(expr.right):
        lits.insert(0, expr.right.value)
        expr = expr.left
    return expr, lits


def _repo_load(f, expr, tracked, bound):
    """The repo file a load reads when a run-time root that is a folder of the repo comes before its literals, as
    os.path.join(root, "lit") or a `/` chain, root / "a" / "b": the file at root plus the literals, when it is a repo file.
    None otherwise. A product module's join reads one literal; a test module's join reads any number, since its REPO is the
    real checkout. A `/` chain reads all its literals. A literal root is not read here."""
    if isinstance(expr, ast.Call) and _callee(expr) == "os.path.join" and len(expr.args) >= 2 \
            and all(_is_str(a) for a in expr.args[1:]) and (_is_test(f) or len(expr.args) == 2):
        root, lits = expr.args[0], [a.value for a in expr.args[1:]]
    elif isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div) and _is_str(expr.right):
        root, lits = _div_chain(expr)
    else:
        return None
    if _is_str(root):
        return None
    base = _path_of(root, f, bound)
    if base is None:
        return None
    try:
        rel = os.path.relpath(base, REPO_REAL).replace(os.sep, "/")
    except ValueError:  # another drive on Windows: not in the repo
        return None
    c = posixpath.normpath(posixpath.join(rel, *lits))
    return c if c in tracked else None


def _join_file(f, call, tracked, own_names, bound):
    """-> (path, kind) for a path expression: kind 'repo' when _repo_load reads it, else for an os.path.join: kind 'dir'
    when the path is read from the loading file's folder (a `..` segment, or a run-time root that is that folder: an
    expression built from __file__, or a module-level Name in own_names bound to one, such as guard.py's _HERE), 'root'
    when it is a repo path from the repo root with no run-time root, 'run-time' when a run-time root comes before a repo
    path (a checkout or a fixture), or (None, None)."""
    c = _repo_load(f, call, tracked, bound)
    if c:
        return c, "repo"
    if not (isinstance(call, ast.Call) and _callee(call) == "os.path.join"):
        return None, None
    segs, lead = _join_segments(call)
    if not segs:
        return None, None
    first = call.args[0]
    own = _uses_file(first) or (isinstance(first, ast.Name) and first.id in own_names)
    if ".." in segs or (lead and own):
        c = posixpath.normpath(posixpath.join(posixpath.dirname(f), *segs))
        if c in tracked:
            return c, "dir"
    if len(segs) >= 2:
        c = posixpath.normpath("/".join(segs))
        if c in tracked:
            return c, "run-time" if lead else "root"
    return None, None


def _keyed(named, parents):
    """-> [(key, what)] for the loads the derivation does not follow, in source order. A key, after its file, is the scope
    the load sits in (its classes and functions, qualified: Class.method, or <module>) and the load's source as ast.unparse
    writes it. A repeat of one key in the file gets #N, N counting from 2, so no two keys are equal. Neither holds a line."""
    seen, out = Counter(), []
    for node, what in sorted(named, key=lambda nw: (nw[0].lineno, nw[0].col_offset)):
        names, p = [], node
        while p in parents:
            p = parents[p]
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(p.name)
        base = f"{'.'.join(reversed(names)) or '<module>'}:{ast.unparse(node)}"
        seen[base] += 1
        out.append((base if seen[base] == 1 else f"{base}#{seen[base]}", what))
    return out


def _refs(f, tree, tracked):
    """What one repo file loads, from its syntax tree: (module names it imports, repo files it loads by path, loader
    targets, loads it does not follow as (key, what)). Cached per (file, tree, tracked set)."""
    return _refs_of(f, tree, frozenset(tracked))


@functools.lru_cache(maxsize=None)
def _refs_of(f, tree, tracked):
    parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    own_names = {t.id for st in tree.body if isinstance(st, ast.Assign) and _uses_file(st.value)
                 for t in st.targets if isinstance(t, ast.Name)}
    bound = _bound_names(tree)
    test = _is_test(f)
    modules, paths, loads, unfollowed = set(), set(), set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            name = _callee(node)
            if name == "importlib.import_module":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    modules.add(node.args[0].value.split(".")[0])
                else:
                    unfollowed.append((node, "importlib.import_module of a name built at run time"))
            elif name == "os.path.join":
                c, kind = _join_file(f, node, tracked, own_names, bound)
                if kind == "run-time":
                    if not test:  # a test's join under a run-time root is a fixture path, not a repo load
                        unfollowed.append((node, f"os.path.join with a run-time root, then {c}"))
                elif c:
                    paths.add(c)
            elif name.endswith("spec_from_file_location") or name.endswith("SourceFileLoader"):
                arg = node.args[1] if len(node.args) > 1 else None
                hits, named = [], False
                for j in _loader_joins(arg, node, tree, parents, bound):
                    c, kind = _join_file(f, j, tracked, own_names, bound)
                    if kind == "run-time":
                        named = True
                        unfollowed.append((j, f"a loader path with a run-time root, then {c}"))
                    elif c:
                        hits.append(c)
                loads.update(hits)
                if not hits and not named:
                    unfollowed.append((arg if arg is not None else node, "a loader path with no literal repo file"))
        elif isinstance(node, ast.BinOp):  # a pathlib `/` load, read wherever it is written
            c = _repo_load(f, node, tracked, bound)
            if c:
                paths.add(c)
    return modules, paths, loads, _keyed(unfollowed, parents)


def closure_of(seeds):
    """-> (files, unfollowed) for the seeds: the repo files the suite they start loads, sorted, and the loads not followed, as
    (file, key, what). Read from the code of the seeds, once per run and per seed set."""
    key = tuple(seeds)
    if key not in _CLOSURE:
        tracked = set(_repo_files())
        by_name = {}
        for p in tracked:
            if p.endswith(".py"):
                by_name.setdefault(posixpath.basename(p)[:-3], []).append(p)
        files, unfollowed, parsed = set(), [], set()
        todo = [(s, True) for s in seeds]
        while todo:
            f, is_python = todo.pop()
            if f not in tracked:
                raise AssertionError(f"{f} is a seed or a load target, and the repo does not have it")
            files.add(f)
            if f in parsed or not is_python:
                continue
            parsed.add(f)
            modules, paths, loads, here = _refs(f, _parse(f, source_of(f)), tracked)
            todo += [(c, True) for m in modules for c in by_name.get(m, [])]
            todo += [(c, c.endswith(".py")) for c in paths]
            todo += [(c, True) for c in loads]
            unfollowed += [(f, key_, what) for key_, what in here]
        _CLOSURE[key] = (sorted(files), sorted(unfollowed))
    return _CLOSURE[key]


def guard_closure():
    """The guard suite's closure: closure_of(GUARD_SEEDS)."""
    return closure_of(GUARD_SEEDS)


def merge_closure():
    """The merge suite's closure: closure_of(MERGE_SEEDS). The same derivation as the guard's, with its root at merge/test_merge.py."""
    return closure_of(MERGE_SEEDS)


@functools.lru_cache(maxsize=None)
def _parse(f, src):
    """The syntax tree of one file's source, parsed once per (file, source): the closure and the cases read the same text."""
    return ast.parse(src, filename=f)


def named_keys(f, src, tracked):
    """The LOAD_EXCEPTIONS keys of the loads one file's source names but does not follow, read from the source text."""
    return [f"{f}:{k}" for k, _ in _refs(f, _parse(f, src), tracked)[3]]


def exceptions_of(f):
    """The LOAD_EXCEPTIONS keys of one file, sorted."""
    return sorted(k for k in LOAD_EXCEPTIONS if k.split(":")[0] == f)


@functools.lru_cache(maxsize=None)
def source_of(f):
    with open(os.path.join(REPO, f), encoding="utf-8") as handle:
        return handle.read()


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
        lines = open(out).read().splitlines()  # one name=value line per output; a value may hold spaces (a JSON list)
        os.remove(out)
        return dict(l.split("=", 1) for l in lines if l)


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
        # README.md is not here: the merge suite reads it (LockProseStatesTheCode), so it is in the merge closure and turns the
        # merge job on (MergeClosure). A docs file outside every closure keeps every job off.
        got = run(["docs/some-record.md", "decisions/some-record.md"])
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
    # The siblings compare the outputs that predate the guard split. Their split flags are not decided here: guard_core.py is
    # shared code, not a rule family (hooks/guard.py _FAMILY_MODULES), and guard_rules.py is not a file yet. GuardWindowsSplit
    # pins the split flags of the family modules.
    GUARD_SIBLINGS = ["hooks/guard_core.py", "hooks/guard_merge.py", "hooks/guard_rules.py"]

    def true_set(self, got):
        return {n for n in ALL if got[n] == "true"}

    def test_guard_sibling_new_file_sets_the_same_flags_as_guard_py(self):
        # checks_windows_merge is on: the guard closure is in the merge closure (MergeClosure), so the merge job starts too.
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep",
                                         "checks_windows_merge"],
                         want_false=["pointer_windows"])
        want = pre_split(got)
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(pre_split(run([p])), want)

    def test_guard_sibling_edit_sets_the_same_flags_as_guard_py(self):
        got = run(["hooks/guard.py"], existing=["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep",
                                         "checks_windows_merge"],
                         want_false=["shell_macos", "pointer_windows"])
        want = pre_split(got)
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(pre_split(run([p], existing=[p])), want)

    def test_shared_names_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and config_watch.py import it, so the guard mutation tests must run on it.
        want = pre_split(run(["hooks/guard.py"]))
        self.assertEqual(pre_split(run(["hooks/shared_names.py"])), want)
        self.assertEqual(pre_split(run(["hooks/shared_names.py"], existing=["hooks/shared_names.py"])),
                         pre_split(run(["hooks/guard.py"], existing=["hooks/guard.py"])))

    def test_git_reads_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and the janitor's sweep.py and session_end_sweep.py import it, so the guard
        # and sweep mutation tests must run on it.
        want = pre_split(run(["hooks/guard.py"]))
        self.assertEqual(pre_split(run(["hooks/git_reads.py"])), want)
        self.assertEqual(pre_split(run(["hooks/git_reads.py"], existing=["hooks/git_reads.py"])),
                         pre_split(run(["hooks/guard.py"], existing=["hooks/guard.py"])))

    # Control: the guard test file keeps today's flags. A family rule must not catch it.
    def test_guard_test_file_keeps_its_current_flags(self):
        p = "hooks/guard_test_x.py"
        self.assertEqual(self.true_set(run([p])),
                         {"checks_windows", "checks_windows_rest", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows_rest", "checks_macos", "code", "guard"})

    # Control: the guard selector test keeps its flags. Its merge job is on too: the test file is in the merge closure (MergeClosure).
    def test_test_guard_keeps_its_current_flags(self):
        p = "hooks/test_guard.py"
        self.assertEqual(self.true_set(run([p])),
                         {"checks_windows", "checks_macos", "shell_macos", "code", "guard", "checks_windows_merge"})
        self.assertEqual(self.true_set(run([p], existing=[p])),
                         {"checks_windows", "checks_macos", "code", "guard", "checks_windows_merge"})

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
    MOD_ARMS = ["mods/zz-new/a.mjs", "lint/test_scanner_traps.mjs", "skills/plain-english-map/README.md"]

    def test_each_mods_arm_starts_the_windows_and_macos_jobs(self):
        for p in self.MOD_ARMS:
            with self.subTest(path=p, edit=True):
                want = {"mods", "checks_windows", "checks_macos"} | ({"code"} if p.startswith("lint/") else set())
                self.assertEqual(self.true_set(run([p], existing=[p])), want)
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

    # bin/sim-test and bin/sim-lease are loaded by the guard suite (GuardClosure derives both), so an edit to either also
    # turns on `guard`, the full Windows guard shards and the checks-guard job. The suite script, lint/test_sim_test.sh,
    # is not loaded by it: its edit turns on the macOS shell job and nothing else.
    def test_sim_test_and_sim_lease_edit_turns_on_the_guard_suite_and_the_suite_script_does_not(self):
        for p in ("bin/sim-test", "bin/sim-lease"):
            with self.subTest(path=p):
                got = run([p], existing=[p])
                self.assertEqual(self.true_set(got), {"shell_macos", "code", "guard", "checks_windows_merge"}, f"{p}: {got}")
                self.assertEqual(got[GUARD_FULL], "true", f"{GUARD_FULL} for {p}: {got}")
                self.assertEqual(got["checks_guard"], "true", f"checks_guard for {p}: {got}")
        with self.subTest(path="lint/test_sim_test.sh"):
            got = run(["lint/test_sim_test.sh"], existing=["lint/test_sim_test.sh"])
            self.assertEqual(self.true_set(got), {"shell_macos", "code"}, f"lint/test_sim_test.sh: {got}")
            self.assertEqual(got[GUARD_FULL], "false", f"{GUARD_FULL} for lint/test_sim_test.sh: {got}")
            self.assertEqual(got["checks_guard"], "false", f"checks_guard for lint/test_sim_test.sh: {got}")

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


@unittest.skipUnless(BASH, "bash not on PATH")
class GuardWindowsSplit(unittest.TestCase):
    """The Windows guard suite on a pull_request. guard_windows_full turns on the full shards (checks-windows-guard's shard 1
    and its other legs). guard_windows_slice turns on the slice, which is guard on and full off, so the two never run
    together. Push, schedule, dispatch and the fail-safe paths turn full on and slice off."""

    def test_a_guard_family_pr_turns_the_full_windows_guard_on(self):
        for p in ["hooks/guard.py", "hooks/test_guard.py", "settings.json"] + family_files():
            for existing in ((), (p,)):
                with self.subTest(path=p, edit=bool(existing)):
                    got = run([p], existing=existing)
                    self.assertEqual(got["guard"], "true", f"scope: guard is off for {p}")
                    self.assertEqual(got.get(GUARD_FULL), "true",
                                     f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {p}, want 'true': its full shards would not run")

    def test_a_non_family_guard_hook_pr_runs_the_slice_and_not_the_full_shards(self):
        got = run(["hooks/daily_note.py"])
        self.assertEqual(got["guard"], "true", "scope: guard is off for hooks/daily_note.py")
        with self.subTest(output=GUARD_SLICE):
            self.assertEqual(got.get(GUARD_SLICE), "true",
                             f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for hooks/daily_note.py, want 'true'")
        with self.subTest(output=GUARD_FULL):
            self.assertEqual(got.get(GUARD_FULL), "false",
                             f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for hooks/daily_note.py, want 'false': not a guard family")

    def test_a_docs_only_pr_turns_both_split_flags_off(self):
        got = run(["README.md", "docs/x.md"])
        self.assertEqual(got["guard"], "false", "scope: a docs-only pull_request sets guard")
        for name in GUARD_SPLIT:
            with self.subTest(output=name):
                self.assertEqual(got.get(name), "false", f"{name} is {got.get(name)!r} on a docs-only pull_request, want 'false'")

    def test_the_slice_is_guard_on_and_full_off_on_every_kind_of_path(self):
        # One path of each kind, with its three flags on a pull_request as absolute values: a family module, a non-family
        # guard hook, a guard test file, a guard-arm module, a guard load outside the guard (merge/merge.py), and a docs file.
        # A push turns the full shards on and the slice off, for each path.
        want = {  # path: (guard, full, slice) on a pull_request
            "hooks/guard.py": ("true", "true", "false"),
            "hooks/daily_note.py": ("true", "false", "true"),
            "hooks/guard_test_x.py": ("true", "false", "true"),
            "lint/guard_log_report.py": ("true", "true", "false"),
            "merge/merge.py": ("true", "true", "false"),
            "README.md": ("false", "false", "false"),
        }
        for p, (guard, full, slice_) in want.items():
            with self.subTest(path=p, event="pull_request"):
                got = run([p])
                self.assertEqual((got["guard"], got.get(GUARD_FULL), got.get(GUARD_SLICE)), (guard, full, slice_),
                                 f"guard, {GUARD_FULL}, {GUARD_SLICE} for {p} on a pull_request")
            with self.subTest(path=p, event="push"):
                got = run([p], event="push")
                self.assertEqual((got.get(GUARD_FULL), got.get(GUARD_SLICE)), ("true", "false"),
                                 f"{GUARD_FULL}, {GUARD_SLICE} for {p} on a push")

    def test_push_schedule_dispatch_and_an_unreadable_diff_run_the_full_guard_and_not_the_slice(self):
        runs = [(f"event {ev}", run(["README.md"], event=ev)) for ev in ("push", "schedule", "workflow_dispatch")]
        runs.append(("an unreadable diff", run(["hooks/guard.py"], base="0" * 40)))
        for label, got in runs:
            with self.subTest(case=label):
                self.assertEqual(got["guard"], "true", f"scope: guard is off for {label}")
                self.assertEqual(got.get(GUARD_FULL), "true",
                                 f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {label}, want 'true'")
                self.assertEqual(got.get(GUARD_SLICE), "false",
                                 f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for {label}, want 'false': the slice would run beside the full shards")

    def test_a_fail_safe_path_runs_the_full_guard_and_not_the_slice(self):
        for p in (".github/scripts/ci-scope.sh", ".github/workflows/checks.yml", ".gitattributes", "zz-unmapped/blob.bin"):
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got["guard"], "true", f"scope: guard is off for {p}")
                self.assertEqual(got.get(GUARD_FULL), "true", f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {p}, want 'true'")
                self.assertEqual(got.get(GUARD_SLICE), "false", f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for {p}, want 'false'")

    def test_a_full_size_guard_pr_turns_the_full_guard_on_once(self):
        # Every guard file in one pull_request, not one file at a time: the full state of the split.
        got = run(["hooks/guard.py", "hooks/test_guard.py", "settings.json"] + family_files())
        self.assertEqual(got["guard"], "true", "scope: guard is off for the full set of guard files")
        with self.subTest(output=GUARD_FULL):
            self.assertEqual(got.get(GUARD_FULL), "true", f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for the full set, want 'true'")
        with self.subTest(output=GUARD_SLICE):
            self.assertEqual(got.get(GUARD_SLICE), "false", f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for the full set, want 'false'")

    def test_a_family_module_sets_the_same_outputs_as_guard_py(self):
        # A family module is a sibling of guard.py: every output matches it, the split flags included.
        for edit in (False, True):
            want = run(["hooks/guard.py"], existing=["hooks/guard.py"] if edit else ())
            for p in family_files():
                with self.subTest(path=p, edit=edit):
                    self.assertEqual(run([p], existing=[p] if edit else ()), want, f"{p}: its outputs differ from guard.py's")


@unittest.skipUnless(BASH, "bash not on PATH")
class GuardClosure(unittest.TestCase):
    """The files the guard suite loads (guard_closure, read from the code of its two seeds) turn the full Windows guard
    shards on for a pull_request. A loaded file that the scope leaves to the slice runs no full shard."""

    def test_every_file_the_guard_suite_loads_turns_the_full_windows_guard_on(self):
        # A new file only: the full-shard flag reads the path, and the one rule that reads whether a file is new (landed
        # dirs) sets no full flag, so an edit would run the same arm.
        files, _ = guard_closure()
        self.assertTrue(set(GUARD_SEEDS) <= set(files), f"the closure lacks a seed: {files}")
        for p in files:
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got.get(GUARD_FULL), "true",
                                 f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {p}, want 'true': the guard suite loads it")

    def test_every_load_the_closure_does_not_follow_is_named_in_load_exceptions(self):
        # The guard's loads and the merge suite's: a load in both is one entry. Counter | keeps the larger count per key.
        found = Counter()
        for closure in (guard_closure, merge_closure):
            found |= Counter(f"{f}:{key}" for f, key, _ in closure()[1])
        named = Counter(LOAD_EXCEPTIONS.keys())
        missing, stale = sorted((found - named).elements()), sorted((named - found).elements())
        self.assertEqual((missing, stale), ([], []),
                         f"LOAD_EXCEPTIONS is out of step: unnamed loads {missing}, entries with no such load {stale}")

    def test_the_derivation_reads_each_kind_of_load(self):
        # One named load of each kind, so a derivation that finds nothing fails here: an import (guard_kill imports
        # _nowindow), a literal repo path (guard.py's RECORD_LAYOUT_FILE), and a loader path (guard.py's sim-lease load).
        files, _ = guard_closure()
        for p in ("hooks/_nowindow.py", "lint/layout.json", "bin/sim-lease"):
            with self.subTest(path=p):
                self.assertIn(p, files)

    def test_blank_lines_above_a_load_keep_its_load_exception(self):
        # Each file read with three blank lines at its top: its named loads must still be its LOAD_EXCEPTIONS entries, so
        # a key cannot hold a line number. The control, the same check unshifted, is the next case.
        tracked = set(_repo_files())
        for f in sorted({key.split(":")[0] for key in LOAD_EXCEPTIONS}):
            with self.subTest(path=f):
                self.assertIn(f, guard_closure()[0] + merge_closure()[0], f"scope: {f} is in neither closure")
                keys = named_keys(f, "\n\n\n" + source_of(f), tracked)
                self.assertEqual(len(keys), len(set(keys)), f"{f}: two named loads share a key: {keys}")
                self.assertEqual(sorted(keys), exceptions_of(f), f"{f}: its named loads moved when blank lines went above them")

    def test_the_plain_source_keeps_its_load_exceptions(self):
        # The control: the same check on each file as it is. It passes on any key scheme that names the loads.
        tracked = set(_repo_files())
        for f in sorted({key.split(":")[0] for key in LOAD_EXCEPTIONS}):
            with self.subTest(path=f):
                keys = named_keys(f, source_of(f), tracked)
                self.assertEqual(sorted(keys), exceptions_of(f), f"{f}: its named loads differ from its LOAD_EXCEPTIONS entries")

    # Forms the derivation misses, each read from a real file. The scope lines first: the file is in the closure and the
    # target is a repo file, so a rename fails for its own cause.
    def test_a_repo_root_join_with_one_literal_loads_its_file(self):
        # janitor/sweep.py's default_settings_path: os.path.join(REPO_ROOT, "settings.json"), REPO_ROOT the checkout.
        tracked = set(_repo_files())
        self.assertIn("janitor/sweep.py", guard_closure()[0], "scope: janitor/sweep.py is not in the closure")
        self.assertIn("settings.json", tracked, "scope: settings.json is not a repo file")
        _, paths, loads, _ = _refs("janitor/sweep.py", _parse("janitor/sweep.py", source_of("janitor/sweep.py")), tracked)
        self.assertIn("settings.json", paths | loads, "the sweep's settings load is not followed")

    def test_a_test_module_join_under_the_repo_root_loads_its_file(self):
        # hooks/test_guard.py reads settings.json as os.path.join(REPO, "settings.json"), REPO the real checkout (line 57).
        tracked = set(_repo_files())
        self.assertIn("hooks/test_guard.py", guard_closure()[0], "scope: hooks/test_guard.py is not in the closure")
        self.assertIn("settings.json", tracked, "scope: settings.json is not a repo file")
        _, paths, loads, _ = _refs("hooks/test_guard.py", _parse("hooks/test_guard.py", source_of("hooks/test_guard.py")), tracked)
        self.assertIn("settings.json", paths | loads, "the test module's settings load under REPO is not followed")

    def test_a_pathlib_load_through_a_name_loads_its_file(self):
        # merge/merge.py: IDLE_BUILD = pathlib.Path(__file__).resolve().parents[1] / "skills/roadmap/build.py", read by
        # importlib's spec_from_file_location(..., IDLE_BUILD) in idle_lanes.
        tracked = set(_repo_files())
        self.assertIn("merge/merge.py", guard_closure()[0], "scope: merge/merge.py is not in the closure")
        self.assertIn("skills/roadmap/build.py", tracked, "scope: skills/roadmap/build.py is not a repo file")
        _, _, loads, unfollowed = _refs("merge/merge.py", _parse("merge/merge.py", source_of("merge/merge.py")), tracked)
        self.assertIn("skills/roadmap/build.py", loads, "the idle-lane loader's pathlib path is not followed")
        self.assertNotIn("a loader path with no literal repo file", [what for _, what in unfollowed])

    # Controls, green on the derivation as it stands: a load the derivation must not follow.
    def test_a_fixture_root_join_in_a_test_is_not_a_repo_load(self):
        tracked = set(_repo_files())
        self.assertIn("settings.json", tracked, "scope: settings.json is not a repo file")
        src = 'import os\n\ndef probe(root):\n    return open(os.path.join(root, "settings.json"))\n'
        _, paths, loads, unfollowed = _refs("hooks/test_zz_probe.py", ast.parse(src), tracked)
        self.assertNotIn("settings.json", paths | loads)
        self.assertEqual(unfollowed, [])

    def test_a_product_join_of_several_literals_under_the_repo_root_stays_named(self):
        # ROOT is the checkout by definition, but the suite can point it at a fixture root, so the join is named.
        tracked = set(_repo_files())
        self.assertIn("lint/rule_mechanisms.json", tracked, "scope: lint/rule_mechanisms.json is not a repo file")
        src = ('import os\nROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n'
               'MAP_FILE = os.path.join(ROOT, "lint", "rule_mechanisms.json")\n')
        _, paths, loads, unfollowed = _refs("lint/zz_probe.py", ast.parse(src), tracked)
        self.assertNotIn("lint/rule_mechanisms.json", paths | loads)
        self.assertTrue(unfollowed, "the join is neither followed nor named")

    def test_load_text_inside_a_string_is_not_followed(self):
        # The derivation reads syntax, not text: a load written in a docstring or a string with a comment opener is no load.
        tracked = set(_repo_files())
        self.assertIn("settings.json", tracked, "scope: settings.json is not a repo file")
        src = ('import os\nDOC = """os.path.join(REPO_ROOT, "settings.json")  # shown, not run"""\n'
               'NOTE = \'open(os.path.join(REPO, "settings.json")) # a comment opener in a string\'\n')
        _, paths, loads, _ = _refs("janitor/zz_probe.py", ast.parse(src), tracked)
        self.assertNotIn("settings.json", paths | loads)

    def test_a_pathlib_path_read_outside_a_loader_is_followed(self):
        # A `/` load that no loader names: the settings path a module keeps as a constant and opens elsewhere.
        tracked = set(_repo_files())
        self.assertIn("settings.json", tracked, "scope: settings.json is not a repo file")
        src = 'import pathlib\nSETTINGS = pathlib.Path(__file__).resolve().parents[1] / "settings.json"\n'
        _, paths, loads, _ = _refs("janitor/zz_probe.py", ast.parse(src), tracked)
        self.assertIn("settings.json", paths | loads, "the pathlib path read outside a loader is not followed")

    def test_a_name_bound_twice_is_not_read_through(self):
        # Control: the root is the repo by its first binding and a fixture folder by its second, so the name is not the repo.
        tracked = set(_repo_files())
        self.assertIn("settings.json", tracked, "scope: settings.json is not a repo file")
        src = ('import os\nROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nROOT = "/fixture"\n'
               'PATH = os.path.join(ROOT, "settings.json")\n')
        _, paths, loads, _ = _refs("janitor/zz_probe.py", ast.parse(src), tracked)
        self.assertNotIn("settings.json", paths | loads)

    # A test module's join under REPO with several literals is a repo load: REPO is the real checkout (hooks/test_guard.py
    # line 57). One case per target: the waiting-page page.html is read at three lines (15632, 17400, 18361).
    def assert_test_module_reads(self, target):
        tracked = set(_repo_files())
        self.assertIn("hooks/test_guard.py", guard_closure()[0], "scope: hooks/test_guard.py is not in the closure")
        self.assertIn(target, tracked, f"scope: {target} is not a repo file")
        _, paths, loads, _ = _refs("hooks/test_guard.py", _parse("hooks/test_guard.py", source_of("hooks/test_guard.py")), tracked)
        self.assertIn(target, paths | loads, f"the test module's join under REPO for {target} is not followed")

    def test_a_test_module_join_under_the_repo_reads_the_impeccable_skill(self):
        # os.path.join(REPO, "skills", "impeccable", "SKILL.md") at hooks/test_guard.py line 15161.
        self.assert_test_module_reads("skills/impeccable/SKILL.md")

    def test_a_test_module_join_under_the_repo_reads_the_waiting_page_html(self):
        # os.path.join(REPO, "skills", "waiting-page", "page.html") at hooks/test_guard.py lines 15632, 17400, 18361.
        self.assert_test_module_reads("skills/waiting-page/page.html")

    def test_a_test_module_join_under_the_repo_reads_the_waiting_page_splice(self):
        # os.path.join(REPO, "skills", "waiting-page", "splice.py") at hooks/test_guard.py line 15843.
        self.assert_test_module_reads("skills/waiting-page/splice.py")

    def test_a_test_module_join_of_several_literals_under_a_fixture_root_is_not_a_repo_load(self):
        # Control: a root passed in is not the repo, so the same several-literal join reads no repo file.
        tracked = set(_repo_files())
        self.assertIn("skills/waiting-page/page.html", tracked, "scope: skills/waiting-page/page.html is not a repo file")
        src = 'import os\n\ndef probe(root):\n    return open(os.path.join(root, "skills", "waiting-page", "page.html"))\n'
        _, paths, loads, unfollowed = _refs("hooks/test_zz_probe.py", ast.parse(src), tracked)
        self.assertNotIn("skills/waiting-page/page.html", paths | loads)
        self.assertEqual(unfollowed, [])

    # Two named loads must not share a key: a key is the scope and the load's source, so each collision shape is a fixture.
    def test_two_same_named_methods_in_two_classes_key_apart(self):
        # Scope first: the probe's two loads are the multi-literal join under ROOT, a named load (lint/rule_mechanisms.json).
        tracked = set(_repo_files())
        self.assertIn("lint/rule_mechanisms.json", tracked, "scope: lint/rule_mechanisms.json is not a repo file")
        src = ('import os\nROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n'
               'class First:\n    def load(self):\n        return os.path.join(ROOT, "lint", "rule_mechanisms.json")\n'
               'class Second:\n    def load(self):\n        return os.path.join(ROOT, "lint", "rule_mechanisms.json")\n')
        _, _, _, unfollowed = _refs("lint/zz_probe.py", ast.parse(src), tracked)
        keys = [key for key, _ in unfollowed]
        self.assertEqual(len(keys), 2, f"the two loads are not both named: {keys}")
        self.assertEqual(len(set(keys)), 2, f"two loads share a key: {keys}")
        self.assertEqual({key.split(":")[0] for key in keys}, {"First.load", "Second.load"}, f"the scope is not qualified: {keys}")

    def test_two_loads_of_one_source_in_one_function_key_apart(self):
        # The probe's loads take a path parameter, which no literal names, so both are named.
        tracked = set(_repo_files())
        src = ('import importlib.util\n\ndef load(path):\n'
               '    a = importlib.util.spec_from_file_location("x", path)\n'
               '    b = importlib.util.spec_from_file_location("y", path)\n    return a, b\n')
        _, _, _, unfollowed = _refs("lint/zz_probe.py", ast.parse(src), tracked)
        keys = [key for key, _ in unfollowed]
        self.assertEqual(len(keys), 2, f"the two loads are not both named: {keys}")
        self.assertEqual(len(set(keys)), 2, f"two loads share a key: {keys}")

    # A `/` chain and `.parent` are loads when the root is the repo and the path is a repo file. The chain is never named:
    # a directory and a user-config path are not repo files, and naming them would cry wolf.
    def test_a_pathlib_chain_through_parent_reads_the_roadmap_page(self):
        # skills/roadmap/build.py: HERE = pathlib.Path(__file__).resolve().parent, then HERE / "page" / "index.html" (line 751).
        tracked = set(_repo_files())
        self.assertIn("skills/roadmap/build.py", guard_closure()[0], "scope: skills/roadmap/build.py is not in the closure")
        self.assertIn("skills/roadmap/page/index.html", tracked, "scope: skills/roadmap/page/index.html is not a repo file")
        _, paths, loads, _ = _refs("skills/roadmap/build.py", _parse("skills/roadmap/build.py", source_of("skills/roadmap/build.py")), tracked)
        self.assertIn("skills/roadmap/page/index.html", paths | loads, "the chain through .parent is not followed")

    def test_a_home_config_chain_is_neither_read_nor_named(self):
        # Control: a path under the user's home is not a repo file, so the chain reads nothing and names nothing. Its target is
        # the repo's .claude/CLAUDE.md: if that file leaves the repo, the scope line fails, rather than the control passing empty.
        tracked = set(_repo_files())
        self.assertIn(".claude/CLAUDE.md", tracked, "scope: .claude/CLAUDE.md is not a repo file, so this control probes nothing")
        src = 'import pathlib\nUSER_CLAUDE = pathlib.Path.home() / ".claude" / "CLAUDE.md"\n'
        _, paths, loads, unfollowed = _refs("lint/zz_probe.py", ast.parse(src), tracked)
        self.assertEqual((paths | loads, unfollowed), (set(), []))

    def test_a_directory_chain_is_neither_read_nor_named(self):
        # Control: skills/roadmap/page is a directory, not a repo file, so the chain reads nothing and names nothing.
        tracked = set(_repo_files())
        self.assertNotIn("skills/roadmap/page", tracked, "scope: skills/roadmap/page is a repo file, not a directory")
        src = 'import pathlib\nPAGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "skills" / "roadmap" / "page"\n'
        _, paths, loads, unfollowed = _refs("lint/zz_probe.py", ast.parse(src), tracked)
        self.assertEqual((paths | loads, unfollowed), (set(), []))

    def test_a_worktree_git_file_is_not_a_repo_file(self):
        # A worktree's .git is a file, not a folder. The walk skips .git folders only, so the file is listed as a repo file.
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as tmp:
            os.makedirs(os.path.join(tmp, "lint"))
            with open(os.path.join(tmp, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: /elsewhere/.git/worktrees/x\n")
            with open(os.path.join(tmp, "lint", "x.py"), "w", encoding="utf-8") as f:
                f.write("\n")
            with mock.patch.object(sys.modules[__name__], "REPO", tmp):
                files = _repo_files()
        self.assertIn("lint/x.py", files, "scope: the walk does not list a plain repo file")
        self.assertNotIn(".git", files, "a worktree's .git file is listed as a repo file")


@unittest.skipUnless(BASH, "bash not on PATH")
class MergeWindowsSplit(unittest.TestCase):
    """The Windows merge suite on a pull_request. merge_windows_full turns on the full shards (checks-windows-merge's shard 1 and
    and its other legs). merge_windows_slice turns on the slice: checks_windows_merge on and full off, so the two never
    run together. Push, schedule, dispatch and the fail-safe paths turn full on and slice off."""

    def test_a_merge_suite_file_outside_the_closure_runs_the_slice_and_not_the_full_shards(self):
        # merge/test_launch.py and merge/test_cmd.py are not shard-bound: checks-windows-merge runs each whole on every run. The
        # closure leaves them out, so their pull_request runs the slice only.
        for p in ("merge/test_launch.py", "merge/test_cmd.py"):
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got["checks_windows_merge"], "true", f"scope: checks_windows_merge is off for {p}")
                self.assertEqual(got.get(MERGE_SLICE), "true", f"{MERGE_SLICE} is {got.get(MERGE_SLICE)!r} for {p}, want 'true'")
                self.assertEqual(got.get(MERGE_FULL), "false", f"{MERGE_FULL} is {got.get(MERGE_FULL)!r} for {p}, want 'false'")

    def test_a_non_family_hook_pr_runs_neither_merge_split_flag(self):
        got = run(["hooks/daily_note.py"])
        self.assertEqual(got["checks_windows_merge"], "false", "scope: checks_windows_merge is on for hooks/daily_note.py")
        for name in MERGE_SPLIT:
            with self.subTest(output=name):
                self.assertEqual(got.get(name), "false", f"{name} is {got.get(name)!r} for hooks/daily_note.py, want 'false'")

    def test_a_docs_only_pr_turns_both_merge_split_flags_off(self):
        got = run(["docs/some-record.md", "decisions/some-record.md"])
        for name in MERGE_SPLIT:
            with self.subTest(output=name):
                self.assertEqual(got.get(name), "false", f"{name} is {got.get(name)!r} on a docs-only pull_request, want 'false'")

    def test_the_merge_split_on_every_kind_of_path(self):
        # One path of each kind, with its flags on a pull_request as absolute values: a closure file, a file outside the closure,
        # a non-family hook, and a docs file. A push turns the full shards on and the slice off, for each path.
        want = {  # path: (checks_windows_merge, merge_windows_full, merge_windows_slice) on a pull_request
            "merge/merge.py": ("true", "true", "false"),
            "hooks/guard.py": ("true", "true", "false"),
            "merge/test_launch.py": ("true", "false", "true"),
            "hooks/daily_note.py": ("false", "false", "false"),
            "docs/some-record.md": ("false", "false", "false"),
        }
        for p, (merge, full, slice_) in want.items():
            with self.subTest(path=p, event="pull_request"):
                got = run([p])
                self.assertEqual((got.get("checks_windows_merge"), got.get(MERGE_FULL), got.get(MERGE_SLICE)), (merge, full, slice_),
                                 f"checks_windows_merge, {MERGE_FULL}, {MERGE_SLICE} for {p} on a pull_request")
            with self.subTest(path=p, event="push"):
                got = run([p], event="push")
                self.assertEqual((got.get(MERGE_FULL), got.get(MERGE_SLICE)), ("true", "false"),
                                 f"{MERGE_FULL}, {MERGE_SLICE} for {p} on a push")

    def test_push_schedule_dispatch_and_an_unreadable_diff_run_the_full_merge_and_not_the_slice(self):
        runs = [(f"event {ev}", run(["docs/some-record.md"], event=ev)) for ev in ("push", "schedule", "workflow_dispatch")]
        runs.append(("an unreadable diff", run(["merge/merge.py"], base="0" * 40)))
        for label, got in runs:
            with self.subTest(case=label):
                self.assertEqual(got.get(MERGE_FULL), "true", f"{MERGE_FULL} is {got.get(MERGE_FULL)!r} for {label}, want 'true'")
                self.assertEqual(got.get(MERGE_SLICE), "false",
                                 f"{MERGE_SLICE} is {got.get(MERGE_SLICE)!r} for {label}, want 'false': the slice would run beside the full shards")

    def test_a_fail_safe_path_runs_the_full_merge_and_not_the_slice(self):
        for p in (".github/scripts/ci-scope.sh", ".github/workflows/checks.yml", ".gitattributes", "zz-unmapped/blob.bin"):
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got.get(MERGE_FULL), "true", f"{MERGE_FULL} is {got.get(MERGE_FULL)!r} for {p}, want 'true'")
                self.assertEqual(got.get(MERGE_SLICE), "false", f"{MERGE_SLICE} is {got.get(MERGE_SLICE)!r} for {p}, want 'false'")

    def test_a_full_size_merge_pr_turns_the_full_merge_on_once(self):
        # Every closure file in one pull_request: the full state of the split, not one file at a time.
        got = run(merge_closure()[0])
        self.assertEqual(got.get(MERGE_FULL), "true", f"{MERGE_FULL} is {got.get(MERGE_FULL)!r} for the full closure, want 'true'")
        self.assertEqual(got.get(MERGE_SLICE), "false", f"{MERGE_SLICE} is {got.get(MERGE_SLICE)!r} for the full closure, want 'false'")


@unittest.skipUnless(BASH, "bash not on PATH")
class MergeClosure(unittest.TestCase):
    """The files the merge suite loads (merge_closure, read from merge/test_merge.py) turn the full Windows merge shards on for a
    pull_request. Each such file also turns on checks_windows_merge and code: the shards' checkouts and shard 1's job run only on
    those flags, and the full flag implies them, as the guard closure's full flag implies guard and code."""

    def test_every_file_the_merge_suite_loads_turns_the_full_windows_merge_on(self):
        files, _ = merge_closure()
        self.assertIn("merge/test_merge.py", files, "scope: the merge suite's own file is not in its closure")
        for p in files:
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got.get(MERGE_FULL), "true",
                                 f"{MERGE_FULL} is {got.get(MERGE_FULL)!r} for {p}, want 'true': the merge suite loads it")

    def test_every_file_the_merge_suite_loads_also_turns_on_the_merge_job_and_code(self):
        for p in merge_closure()[0]:
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got.get("checks_windows_merge"), "true",
                                 f"checks_windows_merge is {got.get('checks_windows_merge')!r} for {p}: its shards would start without their job")
                self.assertEqual(got.get("code"), "true", f"code is {got.get('code')!r} for {p}: the shard steps read it")

    def test_the_merge_closure_reads_each_kind_of_load(self):
        # Control, green on the derivation as it stands: one named load of each kind, so a derivation that finds nothing fails here.
        files, _ = merge_closure()
        for p in ("merge/merge.py",            # an import: test_merge imports merge
                  "hooks/decision_watch.py",   # an import, and through it hooks/guard.py: the guard closure is in this one
                  "lint/test_rule_audit.py",   # an import of a test module, by the lint folder on sys.path
                  "testing/shallow_clone.py",  # an import, by the testing folder on sys.path
                  "skills/roadmap/build.py",   # a pathlib name read by a loader in merge.py
                  "merge/cloud_allow.json",    # a literal path in merge.py
                  "README.md"):                # a test module's join under the repo: LockProseStatesTheCode reads its prose
            with self.subTest(path=p):
                self.assertIn(p, files, f"the merge closure lacks {p}")


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


@unittest.skipUnless(BASH, "bash not on PATH")
class WindowsShardLists(unittest.TestCase):
    """The leg list each sharded suite's matrix reads (LIST_SPLIT). ci-scope.sh writes it as a JSON list. A full run lists the
    suite's full legs (GUARD_LEGS, MERGE_LEGS: shards 1 to n, each once), and a run where the suite's job is on but its full flag
    is off, or its job is off on a pull_request, lists the slice alone (SLICE_ONLY). Each list must pass shard_list_problems,
    and the shard count lives in ci-scope.sh only: every full run writes the same list."""

    def legs(self, got, name):
        """The JSON list `name` holds in one run. The output must exist first, so a missing one names the cause."""
        self.assertIn(name, got, f"ci-scope.sh writes no {name} output: the suite's matrix has no legs")
        try:
            values = json.loads(got[name])
        except ValueError:
            self.fail(f"{name} is not JSON: {got[name]!r}")
        self.assertIsInstance(values, list, f"{name} is not a JSON list: {got[name]!r}")
        return values

    def assert_legs(self, got, name, want, label):
        """`name` in one run is `want`, and it passes shard_list_problems (non-empty, covers 1 to n once each)."""
        values = self.legs(got, name)
        self.assertEqual(windows_split.shard_list_problems(values), [], f"{label}: {name} = {values}")
        self.assertEqual(values, want, f"{label}: {name} is {values}, want {want}")

    def test_a_guard_family_pr_lists_the_full_guard_shards(self):
        for p in ["hooks/guard.py", "hooks/test_guard.py", "settings.json"] + family_files():
            with self.subTest(path=p):
                self.assert_legs(run([p]), GUARD_LIST, GUARD_LEGS, p)

    def test_a_non_family_guard_hook_pr_lists_the_slice_alone(self):
        self.assert_legs(run(["hooks/daily_note.py"]), GUARD_LIST, SLICE_ONLY, "hooks/daily_note.py")

    def test_a_merge_closure_pr_lists_the_full_merge_shards(self):
        self.assert_legs(run(["merge/merge.py"]), MERGE_LIST, MERGE_LEGS, "merge/merge.py")

    def test_a_merge_file_outside_the_closure_lists_the_slice_alone(self):
        # merge/test_launch.py is not shard-bound: the job runs it whole, on the slice leg.
        self.assert_legs(run(["merge/test_launch.py"]), MERGE_LIST, SLICE_ONLY, "merge/test_launch.py")

    def test_a_docs_only_pr_lists_the_slice_alone_for_both_suites(self):
        got = run(["README.md", "docs/x.md"])
        self.assert_legs(got, GUARD_LIST, SLICE_ONLY, "docs-only, guard")
        self.assert_legs(got, MERGE_LIST, SLICE_ONLY, "docs-only, merge")

    def test_a_full_size_guard_pr_lists_the_full_guard_shards_once(self):
        # Every guard file in one pull_request: the list is the full legs once, not one copy per path.
        self.assert_legs(run(["hooks/guard.py", "hooks/test_guard.py", "settings.json"] + family_files()),
                         GUARD_LIST, GUARD_LEGS, "full-size guard pr")

    def test_push_schedule_dispatch_and_an_unreadable_diff_list_the_full_shards(self):
        runs = [(f"event {ev}", run(["README.md"], event=ev)) for ev in ("push", "schedule", "workflow_dispatch")]
        runs.append(("an unreadable diff", run(["hooks/guard.py"], base="0" * 40)))
        for label, got in runs:
            with self.subTest(case=label):
                self.assert_legs(got, GUARD_LIST, GUARD_LEGS, label)
                self.assert_legs(got, MERGE_LIST, MERGE_LEGS, label)

    def test_a_fail_safe_path_lists_the_full_shards(self):
        for p in (".github/scripts/ci-scope.sh", ".github/workflows/checks.yml", ".gitattributes", "zz-unmapped/blob.bin"):
            with self.subTest(path=p):
                got = run([p])
                self.assert_legs(got, GUARD_LIST, GUARD_LEGS, p)
                self.assert_legs(got, MERGE_LIST, MERGE_LEGS, p)

    def test_the_full_list_is_the_same_on_every_full_run(self):
        # One home for the count: a full run on a push, a schedule, an unreadable diff or a fail-safe path writes the same list.
        full = [run(["hooks/guard.py"], event="push"), run(["hooks/guard.py"], base="0" * 40), run([".gitattributes"])]
        for got in full:
            self.assertEqual(self.legs(got, GUARD_LIST), GUARD_LEGS, f"a full run lists {GUARD_LIST} other than GUARD_LEGS")
            self.assertEqual(self.legs(got, MERGE_LIST), MERGE_LEGS, f"a full run lists {MERGE_LIST} other than MERGE_LEGS")


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
