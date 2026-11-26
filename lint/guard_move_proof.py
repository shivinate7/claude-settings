#!/usr/bin/env python3
"""Proves that a change moved guard code between modules and changed none of it.

A guard-family move takes top-level units (functions, classes, module-level assignments) out of hooks/guard.py
into a hooks/guard_<family>.py and edits none. This script reads the guard modules at two refs with `git show`
(no checkout) and prints one verdict line, PASS or FAIL, then one line per reason.

    python3 lint/guard_move_proof.py BASE HEAD [--new NAME,...] [--changed NAME,...] [--importtime] [--root DIR]

The guard modules are hooks/guard.py and each hooks/guard_*.py (guard_core.py too) that is not a test. Four checks:

1. Each unit at BASE exists at HEAD with an identical `ast.dump`, in some guard module. A def or class is matched by
   name, a module-level assignment by its target names (an `X += ...` joins the key of `X`). A unit new at HEAD is
   listed, and passes only when `--new` names it. A unit whose body changed passes only when `--changed` names it:
   a move that adds a family module must also edit `_FAMILY_MODULES`, so that one name needs the flag. Import
   statements, a module docstring and `if __name__` are not units. Any other top-level statement (a `try:` block,
   a call) is a unit with no name: it is compared by its dump with its import statements removed, and a changed one
   is listed and fails.
2. No name is defined in two guard modules at HEAD, because guard.py's `__getattr__` returns the first module
   that holds a name. A name that sat in the same modules at BASE is listed and does not fail: the move did not
   make it.
3. Free names: each unit that changed module reads only global names its new module defines, imports or gets
   from builtins. A function's own locals, parameters and enclosing names are not global; Python's `symtable`
   decides, not a text match.
4. `--importtime` runs `python3 -X importtime -c "import guard"` in hooks/ of a `git archive` copy of each ref
   (one warm-up, then five runs, PYTHONPYCACHEPREFIX and CLAUDE_CONFIG_DIR in a temp folder) and compares the
   median cumulative time of `guard`. HEAD fails when it is more than 10% above BASE.

Without `--importtime` the script starts no process beyond git. Cost with it: 12 `python3` starts and two `git archive`
reads, files only under a temp folder it removes.

Limits: a unit nested in a top-level `if` or `try` is part of that statement, never a named unit, and rule 2 does not
see it. A comment-only change is invisible to `ast` and passes. Rule 3 checks the moved units; a unit that stayed
behind and reads a name that moved is not checked here (a call through a module attribute resolves at run time).

Exit 0 on PASS, 1 on FAIL, 2 when a ref or a guard file cannot be read (printed as `unknown: ...`, never as a verdict).
Python 3.9 floor (lint/check_python_floor.py).
"""
import argparse
import ast
import builtins
import collections
import copy
import os
import statistics
import subprocess
import sys
import symtable
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
IMPORTTIME_RUNS = 5
IMPORTTIME_MAX_RATIO = 1.10
LOAD_MARKER = "_loading"  # the name guard.py's load block assigns before each import step
MODULE_DUNDERS = {"__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__", "__builtins__",
                  "__cached__", "__class__", "__module__", "__qualname__"}


class Unreadable(Exception):
    """A ref or a file that git could not give: the proof cannot run."""


def git_bytes(root, *args):
    done = subprocess.run(["git", "-C", root] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode != 0:
        raise Unreadable("git %s: %s" % (" ".join(args), done.stderr.decode("utf-8", "replace").strip()))
    return done.stdout


def is_guard_module(path):
    base = os.path.basename(path)
    if not base.endswith(".py") or base.endswith("_test.py") or base.startswith("test_"):
        return False
    return base == "guard.py" or base.startswith("guard_")


def read_modules(root, ref):
    """{module file name: source text} for each guard module at `ref`."""
    names = git_bytes(root, "ls-tree", "--name-only", ref, "hooks/").decode("utf-8").split("\n")
    modules = {}
    for path in sorted(name for name in names if name and is_guard_module(name)):
        modules[os.path.basename(path)] = git_bytes(root, "show", "%s:%s" % (ref, path)).decode("utf-8")
    if not modules:
        raise Unreadable("no hooks/guard.py or hooks/guard_*.py at %s" % ref)
    return modules


class Unit:
    def __init__(self, module, kind, key, names, dump, node):
        self.module, self.kind, self.key, self.names, self.dump, self.node = module, kind, key, names, dump, node
        self.line = node.lineno

    def label(self):
        if self.kind in ("def", "class"):
            return "%s %s" % (self.kind, ", ".join(sorted(self.names)))
        if self.kind == "assign":
            return ", ".join(sorted(self.names)) or self.key[len("assign "):][:60]
        return "statement `%s`" % ast.unparse(self.node).split("\n")[0][:60]

    def where(self):
        return "%s:%d" % (self.module, self.line)


class StripImports(ast.NodeTransformer):
    """Removes import statements, and the `_loading = "<module>"` marker that guard.py's load block sets beside each
    import, so a block whose only edit is an import compares equal."""

    def visit_Import(self, node):
        return None

    visit_ImportFrom = visit_Import

    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == LOAD_MARKER
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            return None
        return node


def stripped_dump(node):
    return ast.dump(StripImports().visit(copy.deepcopy(node)))


def target_identifiers(targets):
    """The names an assignment binds; a non-name target (an attribute or a subscript) counts by its dump."""
    names, other = set(), []
    for target in targets:
        found = [n.id for n in ast.walk(target) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]
        if found:
            names.update(found)
        else:
            other.append(ast.dump(target))
    return names, other


def is_main_guard(node):
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")


def module_units(module, tree):
    units = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) or is_main_guard(node):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            units.append(Unit(module, kind, "%s %s" % (kind, node.name), {node.name}, ast.dump(node), node))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names, other = target_identifiers(targets)
            key = "assign " + ",".join(sorted(names) + sorted(other))
            units.append(Unit(module, "assign", key, names, ast.dump(node), node))
        else:
            dump = stripped_dump(node)
            units.append(Unit(module, "statement", "statement " + dump, set(), dump, node))
    return units


