#!/usr/bin/env python3
"""Every guard refusal and ask names an allowed way out, and a test proves each way out is allowed.

Run it from the repository root:

    python3 hooks/test_guard_remedies.py -v

The scan reads the source with ast, so no guard module is imported here (importing hooks/test_guard.py
alone takes minutes). Six test methods in three groups:

1. STATIC: each refuse() site in every hooks/ module, and each call of a module's own refuse() wrapper,
   resolves to a reason that carries "Remedy:". A site is a call of guard_core's refuse() (imported or
   attribute form), or a call of a refuse() wrapper that takes a rule and a reason. The resolution follows
   local names (the nearest assignment above the use), module constants, imported constants, dict lookups,
   helper returns, appended values and the arguments a helper's return names. A refuse() that reads a
   parameter, or a queue element an appender fills (guard.py's ask_command), counts once per call of that
   function, with the call's own arguments. An unresolvable reason counts as lacking. No rule is exempt.
2. PROBES: each rule that has a Remedy is in REMEDY_PROBES, with the allowed act its Remedy names, or in
   REMEDY_PROSE_ONLY, with the reason no runnable act exists. Each probe runs through the guard, which must
   answer, and must not refuse or ask it under that rule. Each probe row names a token, which must appear in
   the rule's resolved Remedy, so the probe is bound to the act the Remedy names. A row with no payload is a
   prose act of a rule that also has a probe: its reason says why no runnable act proves it.
3. HYGIENE: no Remedy names a forbidden target. The list and the exemptions are read from their one home,
   tests/guard/s30130-rule9.py (names_the_target), not copied.

Standard library only. GUARD_UNDER_TEST points the probes at another copy of the guard, such as a mutant.
"""

import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

REMEDY = "Remedy:"
# The argument positions of (rule, reason) in guard_core.refuse(tool, decision, rule, reason, matched, ...). A
# module's own refuse() wrapper gives its positions by its parameter names (see refuse_shape).
GUARD_SHAPE = (2, 3)
# Fewer sites than this means the scan lost sites, not that the guard is clean. The scan finds 132 on the head.
MIN_SITES = 120
RULE_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
ONE_HOME = os.path.join(REPO, "tests", "guard", "s30130-rule9.py")
# Where the names the forbidden list reads are defined. ROOT is a fixture path: it stands in for itself
# here, since a static Remedy never holds a fixture path.
HOME_DEFS = {
    "ENV": os.path.join(HERE, "test_guard.py"),
    "VCS": os.path.join(HERE, "test_guard.py"),
    "TWO_RULE": os.path.join(REPO, "tests", "guard", "s04342-two-worktrees-one-branch.py"),
    "slash": os.path.join(REPO, "tests", "guard", "s00442-misc.py"),
}
ROOT_STAND_IN = "<fixture root>"

# ------------------------------------------------------------------ the static scan

MODULES = {}


def bound_names(target):
    """The names one assignment target binds."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for elt in target.elts for name in bound_names(elt)]
    if isinstance(target, ast.Starred):
        return bound_names(target.value)
    return []


class Module:
    """One hooks/ module, read with ast: top-level values and functions, imports, and appended values."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            self.tree = ast.parse(f.read(), path)
        self.parent = {}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parent[child] = node
        self.values = {}    # top-level name -> value nodes
        self.funcs = {}     # top-level name -> FunctionDef
        self.imports = {}   # bound name -> (module name, attribute, or None for the whole module)
        self.appended = {}  # name -> nodes passed to name.append(...)
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef):
                self.funcs[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Name) for e in target.elts):
                        for index, elt in enumerate(target.elts):
                            self.values.setdefault(elt.id, []).append(Pick(node.value, index))
                        continue
                    for name in bound_names(target):
                        self.values.setdefault(name, []).append(node.value)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports[alias.asname or alias.name.split(".")[0]] = (alias.name, None)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (node.module, alias.name)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "append" and isinstance(node.func.value, ast.Name) and node.args):
                self.appended.setdefault(node.func.value.id, []).append(node.args[0])


def load(name):
    """The hooks/ module called `name`, or None when hooks/ has no such file (stdlib, lint)."""
    if name not in MODULES:
        path = os.path.join(HERE, name + ".py")
        MODULES[name] = Module(path) if os.path.isfile(path) else None
    return MODULES[name]


def is_module(mod, name):
    return name in mod.imports and mod.imports[name][1] is None


def module_of(mod, name):
    return load(mod.imports[name][0])


def scopes(mod, node):
    """The functions around `node`, innermost first."""
    out = []
    cur = mod.parent.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            out.append(cur)
        cur = mod.parent.get(cur)
    return out


def params(func):
    a = func.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return names


FUNC_CACHE = {}  # id(FunctionDef) -> (locals: name -> value nodes, returns: Return nodes)


class Pick:
    """A name bound by tuple unpacking: the element at `index` of the value assigned, not the whole tuple."""

    def __init__(self, value, index):
        self.value = value
        self.index = index
        self.lineno = value.lineno


