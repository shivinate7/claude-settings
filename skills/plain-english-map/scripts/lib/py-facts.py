"""The Python reader of the map's fact lines (MAP9). One start answers every Python fact of one run.

stdin is one JSON object: {"root": str, "tracked": [path], "requests": [request]}.
stdout is a JSON list with one result for each request, in order.
A request is {"file", "op", "symbol", "target"}:
  op "value"   the literal at module level that `symbol` is assigned (`Assign` and `AnnAssign` only)
  op "defines" whether `symbol` is bound at module level (def, class, import, assignment)
  op "uses"    whether `file` imports the tracked file `target`, and whether it refers to `symbol`
  op "loads"   the tracked files `file` loads at runtime: {"imports": [path], "named": [path]}. `imports` leaves out an import under
               `if TYPE_CHECKING:`. `named` holds each tracked file that a string in the code equals, from the file's folder or the root.
               A docstring or a bare string statement is no code string. A join counts as one string: `os.path.join` or `posixpath.join` (named
               through the file's imports) and a `/` chain, whose pieces after the anchor are plain string literals (see `joined_strings`).
A result is {"ok": true, "value": v} or {"ok": false, "reason": str, "gone": bool}.
`gone` is true when the file was read and the symbol is not there. Any other failure is unknown, so it has no `gone`.
The module imports only the standard library and reads files as text, so it runs under `python3 -I`.
"""
import ast
import json
import os
import posixpath
import sys


