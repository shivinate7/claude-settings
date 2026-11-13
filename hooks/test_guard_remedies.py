#!/usr/bin/env python3
"""Every guard refusal and ask names an allowed way out, and a test proves each way out is allowed.

Run it from the repository root:

    python3 hooks/test_guard_remedies.py -v

The scan reads the source with ast, so no guard module is imported here (importing hooks/test_guard.py
alone takes minutes). Five test methods in three groups:

1. STATIC: each refuse() site in hooks/guard*.py, and each call of call_judge.py's refuse() wrapper,
   resolves to a reason that carries "Remedy:". The resolution follows local names (the nearest assignment
   above the use), module constants, imported constants, dict lookups, helper returns, appended values and
   the arguments a helper's return names. An unresolvable reason counts as lacking.
2. PROBES: each rule that has a Remedy is in REMEDY_PROBES, with the allowed act its Remedy names, or in
   REMEDY_PROSE_ONLY, with the reason no runnable act exists. Each probe runs through the guard, which must
   answer, and must not refuse or ask it under that rule. The table entries are checked against the scan.
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
# The argument positions of (rule, reason). guard_core.refuse(tool, decision, rule, reason, matched, ...) in
# hooks/guard*.py, and call_judge.refuse(payload, tool, args, rule, reason), its own wrapper.
GUARD_SHAPE = (2, 3)
WRAPPER_SHAPE = (3, 4)
# 117 refuse sites in hooks/guard*.py on main, plus 3 in call_judge.py. Fewer than this means the scan lost
# sites, not that the guard is clean.
MIN_SITES = 50
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


def sites_in(mod, shape):
    rule_i, reason_i = shape  # the decision is not read: a Remedy is owed on a deny and on an ask alike
    out = []
    for node in ast.walk(mod.tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "refuse"):
            continue
        rule_node, reason_node = call_arg(node, rule_i, "rule"), call_arg(node, reason_i, "reason")
        rule_trail = Trail()
        if rule_node is not None:
            text_of(mod, rule_node, rule_trail, rule=True)
        rules = sorted({s for s in rule_trail.strings if RULE_RE.fullmatch(s)})
        if not rules:
            rules = ["<%s>" % (ast.unparse(rule_node)[:50] if rule_node is not None else "missing")]
        reason_trail = Trail()
        if reason_node is not None:
            text_of(mod, reason_node, reason_trail)
        out.append(Site(mod.path, node.lineno, rules,
                        ast.unparse(reason_node)[:80] if reason_node is not None else "<no reason argument>",
                        reason_trail.strings))
    return out


SCANNED = []


def scan():
    """Every refuse() site of hooks/guard*.py and call_judge.py's wrapper, read with ast. Read once per run."""
    if not SCANNED:
        sites = []
        for path in sorted(glob.glob(os.path.join(HERE, "guard*.py"))):
            mod = load(os.path.splitext(os.path.basename(path))[0])
            sites += sites_in(mod, GUARD_SHAPE)
        sites += sites_in(load("call_judge"), WRAPPER_SHAPE)
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

# rule -> [(what the act is, payload)]. Each payload is the body the guard reads on stdin, as test_guard.py
# builds it: tool_name, tool_input, and cwd when a case names one. Each act is one the Remedy tells the
# session to do; the guard must not refuse or ask it under that rule. The guard decides; it runs nothing.
# <REPO> and <RUN> stand for the fixture folders, which exist only once the module runs.
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


def setUpModule():
    global RUN, CFG, REPO_DIR
    RUN = _test_temp.run_folder()
    CFG = os.path.join(RUN, "cfg")
    os.makedirs(CFG)
    REPO_DIR = os.path.join(RUN, "repo")
    os.makedirs(REPO_DIR)
    # A readable origin: a forced push is judged against its remote, so without one the guard reads the target
    # as unreadable and refuses even the lease form the Remedy names.
    origin = os.path.join(RUN, "origin.git")
    subprocess.run(["git", "init", "-q", REPO_DIR], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "--bare", origin], check=True, capture_output=True)
    subprocess.run(["git", "-C", REPO_DIR, "remote", "add", "origin", origin], check=True, capture_output=True)
    # The waiting page of this fixture repo: the page rules judge an ArtifactData write only on the page the repo names.
    os.makedirs(os.path.join(REPO_DIR, ".claude"))
    with open(os.path.join(REPO_DIR, ".claude", "layout-extras.json"), "w", encoding="utf-8") as f:
        json.dump({"kinds": {}, "waiting-page": PAGE_URL}, f)
    # The stamp probe restamps a premise, so the guard needs a dated handoff on disk and a transcript to read.
    os.makedirs(os.path.join(CFG, "handoffs"))
    with open(os.path.join(CFG, "handoffs", "probe-stamp.md"), "w", encoding="utf-8") as f:
        f.write(full_handoff(PREMISE_DATED))
    with open(os.path.join(RUN, "transcript.jsonl"), "w", encoding="utf-8"):
        pass


