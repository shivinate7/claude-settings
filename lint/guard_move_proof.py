#!/usr/bin/env python3
"""Proves that a change moved guard code between modules and changed none of it.

A guard-family move takes top-level units (functions, classes, module-level assignments) out of hooks/guard.py
into a hooks/guard_<family>.py and edits none. This script reads the guard modules at two refs with `git show`
(no checkout) and prints one verdict line, PASS or FAIL, then one line per reason.

    python3 lint/guard_move_proof.py BASE HEAD [--new NAME,...] [--changed NAME,...] [--importtime] [--root DIR]

The guard modules are hooks/guard.py and each hooks/guard_*.py (guard_core.py too) that is not a test. Six checks:

1. Each unit at BASE exists at HEAD with an identical `ast.dump`, in some guard module. A def or class is matched by
   name, a module-level assignment by its target names (an `X += ...` joins the key of `X`). A unit new at HEAD is
   listed, and passes only when `--new` names it. A unit whose body changed passes only when `--changed` names it.
   Import statements, a module docstring and `if __name__` are not units. Any other top-level statement (a `try:`
   block, a call) is a unit with no name: it is compared by its dump with its import statements removed, and a
   changed one is listed and fails. `--changed _FAMILY_MODULES` is the one edit that needs more: the base entries
   must stay in order, and each added entry must be a guard module new at HEAD.
2. No name is defined in two guard modules at HEAD, because guard.py's `__getattr__` returns the first module
   that holds a name. A name that sat in the same modules at BASE is listed and does not fail: the move did not
   make it.
3. Free names: each unit that changed module (an edited one too), each unit new at HEAD, and each unit of a module
   that lost a unit (a `try:` block counts) reads only global names its module defines, imports or gets from
   builtins. A function's own locals, parameters and enclosing names are not global; Python's `symtable` decides,
   not a text match. A moved unit that declares `global X` fails: the declaration binds X in its new module.
4. Names and order at HEAD, in every guard module. Each `from guard_<x> import n` (or `from guard import n`) names
   a top-level name of that module at HEAD. Each name a top-level statement reads at import time (outside a def or
   lambda body: a decorator, a default, a class body, a comprehension) is bound above that statement when the
   module binds it at all.
5. Each guard module new at HEAD (guard_core aside) is listed in `_FAMILY_MODULES` at HEAD, when guard.py has one.
6. `--importtime` runs `python3 -X importtime -c "import guard"` in hooks/ of a `git archive` copy of each ref
   (one warm-up, then five runs, PYTHONPYCACHEPREFIX and CLAUDE_CONFIG_DIR in a temp folder) and compares the
   median cumulative time of `guard`. HEAD fails when it is more than 10% above BASE.

Without `--importtime` the script starts no process beyond git. Cost with it: 12 `python3` starts and two `git archive`
reads, files only under a temp folder it removes.

Limits, what stays unchecked:
- The `if __name__` block is not read at all: not compared, not scanned for names, not scanned for imports.
- Import statements are stripped before units are compared, so an edit that only changes an import passes rule 1.
  Rule 4 still checks the names it imports. A `try:` block holding an import is compared without that import.
- A comment-only change is invisible to `ast` and passes.
- A unit nested in a top-level `if` or `try` is part of that statement, never a named unit, and rule 2 does not
  see it.
- Rule 3 checks the units named above. A unit in a module that lost nothing is not checked, and an unmoved unit
  that reads a moved name is seen only when its module lost a unit.
- A name read through a module attribute (`guard_core.Y`), `getattr`, a string, or a module `__getattr__` resolves
  at run time and is not seen. For `from guard import n`, a `__getattr__` in guard.py makes any name any guard
  module defines count.
- The order check (rule 4) sees one module: an import cycle between guard modules, or a family module that imports
  one listed after it in `_FAMILY_MODULES`, is not seen. It sees a read as import time by scope only: a generator
  expression counts as run, and a `try:` that catches the NameError still fails.
- A `global X` in a unit that stayed behind counts X as defined in its module, so a read of X that moved out of
  that module is not seen when the staying unit declares it.
- `_FAMILY_MODULES` is read only as a plain tuple or list of strings; any other form fails.

Exit 0 on PASS, 1 on FAIL, 2 when a ref or a guard file cannot be read, or `symtable` refuses one (printed as `unknown: ...`, never as a verdict).
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
FAMILY = "_FAMILY_MODULES"  # guard.py's tuple of family module names, in import order
ALWAYS_LOADED = {"guard.py", "guard_core.py"}  # guard.py loads guard_core by name, so the tuple does not list it
COMPREHENSION_SCOPES = {"listcomp", "dictcomp", "setcomp", "genexpr"}
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


def family_entries(node):
    """The strings of a plain `_FAMILY_MODULES = (...)` assignment, or None for any other form."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, (ast.Tuple, ast.List))):
        return None
    items = node.value.elts
    if not all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in items):
        return None
    return [item.value for item in items]


