#!/usr/bin/env python3
"""Fails when a test stand-in for a product function cannot take a call the product makes.

A test replaces a product function with `patch.object(product, "name", stand_in)`. When the product adds a
keyword to a call of that function, or passes more positional arguments, a stand-in without that parameter
raises TypeError, and only when the test runs. The incident: a pull request added `stdout_only=` to `sh()` in
merge/merge.py, and 112 tests that patched `sh` with a stand-in lacking it failed in CI alone.

    python3 lint/check_standin_signatures.py [--root DIR]

DIR defaults to the checkout. Each `test_X.py` is paired with `X.py` in the same folder. Both files are read with
the ast module, never imported, and no test runs.

For each top-level function the product defines, the check collects the keywords and the largest positional count
of its calls in the product (a call in a nested scope counts). It then reads each `patch.object(X, "name", ...)`
in the test file, where X is the product's module name: the stand-in is the third argument, or `new=`, or
`side_effect=`. A stand-in is judged when it is a def (the nearest def in scope wins), a method reached as
`obj.method` whose def is unique in the file, a lambda, or `Class()` for a class with `__call__`. Such a stand-in
is a finding when it lacks a keyword the product passes, unless it takes `**kwargs`, or when it takes fewer
positional parameters than the largest call passes, unless it takes `*args`. A bound method's `self` does not
count. Anything else (a Mock, an imported name, a call result, a patch of a name the product does not define as a
literal) is counted, not judged; a patch of a literal name the product does not define is out of scope.

Prints one `test_X.py:LINE` line per finding, with the remedy, and one `N stand-ins not judged` line when N is
more than 0. Exits 1 on a finding, 2 when a file cannot be read or parsed (an unread file is never clean), else 0.
Cost: one read and one parse per paired file; no process start, no file written.

Limits: only calls by plain name count as product calls; a stand-in passed through a variable that is assigned is
not judged; a stand-in class's inherited `__call__` is not followed.
"""
import argparse
import ast
import os
import sys

SKIP_DIRS = {"node_modules", "__pycache__"}


class Bindings:
    """The names one scope binds: its defs (name to nodes) and every other binding (params, assigns, imports)."""

    def __init__(self, scope):
        self.defs = {}
        self.other = set()
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = scope.args
            for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
                self.other.add(arg.arg)
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        stack = list(body)
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs.setdefault(node.name, []).append(node)
                continue
            if isinstance(node, ast.Lambda):
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.other.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    self.other.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self.other.add(node.name)
            stack.extend(ast.iter_child_nodes(node))


def product_calls(tree, names):
    """For each name, {"keywords": set, "positional": largest count of positional arguments in a call}."""
    seen = {name: {"keywords": set(), "positional": 0} for name in names}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in seen:
            slot = seen[node.func.id]
            count = 0
            for arg in node.args:
                if isinstance(arg, ast.Starred):
                    break
                count += 1
            slot["positional"] = max(slot["positional"], count)
            slot["keywords"].update(kw.arg for kw in node.keywords if kw.arg)
    return seen


def module_aliases(tree, stem):
    names = {stem}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == stem and alias.asname:
                    names.add(alias.asname)
    return names


def is_patch_object(call):
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "object"):
        return False
    owner = func.value
    return (isinstance(owner, ast.Attribute) and owner.attr == "patch") or (
        isinstance(owner, ast.Name) and owner.id == "patch")


def standin_expr(call):
    if len(call.args) >= 3:
        return call.args[2]
    for kw in call.keywords:
        if kw.arg in ("new", "side_effect"):
            return kw.value
    return None


