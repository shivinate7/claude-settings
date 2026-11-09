#!/usr/bin/env python3
"""Fails when a test file holds a literal copy of a line a hook prints.

A hook declares the text it prints: `PRINTED_LINES = ("NAME", ...)`, a module-level tuple or list
(annotated or not) of string literals that name module-level string constants of the hook. A hook with
no PRINTED_LINES is not opted in and is skipped. A test that spells that text out as a literal goes
stale when the hook changes the line. The test builds its line from the constant instead.

A pin is a string token in `test_*.py` or `*_test.py` under `hooks/` or `lint/` that starts with a
constant's text (both sides after `lstrip`). Not a pin: text in the middle of a string, a string that
is a whole statement (a docstring), a comment, and the hook's own `hooks/test_<hook>.py` or
`hooks/<hook>_test.py`, which may pin its own hook. A constant under 8 characters (stripped) is ignored: it would match too much. An f-string
counts when its first literal part starts with the text.

Scanned with `ast` for the hooks and `tokenize` for the tests, so a comment opener inside a string,
a multi-line string and a lone quote read as the language reads them.

Cost: no process start. It reads each hooks/*.py and each test file once per run and writes nothing.

    python3 lint/check_hook_output_pins.py [--root DIR]     # DIR defaults to this script's repo

Exit 0 clean and silent, 1 on a FAIL line (one per pin), 2 when an input cannot be read (never green).
Unknown (exit 2): a file that does not parse or decode; a PRINTED_LINES that is not a tuple or list
(names the hook and PRINTED_LINES); a member that is not a string literal, or that names no module-level
plain string constant of the hook, such as a missing name or a concatenation (names the hook and the member).
"""
import ast
import glob
import io
import os
import sys
import tokenize

NAME = "check_hook_output_pins"
DECLARATION = "PRINTED_LINES"
MIN_LENGTH = 8  # stripped constant length below which a text would match too much
TEST_FOLDERS = ("hooks", "lint")
FSTRING_START = getattr(tokenize, "FSTRING_START", None)
FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)
FSTRING_END = getattr(tokenize, "FSTRING_END", None)
LINE_START = (None, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)


class Unknown(Exception):
    pass


def is_test_name(base):
    return base.startswith("test_") or base.endswith("_test.py")


def read_tree(path, rel):
    try:
        with open(path, encoding="utf-8") as f:
            return ast.parse(f.read(), filename=rel)
    except (OSError, SyntaxError, ValueError) as e:
        raise Unknown("%s does not parse: %s" % (rel, e))


def string_constants(tree):
    """Map each module-level name bound to a str constant to that text."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for t in targets:
                if isinstance(t, ast.Name):
                    out[t.id] = value.value
    return out


def declared_names(tree, rel):
    """Names listed in the hook's PRINTED_LINES, or [] when it declares none. Raises Unknown on a shape it cannot read."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == DECLARATION
                                                for t in node.targets):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == DECLARATION and node.value is not None:
            value = node.value
        else:
            continue
        if not isinstance(value, (ast.Tuple, ast.List)):
            raise Unknown("%s: %s is not a tuple or list of string literals" % (rel, DECLARATION))
        for e in value.elts:
            if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
                member = e.id if isinstance(e, ast.Name) else ast.unparse(e)
                raise Unknown("%s: %s member %s is not a string literal naming a constant"
                              % (rel, DECLARATION, member))
        return [e.value for e in value.elts]
    return []


def read_printed(root):
    """List of (hook rel path, constant name, text to match) for every declared, long enough constant."""
    hooks = os.path.join(root, "hooks")
    if not os.path.isdir(hooks):
        raise Unknown("no hooks folder under %s" % root)
    printed, scanned = [], 0
    # The folder is escaped so a root such as r[x] is read as a path, not as a glob pattern.
    for path in sorted(glob.glob(os.path.join(glob.escape(hooks), "*.py"))):
        base = os.path.basename(path)
        if is_test_name(base):
            continue
        rel = "hooks/" + base
        scanned += 1
        tree = read_tree(path, rel)
        consts = string_constants(tree)
        for name in declared_names(tree, rel):
            if name not in consts:
                raise Unknown("%s: %s names %s, which is not a module-level string constant" % (rel, DECLARATION, name))
            text = consts[name].lstrip()
            if len(text.strip()) >= MIN_LENGTH:
                printed.append((rel, name, text))
    if not scanned:  # nothing scanned must never read as a pass
        raise Unknown("no hook modules under %s" % hooks)
    return printed