def family_edit_problems(gone, now, base_files, head_files):
    """An edit of `_FAMILY_MODULES` that --changed allows keeps each base entry, in order, and adds only guard
    modules that are new at head."""
    before, after = family_entries(gone.node), family_entries(now.node)
    if before is None or after is None:
        return ["%s is not a plain tuple of strings at base and head: its edit cannot be checked" % FAMILY]
    added, cursor = [], 0
    for entry in after:
        if cursor < len(before) and entry == before[cursor]:
            cursor += 1
        else:
            added.append(entry)
    problems = []
    if cursor < len(before):
        problems.append("%s: base entry `%s` is dropped or out of order at head (%s)" % (
            FAMILY, before[cursor], now.where()))
    for entry in added:
        if entry + ".py" not in head_files or entry + ".py" in base_files:
            problems.append("%s: added entry `%s` is not a guard module new at head (%s)" % (FAMILY, entry, now.where()))
    return problems


def check_units(base_units, head_units, allowed_new, allowed_changed, base_files, head_files):
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
        elif lost and not added:
            problems.append("lost: %s (was %s), a copy is gone from head (--changed does not excuse a drop)" % (
                shown.label(), shown.where()))
        elif lost:
            gone = [u for u in olds if u.dump in lost][0]
            now = [u for u in news if u.dump in added]
            if shown.names and shown.names <= allowed_changed:
                found = family_edit_problems(gone, now[0], base_files, head_files) if shown.names == {FAMILY} else []
                problems += found
                if not found:
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
        if unit.kind != "statement" and not isinstance(unit.node, ast.AugAssign):  # `X += ...` reads X, never defines it
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


class ModuleScopeAugAssign(ast.NodeVisitor):
    """The `X += ...` statements that run in a unit's own scope (not inside a def, class or lambda)."""

    def __init__(self):
        self.found = []

    def visit_AugAssign(self, node):
        self.found.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        pass

    visit_AsyncFunctionDef = visit_ClassDef = visit_Lambda = visit_FunctionDef


class DropAugAssign(ast.NodeTransformer):
    """Replaces each module-scope `X += v` with its value, so symtable does not count X as bound by it."""

    def visit_AugAssign(self, node):
        return ast.copy_location(ast.Expr(value=node.value), node)

    def visit_FunctionDef(self, node):
        return node  # an augmented assignment inside a def, class or lambda is that scope's, not the module's

    visit_AsyncFunctionDef = visit_ClassDef = visit_Lambda = visit_FunctionDef


def make_table(source, label):
    """`symtable` of `source`. It refuses what `ast.parse` accepts (a module-level `nonlocal`), and then the proof
    cannot run."""
    try:
        return symtable.symtable(source, label, "exec")
    except SyntaxError as exc:
        raise Unreadable("symtable refused %s: %s" % (label, exc))