def func_facts(func):
    """The values each name is assigned in `func` (and the iterables it loops over), and its Return nodes.
    Read once per function: a guard's functions are long, and every name lookup asks."""
    if id(func) not in FUNC_CACHE:
        local, returns = {}, []
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Name) for e in target.elts):
                        for index, elt in enumerate(target.elts):
                            local.setdefault(elt.id, []).append(Pick(node.value, index))
                        continue
                    for name in bound_names(target):
                        local.setdefault(name, []).append(node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
                for name in bound_names(node.target):
                    local.setdefault(name, []).append(node.value)
            elif isinstance(node, ast.For):
                for name in bound_names(node.target):
                    local.setdefault(name, []).append(node.iter)
            elif isinstance(node, ast.Return) and node.value is not None:
                returns.append(node)
        FUNC_CACHE[id(func)] = (local, returns)
    return FUNC_CACHE[id(func)]


def local_values(func, name):
    """The values assigned to `name` anywhere in `func`, and the iterables it loops over."""
    return func_facts(func)[0].get(name, [])


class Trail:
    """What one resolution reached: the string literals. `active` holds the nodes on the current path, so a
    cycle stops; `bindings` maps a helper's parameter to the argument its caller passed, so a Remedy that
    comes in as an argument still counts."""

    def __init__(self):
        self.strings = []
        self.active = set()
        self.bindings = {}


MAX_DEPTH = 200  # a resolution deeper than this stops: a guard's reason never nests this far


def name_text(mod, node, trail, rule):
    name = node.id
    for func in scopes(mod, node):
        if name in params(func) or local_values(func, name):
            values = local_values(func, name)
            if values:
                # The assignment above this use is the one that reaches it; a later one is not yet
                # assigned. With none above (a loop's back edge), every assignment counts.
                before = [v for v in values if v.lineno <= node.lineno]
                for value in ([max(before, key=lambda v: v.lineno)] if before else values):
                    if isinstance(value, Pick):
                        text_pick(mod, value.value, value.index, trail, rule)
                    else:
                        text_of(mod, value, trail, rule)
            elif (id(func), name) in trail.bindings:  # a parameter: the argument its caller passed
                caller, arg = trail.bindings[(id(func), name)]
                text_of(caller, arg, trail, rule)
            return  # a parameter with no caller in view adds no text
    if name in mod.values or name in mod.appended:
        module_value_text(mod, name, rule, trail)
        return
    if name in mod.imports:
        modname, attr = mod.imports[name]
        other = load(modname)
        if other is not None and attr is not None:
            module_value_text(other, attr, rule, trail)


MODULE_CACHE = {}  # (module, name, rule) -> the strings: a top-level value takes no parameter


def module_value_text(other, name, rule, trail):
    """The text of a top-level value of `other`, and of what is appended to it. Read once per module."""
    key = (other.name, name, rule)
    if key not in MODULE_CACHE:
        MODULE_CACHE[key] = ()  # a cycle reaches this empty answer, not a loop
        sub = Trail()
        for value in other.values.get(name, []):
            if isinstance(value, Pick):
                text_pick(other, value.value, value.index, sub, rule)
            else:
                text_of(other, value, sub, rule)
        for value in other.appended.get(name, []):
            text_of(other, value, sub, rule)
        MODULE_CACHE[key] = tuple(sub.strings)
    trail.strings.extend(MODULE_CACHE[key])


def callee_targets(mod, func):
    """The (module, FunctionDef) a call reaches, when hooks/ defines it."""
    if isinstance(func, ast.Name):
        if func.id in mod.funcs:
            return [(mod, mod.funcs[func.id])]
        if func.id in mod.imports:
            modname, attr = mod.imports[func.id]
            other = load(modname)
            if other is not None and attr is not None and attr in other.funcs:
                return [(other, other.funcs[attr])]
        return []
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and is_module(mod, func.value.id):
        other = module_of(mod, func.value.id)
        if other is not None and func.attr in other.funcs:
            return [(other, other.funcs[func.attr])]
    return []


def dict_literals(mod, node):
    """(module, Dict) for each dict literal `node` names, through a constant or an imported module."""
    if isinstance(node, ast.Name):
        found = [(mod, v) for v in mod.values.get(node.id, []) if isinstance(v, ast.Dict)]
        if not found and node.id in mod.imports and mod.imports[node.id][1] is not None:
            other = load(mod.imports[node.id][0])
            found = [(other, v) for v in other.values.get(mod.imports[node.id][1], [])
                     if other is not None and isinstance(v, ast.Dict)]
        return found
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and is_module(mod, node.value.id):
        other = module_of(mod, node.value.id)
        if other is not None:
            return [(other, v) for v in other.values.get(node.attr, []) if isinstance(v, ast.Dict)]
    return []


def bind_call(other, func, call, mod, trail):
    """Bind each parameter of `func` to the argument `call` passes it. Returns the keys it added."""
    names = [a.arg for a in func.args.posonlyargs + func.args.args]
    added = []
    for name, arg in zip(names, call.args):
        added.append((id(func), name))
        trail.bindings[(id(func), name)] = (mod, arg)
    for kw in call.keywords:
        if kw.arg:
            added.append((id(func), kw.arg))
            trail.bindings[(id(func), kw.arg)] = (mod, kw.value)
    return added


def text_of(mod, node, trail, rule=False):
    """Collect the string literals `node` yields. A call's arguments are data, so an argument counts only
    where a helper's return names its parameter. In rule mode, only the default of a dict's
    .get(key, default) counts: a rule name never comes from a key."""
    key = id(node)
    if key in trail.active or len(trail.active) > MAX_DEPTH:
        return
    trail.active.add(key)
    try:
        _text_of(mod, node, trail, rule)
    finally:
        trail.active.discard(key)


def text_pick(mod, node, index, trail, rule):
    """The text of element `index` of the tuple `node` yields: a tuple literal, a dict's tuple values, or a
    helper's returns. Any other value counts whole, which is the safe side for a Remedy and a rule name alike."""
    key = (id(node), index)
    if key in trail.active or len(trail.active) > MAX_DEPTH:
        return
    trail.active.add(key)
    try:
        if isinstance(node, (ast.Tuple, ast.List)) and index < len(node.elts):
            text_of(mod, node.elts[index], trail, rule)
        elif isinstance(node, ast.Dict):
            for value in node.values:
                text_pick(mod, value, index, trail, rule)
        elif isinstance(node, ast.Subscript):  # a dict's value: the one under a constant key, else every value
            found = False
            for other, dnode in dict_literals(mod, node.value):
                for key, value in zip(dnode.keys, dnode.values):
                    if isinstance(node.slice, ast.Constant) and not (
                            isinstance(key, ast.Constant) and key.value == node.slice.value):
                        continue
                    found = True
                    text_pick(other, value, index, trail, rule)
            if not found:
                text_of(mod, node, trail, rule)
        elif isinstance(node, ast.IfExp):
            text_pick(mod, node.body, index, trail, rule)
            text_pick(mod, node.orelse, index, trail, rule)
        elif isinstance(node, ast.Call) and callee_targets(mod, node.func):
            for other, func in callee_targets(mod, node.func):
                added = bind_call(other, func, node, mod, trail)
                for ret in func_facts(func)[1]:
                    if scopes(other, ret)[:1] == [func]:
                        text_pick(other, ret.value, index, trail, rule)
                for name in added:
                    trail.bindings.pop(name, None)
        elif isinstance(node, ast.Call) and rule and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and len(node.args) >= 2:
            text_pick(mod, node.func.value, index, trail, rule)
            text_pick(mod, node.args[1], index, trail, rule)
        else:
            text_of(mod, node, trail, rule)
    finally:
        trail.active.discard(key)


def _text_of(mod, node, trail, rule):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            trail.strings.append(node.value)
        return
    if isinstance(node, ast.Name):
        name_text(mod, node, trail, rule)
        return
    if isinstance(node, ast.IfExp):  # the two branches are text; the test is not
        text_of(mod, node.body, trail, rule)
        text_of(mod, node.orelse, trail, rule)
        return
    if isinstance(node, ast.Dict):  # the values only: a key is a lookup word, not text the guard prints
        for value in node.values:
            text_of(mod, value, trail, rule)
        return
    if isinstance(node, ast.Call):
        targets = callee_targets(mod, node.func)
        if targets:
            for other, func in targets:
                added = bind_call(other, func, node, mod, trail)
                for ret in func_facts(func)[1]:
                    if scopes(other, ret)[:1] == [func]:
                        text_of(other, ret.value, trail, rule)
                for name in added:
                    trail.bindings.pop(name, None)
            return
        if rule:
            if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and len(node.args) >= 2:
                text_of(mod, node.func.value, trail, rule)
                text_of(mod, node.args[1], trail, rule)
            return
        if isinstance(node.func, ast.Attribute):  # a method on text, such as "...".format(...): its receiver
            text_of(mod, node.func.value, trail, rule)
        return
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and is_module(mod, node.value.id):
        other = module_of(mod, node.value.id)
        if other is not None:
            module_value_text(other, node.attr, rule, trail)
        return
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        for other, dnode in dict_literals(mod, node.value):
            for key, value in zip(dnode.keys, dnode.values):
                if isinstance(key, ast.Constant) and key.value == node.slice.value:
                    text_of(other, value, trail, rule)
                    return
    for child in ast.iter_child_nodes(node):
        text_of(mod, child, trail, rule)


class Site:
    """One refuse() call: where it is, the rules it can name, and the Remedy text its reason reaches."""

    def __init__(self, path, line, rules, reason_src, pieces):
        self.path = path
        self.line = line
        self.rules = rules
        self.reason_src = reason_src
        self.remedies = [p[p.index(REMEDY):] for p in pieces if REMEDY in p]

    @property
    def has_remedy(self):
        return bool(self.remedies)

    def where(self):
        return "%s:%d" % (os.path.relpath(self.path, REPO), self.line)


def call_arg(call, index, keyword):
    """The argument at `index`, or the keyword argument `keyword`, of a call; None when it passes neither."""
    if len(call.args) > index:
        return call.args[index]
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def positional(func):
    return [a.arg for a in func.args.posonlyargs + func.args.args]


def param_slot(mod, node):
    """(function, parameter) that a refuse() argument reads its text from, or None. A bare name is a parameter its
    function never assigns. A name unpacked from a module list's element (`rule, reason, ... = QUEUE[0]`) reads the
    element each appender stores: the parameter the appended tuple takes at that position is the slot."""
    if not isinstance(node, ast.Name):
        return None
    for func in scopes(mod, node):
        if node.id not in params(func) and not local_values(func, node.id):
            continue
        values = local_values(func, node.id)
        if not values:
            return (func, node.id)
        if len(values) != 1 or not isinstance(values[0], Pick) or not isinstance(values[0].value, ast.Subscript):
            return None
        queue = values[0].value.value
        if not isinstance(queue, ast.Name):
            return None
        slots = set()
        for appended in mod.appended.get(queue.id, []):
            if not isinstance(appended, ast.Tuple) or values[0].index >= len(appended.elts):
                continue
            elt = appended.elts[values[0].index]
            if isinstance(elt, ast.Name) and scopes(mod, elt) and elt.id in params(scopes(mod, elt)[0]):
                slots.add((scopes(mod, elt)[0], elt.id))
        return slots.pop() if len(slots) == 1 else None
    return None


def site_of(mod, call, rule_node, reason_node):
    """The Site a refuse() call makes from its rule and reason arguments, each read in the scope it is written in."""
    rule_trail = Trail()
    if rule_node is not None:
        text_of(mod, rule_node, rule_trail, rule=True)
    rules = sorted({s for s in rule_trail.strings if RULE_RE.fullmatch(s)})
    if not rules:
        rules = ["<%s>" % (ast.unparse(rule_node)[:50] if rule_node is not None else "missing")]
    reason_trail = Trail()
    if reason_node is not None:
        text_of(mod, reason_node, reason_trail)
    return Site(mod.path, call.lineno, rules,
                ast.unparse(reason_node)[:80] if reason_node is not None else "<no reason argument>",
                reason_trail.strings)


def expansions(mod, node, shape):
    """One Site per call of the function whose parameter a refuse() reads, each read with that call's own arguments.
    None when neither argument reads a parameter, or the two read parameters of different functions."""
    rule_node, reason_node = call_arg(node, shape[0], "rule"), call_arg(node, shape[1], "reason")
    slots = {}
    for key, arg in (("rule", rule_node), ("reason", reason_node)):
        slot = param_slot(mod, arg) if arg is not None else None
        if slot:
            slots[key] = slot
    if not slots or len({id(owner) for owner, _ in slots.values()}) != 1:
        return None
    owner = next(iter(slots.values()))[0]
    names = positional(owner)
    out = []
    for caller in ast.walk(mod.tree):
        if not (isinstance(caller, ast.Call) and isinstance(caller.func, ast.Name) and caller.func.id == owner.name):
            continue
        args = {"rule": rule_node, "reason": reason_node}
        for key, (_, name) in slots.items():
            args[key] = call_arg(caller, names.index(name) if name in names else len(names), name)
        out.append(site_of(mod, caller, args["rule"], args["reason"]))
    return out


def refuse_shape(mod):
    """The (rule, reason) argument positions of the refuse() calls that a module's Name calls make, or None when
    they name no rule. A module that imports guard_core's refuse takes GUARD_SHAPE. A module with its own refuse()
    wrapper takes the positions of the wrapper's rule and reason parameters (call_judge.py). A wrapper with no rule
    parameter (blind_brief.py, prose_judge.py, sendmessage_state.py) fixes its rule in its body, so its Name calls
    add no site: the guard_core.refuse() call inside it is the site, and it reads the Remedy the wrapper appends."""
    if "refuse" not in mod.funcs:
        return GUARD_SHAPE
    names = positional(mod.funcs["refuse"])
    if "rule" in names and "reason" in names:
        return names.index("rule"), names.index("reason")
    return None


def is_guard_core_refuse(mod, func):
    """True when `func` is guard_core.refuse, called as an attribute of the imported module."""
    return (isinstance(func, ast.Attribute) and func.attr == "refuse" and isinstance(func.value, ast.Name)
            and is_module(mod, func.value.id) and mod.imports[func.value.id][0] == "guard_core")


def sites_in(mod):
    out = []  # the decision is not read: a Remedy is owed on a deny and on an ask alike
    shape = refuse_shape(mod)
    wrapper = mod.funcs.get("refuse") if shape is not None else None
    for node in ast.walk(mod.tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "refuse" and shape is not None:
            call_shape = shape
        elif is_guard_core_refuse(mod, node.func):
            # Inside a wrapper that takes the reason, the reason is the caller's: the wrapper's Name calls are the sites.
            if wrapper is not None and any(f is wrapper for f in scopes(mod, node)):
                continue
            call_shape = GUARD_SHAPE
        else:
            continue
        followed = expansions(mod, node, call_shape)
        if followed is None:
            followed = [site_of(mod, node, call_arg(node, call_shape[0], "rule"),
                                call_arg(node, call_shape[1], "reason"))]
        out += followed
    return out


def is_product_module(name):
    """Every hooks/ module but the tests: a test file calls refuse() with fixture arguments, and is no guard site."""
    return not (name.startswith("test_") or name.endswith("_test"))


SCANNED = []


def scan():
    """Every refuse() site of every product module in hooks/, read with ast. Read once per run."""
    if not SCANNED:
        sites = []
        for path in sorted(glob.glob(os.path.join(HERE, "*.py"))):
            name = os.path.splitext(os.path.basename(path))[0]
            if is_product_module(name):
                sites += sites_in(load(name))
        SCANNED.append(sites)
    return SCANNED[0]


# ------------------------------------------------------------------ the forbidden list, from its one home

def exec_definition(path, name, ns):
    """Run the top-level assignment or def `name` of `path` in `ns`. A missing name fails the test."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            exec(compile(ast.Module([node], []), path, "exec"), ns)
            return
        if isinstance(node, ast.Assign) and any(name in bound_names(t) for t in node.targets):
            exec(compile(ast.Module([node], []), path, "exec"), ns)
            return
    raise AssertionError("%s no longer defines %s, so the forbidden list cannot be read" % (path, name))


def one_home_reason_rules():
    """(FORBIDDEN_IN_A_REASON, REASON_MAY_NAME) as tests/guard/s30130-rule9.py builds them."""
    ns = {"ROOT": ROOT_STAND_IN, "os": os}
    for name, path in HOME_DEFS.items():
        exec_definition(path, name, ns)
    with open(ONE_HOME, encoding="utf-8") as f:
        home = ast.parse(f.read(), ONE_HOME)
    wanted = ("FORBIDDEN_IN_A_REASON", "REASON_MAY_NAME")
    for node in home.body:
        if isinstance(node, ast.Assign) and any(name in wanted for t in node.targets for name in bound_names(t)):
            exec(compile(ast.Module([node], []), ONE_HOME, "exec"), ns)
    return ns["FORBIDDEN_IN_A_REASON"], ns["REASON_MAY_NAME"]


# ------------------------------------------------------------------ the probes: the act each Remedy names

# rule -> [(what the act is, payload, token)]. Each payload is the body the guard reads on stdin, as test_guard.py
# builds it: tool_name, tool_input, and cwd when a case names one. Each act is one the Remedy tells the
# session to do, of a tool kind the rule judges; the guard must not refuse or ask it under that rule. The guard
# decides; it runs nothing. The token is the words of that Remedy which name the act, and it must appear in the
# rule's resolved Remedy text. A row with a payload of None is an act no runnable probe can make: its first field
# is the reason, and the rule's other rows still probe it.
# <REPO>, <RUN>, <CFG>, <LANE>, <POINTER>, <POINTER_LANE> and <TMP> stand for the fixture folders, which exist only
# once the module runs.
REMEDY_PROBES = {}

# rule -> one-line reason no runnable act can prove the Remedy. Read by the coverage test only.
REMEDY_PROSE_ONLY = {}


def bash_payload(command, cwd=None):
    body = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd:
        body["cwd"] = cwd
    return body


def tool_payload(tool, tool_input):
    return {"tool_name": tool, "tool_input": tool_input}


PAGE_URL = "https://claude.ai/artifact/remedy-probe"  # the waiting page of the fixture repo, set in setUpModule


def page_payload(tool_input):
    """An ArtifactData call on the fixture repo's waiting page: the page rules judge it from the repo the cwd names."""
    body = tool_payload("ArtifactData", dict({"url": PAGE_URL, "action": "set", "collection": "items",
                                              "doc_id": "probe-item"}, **tool_input))
    body["cwd"] = "<REPO>"
    return body


RUN = None
CFG = None
REPO_DIR = None
LANE_DIR = None  # a worktree of the fixture repo, where a per-file discard runs
POINTER_DIR = None  # the pointer checkout the owner's global rules name: a repo of its own
POINTER_LANE = None  # a worktree of the pointer checkout, the place EnterWorktree makes
TMP = None  # the guard's temp folder. The fixtures sit outside it: a repo under the temp folder is a throwaway that
            # several rules pass unjudged, so a probe there would pass for the wrong reason.


def setUpModule():
    global RUN, CFG, REPO_DIR, LANE_DIR, POINTER_DIR, POINTER_LANE, TMP
    RUN = _test_temp.run_folder()
    CFG = os.path.join(RUN, "cfg")
    os.makedirs(CFG)
    TMP = os.path.join(RUN, "tmp")
    os.makedirs(TMP)
    REPO_DIR = os.path.join(RUN, "repo")
    os.makedirs(REPO_DIR)
    # The pointer checkout: the global CLAUDE.md in CFG names it, so the pointer rules judge its files and HEAD.
    POINTER_DIR = os.path.join(RUN, "pointer")
    os.makedirs(POINTER_DIR)
    subprocess.run(["git", "init", "-q", POINTER_DIR], check=True, capture_output=True)
    subprocess.run(["git", "-C", POINTER_DIR, "-c", "user.name=probe", "-c", "user.email=probe@example.invalid",
                    "commit", "-q", "--allow-empty", "-m", "probe"], check=True, capture_output=True)
    POINTER_LANE = os.path.join(POINTER_DIR, ".claude", "worktrees", "probe-lane")
    subprocess.run(["git", "-C", POINTER_DIR, "worktree", "add", "-q", "--detach", POINTER_LANE], check=True,
                   capture_output=True)
    with open(os.path.join(CFG, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write("@%s/CLAUDE.md\n" % POINTER_DIR)
    # A readable origin: a forced push is judged against its remote, so without one the guard reads the target
    # as unreadable and refuses even the lease form the Remedy names.
    origin = os.path.join(RUN, "origin.git")
    subprocess.run(["git", "init", "-q", REPO_DIR], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "--bare", origin], check=True, capture_output=True)
    subprocess.run(["git", "-C", REPO_DIR, "remote", "add", "origin", origin], check=True, capture_output=True)
    # The session home record of probe-session-1: its worktree is gone, so the session-home rule judges its calls.
    home_records = os.path.join(REPO_DIR, ".git", "session-homes")  # the guard's SESSION_HOME_DIR, under the clone's .git
    os.makedirs(home_records)
    with open(os.path.join(home_records, "probe-session-1"), "w", encoding="utf-8") as f:
        f.write(os.path.join(RUN, "gone-lane"))
    # The waiting page of this fixture repo: the page rules judge an ArtifactData write only on the page the repo names.
    os.makedirs(os.path.join(REPO_DIR, ".claude"))
    with open(os.path.join(REPO_DIR, ".claude", "layout-extras.json"), "w", encoding="utf-8") as f:
        json.dump({"kinds": {}, "waiting-page": PAGE_URL}, f)
    # A lane worktree of the fixture repo: a worktree needs a commit to start from.
    subprocess.run(["git", "-C", REPO_DIR, "-c", "user.name=probe", "-c", "user.email=probe@example.invalid",
                    "commit", "-q", "--allow-empty", "-m", "probe"], check=True, capture_output=True)
    LANE_DIR = os.path.join(RUN, "lane")
    subprocess.run(["git", "-C", REPO_DIR, "worktree", "add", "-q", "--detach", LANE_DIR], check=True,
                   capture_output=True)
    # An upstream on the fixture's branch: a push with an implied destination off it is what push-stray-branch asks about.
    current = subprocess.run(["git", "-C", REPO_DIR, "symbolic-ref", "--short", "HEAD"], check=True,
                             capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", REPO_DIR, "update-ref", "refs/remotes/origin/lane-x", "HEAD"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", REPO_DIR, "config", "branch.%s.remote" % current, "origin"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", REPO_DIR, "config", "branch.%s.merge" % current, "refs/heads/lane-x"], check=True,
                   capture_output=True)
    # The stamp probe restamps a premise, so the guard needs a dated handoff on disk and a transcript to read.
    os.makedirs(os.path.join(CFG, "handoffs"))
    with open(os.path.join(CFG, "handoffs", "probe-stamp.md"), "w", encoding="utf-8") as f:
        f.write(full_handoff(PREMISE_DATED))
    with open(os.path.join(RUN, "transcript.jsonl"), "w", encoding="utf-8"):
        pass


def session_payload(body, cwd):
    """A call from a session, not an agent, in `cwd`: the session id the session-home rule reads."""
    body = dict(body, session_id="probe-session-1")
    body["cwd"] = cwd
    return body


REMEDY_PROBES.update({
    "pointer-edit": [("a write in a worktree of your own under the pointer checkout", tool_payload(
        "Write", {"file_path": "<POINTER_LANE>/notes.md", "content": "probe"}), "inside that worktree")],
    "pointer-head": [("git -C on a worktree of your own, not the pointer checkout's HEAD", bash_payload(
        "git -C <POINTER_LANE> checkout -b probe-lane-branch"), "git -C <that worktree>")],
    "session-home": [("a write inside the worktree the session makes, from the primary checkout's cwd",
                      session_payload(tool_payload("Write", {"file_path": "<REPO>/.claude/worktrees/probe-lane/notes.md",
                                                             "content": "probe"}), "<REPO>"),
                      "write inside that worktree")],
    "hand-made-worktree": [("a red-run checkout, its path written out in full under the primary's worktrees folder",
                            bash_payload("git worktree add --detach <REPO>/.claude/worktrees/probe-red HEAD", "<REPO>"),
                            "write its path out in full")],
    "process-args": [("ps by pid and command name", bash_payload("ps -o pid,comm"), "ps -o pid,comm")],
    "git-env-set": [("git -C with the repo path", bash_payload("git -C <REPO> status"), "git -C <dir>")],
    "two-worktrees-one-branch": [("git -C on the own checkout", bash_payload("git -C <REPO> status"),
                                  "git -C <own worktree>")],
    "shared-tree": [("git stash list, a read", bash_payload("git stash list", "<REPO>"), "git stash list"),
                    ("git worktree list, the read the prune Remedy names", bash_payload("git worktree list", "<REPO>"),
                     "git worktree list"),
                    ("a per-file discard in the session's own lane worktree, with no cd", bash_payload(
                        "git -C <LANE> restore probe.txt", "<LANE>"), "git -C <lane> restore")],
    "other-checkout": [("git -C log of another clone", bash_payload("git -C <REPO> log -1", "<RUN>"),
                        "git -C <dir> log")],
    "verdict-pipe": [("verdict with nothing after it", bash_payload("verdict python3 hooks/test_guard.py"),
                      "verdict <cmd>")],
    "check-tail": [("verdict with nothing after it", bash_payload("verdict python3 hooks/test_guard.py"),
                    "verdict <cmd>")],
    "force-push": [("push with --force-with-lease", bash_payload(
        "git push --force-with-lease --force-if-includes origin HEAD:probe-branch", "<REPO>"), "--force-with-lease"),
        ("the lane's own branch, by name, with a lease", bash_payload(
            "git push --force-with-lease --force-if-includes origin HEAD:lane-probe", "<REPO>"), "--force-with-lease")],
    "push-agent-branch": [("push the lane's branch by name", bash_payload(
        "git push origin HEAD:lane-probe", "<REPO>"), "git push origin HEAD:<lane-branch>")],
    "push-all-main": [("push the lane's branch by name", bash_payload(
        "git push origin HEAD:lane-probe", "<REPO>"), "git push origin HEAD:<lane-branch>")],
    "agent-role-model": [("a builder on its role's model", tool_payload(
        "Agent", {"subagent_type": "builder", "model": "sonnet", "prompt": "probe", "description": "probe"}),
        "name the role's model")],
    "agent-model-cap": [("a builder on its role's model", tool_payload(
        "Agent", {"subagent_type": "builder", "model": "sonnet", "prompt": "probe", "description": "probe"}),
        "name the role's model")],
    "waiter": [("wait until a clock time with bin/wait-until", bash_payload(
        "bin/wait-until 2099-01-01T00:00:00Z"), "bin/wait-until")],
    "background-end": [("a background job with an until note", tool_payload(
        "Bash", {"command": "echo done", "run_in_background": True, "description": "until: probe done"}),
        "until: <condition>")],
    "playwright-browsers-path": [("pgrep -f, which prints pids only", bash_payload("pgrep -f playwright"),
                                  "pgrep -f playwright")],
    "machine-wide-kill": [("kill of the pid this launch printed", bash_payload("kill $!"), "stop that one process")],
    "destructive-delete": [("delete of one named directory", bash_payload("rm -rf build", "<RUN>"),
                            "name the one directory you mean")],
    "ln-over-directory": [("ln -sfn, with -n beside -f", bash_payload("ln -sfn target linkname", "<RUN>"),
                           "add -n beside -f")],
    "scratchpad-commit-msg-owner": [("a commit with -m", bash_payload("git commit -m probe", "<REPO>"),
                                     "with `-m`")],
    "hook-bypass": [("a commit with the hooks on", bash_payload("git commit -m probe", "<REPO>"),
                     "the repo's own hooks on")],
    "env-file": [("node with --env-file ahead of it", bash_payload(
        "node --env-file=.env.local tool.mjs", "<RUN>"), "--env-file")],
})


def agent_payload(body):
    """A call from a scratchpad agent: the agent and session ids the scratchpad-owner rule reads."""
    body = dict(body)
    body["agent_id"] = "probe-agent"
    body["session_id"] = "probe-session-1"
    return body


def handoff_sections():
    """The required handoff sections, read from the prompt's own marker line: the list the guard reads."""
    with open(os.path.join(REPO, "hooks", "precompact_handoff_prompt.md"), encoding="utf-8") as f:
        marker = re.search(r"<!--[ \t]*handoff-sections:[ \t]*(.*?)[ \t]*-->", f.read())
    return [s.strip() for s in marker.group(1).split("|")]


def full_handoff(premise):
    """A handoff with every required section, its premise line under Working premises."""
    return "\n\n".join("## %s\n\n%s" % (s, premise if s == "Working premises" else "probe")
                       for s in handoff_sections()) + "\n"


def handoff_write(sid, text, transcript=None):
    body = tool_payload("Write", {"file_path": "<CFG>/handoffs/%s.md" % sid, "content": text})
    body["session_id"] = sid
    if transcript:
        body["transcript_path"] = transcript
    return body


PREMISE_DATED = "- P1 [read] Probe premise. Source: probe. Checked 2026-11-01."
PREMISE_NEVER = "- P1 [assumed] Probe premise. Source: probe. Checked never."
# Under the session scratchpad path the scratchpad-owner rule judges: <tmp>/<session id>/scratchpad.
SCRATCH_COPY = "<TMP>/claude/probe-session-1/scratchpad/fresh-copy.py"

REMEDY_PROBES.update({
    "cite-by-id": [("a commit with its message inline", bash_payload('git commit -m "probe"', "<REPO>"),
                    "pass the message inline"),
                   ("a commit that names the lane by its slug", bash_payload(
                       'git commit -m "lane-number-cite: probe"', "<REPO>"), "its slug")],
    "lane-by-slug": [("a commit that names the lane by its slug", bash_payload(
        'git commit -m "lane-number-cite: probe"', "<REPO>"), "name the lane by its branch slug")],
    "conflict-markers": [("a push in a call of its own", bash_payload("git push origin HEAD:lane-probe", "<REPO>"),
                          "run the push in a call of its own")],
    "octopus-push": [("a push of one branch", bash_payload("git push origin HEAD:lane-probe", "<REPO>"),
                      "retry the push")],
    "detached-launch": [("a launch with its pid captured by echo $!", bash_payload("echo probe & echo $!"),
                         "cmd & echo $!")],
    "frozen-path": [("a write to a file in the clone", tool_payload(
        "Write", {"file_path": "<REPO>/notes.md", "content": "probe"}), "edit the clone")],
    "handoff-sections": [("a handoff with every required section", handoff_write(
        "probe-sections", full_handoff(PREMISE_NEVER)), "write the whole handoff again")],
    "handoff-checked-stamp": [("a handoff that restamps a premise as Checked never", handoff_write(
        "probe-stamp", full_handoff(PREMISE_NEVER), "<RUN>/transcript.jsonl"), "write `Checked never` on it")],
    "linked-node-modules": [("the repo's setup script", bash_payload("npm run setup", "<REPO>"), "npm run setup")],
    "live-stream": [("a command redirected to a file that is read back", bash_payload(
        "node tool.mjs > out.log", "<RUN>"), "run the command in the foreground"),
        ("a command with nothing after it", bash_payload("node tool.mjs", "<RUN>"),
         "run the command with nothing after it")],
    "merge-checks": [("the merge tool with --confirm", bash_payload("merge 123 --confirm"), "merge <pr> --confirm")],
    "records-page": [("a commit that leaves the records page out", bash_payload('git commit -m "probe"', "<REPO>"),
                      "drop the page from this commit")],
    "records-page-ready": [("return the pull request to draft", tool_payload(
        "mcp__github__update_pull_request", {"owner": "probe", "repo": "probe", "pullNumber": 1, "draft": True}),
        "return the pull request to draft")],
    "scratchpad-owner": [
        ("a write under a fresh name in the session's own scratchpad", agent_payload(tool_payload(
            "Write", {"file_path": SCRATCH_COPY, "content": "probe"})), "under a fresh file name"),
        ("a run of that fresh copy", agent_payload(bash_payload("python3 %s" % SCRATCH_COPY, "<TMP>")),
         "run that copy")],
    "silent-write": [("the push with its output kept, ending 2>&1 | tail -1", bash_payload(
        "git push origin HEAD:lane-probe 2>&1 | tail -1", "<REPO>"), "2>&1 | tail -1")],
})

# ---- the spawn, lane, role, page and shell rules: each act is the one its Remedy names, judged as allowed.

GET_SESSION = "mcp__claude-code-remote__get_session"
CREATE_SESSION = "mcp__claude-code-remote__create_session"
LANE_START = tool_payload(CREATE_SESSION, {
    "prompt": "Grant: the owner said to run the probe lane, 2026-11-12 10:00 CST\n"
              "Lane brief: probe-step. Topic: probe-topic.\nRun the probe and report.",
    "effort": "medium", "model": "sonnet", "source_url": "https://github.com/probe/probe",
    "tags": ["cs-build:lane", "cs-repo:probe/probe", "cs-topic:probe-topic"]})
EDIT_PRODUCT = {"file_path": "<REPO>/src/app.py", "old_string": "a", "new_string": "b"}


def brief_spawn(prompt, role="builder", model="sonnet"):
    return tool_payload("Agent", {"subagent_type": role, "model": model, "prompt": prompt, "description": "probe"})


def role_payload(role, tool, tool_input):
    """A call from an agent of one role, in the fixture repo: the agent type and id the role rules read."""
    body = tool_payload(tool, tool_input)
    body.update(agent_id="probe-agent", agent_type=role, session_id="probe-session-1", cwd="<REPO>")
    return body


# A waiting-page decision that every page rule passes: the form lines, a Departs from line, a stake on the
# Problem line, and a gain and a lose on each option.
PAGE_OPTIONS = [{"key": "a", "label": "Ship it", "how": "Merge it.", "gain": "g", "lose": "l"},
                {"key": "b", "label": "Wait", "how": "Do nothing yet.", "gain": "g", "lose": "l"}]
PAGE_CONTEXT = ("Goal: keep the guard honest.\nProblem (risk): the probe needs his word.\n"
                "Based on (read): the probe ran.\nDeparts from: main — adds a probe check.\nThe probe checks the guard.")
PAGE_PRESS_OPTION = dict(PAGE_OPTIONS[0], label="Merge home#374 yourself", how="Mark home#374 ready and press Merge.",
                         links=[{"label": "home#374 on GitHub", "url": "https://github.com/shivinate7/home/pull/374"}])
PAGE_TASK = {"id": "probe-item", "kind": "task", "status": "open", "title": "Probe the guard",
             "steps": ["Open Terminal", "Paste the command below and run it"],
             "command": {"powershell": "git status", "mac": "git status"},
             "context": "Why yours: a session on your computer was asked first and none could reach the remote "
                        "(measured 2026-11-12, the check ran and refused)."}


def page_item(**over):
    item = {"id": "probe-item", "kind": "decision", "status": "open", "title": "Ship the probe?",
            "context": PAGE_CONTEXT, "options": PAGE_OPTIONS}
    item.update(over)
    return item


def page_write(data, action="set"):
    """One ArtifactData write of a waiting item to the fixture repo's waiting page."""
    return page_payload({"action": action, "data": data})


REMEDY_PROBES.update({
    "agent-no-remote-tools": [("the agent's own shell work, not a remote call",
                               agent_payload(bash_payload("git status", "<REPO>")), "put the request in your report")],
    "agent-model-floor": [("an Agent spawn on sonnet", brief_spawn("probe"), "model sonnet"),
                          ("a lane start on sonnet with its source_url", LANE_START, "model sonnet")],
    "ask-alone": [("the force push with --force-if-includes, alone in its call", bash_payload(
        "git push --force-with-lease --force-if-includes origin HEAD:probe-branch", "<REPO>"), "Run that command alone")],
    "brief-claim-has-probe": [("a builder brief that carries the probe under its claim", brief_spawn(
        "Keep the scan as it is.\nmain allows `port: 0`.\n```\n$ python3 hooks/probe_main.py 'port: 0'\nallowed\n```"),
        "add the probe")],
    "brief-destructive-git": [("a brief that orders tests only", brief_spawn(
        "Run the tests and report the result. Discard nothing."), "drop the order from the brief")],
    "command-in-item": [("a task whose command is set for both shells", page_write(PAGE_TASK),
                         "Put the command in the item's")],
    "designer-scope": [("a designer's Write in the design folder", role_payload("designer", "Write", {
        "file_path": "<REPO>/docs/design/probe-mockup.html", "content": "probe"}), "change only files in that folder")],
    "draft-pr": [("create_pull_request with draft true", tool_payload("mcp__github__create_pull_request", {
        "owner": "probe", "repo": "probe", "title": "probe", "head": "lane-probe", "base": "main", "body": "probe",
        "draft": True}), "draft")],
    "gh-login-switch": [("a task whose command switches the gh login first", page_write(dict(PAGE_TASK, command={
        "powershell": "gh auth switch -u shivinate7; gh pr view 1",
        "mac": "gh auth switch -u shivinate7 && gh pr view 1"})), "gh auth switch -u")],
    "impeccable-review-only": [("the impeccable skill with audit as its first word", tool_payload(
        "Skill", {"skill": "impeccable", "args": "audit <screen>"}), "as the first word of its args")],
    "item-field-rendered": [("an item whose fields the page draws", page_write(page_item()), "Draw the field on the page")],
    "lane-effort-pin": [("a lane start at medium, its Grant line first", LANE_START, "put the Grant line first")],
    "lane-one-topic": [("a lane start whose cs-topic tag holds its brief's topic", LANE_START,
                        "a cs-topic tag that matches")],
    "lane-repo-tag": [("a lane start with the full cs-repo tag", LANE_START, "to the lane's tags")],
    "lane-start-settings": [("a lane start with its model and source_url", LANE_START, "on create_session")],
    "message-time-matches-clock": [("the clock read with now-central", bash_payload(
        "~/.claude/bin/now-central", "<REPO>"), "~/.claude/bin/now-central")],
    "mockup-home": [("a design whose file is a mockup in the design folder", page_write(page_item(designs=[
        {"id": "d1", "file": "docs/design/probe-mockup.html", "label": "d1"}])), "a mockup committed in that folder")],
    "option-letter-keys": [("options keyed a and b in the order shown", page_write(page_item()), "in the order shown")],
    "owner-judge": [("a decision whose Problem line names a stake", page_write(page_item()),
                     "Write the Problem line as")],
    "page-thread-reply": [("the item rewritten, the act the Remedy names", page_write(
        page_item(context=PAGE_CONTEXT + "\nRewritten after the comment.")), "rewrite the item the comment is about")],
    "playwright-install": [("the playwright install under node 22", bash_payload(
        "npx -y node@22 node_modules/playwright/cli.js install", "<REPO>"),
        "npx -y node@22 node_modules/playwright/cli.js install")],
    "port-question": [("a port item with its Departs from line", page_write(page_item(port=True)), "Departs from:")],
    "press-link": [("a press option with its link", page_write(page_item(options=[PAGE_PRESS_OPTION, PAGE_OPTIONS[1]])),
                    "an https:// url of the page where he presses")],
    "question-checked-with-repo": [("a question on this repo, named by its repo field", page_write(
        page_item(repo="probe/probe")), "add `repo`")],
    "question-departs": [("a Departs from line with both sides filled", page_write(page_item()), "Departs from:")],
    "question-form": [("a decision in the form, a gain and a lose on each option", page_write(page_item()),
                       "On the waiting page the lines go in")],
    "record-writer-scope": [("a record writer's Write of a Markdown file", role_payload("record-writer", "Write", {
        "file_path": "<REPO>/docs/probe-record.md", "content": "probe"}), "change only *.md files")],
    "rework-off-page": [("an item closed with a home that names the rework", page_write(page_item(
        status="closed", home="rework of probe-item",
        context=PAGE_CONTEXT + "\nThe item is being reworked; the fresh item carries the options.")),
        "Close the item with a home that names the rework")],
    "rm-after-cd": [("a recursive delete with no cd before it, the target a full path", bash_payload(
        "rm -rf /tmp/w/out", "<REPO>"), "give the target as a full path")],
    "rm-var-unguarded": [("a variable written as ${NAME:?}", bash_payload('D=/tmp/w; rm -rf "${D:?}"/old', "<RUN>"),
                          "write every expansion as ${NAME:?}"),
                         ("a literal path", bash_payload("rm -rf /srv/build/out", "<RUN>"),
                          "run the delete with a literal path")],
    "roadmap-one-writer": [("get_session with no argument", tool_payload(GET_SESSION, {}),
                            "get_session (no argument) alone")],
    "roles-third-round-steps-up": [("a reviewer's second round on sonnet", brief_spawn(
        "Round 2 of 3. Review the diff.", role="reviewer"), "spawn it with model sonnet")],
    "sendmessage-session-id": [
        ("a session's send_message with the id as session_id", tool_payload(
            "mcp__claude-code-remote__send_message", {"session_id": "session_probe", "message": "probe"}),
         "send_message"),
        ("agents cannot call send_message; the Remedy says report to parent", None, "final report")],
    "simulator-boot-bypass": [("sim-test, which takes the lock and boots", bash_payload(
        "sim-test -scheme Probe", "<REPO>"), "sim-test -scheme")],
    "task-why-cited": [("a Why yours line that ends in a measured cite", page_write(PAGE_TASK), "End the line with")],
    "test-author-scope": [("a test author's Write of a test file", role_payload("test-author", "Write", {
        "file_path": "<REPO>/tests/test_probe.py", "content": "probe"}), "write only tests and test config")],
    "trust-card-in-build": [("get_session with no argument", tool_payload(GET_SESSION, {}),
                             "get_session (no argument) alone")],
    "uniform-pick": [("an item with no pick", page_write(page_item()), "leave pick out")],
    "workflow-args-shape-check": [("a Workflow started with a real value", tool_payload(
        "Workflow", {"script": "probe", "args": {"repo": "probe/probe"}}), "Replace it with the real value")],
    "wsl-allow-list": [("wsl with -e and a python script", bash_payload("wsl -e python3 hooks/test_guard.py", "<REPO>"),
                        "wsl -e python3 <dir>/test_<name>.py")],
})

# ---- the ask reasons the scan reads through ask_command's queue: each act is the one its Remedy names.
REMEDY_PROBES.update({
    # A network remote is the one the guard judges by its URL: a push to main asks there, and the local origin never does.
    "push-main": [("the lane's own branch, by name", bash_payload("git push origin HEAD:lane-probe", "<REPO>"),
                   "git push origin HEAD:<lane-branch>"),
                  ("the lane's own branch, by name, on a network remote", bash_payload(
                      "git push https://github.com/probe/probe.git HEAD:lane-probe", "<REPO>"),
                   "git push origin HEAD:<lane-branch>")],
    "push-stray-branch": [("the destination named, as the Remedy says", bash_payload(
        "git push origin HEAD:lane-probe", "<REPO>"), "name the destination")],
    "bare-merge": [("the merge tool with --confirm", bash_payload("merge 123 --confirm"), "merge <pr> --confirm")],
})

REMEDY_PROSE_ONLY.update({
    "worktree-home": "the Remedy is to stop and report to the orchestrator: no tool call is the act",
    # A builder's Edit of a product file is allowed, but the Remedy names a report to the orchestrator, not an edit.
    "builder-diff": "the Remedy's act is a report of the test change to the orchestrator, which no tool call is",
    "builder-test-edit": "the Remedy's act is a report of the test change to the orchestrator, which no tool call is",
    # The Remedy names the GitHub MCP tools and the merge tool. The rule judges only a Bash gh write in a cloud
    # session, and no act the Remedy names is one, so the guard judges none of them under this rule.
    "gh-write-cloud": "the Remedy names GitHub MCP tools and the merge tool, and the rule judges only a Bash gh write "
                      "in a cloud session: no act the Remedy names is one",
    "task-names-check": "the Remedy's first act is to ask the owner, or to hand the task to a session with no cs-build "
                        "tag: cs-build refuses request_computer_folder, so no cs-build session can make that ask, and "
                        "the guard never judges it",
    # The next three are model judges or their own hooks. guard.py does not run them, and run_guard drives only guard.py.
    "blind-brief": "the check is hooks/blind_brief.py's own hook, which guard.py does not run; hooks/test_blind_brief.py "
                   "judges the refusal in-process",
    "prose-judge": "the verdict is a model's (hooks/prose_judge.py), and this fixture makes no model call; "
                   "hooks/test_prose_judge.py judges the refusal in-process",
    "parallelism-no-mid-task-talk": "the verdict is a model's (the wording judge and the busy check in "
                                    "hooks/sendmessage_state.py), which run as their own hook, not in guard.py; "
                                    "hooks/test_sendmessage_state.py judges them in-process",
    # The Remedy's act is a Read. The guard never judges a Read, and the check clears on the read itself, outside
    # the guard, so no guard call can prove the Remedy. A probe here would pass whatever the Read did.
    "handoff-unread": "the Remedy's act is a Read, which the guard never judges: the read clears the check outside "
                      "the guard, so no guard call can prove it",
    "lane-closes-after-records": "the act is get_session on the target and then the archive again, and the archive's check "
                                 "reads the lane's records from its transcript, which this fixture does not stage",
    "load-brake": "the Remedy's act is to end the turn and send the reading to the parent: no tool call the guard judges",
    "merge-confirm-repo": "the act is get_session in this session's own turn, and the check reads the live session's "
                          "tags and the pull request, which this fixture does not stage",
    "merge-role-proof": "the act is get_session in the batch runner's own turn, or a review record on the pull request; "
                        "the check reads the live session and the pull request, which this fixture does not stage",
    "page-item-design": "the check reads the live waiting page to see the republished design, and this fixture holds "
                        "no live page",
    "page-stale": "the check compares the publish file with main's page.html and with the live page, and neither is "
                  "staged here",
    "past-ruling": "the question judge checks the question against the records with a model call, which this fixture "
                   "does not make",
    "question-judge": "the verdict is a model's (call_judge), and this fixture makes no model call",
    "spawn-judge": "the verdict is a model's (call_judge), and this fixture makes no model call",
    "simulator-boot-cap": "the rule reads the booted simulators through janitor sweep, which needs xcrun, and this "
                          "Linux fixture has none",
    "simulator-boot-lease": "the rule reads the booted simulators through janitor sweep, which needs xcrun, and this "
                            "Linux fixture has none",
    "simulator-boot-route": "the rule reads the booted simulators through janitor sweep, which needs xcrun, and this "
                            "Linux fixture has none",
    "simulator-boot-twin": "the rule reads the booted simulators through janitor sweep, which needs xcrun, and this "
                           "Linux fixture has none",
})


def tearDownModule():
    if RUN:
        shutil.rmtree(RUN, ignore_errors=True)


def run_guard(body):
    """(decision, reason) the guard prints for one payload, judged the way the guard suite judges it.
    <REPO>, <RUN>, <CFG>, <LANE>, <POINTER>, <POINTER_LANE> and <TMP> in the payload stand for this run's fixture folders."""
    text = (json.dumps(body).replace("<REPO>", REPO_DIR).replace("<RUN>", RUN).replace("<CFG>", CFG)
            .replace("<LANE>", LANE_DIR).replace("<POINTER_LANE>", POINTER_LANE)
            .replace("<POINTER>", POINTER_DIR).replace("<TMP>", TMP))
    body = json.loads(text)
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR",
                 "CLAUDE_CODE_REMOTE"):
        env.pop(name, None)
    env.update({
        "CLAUDE_CONFIG_DIR": CFG,
        "CLAUDE_GUARD_ROOT_PID": str(os.getpid()),
        "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet",
        "TMPDIR": TMP, "TEMP": TMP, "TMP": TMP,
    })
    result = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True,
                            text=True, env=env, timeout=120, cwd=RUN)
    if result.returncode != 0:
        return "error", "exit %d: %s" % (result.returncode, result.stderr.strip()[:200])
    out = result.stdout.strip()
    if not out:
        return "allow", ""
    try:
        parsed = json.loads(out)
        if parsed.get("decision") == "block":
            return "deny", parsed["reason"]
        block = parsed["hookSpecificOutput"]
        return block["permissionDecision"], block["permissionDecisionReason"]
    except Exception:
        return "unparsable", out[:200]


# ------------------------------------------------------------------ the tests

class StaticRemedyTest(unittest.TestCase):

    def test_every_refuse_site_names_a_remedy(self):
        # No rule is exempt: a site without a Remedy fails, whatever its rule.
        sites = scan()
        self.assertGreaterEqual(len(sites), MIN_SITES,
                                "the scan found %d refuse sites, fewer than %d: the scan lost sites"
                                % (len(sites), MIN_SITES))
        lacking = [s for s in sites if not s.has_remedy]
        if lacking:
            lines = ["  %s  rule %s  reason %s" % (s.where(), "/".join(s.rules), s.reason_src) for s in lacking]
            self.fail("%d of %d refuse sites carry no %r in their reason:\n%s"
                      % (len(lacking), len(sites), REMEDY, "\n".join(lines)))


class CoverageTest(unittest.TestCase):

    def remedy_rules(self):
        return {rule for s in scan() if s.has_remedy for rule in s.rules}

    def test_each_remedy_rule_has_a_probe_or_a_prose_reason(self):
        uncovered = sorted(self.remedy_rules() - set(REMEDY_PROBES) - set(REMEDY_PROSE_ONLY))
        if uncovered:
            self.fail("%d rule(s) carry a Remedy but are in neither REMEDY_PROBES nor REMEDY_PROSE_ONLY: %s"
                      % (len(uncovered), ", ".join(uncovered)))

    def test_each_table_entry_is_a_rule_that_has_a_remedy(self):
        stale = sorted((set(REMEDY_PROBES) | set(REMEDY_PROSE_ONLY)) - self.remedy_rules())
        both = sorted(set(REMEDY_PROBES) & set(REMEDY_PROSE_ONLY))
        blank = sorted(rule for rule, why in REMEDY_PROSE_ONLY.items() if not why.strip())
        all_prose = sorted(rule for rule, rows in REMEDY_PROBES.items() if rows and all(body is None for _, body, _ in rows))
        problems = []
        if stale:
            problems.append("table entries name no refuse site with a Remedy: %s" % ", ".join(stale))
        if both:
            problems.append("a rule is in both tables: %s" % ", ".join(both))
        if blank:
            problems.append("REMEDY_PROSE_ONLY gives no reason for: %s" % ", ".join(blank))
        if all_prose:
            problems.append("these rules have only prose rows, so they belong in REMEDY_PROSE_ONLY: %s"
                            % ", ".join(all_prose))
        if problems:
            self.fail("; ".join(problems))


def normal(text):
    """The text with every run of whitespace folded to one space, so a token matches across a source line break."""
    return " ".join(text.split())


def remedy_text(rule):
    """The Remedy text the scan resolves for a rule, from every site that names it."""
    return normal(" ".join(p for s in scan() if rule in s.rules for p in s.remedies))


class ProbeTest(unittest.TestCase):

    def test_each_probe_names_a_token_its_remedy_holds(self):
        # The probe is bound to the act its Remedy names: the token is a word of that Remedy. A prose row names its
        # reason in the act field, so a blank reason fails here too.
        problems = []
        for rule in sorted(REMEDY_PROBES):
            text = remedy_text(rule)
            for act, _body, token in REMEDY_PROBES[rule]:
                if not act.strip():
                    problems.append("%s: a probe row has no act or reason" % rule)
                if not normal(token) or normal(token) not in text:
                    problems.append("%s: the probe %r names %r, which its Remedy does not hold" % (rule, act, token))
        if problems:
            self.fail("%d probe row(s) do not name an act of their Remedy:\n  %s"
                      % (len(problems), "\n  ".join(problems)))

    def test_each_remedy_names_an_act_the_guard_allows(self):
        for rule in sorted(REMEDY_PROBES):
            for act, body, _token in REMEDY_PROBES[rule]:
                if body is None:  # a prose row: its reason says why no runnable act proves the Remedy
                    continue
                with self.subTest(rule=rule, act=act):
                    got, reason = run_guard(body)
                    if got not in ("allow", "deny", "ask"):  # a guard that crashed answers nothing: never a pass
                        self.fail("the guard did not answer the act (%s): %s %s" % (act, got, reason[:160]))
                    if got in ("deny", "ask") and reason.startswith(rule + ":"):
                        self.fail("%s refuses the act its Remedy names (%s): %s" % (rule, act, reason[:160]))


class HygieneTest(unittest.TestCase):

    def test_remedy_never_names_the_forbidden_target(self):
        forbidden, may_name = one_home_reason_rules()
        if len(forbidden) < 5:  # the list holds at least its paths and commands: fewer means it was read wrong
            self.fail("the forbidden list read from %s has %d fragments" % (ONE_HOME, len(forbidden)))
        problems = []
        for s in scan():
            for rule in s.rules:
                permitted = may_name.get(rule, ())
                for piece in s.remedies:
                    for fragment in forbidden:
                        if fragment and fragment not in permitted and fragment in piece:
                            problems.append("%s rule %s names %r in its Remedy" % (s.where(), rule, fragment))
        if problems:
            self.fail("%d Remedy text(s) name a forbidden target:\n  %s"
                      % (len(problems), "\n  ".join(sorted(set(problems)))))


if __name__ == "__main__":
    unittest.main()