ENTER = tool_payload("EnterWorktree", {"name": "probe-lane"})
REMEDY_PROBES.update({
    "pointer-edit": [("EnterWorktree with a name", ENTER)],
    "pointer-head": [("EnterWorktree with a name", ENTER)],
    "session-home": [("EnterWorktree with a name", ENTER)],
    "hand-made-worktree": [("EnterWorktree with a name", ENTER)],
    "process-args": [("ps by pid and command name", bash_payload("ps -o pid,comm"))],
    "git-env-set": [("git -C with the repo path", bash_payload("git -C <REPO> status"))],
    "two-worktrees-one-branch": [("git -C on the own checkout", bash_payload("git -C <REPO> status"))],
    "shared-tree": [("git stash list, a read", bash_payload("git stash list", "<REPO>"))],
    "other-checkout": [("git -C log of another clone", bash_payload("git -C <REPO> log -1", "<RUN>"))],
    "verdict-pipe": [("verdict with nothing after it", bash_payload("verdict python3 hooks/test_guard.py"))],
    "check-tail": [("verdict with nothing after it", bash_payload("verdict python3 hooks/test_guard.py"))],
    "force-push": [("push with --force-with-lease", bash_payload(
        "git push --force-with-lease --force-if-includes origin HEAD:probe-branch", "<REPO>"))],
    "push-agent-branch": [("push the lane's branch by name", bash_payload(
        "git push origin HEAD:lane-probe", "<REPO>"))],
    "push-all-main": [("push the lane's branch by name", bash_payload(
        "git push origin HEAD:lane-probe", "<REPO>"))],
    "gh-write-cloud": [("a GitHub MCP comment", tool_payload(
        "mcp__github__add_issue_comment", {"owner": "probe", "repo": "probe", "issue_number": 1, "body": "probe"}))],
    "agent-role-model": [("a builder on its role's model", tool_payload(
        "Agent", {"subagent_type": "builder", "model": "sonnet", "prompt": "probe", "description": "probe"}))],
    "agent-model-cap": [("a builder on its role's model", tool_payload(
        "Agent", {"subagent_type": "builder", "model": "sonnet", "prompt": "probe", "description": "probe"}))],
    "waiter": [("wait until a clock time with bin/wait-until", bash_payload(
        "bin/wait-until 2099-01-01T00:00:00Z"))],
    "background-end": [("a background job with an until note", tool_payload(
        "Bash", {"command": "echo done", "run_in_background": True, "description": "until: probe done"}))],
    "playwright-browsers-path": [("pgrep -f, which prints pids only", bash_payload("pgrep -f playwright"))],
    "machine-wide-kill": [("kill of the pid this launch printed", bash_payload("kill $!"))],
    "destructive-delete": [("delete of one named directory", bash_payload("rm -rf build", "<RUN>"))],
    "ln-over-directory": [("ln -sfn, with -n beside -f", bash_payload("ln -sfn target linkname", "<RUN>"))],
    "scratchpad-commit-msg-owner": [("a commit with -m", bash_payload("git commit -m probe", "<REPO>"))],
    "hook-bypass": [("a commit with the hooks on", bash_payload("git commit -m probe", "<REPO>"))],
    "env-file": [("node with --env-file ahead of it", bash_payload(
        "node --env-file=.env.local tool.mjs", "<RUN>"))],
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
SCRATCH_COPY = "<RUN>/claude/probe-session-1/scratchpad/fresh-copy.py"

REMEDY_PROBES.update({
    "cite-by-id": [("a commit with its message inline", bash_payload('git commit -m "probe"', "<REPO>")),
                   ("a commit that names the lane by its slug", bash_payload(
                       'git commit -m "lane-number-cite: probe"', "<REPO>"))],
    "lane-by-slug": [("a commit that names the lane by its slug", bash_payload(
        'git commit -m "lane-number-cite: probe"', "<REPO>"))],
    "conflict-markers": [("a push in a call of its own", bash_payload("git push origin HEAD:lane-probe", "<REPO>"))],
    "octopus-push": [("a push of one branch", bash_payload("git push origin HEAD:lane-probe", "<REPO>"))],
    "detached-launch": [("a launch with its pid captured by echo $!", bash_payload("echo probe & echo $!"))],
    "frozen-path": [("a write to a file in the clone", tool_payload(
        "Write", {"file_path": "<REPO>/notes.md", "content": "probe"}))],
    "handoff-sections": [("a handoff with every required section", handoff_write(
        "probe-sections", full_handoff(PREMISE_NEVER)))],
    "handoff-checked-stamp": [("a handoff that restamps a premise as Checked never", handoff_write(
        "probe-stamp", full_handoff(PREMISE_NEVER), "<RUN>/transcript.jsonl"))],
    "linked-node-modules": [("the repo's setup script", bash_payload("npm run setup", "<REPO>"))],
    "live-stream": [("a command redirected to a file that is read back", bash_payload(
        "node tool.mjs > out.log", "<RUN>")),
        ("a command with nothing after it", bash_payload("node tool.mjs", "<RUN>"))],
    "merge-checks": [("the merge tool with --confirm", bash_payload("merge 123 --confirm"))],
    "records-page": [("a commit that leaves the records page out", bash_payload('git commit -m "probe"', "<REPO>"))],
    "records-page-ready": [("return the pull request to draft", tool_payload(
        "mcp__github__update_pull_request", {"owner": "probe", "repo": "probe", "pullNumber": 1, "draft": True}))],
    "scratchpad-owner": [
        ("a write under a fresh name in the session's own scratchpad", agent_payload(tool_payload(
            "Write", {"file_path": SCRATCH_COPY, "content": "probe"}))),
        ("a run of that fresh copy", agent_payload(bash_payload("python3 %s" % SCRATCH_COPY, "<RUN>")))],
    "silent-write": [("the push with its output kept, ending 2>&1 | tail -1", bash_payload(
        "git push origin HEAD:lane-probe 2>&1 | tail -1", "<REPO>"))],
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
                               agent_payload(bash_payload("git status", "<REPO>")))],
    "agent-model-floor": [("an Agent spawn on sonnet", brief_spawn("probe")),
                          ("a lane start on sonnet with its source_url", LANE_START)],
    "ask-alone": [("the force push with --force-if-includes, alone in its call", bash_payload(
        "git push --force-with-lease --force-if-includes origin HEAD:probe-branch", "<REPO>"))],
    "brief-claim-has-probe": [("a builder brief that carries the probe under its claim", brief_spawn(
        "Keep the scan as it is.\nmain allows `port: 0`.\n```\n$ python3 hooks/probe_main.py 'port: 0'\nallowed\n```"))],
    "brief-destructive-git": [("a brief that orders tests only", brief_spawn(
        "Run the tests and report the result. Discard nothing."))],
    "builder-diff": [("a builder's Edit of a product file", role_payload("builder", "Edit", EDIT_PRODUCT))],
    "builder-test-edit": [("a builder's Edit of a product file", role_payload("builder", "Edit", EDIT_PRODUCT))],
    "command-in-item": [("a task whose command is set for both shells", page_write(PAGE_TASK))],
    "designer-scope": [("a designer's Write in the design folder", role_payload("designer", "Write", {
        "file_path": "<REPO>/docs/design/probe-mockup.html", "content": "probe"}))],
    "draft-pr": [("create_pull_request with draft true", tool_payload("mcp__github__create_pull_request", {
        "owner": "probe", "repo": "probe", "title": "probe", "head": "lane-probe", "base": "main", "body": "probe",
        "draft": True}))],
    "gh-login-switch": [("a task whose command switches the gh login first", page_write(dict(PAGE_TASK, command={
        "powershell": "gh auth switch -u shivinate7; gh pr view 1",
        "mac": "gh auth switch -u shivinate7 && gh pr view 1"})))],
    "impeccable-review-only": [("the impeccable skill with audit as its first word", tool_payload(
        "Skill", {"skill": "impeccable", "args": "audit <screen>"}))],
    "item-field-rendered": [("an item whose fields the page draws", page_write(page_item()))],
    "lane-effort-pin": [("a lane start at medium, its Grant line first", LANE_START)],
    "lane-one-topic": [("a lane start whose cs-topic tag holds its brief's topic", LANE_START)],
    "lane-repo-tag": [("a lane start with the full cs-repo tag", LANE_START)],
    "lane-start-settings": [("a lane start with its model and source_url", LANE_START)],
    "message-time-matches-clock": [("the clock read with now-central", bash_payload(
        "~/.claude/bin/now-central", "<REPO>"))],
    "mockup-home": [("a design whose file is a mockup in the design folder", page_write(page_item(designs=[
        {"id": "d1", "file": "docs/design/probe-mockup.html", "label": "d1"}])))],
    "option-letter-keys": [("options keyed a and b in the order shown", page_write(page_item()))],
    "owner-judge": [("a decision whose Problem line names a stake", page_write(page_item()))],
    "page-thread-reply": [("the item rewritten, the act the Remedy names", page_write(
        page_item(context=PAGE_CONTEXT + "\nRewritten after the comment.")))],
    "playwright-install": [("the playwright install under node 22", bash_payload(
        "npx -y node@22 node_modules/playwright/cli.js install", "<REPO>"))],
    "port-question": [("a port item with its Departs from line", page_write(page_item(port=True)))],
    "press-link": [("a press option with its link", page_write(page_item(options=[PAGE_PRESS_OPTION, PAGE_OPTIONS[1]])))],
    "question-checked-with-repo": [("a question on this repo, named by its repo field", page_write(
        page_item(repo="probe/probe")))],
    "question-departs": [("a Departs from line with both sides filled", page_write(page_item()))],
    "question-form": [("a decision in the form, a gain and a lose on each option", page_write(page_item()))],
    "record-writer-scope": [("a record writer's Write of a Markdown file", role_payload("record-writer", "Write", {
        "file_path": "<REPO>/docs/probe-record.md", "content": "probe"}))],
    "rework-off-page": [("an item closed with a home that names the rework", page_write(page_item(
        status="closed", home="rework of probe-item",
        context=PAGE_CONTEXT + "\nThe item is being reworked; the fresh item carries the options.")))],
    "rm-after-cd": [("a recursive delete with no cd before it, the target a full path", bash_payload(
        "rm -rf /tmp/w/out", "<REPO>"))],
    "rm-var-unguarded": [("a variable written as ${NAME:?}", bash_payload('D=/tmp/w; rm -rf "${D:?}"/old', "<RUN>")),
                         ("a literal path", bash_payload("rm -rf /srv/build/out", "<RUN>"))],
    "roadmap-one-writer": [("get_session with no argument", tool_payload(GET_SESSION, {}))],
    "roles-third-round-steps-up": [("a reviewer's second round on sonnet", brief_spawn(
        "Round 2 of 3. Review the diff.", role="reviewer"))],
    "sendmessage-session-id": [("send_message with the id as session_id", tool_payload(
        "mcp__claude-code-remote__send_message", {"session_id": "session_probe", "message": "probe"}))],
    "simulator-boot-bypass": [("sim-test, which takes the lock and boots", bash_payload(
        "sim-test -scheme Probe", "<REPO>"))],
    "task-names-check": [("a task whose context holds a Why yours line", page_write(PAGE_TASK))],
    "task-why-cited": [("a Why yours line that ends in a measured cite", page_write(PAGE_TASK))],
    "test-author-scope": [("a test author's Write of a test file", role_payload("test-author", "Write", {
        "file_path": "<REPO>/tests/test_probe.py", "content": "probe"}))],
    "trust-card-in-build": [("get_session with no argument", tool_payload(GET_SESSION, {}))],
    "uniform-pick": [("an item with no pick", page_write(page_item()))],
    "workflow-args-shape-check": [("a Workflow started with a real value", tool_payload(
        "Workflow", {"script": "probe", "args": {"repo": "probe/probe"}}))],
    "wsl-allow-list": [("wsl with -e and a python script", bash_payload("wsl -e python3 hooks/test_guard.py", "<REPO>"))],
})