class Judge:
    """Resolves a stand-in expression to a def and judges its signature against the product's calls."""

    def __init__(self, tree):
        self.tree = tree
        self.cache = {}
        self.methods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self.methods.update(n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))

    def bindings(self, scope):
        if scope not in self.cache:
            self.cache[scope] = Bindings(scope)
        return self.cache[scope]

    def resolve_name(self, name, scopes):
        for index in range(len(scopes) - 1, -1, -1):
            scope = scopes[index]
            if isinstance(scope, ast.ClassDef) and index != len(scopes) - 1:
                continue
            found = self.bindings(scope)
            defs = found.defs.get(name)
            if defs and name not in found.other and len(defs) == 1:
                return defs[0]
            if defs or name in found.other:
                return None
        return None

    def unique_def(self, name):
        hits = [n for n in ast.walk(self.tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        return hits[0] if len(hits) == 1 else None

    def callable_of(self, expr, scopes):
        """Return (label, ast.arguments, skips_first_parameter), or None when the stand-in cannot be resolved."""
        if isinstance(expr, ast.Lambda):
            return None, expr.args, False
        if isinstance(expr, ast.Name):
            fn = self.resolve_name(expr.id, scopes)
            label = expr.id
        elif isinstance(expr, ast.Attribute):
            fn = self.unique_def(expr.attr)
            label = expr.attr
        elif isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            cls = self.resolve_name(expr.func.id, scopes)
            label = expr.func.id
            fn = None
            if isinstance(cls, ast.ClassDef):
                calls = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__call__"]
                fn = calls[0] if len(calls) == 1 else None
        else:
            return None
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
        static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)
        return label, fn.args, fn in self.methods and not static


def signature_gaps(args, skip_first, wanted):
    """The keywords in wanted that args cannot take, and the positional capacity (None when unlimited)."""
    positional = args.posonlyargs + args.args
    if skip_first and positional:
        positional = positional[1:]
    names = {a.arg for a in positional if a not in args.posonlyargs} | {a.arg for a in args.kwonlyargs}
    missing = [] if args.kwarg else sorted(k for k in wanted["keywords"] if k not in names)
    capacity = None if args.vararg else len(positional)
    return missing, capacity


def check_standins(product_path, test_paths):
    """Return (findings, not_judged) for the stand-ins in test_paths that patch a function product_path defines."""
    with open(product_path, encoding="utf-8") as f:
        product = ast.parse(f.read(), product_path)
    defined = {n.name for n in product.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    wanted = product_calls(product, defined)
    stem = os.path.splitext(os.path.basename(product_path))[0]
    findings = []
    not_judged = 0
    for path in test_paths:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        judge = Judge(tree)
        targets = module_aliases(tree, stem)
        sites = []
        collect_sites(tree, [tree], targets, sites)
        for call, scopes in sites:
            literal = call.args[1] if len(call.args) > 1 else None
            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                if literal.value not in defined:
                    continue
                name = literal.value
            else:
                not_judged += 1
                continue
            expr = standin_expr(call)
            if expr is None:
                continue
            got = judge.callable_of(expr, scopes)
            if got is None:
                not_judged += 1
                continue
            label, args, skip_first = got
            need = wanted[name]
            missing, capacity = signature_gaps(args, skip_first, need)
            base = {"file": path, "line": call.lineno, "name": name, "standin": label}
            for keyword in missing:
                findings.append(dict(base, keyword=keyword, kind="keyword", need=None))
            if capacity is not None and capacity < need["positional"]:
                findings.append(dict(base, keyword=None, kind="positional", need=need["positional"]))
    findings.sort(key=lambda f: (f["file"], f["line"], f["kind"], f["keyword"] or ""))
    return findings, not_judged


def collect_sites(node, scopes, targets, sites):
    """Gather each patch.object call on the product module with the scope chain it sits in, in source order."""
    if isinstance(node, ast.Call) and is_patch_object(node) and node.args:
        target = node.args[0]
        if isinstance(target, ast.Name) and target.id in targets:
            sites.append((node, scopes))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        outer = node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d]
        for child in outer:
            collect_sites(child, scopes, targets, sites)
        for child in node.body:
            collect_sites(child, scopes + [node], targets, sites)
    elif isinstance(node, ast.ClassDef):
        for child in node.decorator_list + node.bases:
            collect_sites(child, scopes, targets, sites)
        for child in node.body:
            collect_sites(child, scopes + [node], targets, sites)
    elif isinstance(node, ast.Lambda):
        collect_sites(node.body, scopes + [node], targets, sites)
    else:
        for child in ast.iter_child_nodes(node):
            collect_sites(child, scopes, targets, sites)


def pairs_under(root):
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(files):
            if name.startswith("test_") and name.endswith(".py") and name[len("test_"):] in files:
                found.append((os.path.join(folder, name[len("test_"):]), os.path.join(folder, name)))
    return found


def describe(finding, product_name):
    who = finding["standin"] or "the inline stand-in"
    if finding["kind"] == "keyword":
        gap = "lacks the keyword %s that %s passes to %s()" % (finding["keyword"], product_name, finding["name"])
    else:
        gap = "takes fewer than the %d positional arguments that %s passes to %s()" % (
            finding["need"], product_name, finding["name"])
    return "stand-in %s %s; build the stand-in through the file's helper or give it **kwargs" % (who, gap)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Flag test stand-ins whose signature cannot take the product's calls.")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    opts = parser.parse_args(argv)
    root = os.path.abspath(opts.root)
    flagged = 0
    not_judged = 0
    unread = 0
    for product, test in pairs_under(root):
        try:
            findings, skipped = check_standins(product, [test])
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as err:
            print("unread: %s: %s" % (os.path.relpath(test, root).replace(os.sep, "/"), err))
            unread += 1
            continue
        not_judged += skipped
        rel = os.path.relpath(test, root).replace(os.sep, "/")
        for finding in findings:
            print("%s:%d: %s" % (rel, finding["line"], describe(finding, os.path.basename(product))))
        flagged += len(findings)
    if not_judged:
        print("%d stand-ins not judged" % not_judged)
    if flagged:
        return 1
    return 2 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