def bound_names(node, label):
    """Names `node` binds at module level: assigned, imported, def, class. An augmented assignment binds nothing it
    did not already have."""
    table = make_table(ast.unparse(ast.fix_missing_locations(DropAugAssign().visit(copy.deepcopy(node)))), label)
    return {sym.get_name() for sym in table.get_symbols()
            if sym.is_assigned() or sym.is_imported() or sym.is_namespace()}


def module_names(text, label):
    """(names a module binds at its top level or sets by a `global` statement, has a star import)."""
    tree = ast.parse(text)
    names = set()
    star = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            star = True
    for node in tree.body:
        names |= bound_names(node, "%s:%d" % (label, node.lineno))
    return names, star


def runs_at_import(table):
    """True for the nested scopes that run when their statement does: a class body and a comprehension."""
    return table.get_type() == "class" or table.get_name().strip("<>") in COMPREHENSION_SCOPES


def global_reads(node, label, import_time=False):
    """Global names that the statement `node` reads. An augmented assignment reads its target. With `import_time`,
    only the reads that run when the statement does: no def or lambda body."""
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
            if not import_time or runs_at_import(child):
                walk(child, False)

    walk(make_table(ast.unparse(node), label), True)
    scoped = ModuleScopeAugAssign()
    scoped.visit(node)
    for aug in scoped.found:
        if isinstance(aug.target, ast.Name):
            out.add(aug.target.id)
    return out


def global_declarations(node):
    """The names a `global` statement inside `node` declares."""
    return {name for inner in ast.walk(node) if isinstance(inner, ast.Global) for name in inner.names}


def moved_units(base_units, head_units):
    """The head units that sit in a module where base held no unit with their key, while base held one elsewhere.
    A unit edited on the way (--changed) is moved too: its dump differs, its key does not."""
    base_places = {(unit.module, unit.key) for unit in base_units}
    base_keys = {unit.key for unit in base_units}
    return [unit for unit in head_units if (unit.module, unit.key) not in base_places and unit.key in base_keys]


def units_to_check(base_units, head_units, moved):
    """Rule 3 reads the moved units, the units new at head, and every head unit of a module that lost a unit (a
    block with no name too), since a unit that stayed behind can read a name that moved out."""
    head_places = {(unit.module, unit.key) for unit in head_units}
    base_keys = {unit.key for unit in base_units}
    losers = {unit.module for unit in base_units if (unit.module, unit.key) not in head_places}
    checked = list(moved)
    seen = {id(unit) for unit in moved}
    for unit in head_units:
        if id(unit) not in seen and (unit.module in losers or unit.key not in base_keys):
            checked.append(unit)
    return checked


def check_free_names(checked, names, elsewhere):
    """Rule 3. `names(module)` is (names the module binds, has a star import). `elsewhere` is {name: modules that
    define it at head}, to say where an unresolved name went."""
    problems, starred = [], set()
    builtin_names = set(dir(builtins)) | MODULE_DUNDERS
    for unit in checked:
        defined, star = names(unit.module)
        if star:
            if unit.module not in starred:
                starred.add(unit.module)
                problems.append("%s has a star import: free names of %s cannot be checked" % (
                    unit.module, unit.label()))
            continue
        for name in sorted(global_reads(unit.node, unit.where()) - defined - builtin_names):
            homes = sorted(elsewhere.get(name, ()))
            hint = " (`%s` is defined in %s: import it)" % (name, ", ".join(homes)) if homes else ""
            problems.append("unresolved name `%s` in %s, now in %s%s" % (name, unit.label(), unit.where(), hint))
    return problems


def check_globals(moved):
    """Rule 3, part two: a `global X` in a moved unit binds X in the module it moved to."""
    problems = []
    for unit in moved:
        declared = global_declarations(unit.node)
        if declared:
            problems.append("%s moved to %s and declares `global %s`: that rebinds the name in its new module" % (
                unit.label(), unit.where(), ", ".join(sorted(declared))))
    return problems


def head_family(head_units):
    """(found, entries): `_FAMILY_MODULES` at head; entries is None when it is not a plain tuple of strings."""
    units = [unit for unit in head_units if unit.names == {FAMILY}]
    if not units:
        return False, None
    return True, family_entries(units[0].node) if len(units) == 1 else None