def read_units(root, ref):
    """(units, sources, problems): every unit across the guard modules at `ref`."""
    sources = read_modules(root, ref)
    units, problems = [], []
    for module, text in sources.items():
        try:
            tree = ast.parse(text, filename="%s:%s" % (ref, module))
        except SyntaxError as exc:
            problems.append("%s at %s does not parse: %s" % (module, ref, exc))
            continue
        units.extend(module_units(module, tree))
    return units, sources, problems


def by_key(units):
    table = collections.OrderedDict()
    for unit in units:
        table.setdefault(unit.key, []).append(unit)
    return table


def check_units(base_units, head_units, allowed_new, allowed_changed):
    """Rule 1. Returns (problems, notes)."""
    problems, notes = [], []
    base, head = by_key(base_units), by_key(head_units)
    for key, olds in base.items():
        news = head.get(key, [])
        old_count = collections.Counter(unit.dump for unit in olds)
        new_count = collections.Counter(unit.dump for unit in news)
        lost, added = old_count - new_count, new_count - old_count
        if not lost and not added:
            continue
        shown = olds[0]
        if lost and not news:
            problems.append("lost: %s (was %s), not in any guard module at head" % (shown.label(), shown.where()))
        elif lost:
            gone = [u for u in olds if u.dump in lost][0]
            now = [u for u in news if u.dump in added]
            if shown.names and shown.names <= allowed_changed:
                notes.append("changed (allowed by --changed): %s" % shown.label())
            else:
                problems.append("changed: %s (was %s, now %s)" % (
                    gone.label(), gone.where(), now[0].where() if now else news[0].where()))
        else:
            extra = [u for u in news if u.dump in added][0]
            if extra.names and extra.names <= allowed_new:
                notes.append("new copy (allowed by --new): %s at %s" % (extra.label(), extra.where()))
            else:
                problems.append("new unit not in --new: %s at %s (a second copy of one in base)" % (
                    extra.label(), extra.where()))
    for key, news in head.items():
        if key in base:
            continue
        for unit in news:
            if unit.kind != "statement" and unit.names and unit.names <= allowed_new:
                notes.append("new (allowed by --new): %s at %s" % (unit.label(), unit.where()))
            else:
                problems.append("new unit not in --new: %s at %s" % (unit.label(), unit.where()))
    return problems, notes


def definers(units):
    table = collections.defaultdict(set)
    for unit in units:
        if unit.kind != "statement":
            for name in unit.names:
                table[name].add(unit.module)
    return table


def check_duplicates(base_units, head_units):
    """Rule 2. Returns (problems, notes). A name that sat in the same modules at base is a note, not a problem:
    the move did not make it."""
    problems, notes = [], []
    base_defs = definers(base_units)
    for name, modules in sorted(definers(head_units).items()):
        if len(modules) > 1:
            line = "defined in two modules at head: %s in %s" % (name, ", ".join(sorted(modules)))
            if base_defs.get(name) == modules:
                notes.append(line + " (the same two at base)")
            else:
                problems.append(line)
    return problems, notes


def module_names(text):
    """Names a module binds at its top level: assigned, imported, def, class, or set by a `global` statement."""
    table = symtable.symtable(text, "<module>", "exec")
    names = {sym.get_name() for sym in table.get_symbols()
             if sym.is_assigned() or sym.is_imported() or sym.is_namespace()}
    star = False
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            star = True
    return names, star


def global_reads(source):
    """Global names that `source` (one unit) reads."""
    out = set()

    def walk(table, top):
        for sym in table.get_symbols():
            if not sym.is_referenced():
                continue
            if top:
                if not (sym.is_assigned() or sym.is_imported() or sym.is_namespace()):
                    out.add(sym.get_name())
            elif sym.is_global():
                out.add(sym.get_name())
        for child in table.get_children():
            walk(child, False)

    walk(symtable.symtable(source, "<unit>", "exec"), True)
    return out


