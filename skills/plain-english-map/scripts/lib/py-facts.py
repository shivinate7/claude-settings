"""The Python reader of the map's fact lines (MAP9). One start answers every Python fact of one run.

stdin is one JSON object: {"root": str, "tracked": [path], "requests": [request]}.
stdout is a JSON list with one result for each request, in order.
A request is {"file", "op", "symbol", "target"}:
  op "value"   the literal at module level that `symbol` is assigned (`Assign` and `AnnAssign` only)
  op "defines" whether `symbol` is bound at module level (def, class, import, assignment)
  op "uses"    whether `file` imports the tracked file `target`, and whether it refers to `symbol`
  op "loads"   the tracked files `file` loads at runtime: {"imports": [path], "named": [path]}. `imports` leaves out an import under
               `if TYPE_CHECKING:`. `named` holds each tracked file that a string in the code equals, from the file's folder or the root.
               A docstring or a bare string statement is no code string. A join names a file too: `os.path.join` or `posixpath.join` (named
               through the file's imports) and a `/` chain, whose pieces after the anchor are plain string literals. A literal anchor makes it
               one more code string. Any other anchor must be a known place of the repository, and the join resolves from there only (see
               `joined_strings`).
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


PATH_FUNCS = {
    "os.path.join": "join", "posixpath.join": "join",
    "os.path.dirname": "dirname", "posixpath.dirname": "dirname",
    "os.path.abspath": "same", "posixpath.abspath": "same", "os.path.realpath": "same", "posixpath.realpath": "same",
    "os.path.normpath": "same", "posixpath.normpath": "same",
    "pathlib.Path": "same",
}


def path_callees(tree):
    """Each dotted name that holds a function of PATH_FUNCS in the file, read from its runtime imports, with what it does to a path:
    `import os`, `import os.path as p`, `from os import path`, `from os.path import join as pj`, `import posixpath`, `from pathlib import Path`."""
    names = {}
    for module, held in import_bindings(tree, types=False):
        if not held:
            continue
        for func, does in PATH_FUNCS.items():
            if func == module:
                names[held] = does
            elif func.startswith(module + "."):
                names[held + func[len(module):]] = does
    return names


def is_literal_string(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def binding_counts(tree):
    """How many times the file binds each name, in any scope: a store, a parameter, an import, a def or class, a `global`, an `except`
    name or a match capture. A name bound once, at module level, holds the same value in every function that reads it."""
    counts = {}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names = [node.id]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.asname or a.name.split(".")[0] for a in node.names]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names = list(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names = [node.name]
        elif type(node).__name__ in ("MatchAs", "MatchStar") and node.name:
            names = [node.name]
        elif type(node).__name__ == "MatchMapping" and node.rest:
            names = [node.rest]
        for n in names:
            counts[n] = counts.get(n, 0) + 1
    return counts


def inside(path):
    """`path`, normalized, or None when it climbs out of the repository."""
    path = posixpath.normpath(path)
    return None if path == ".." or path.startswith("../") else path


def joined_strings(tree, parent):
    """What each join call or `/` chain names, as (strings, places). Every piece after the first argument (the anchor) is a plain string
    literal that does not start with `/`, or the call names nothing.
    A literal anchor is the first piece, and the joined text goes to `strings`, which `named_files` tries from the folder, then the root.
    Any other anchor must be a known place of the repository (`place`), and the join resolved from it goes to `places`, tried from there only."""
    callees = path_callees(tree)
    counts = binding_counts(tree)
    top = assigned(tree)
    star = any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree))

    def split(node):
        """(anchor, pieces) of a join call or a `/` chain, or None."""
        if isinstance(node, ast.Call) and callees.get(dotted_name(node.func)) == "join":
            args = node.args
            if len(args) > 1 and not node.keywords and not any(isinstance(a, ast.Starred) for a in args):
                return args[0], args[1:]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            pieces = []
            while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                pieces.append(node.right)
                node = node.left
            return node, pieces[::-1]
        return None

    def texts(pieces):
        if not all(is_literal_string(p) for p in pieces):
            return None
        out = [p.value for p in pieces]
        return None if any(t.startswith("/") for t in out) else out

    def place(node, seen):
        """("file" or "dir", repo-relative path) for an expression that names a place of the repository by static reading, or None.
        `__file__` is the file. `dirname(x)` and `x.parent` go up one folder. `abspath(x)`, `realpath(x)`, `Path(x)`, `x.resolve()` and
        `x.absolute()` keep x, and so does `normpath(x)`. `x.parents[n]` with a literal n goes up n + 1 folders. A join of a folder with
        literal pieces is a folder. A join call from the file itself resolves as path normalization does, the file name being one segment, so
        `os.path.join(__file__, "..", x)` is `x` beside the file; a `/` chain does not, since pathlib keeps `..` as written. A name bound once
        in the file, at module level, is the place its value names. Anything else (a parameter, an import, a call to a helper, a name bound
        in a function) is no known place."""
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return None if counts.get(node.id) else ("file", parent)
            if star or node.id in seen or counts.get(node.id) != 1 or top.get(node.id) is None:
                return None
            return place(top[node.id], seen | {node.id})
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            got = place(node.value, seen)
            up = got and inside(got[1] + "/..")
            return ("dir", up) if up else None
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, int) and not isinstance(index.value, bool) and index.value >= 0:
                got = place(node.value.value, seen)
                up = got and inside(got[1] + "/.." * (index.value + 1))
                return ("dir", up) if up else None
            return None
        if isinstance(node, ast.Call) and not node.keywords:
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("resolve", "absolute") and not node.args:
                return place(node.func.value, seen)
            does = callees.get(dotted_name(node.func))
            if does in ("dirname", "same") and len(node.args) == 1 and not isinstance(node.args[0], ast.Starred):
                got = place(node.args[0], seen)
                if got is None or does == "same":
                    return got
                up = inside(got[1] + "/..")
                return ("dir", up) if up else None
        parts = split(node)
        if parts is None:
            return None
        got, tail = place(parts[0], seen), texts(parts[1])
        if got is None or tail is None or (got[0] == "file" and not isinstance(node, ast.Call)):
            return None
        joined = inside(posixpath.join(got[1], *tail))
        return ("dir", joined) if joined else None

    inner = {id(n.left) for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)}
    strings, places = [], []
    for node in ast.walk(tree):
        parts = None if id(node) in inner else split(node)
        if parts is None:
            continue
        if is_literal_string(parts[0]):
            tail = texts([parts[0]] + list(parts[1]))
            if tail is not None:
                strings.append("/".join(tail))
        else:
            got = place(node, frozenset())
            if got:
                places.append(got[1])
    return strings, places


def named_files(tree, parent, tracked, joined=((), ())):
    """The tracked files that a string in the code equals, from the parent's folder or from the root, and the tracked files that a join names.
    `joined` is the (strings, places) of `joined_strings`: each string is tried as a code string is, and each place is a path from the root."""
    found = set(tracked)
    folder = parent.rsplit("/", 1)[0] if "/" in parent else ""
    strings, places = joined
    out = {p for p in places if p in found and p != parent}
    for s in code_strings(tree) + list(strings):
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
        return {"ok": True, "value": {"imports": sorted(imports), "named": named_files(tree, req["file"], tracked, joined_strings(tree, req["file"]))}}
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