def literal_to_json(value):
    """Sets and tuples become lists. A set is sorted, so its order is stable."""
    if isinstance(value, (set, frozenset)):
        return sorted((literal_to_json(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [literal_to_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): literal_to_json(v) for k, v in value.items()}
    return value


def assigned(tree):
    """Each module-level name an Assign or an AnnAssign binds, with the last value node it gets. A name with no value maps to None."""
    found = {}
    for st in tree.body:
        if isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Name):
                    found[t.id] = st.value
        elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
            found[st.target.id] = st.value
    return found


def defined_names(tree):
    names = set(assigned(tree))
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(st.name)
        elif isinstance(st, ast.Import):
            names.update((a.asname or a.name.split(".")[0]) for a in st.names)
        elif isinstance(st, ast.ImportFrom):
            names.update((a.asname or a.name) for a in st.names)
    return names


def is_type_checking(test):
    """True for the test of `if TYPE_CHECKING:` and `if typing.TYPE_CHECKING:`."""
    return dotted_name(test) in ("TYPE_CHECKING", "typing.TYPE_CHECKING")


def runtime_walk(tree):
    """Every node of the tree except the body of an `if TYPE_CHECKING:`, which a run never executes. Its `else` stays."""
    todo = [tree]
    while todo:
        node = todo.pop()
        yield node
        if isinstance(node, ast.If) and is_type_checking(node.test):
            todo.extend(node.orelse)
        else:
            todo.extend(ast.iter_child_nodes(node))


def import_bindings(tree, types=True):
    """Each dotted module name the file imports, with the dotted name that holds that module in the file, or None.
    `import a.b` gives (`a.b`, `a.b`). `from a import b` gives (`a`, None) and (`a.b`, `b`), since `b` may be a module.
    With `types` false, an import that only a type checker runs is left out."""
    pairs = []
    for node in (ast.walk(tree) if types else runtime_walk(tree)):
        if isinstance(node, ast.Import):
            pairs.extend((a.name, a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base:
                pairs.append((base, None))
            for a in node.names:
                pairs.append((f"{base}.{a.name}" if base else a.name, a.asname or a.name))
    return pairs


def imported_modules(tree, types=True):
    """Each dotted module name the file imports."""
    return [m for m, _ in import_bindings(tree, types)]


def resolve(dotted, parent, tracked):
    """The one tracked file a module name stands for, or None. A module name resolves to the tracked file with that base name,
    which covers an import after a `sys.path.insert`, or to the `__init__.py` of the package with that name.
    With several, the dotted path then the parent's folder narrow it."""
    parts = dotted.split(".")
    base = parts[-1] + ".py"
    package = parts[-1] + "/__init__.py"
    hits = [t for t in tracked if t.rsplit("/", 1)[-1] == base or t == package or t.endswith("/" + package)]
    if len(hits) > 1:
        suffix = "/".join(parts) + ".py"
        pkg_suffix = "/".join(parts) + "/__init__.py"
        narrowed = [t for t in hits if t in (suffix, pkg_suffix) or t.endswith("/" + suffix) or t.endswith("/" + pkg_suffix)]
        hits = narrowed or hits
    if len(hits) > 1:
        folder = parent.rsplit("/", 1)[0] if "/" in parent else ""
        narrowed = [t for t in hits if (t.rsplit("/", 1)[0] if "/" in t else "") == folder]
        hits = narrowed or hits
    return hits[0] if len(hits) == 1 else None


def target_aliases(tree, parent, target, tracked):
    """Each dotted name that holds the module `target` in `parent`: the binding of an import that resolves to `target`."""
    return {held for mod, held in import_bindings(tree) if held and resolve(mod, parent, tracked) == target}


def dotted_name(node):
    """The dotted text of a chain such as `a.b.c`, or None when the chain starts with a call or a subscript."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def referenced_names(tree, aliases):
    """A bare name is a reference. `x.name` is one only when `x` starts at an alias of the cited file, so `job.run()` on an
    object and `subprocess.run` on another module are none."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain = dotted_name(node.value)
            if chain and any(chain == a or chain.startswith(a + ".") for a in aliases):
                names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def code_strings(tree):
    """Each string in the code. A docstring and any other bare string statement are comments in all but name, so they are left out,
    and so is each piece of an f-string that has a placeholder."""
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skip.add(id(node.value))
        elif isinstance(node, ast.JoinedStr) and len(node.values) > 1:
            skip.update(id(v) for v in node.values)
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]


JOINS = ("os.path.join", "posixpath.join")


def join_callees(tree):
    """Each dotted name that holds `os.path.join` or `posixpath.join` in the file, read from its imports:
    `import os`, `import os.path as p`, `from os import path`, `from os.path import join as pj`, `import posixpath`."""
    names = set()
    for module, held in import_bindings(tree, types=False):
        if not held:
            continue
        for join in JOINS:
            if join == module:
                names.add(held)
            elif join.startswith(module + "."):
                names.add(held + join[len(module):])
    return names


def is_literal_string(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


TMP_NAMES = frozenset(("tmp_path", "tmpdir", "tmp_path_factory"))
TMP_CALLS = frozenset(("mkdtemp", "TemporaryDirectory", "gettempdir"))
SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def is_tmp_expr(node, tmp):
    """Whether `node` is a temp folder: a pytest temp fixture name, a call to `tempfile.mkdtemp()`, `TemporaryDirectory()` or `gettempdir()`
    (the call, not the module it hangs on), or a name in `tmp`. A chain that starts on one reads the temp folder, never the repository."""
    if isinstance(node, ast.Name):
        return node.id in TMP_NAMES or node.id in tmp
    if isinstance(node, ast.Call):
        dotted = dotted_name(node.func)
        return dotted is not None and dotted.rsplit(".", 1)[-1] in TMP_CALLS
    return False


def tmp_bound(scope, tmp):
    """The names that `scope` binds to a temp folder: `d = tempfile.mkdtemp()` and `with TemporaryDirectory() as d`. The walk stops at a nested
    function, which gets its own pass; a name bound in a function is no temp folder outside it."""
    found = set(tmp)
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, SCOPES):
            continue
        if isinstance(node, ast.Assign) and is_tmp_expr(node.value, found):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and node.value is not None and isinstance(node.target, ast.Name) and is_tmp_expr(node.value, found):
            found.add(node.target.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name) and is_tmp_expr(item.context_expr, found):
                    found.add(item.optional_vars.id)
        stack.extend(ast.iter_child_nodes(node))
    return found


def joined_strings(tree):
    """The path that each join call or `/` chain names, as one string. Only the first argument (the anchor) may be anything but a plain
    string literal. A literal anchor is the first piece. A piece after it that is not a literal (a name, an f-string, a star) drops the call,
    and so does a piece that starts with `/`, and so does a call with no piece after the anchor. So does an anchor that is a temp folder
    (`is_tmp_expr`), read in the function that holds the call: a temp folder is no part of the repository."""
    callees = join_callees(tree)
    inner = {id(n.left) for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)}
    out = []
    stack = [(tree, frozenset())]
    while stack:
        node, tmp = stack.pop()
        if isinstance(node, SCOPES):
            tmp = tmp_bound(node, tmp)
        pieces = None
        if isinstance(node, ast.Call) and callees and dotted_name(node.func) in callees:
            args = node.args
            if args and not node.keywords and not any(isinstance(a, ast.Starred) for a in args) and len(args) > 1:
                pieces = [args[0]] + args[1:]
                anchor = args[0]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and id(node) not in inner:
            chain, anchor = [], node
            while isinstance(anchor, ast.BinOp) and isinstance(anchor.op, ast.Div):
                chain.append(anchor.right)
                anchor = anchor.left
            pieces = [anchor] + chain[::-1]
        if pieces is not None and all(is_literal_string(p) for p in pieces[1:]) and not is_tmp_expr(anchor, tmp):
            texts = [p.value for p in pieces[1:]]
            if is_literal_string(anchor):
                texts.insert(0, anchor.value)
            if not any(t.startswith("/") for t in texts):
                out.append("/".join(texts))
        stack.extend((child, tmp) for child in ast.iter_child_nodes(node))
    return out


def named_files(tree, parent, tracked, joined=()):
    """The tracked files that a string in the code equals, from the parent's folder or from the root. `joined` holds the strings that joins name."""
    found = set(tracked)
    folder = parent.rsplit("/", 1)[0] if "/" in parent else ""
    out = set()
    for s in code_strings(tree) + list(joined):
        if not s or "\n" in s or s.startswith("/"):
            continue
        for c in (posixpath.normpath(posixpath.join(folder, s)), posixpath.normpath(s)):
            if c in found and c != parent:
                out.add(c)
    return sorted(out)


def answer(req, tree, tracked):
    op, symbol = req.get("op", "value"), req.get("symbol")
    if op == "loads":
        imports = {resolve(m, req["file"], tracked) for m in imported_modules(tree, types=False)}
        imports.discard(None)
        imports.discard(req["file"])
        return {"ok": True, "value": {"imports": sorted(imports), "named": named_files(tree, req["file"], tracked, joined_strings(tree))}}
    if op == "uses":
        target = req["target"]
        imports = any(resolve(m, req["file"], tracked) == target for m in imported_modules(tree))
        uses = None if symbol is None else symbol in referenced_names(tree, target_aliases(tree, req["file"], target, tracked))
        return {"ok": True, "value": {"imports": imports, "uses": uses}}
    if op == "defines":
        if symbol in defined_names(tree):
            return {"ok": True, "value": True}
        return {"ok": False, "gone": True, "reason": f"{req['file']} has no module-level {symbol}"}
    found = assigned(tree)
    if symbol not in found:
        return {"ok": False, "gone": True, "reason": f"{req['file']} has no module-level {symbol}"}
    if found[symbol] is None:
        return {"ok": False, "reason": f"{req['file']} {symbol} has no value"}
    try:
        value = literal_to_json(ast.literal_eval(found[symbol]))
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return {"ok": False, "reason": f"{req['file']} {symbol} is not a literal that JSON can hold"}
    return {"ok": True, "value": value}


def main():
    data = json.load(sys.stdin)
    root, tracked = data["root"], data.get("tracked", [])
    trees = {}
    results = []
    for req in data["requests"]:
        f = req["file"]
        if f not in trees:
            try:
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    trees[f] = ast.parse(fh.read(), filename=f)
            except (OSError, UnicodeDecodeError) as e:
                trees[f] = f"{f} cannot be read: {e.__class__.__name__}"
            except (SyntaxError, ValueError) as e:
                trees[f] = f"{f} does not parse: {e}"
        tree = trees[f]
        results.append({"ok": False, "reason": tree} if isinstance(tree, str) else answer(req, tree, tracked))
    sys.stdout.write(json.dumps(results))


if __name__ == "__main__":
    main()