REMEDY_PROSE_ONLY.update({
    "worktree-home": "the Remedy is to stop and report to the orchestrator: no tool call is the act",
    # The Remedy's act is a Read. The guard never judges a Read, and the check clears on the read itself, outside
    # the guard, so no guard call can prove the Remedy. A probe here would pass whatever the Read did.
    "handoff-unread": "the Remedy's act is a Read, which the guard never judges: the read clears the check outside "
                      "the guard, so no guard call can prove it",
    # A placeholder for a rule the caller passes in: call_judge.unvetted's callers name spawn-judge and question-judge.
    "<rule>": "a placeholder for a rule passed in as a parameter, not a rule: its callers are spawn-judge and "
              "question-judge, which are prose-only here",
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
    <REPO>, <RUN> and <CFG> in the payload stand for this run's fixture folders."""
    text = json.dumps(body).replace("<REPO>", REPO_DIR).replace("<RUN>", RUN).replace("<CFG>", CFG)
    body = json.loads(text)
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR",
                 "CLAUDE_CODE_REMOTE"):
        env.pop(name, None)
    env.update({
        "CLAUDE_CONFIG_DIR": CFG,
        "CLAUDE_GUARD_ROOT_PID": str(os.getpid()),
        "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet",
        "TMPDIR": RUN, "TEMP": RUN, "TMP": RUN,
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

# Rules whose refusal has no Remedy yet, by the area PR that adds it. Each area PR deletes its own lines, so
# every PR passes alone; the last one leaves this table empty. A rule listed here that already carries a
# Remedy fails test_pending_rules_still_lack_a_remedy, so a line cannot outlive its fix.
REMEDY_PENDING = {
    # The ask path. settle_ask()'s refuse() takes its reason from the queue that ask_command() fills, which the scan
    # does not follow, so its site reads as "<rule>". Those asks carry no Remedy yet: shared-tree (WORKTREE_PRUNE_ASK_REASON,
    # TREE_ASK_REASON), force-push (PUSH_ASK_REASON), push-main (PUSH_MAIN_REASON) and push-stray-branch (PUSH_STRAY_REASON).
    # The row goes once those carry one and the scan follows the queue.
    "ask": ["<rule>"],
}
PENDING = {rule for rules in REMEDY_PENDING.values() for rule in rules}


class StaticRemedyTest(unittest.TestCase):

    def test_pending_rules_still_lack_a_remedy(self):
        # A pending rule is done only when it has a Remedy at every refuse site: one site without one keeps it pending.
        sites = scan()
        with_remedy = {rule for s in sites if s.has_remedy for rule in s.rules}
        lacking = {rule for s in sites if not s.has_remedy for rule in s.rules}
        done = sorted(PENDING & (with_remedy - lacking))
        if done:
            self.fail("these rules carry a Remedy at every refuse site now: delete them from REMEDY_PENDING: %s"
                      % ", ".join(done))

    def test_every_refuse_site_names_a_remedy(self):
        sites = scan()
        self.assertGreaterEqual(len(sites), MIN_SITES,
                                "the scan found %d refuse sites, fewer than %d: the scan lost sites"
                                % (len(sites), MIN_SITES))
        lacking = [s for s in sites if not s.has_remedy and not (s.rules and set(s.rules) <= PENDING)]
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
        problems = []
        if stale:
            problems.append("table entries name no refuse site with a Remedy: %s" % ", ".join(stale))
        if both:
            problems.append("a rule is in both tables: %s" % ", ".join(both))
        if blank:
            problems.append("REMEDY_PROSE_ONLY gives no reason for: %s" % ", ".join(blank))
        if problems:
            self.fail("; ".join(problems))


class ProbeTest(unittest.TestCase):

    def test_each_remedy_names_an_act_the_guard_allows(self):
        for rule in sorted(REMEDY_PROBES):
            for act, body in REMEDY_PROBES[rule]:
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
