"""The Python reader of the map's fact lines (MAP9). One start answers every Python fact of one run.

stdin is one JSON object: {"root": str, "tracked": [path], "requests": [request]}.
stdout is a JSON list with one result for each request, in order.
A request is {"file", "op", "symbol", "target"}:
  op "value"   the literal at module level that `symbol` is assigned (`Assign` and `AnnAssign` only)
  op "defines" whether `symbol` is bound at module level (def, class, import, assignment)
  op "uses"    whether `file` imports the tracked file `target`, and whether it refers to `symbol`
A result is {"ok": true, "value": v} or {"ok": false, "reason": str, "gone": bool}.
`gone` is true when the file was read and the symbol is not there. Any other failure is unknown, so it has no `gone`.
The module imports only the standard library and reads files as text, so it runs under `python3 -I`.
"""
import ast
import json
import os
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


def imported_modules(tree):
    """Each dotted module name the file imports. `from a import b` gives `a` and `a.b`, since `b` may be a module."""
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base:
                mods.append(base)
            for a in node.names:
                mods.append(f"{base}.{a.name}" if base else a.name)
    return mods


def resolve(dotted, parent, tracked):
    """The one tracked file a module name stands for, or None. A module name resolves to the tracked file with that base name,
    which covers an import after a `sys.path.insert`. With several, the dotted path then the parent's folder narrow it."""
    parts = dotted.split(".")
    base = parts[-1] + ".py"
    hits = [t for t in tracked if t.rsplit("/", 1)[-1] == base]
    if len(hits) > 1:
        suffix = "/".join(parts) + ".py"
        narrowed = [t for t in hits if t == suffix or t.endswith("/" + suffix)]
        hits = narrowed or hits
    if len(hits) > 1:
        folder = parent.rsplit("/", 1)[0] if "/" in parent else ""
        narrowed = [t for t in hits if (t.rsplit("/", 1)[0] if "/" in t else "") == folder]
        hits = narrowed or hits
    return hits[0] if len(hits) == 1 else None


def imported_aliases(tree):
    """Each name an import binds. `from a import b` binds `b`, which may be a module."""
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update((a.asname or a.name.split(".")[0]) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            aliases.update((a.asname or a.name) for a in node.names)
    return aliases


def root_name(node):
    """The name at the start of a chain such as `a.b.c`, or None when the chain starts with a call or a subscript."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def referenced_names(tree):
    """A bare name is a reference. `x.name` is one only when `x` starts at an imported name, so `job.run()` on an object is none."""
    aliases = imported_aliases(tree)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if root_name(node.value) in aliases:
                names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def answer(req, tree, tracked):
    op, symbol = req.get("op", "value"), req.get("symbol")
    if op == "uses":
        target = req["target"]
        imports = any(resolve(m, req["file"], tracked) == target for m in imported_modules(tree))
        uses = None if symbol is None else symbol in referenced_names(tree)
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