def moved_units(base_units, head_units):
    """The head units that sit in a module where base held no identical copy, while base held one elsewhere."""
    base_places = collections.defaultdict(collections.Counter)
    for unit in base_units:
        base_places[(unit.key, unit.dump)][unit.module] += 1
    head_places = collections.defaultdict(collections.Counter)
    for unit in head_units:
        head_places[(unit.key, unit.dump)][unit.module] += 1
    moved = []
    for unit in head_units:
        key = (unit.key, unit.dump)
        if key in base_places and head_places[key][unit.module] > base_places[key][unit.module]:
            moved.append(unit)
    return moved


def check_free_names(moved, head_sources):
    """Rule 3."""
    problems, known = [], {}
    builtin_names = set(dir(builtins)) | MODULE_DUNDERS
    for unit in moved:
        if unit.module not in known:
            known[unit.module] = module_names(head_sources[unit.module])
        defined, star = known[unit.module]
        if star:
            problems.append("%s has a star import: free names of %s cannot be checked" % (unit.module, unit.label()))
            continue
        for name in sorted(global_reads(ast.unparse(unit.node)) - defined - builtin_names):
            problems.append("unresolved name `%s` in %s, now in %s" % (name, unit.label(), unit.where()))
    return problems


def extract_hooks(root, ref, dest):
    """Writes the regular files of `git archive REF hooks` under `dest`, with no tar process."""
    proc = subprocess.Popen(["git", "-C", root, "archive", ref, "hooks"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
        for member in archive:
            if not member.isfile():
                continue
            target = os.path.normpath(os.path.join(dest, member.name))
            if not target.startswith(dest + os.sep):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(archive.extractfile(member).read())
    proc.stdout.close()
    if proc.wait() != 0:
        raise Unreadable("git archive %s hooks: %s" % (ref, proc.stderr.read().decode("utf-8", "replace").strip()))


def import_microseconds(hooks_dir, scratch):
    """Cumulative microseconds of `import guard`, from one -X importtime run; None when it cannot be read."""
    env = dict(os.environ, PYTHONPYCACHEPREFIX=os.path.join(scratch, "pycache"), CLAUDE_CONFIG_DIR=scratch)
    done = subprocess.run([sys.executable, "-X", "importtime", "-c", "import guard"], cwd=hooks_dir, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode != 0:
        return None
    found = None
    for line in done.stderr.decode("utf-8", "replace").split("\n"):
        parts = line.split("|")
        if len(parts) == 3 and parts[2].strip() == "guard":
            try:
                found = int(parts[1])
            except ValueError:
                return None
    return found


def median_import(root, ref):
    with tempfile.TemporaryDirectory() as scratch:
        scratch = os.path.realpath(scratch)
        extract_hooks(root, ref, scratch)
        hooks_dir = os.path.join(scratch, "hooks")
        if import_microseconds(hooks_dir, scratch) is None:  # the warm-up writes the pycache
            return None
        runs = [import_microseconds(hooks_dir, scratch) for _ in range(IMPORTTIME_RUNS)]
        if None in runs:
            return None
        return statistics.median(runs)


def check_importtime(root, base_ref, head_ref):
    """Rule 4. Returns (problems, notes)."""
    base_us, head_us = median_import(root, base_ref), median_import(root, head_ref)
    if base_us is None or head_us is None:
        which = base_ref if base_us is None else head_ref
        return ["importtime: `import guard` did not run or printed no `guard` line at %s" % which], []
    note = "importtime median of %d: base %d us, head %d us (%+.1f%%)" % (
        IMPORTTIME_RUNS, base_us, head_us, (head_us - base_us) * 100.0 / base_us)
    if head_us > base_us * IMPORTTIME_MAX_RATIO:
        return ["%s, more than %d%% slower" % (note, round((IMPORTTIME_MAX_RATIO - 1) * 100))], []
    return [], [note]


def names_option(text):
    return {name.strip() for name in text.split(",") if name.strip()}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prove a guard family move is a pure move.")
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--new", default="", help="comma-separated names a unit new at head may carry")
    parser.add_argument("--changed", default="", help="comma-separated names a changed unit may carry")
    parser.add_argument("--importtime", action="store_true", help="also compare `import guard` time")
    parser.add_argument("--root", default=ROOT, help="the repo (default: this script's repo)")
    args = parser.parse_args(argv)
    try:
        base_units, _, base_bad = read_units(args.root, args.base)
        head_units, head_sources, head_bad = read_units(args.root, args.head)
        problems, notes = list(base_bad) + list(head_bad), []
        if not problems:
            found, listed = check_units(base_units, head_units, names_option(args.new), names_option(args.changed))
            problems += found
            notes += listed
            found, listed = check_duplicates(base_units, head_units)
            problems += found
            notes += listed
            moved = moved_units(base_units, head_units)
            problems += check_free_names(moved, head_sources)
            notes.append("%d units at base, %d moved module" % (len(base_units), len(moved)))
        if args.importtime and not (base_bad or head_bad):
            found, listed = check_importtime(args.root, args.base, args.head)
            problems += found
            notes += listed
    except Unreadable as exc:
        print("unknown: %s" % exc)
        return 2
    print("%s guard move proof %s..%s" % ("FAIL" if problems else "PASS", args.base, args.head))
    for line in problems:
        print("  - %s" % line)
    for line in notes:
        print("  . %s" % line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