def check_new_modules(head_units, base_files, head_files):
    """Rule 5. Each guard module new at head is in `_FAMILY_MODULES` at head. A head with no such tuple is not
    checked: its guard.py holds no family list to keep."""
    found, entries = head_family(head_units)
    if not found:
        return []
    if entries is None:
        return ["%s is not a plain tuple of strings at head: the new guard modules cannot be checked" % FAMILY]
    return ["new guard module %s is not in %s at head" % (name, FAMILY)
            for name in sorted(set(head_files) - set(base_files) - ALWAYS_LOADED) if name[:-3] not in entries]


def check_imports(head_sources, names):
    """Rule 4, part one. `names(module)` is (names the module binds, has a star import)."""
    problems = []
    for module, text in head_sources.items():
        for node in ast.walk(ast.parse(text)):
            if not (isinstance(node, ast.ImportFrom) and not node.level and node.module
                    and (node.module == "guard" or node.module.startswith("guard_"))):
                continue
            source = node.module + ".py"
            if source not in head_sources:
                problems.append("%s:%d imports from %s, which is not a guard module at head" % (
                    module, node.lineno, node.module))
                continue
            held, star = names(source)
            if star:
                continue
            for alias in node.names:
                if alias.name == "*" or alias.name in held:
                    continue
                if "__getattr__" in held and any(alias.name in names(other)[0] for other in head_sources):
                    continue
                problems.append("%s:%d imports `%s` from %s, which defines no top-level `%s` at head" % (
                    module, node.lineno, alias.name, node.module, alias.name))
    return problems


def check_order(head_sources):
    """Rule 4, part two. A name a top-level statement reads at import time must be bound above it, when the module
    binds it at all (a name bound nowhere is rule 3's)."""
    problems = []
    builtin_names = set(dir(builtins)) | MODULE_DUNDERS
    for module, text in head_sources.items():
        body = [node for node in ast.parse(text).body if not is_main_guard(node)]
        bound = [bound_names(node, "%s:%d" % (module, node.lineno)) for node in body]
        bound_anywhere = set().union(*bound) if bound else set()
        above = set()
        for node, own in zip(body, bound):
            where = "%s:%d" % (module, node.lineno)
            for name in sorted(global_reads(node, where, import_time=True)):
                if name in bound_anywhere and name not in above and name not in own and name not in builtin_names:
                    problems.append("`%s` is read at import time at %s, before the module binds it" % (name, where))
            above |= own
    return problems


class HeadNames:
    """module_names of each head module, read once."""

    def __init__(self, sources):
        self.sources, self.cache = sources, {}

    def __call__(self, module):
        if module not in self.cache:
            self.cache[module] = module_names(self.sources[module], module)
        return self.cache[module]


def extract_hooks(root, ref, dest):
    """Writes the regular files of `git archive REF hooks` under `dest`, with no tar process."""
    proc = subprocess.Popen(["git", "-C", root, "archive", ref, "hooks"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
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
    finally:
        proc.stdout.close()
        proc.stderr.close()


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
        base_units, base_sources, base_bad = read_units(args.root, args.base)
        head_units, head_sources, head_bad = read_units(args.root, args.head)
        problems, notes = list(base_bad) + list(head_bad), []
        if not problems:
            found, listed = check_units(base_units, head_units, names_option(args.new), names_option(args.changed),
                                        set(base_sources), set(head_sources))
            problems += found
            notes += listed
            found, listed = check_duplicates(base_units, head_units)
            problems += found
            notes += listed
            moved = moved_units(base_units, head_units)
            names = HeadNames(head_sources)
            problems += check_free_names(units_to_check(base_units, head_units, moved), names, definers(head_units))
            problems += check_globals(moved)
            problems += check_new_modules(head_units, set(base_sources), set(head_sources))
            problems += check_imports(head_sources, names)
            problems += check_order(head_sources)
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