def span_end(toks, i):
    """Index after the string or f-string that starts at toks[i], or i when none starts there."""
    if toks[i].type == tokenize.STRING:
        return i + 1
    if toks[i].type == FSTRING_START:
        depth = 0
        while i < len(toks):
            if toks[i].type == FSTRING_START:
                depth += 1
            elif toks[i].type == FSTRING_END:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
    return i


def bare_statements(toks):
    """Indexes of the tokens of every statement that is only strings: a docstring or a bare string."""
    bare = set()
    for i, tok in enumerate(toks):
        if tok.type not in (tokenize.STRING, FSTRING_START) or (i and toks[i - 1].type not in LINE_START):
            continue
        j = i
        while j < len(toks) and span_end(toks, j) > j:
            j = span_end(toks, j)
        if j < len(toks) and toks[j].type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            bare.update(range(i, j))
    return bare


def literal_text(tok):
    """The text a STRING token holds, or None for a bytes literal."""
    try:
        value = ast.literal_eval(tok.string)
    except (ValueError, SyntaxError):  # an f-string token from an older tokenizer: use its source text
        return tok.string.lstrip("rRbBuUfF").lstrip("\"'")
    return value if isinstance(value, str) else None


def string_starts(toks):
    """Yield (line, text) for each string whose text starts at its opening quote."""
    bare = bare_statements(toks)
    for i, tok in enumerate(toks):
        if i in bare:
            continue
        if tok.type == tokenize.STRING:
            text = literal_text(tok)
        elif tok.type == FSTRING_MIDDLE and i and toks[i - 1].type == FSTRING_START:
            text = tok.string
        else:
            continue
        if text:
            yield tok.start[0], text


def read_tokens(path, rel):
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        return [t for t in tokenize.generate_tokens(io.StringIO(source).readline)
                if t.type not in (tokenize.COMMENT, tokenize.NL)]
    except (OSError, ValueError, SyntaxError, tokenize.TokenError) as e:
        raise Unknown("%s does not parse: %s" % (rel, e))


def find_pins(root):
    """Pins as dicts with keys test, line, hook, name, sorted by (test, line). Raises Unknown on an unreadable input."""
    printed = read_printed(root)
    pins = []
    for folder in TEST_FOLDERS:
        folder_path = glob.escape(os.path.join(root, folder))
        found = set(glob.glob(os.path.join(folder_path, "test_*.py")))
        found.update(glob.glob(os.path.join(folder_path, "*_test.py")))
        for path in sorted(found):
            rel = folder + "/" + os.path.basename(path)
            toks = read_tokens(path, rel)
            for line, text in string_starts(toks):
                for hook, name, want in printed:
                    stem = hook[len("hooks/"):-len(".py")]
                    own = rel in ("hooks/test_%s.py" % stem, "hooks/%s_test.py" % stem)
                    if not own and text.lstrip().startswith(want):
                        pins.append({"test": rel, "line": line, "hook": hook, "name": name})
    return sorted(pins, key=lambda p: (p["test"], p["line"], p["hook"], p["name"]))


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--root" and args:
            root = args.pop(0)
        else:  # an unknown option must never read as a pass
            print("%s: FAIL: unknown option: %s" % (NAME, a))
            return 1
    try:
        pins = find_pins(root)
    except Unknown as e:
        print("%s: UNKNOWN, %s" % (NAME, e))
        return 2
    for p in pins:
        print("FAIL %s: %s:%d: literal copy of %s from %s, build it from the constant"
              % (NAME, p["test"], p["line"], p["name"], p["hook"]))
    return 1 if pins else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
