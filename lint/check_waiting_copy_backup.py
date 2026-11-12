#!/usr/bin/env python3
"""Check that the waiting copy in git is a backup, and no tool but one reads it as a live source (decision waiting-page-one-store).

The page's database is the one store. The copy folder (layout kind `waiting-data`) serves recovery and
account moves, so a tool that reads its content as a source treats a stale backup as the truth. Two checks:

  reader  a tool under skills/, hooks/, lint/ or bin/ whose code reads the copy folder. A test path
          (hooks/guard.py is_test_rel) is not a tool. Python is followed with `ast`: a copy name (the
          string "waiting-data", a path or git ref into the kind's folder `waiting`, that folder as a path join
          part, a call to waiting_copy()) reaches a path read (open, read_text, a listing of a collection, a git
          show, grep or cat-file) through variables, module constants, `self` attributes, closures, return
          values and helper parameters, export_page.py's reading functions imported included. A read of
          lint/layout.json is no read of the copy. In export_page.py every function that reads a path, itself
          or through a helper, is a reader unless it is a function of the recovery, merge or export modes
          (EXPORT_MODES). JavaScript and shell are read by one scanner, statement by statement: a read word (cat,
          head, jq, readFileSync, git show, ...) in a statement that names the copy, or a variable assigned from it.
  prose   the copy's three prose homes each say, in one sentence, that the copy is a backup.

    python3 lint/check_waiting_copy_backup.py [--root DIR]

Exit 0 clean, with the line `checked <N> source files and <M> prose files: 0 findings`.
Exit 1 findings, one line each:
    <path>:<line>: reads the waiting copy folder as a live source
    <path>: does not call the waiting copy a backup
Exit 2 unknown: a prose file or a source file cannot be read or parsed (and no finding).
"""
import argparse
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402  is_test_rel is the one home of what a test path is (hooks/guard.py)
import layout  # noqa: E402  the one home of the copy folder's kind and path (lint/layout.py)

COPY_KIND = "waiting-data"  # the layout kind of the copy folder
COPY_PATH = layout.layout()["kinds"][COPY_KIND]["path"].strip("/")  # where that kind lives, as a path segment
COLLECTIONS = layout.WAITING_COLLECTIONS  # the folders of the copy that hold docs
LAYOUT_FILE = os.path.basename(layout.LAYOUT_FILE)  # a read of it reads the kind's key, not the copy
COPY_RESOLVER = "waiting_copy"  # a call that resolves the copy folder (hooks/feedback_guard.py)
PATH_READS = frozenset(("open", "read_text", "read_bytes"))  # read the content of a path
PRESENCE = frozenset(("isfile", "exists", "is_file", "listdir", "scandir", "walk", "glob", "iglob", "iterdir"))
JOINS = frozenset(("join", "joinpath", "Path", "PurePath"))  # their arguments are path parts
GIT_READS = frozenset(("grep", "cat-file", "show"))  # git read verbs, as an argument or a word
SHELL_READS = frozenset(("cat", "head", "tail", "jq", "sed", "awk", "less", "more"))
JS_READS = frozenset(("readFileSync", "readFile", "createReadStream", "readdirSync", "existsSync"))
JS_PRESENCE = frozenset(("readdirSync", "existsSync"))  # a read only of a collection
SOURCE_FOLDERS = ("skills", "hooks", "lint", "bin")
SKIP_DIRS = frozenset(("__pycache__", "node_modules", ".git"))
JS_SUFFIXES = (".js", ".mjs", ".cjs", ".ts")
SHELL_SUFFIXES = (".sh", ".bash")
LIVE = "reads the waiting copy folder as a live source"
NOT_BACKUP = "does not call the waiting copy a backup"
WAITING = "skills/waiting-page"
SKILL, COPIES, EXPORT = WAITING + "/SKILL.md", WAITING + "/reference/copies-and-accounts.md", WAITING + "/export_page.py"
EXPORT_MODULE = os.path.splitext(os.path.basename(EXPORT))[0]  # its import name
PROSE = (SKILL, COPIES, EXPORT)
FEEDBACK_GUARD = "hooks/feedback_guard.py"
FILING_CHECK = "Homes.filed_numbers"  # the filing check (debt filing-check-reads-copy)

# Qualified functions that may read the copy, and how many reads each may hold: more reads than that are findings.
ALLOWED = {
    (FEEDBACK_GUARD, FILING_CHECK): 1,
}
# The functions of export_page.py that read a path, by mode. A new function that reads one is a finding.
EXPORT_MODES = {
    "export": ("load_json", "docs_in", "read_page", "supporting_files", "existing", "fetched_docs", "export",
               "export_all", "check_only"),
    "recovery": ("read_copy", "rebuild"),
    "merge": ("live_docs", "merged_design", "merge"),
}
EXPORT_FUNCTIONS = frozenset(name for names in EXPORT_MODES.values() for name in names)
# export_page.py's command line front, and the calls each part may make that are not reads: it hands argv to the
# entry function of a mode, and that function reads.
EXPORT_FRONT = {
    "<module>": ("main",),
    "main": ("check_only", "export_all", "export", "merge", "rebuild"),
}

NAME_AFTER_SLASH = re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(COPY_KIND))
NAME_IN_PATH = re.compile(r"(?<![\w.-])(?:%s|%s)/|:(?:%s|%s)(?![\w-])"
                          % ((re.escape(COPY_KIND), re.escape(COPY_PATH)) * 2))
GIT_IN_STRING = re.compile(r"\bgit\b.*\b(?:%s)\b" % "|".join(sorted(map(re.escape, GIT_READS))))
COLLECTION_IN_PATH = re.compile(r"(?:^|/)(?:%s)(?:/|$)" % "|".join(COLLECTIONS))
SPAWN_FIRST = ("self", "cls")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class Unreadable(Exception):
    """A file could not be read or parsed: unknown, never a pass."""


def names_copy(text):
    """True when the string `text` is the copy's kind, or a path or git ref into it. A sentence that only
    mentions the folder does not count."""
    return text == COPY_KIND or bool(NAME_IN_PATH.search(text))


def call_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def call_inputs(call):
    """The expressions a call reads from: its arguments, keywords and, for a method, its receiver."""
    found = list(call.args) + [k.value for k in call.keywords]
    if isinstance(call.func, ast.Attribute):
        found.append(call.func.value)
    return found


def subtree(nodes):
    for node in nodes:
        yield from ast.walk(node)


def own_nodes(body):
    """Every node of the statements in `body`, leaving out the bodies of nested functions (their own units)."""
    stack, out = [n for n in body if not isinstance(n, FUNCTIONS)], []
    while stack:
        node = stack.pop()
        out.append(node)
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, FUNCTIONS):
                stack.append(child)
    return sorted(out, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))


def self_attribute(node):
    """The attribute name of `self.x` or `cls.x`, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in SPAWN_FIRST:
        return node.attr
    return None


class Unit:
    """A function, or the module's own statements. `parent` is the unit whose names it sees (Python's scope
    rule: a method sees the module, not its class), `cls` the class whose `self` attributes it shares."""

    def __init__(self, qual, name, params, body, parent, cls):
        self.qual, self.name, self.params, self.nodes = qual, name, params, own_nodes(body)
        self.parent, self.cls = parent, cls
        docs = {id(n.value) for n in self.nodes if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        self.strings = [n for n in subtree(self.nodes) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                        and id(n) not in docs]
        self.calls = [n for n in self.nodes if isinstance(n, ast.Call)]
        self.assigns = [n for n in self.nodes if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and n.value]
        self.returns = [n.value for n in self.nodes if isinstance(n, ast.Return) and n.value]
        self.bound = set(params) | {n.id for n in self.nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        self.tainted = set()  # local names that hold the copy folder
        self.derived = dict((p, {p}) for p in params)  # local name -> the parameters it comes from


def targets_of(node):
    return node.targets if isinstance(node, ast.Assign) else [node.target]


def assigned_names(node):
    return {n.id for t in targets_of(node) for n in ast.walk(t) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def units_of(tree):
    module = Unit("<module>", "<module>", [], tree.body, None, None)
    found = [module]

    def visit(node, chain, scope, cls):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, chain + [child.name], scope, ".".join(chain + [child.name]))
            elif isinstance(child, FUNCTIONS):
                params = [a.arg for a in child.args.posonlyargs + child.args.args + child.args.kwonlyargs]
                if params and params[0] in SPAWN_FIRST:
                    params = params[1:]
                unit = Unit(".".join(chain + [child.name]), child.name, params, child.body, scope, cls)
                found.append(unit)
                visit(child, chain + [child.name], unit, cls)
            else:
                visit(child, chain, scope, cls)

    visit(tree, [], module, None)
    return found


def copy_constants(tree):
    """ids of the string constants that name the copy: its kind, a path or git ref into it, or its folder as a
    path join part. The folder's bare name elsewhere ("waiting" as a word or a status) is not the copy."""
    parts = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and call_name(node) in JOINS:
            parts.update(id(a) for a in node.args)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts.update((id(node.left), id(node.right)))
    return {id(n) for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and (names_copy(n.value) or (n.value == COPY_PATH and id(n) in parts))}


def export_imports(tree):
    """(names, modules): local names bound to export_page.py's reading functions, and to the module itself."""
    names, modules = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == EXPORT_MODULE:
            names |= {a.asname or a.name for a in node.names if a.name in EXPORT_FUNCTIONS}
        elif isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name.split(".")[-1] == EXPORT_MODULE}
    return names, modules


def git_reads(unit):
    """The argument lists of `unit` that run a git read verb: a list, tuple or call holding one as a constant."""
    for node in subtree(unit.nodes):
        if isinstance(node, (ast.List, ast.Tuple, ast.Call)):
            direct = node.args if isinstance(node, ast.Call) else node.elts
            if any(isinstance(e, ast.Constant) and e.value in GIT_READS for e in direct):
                yield node


def is_write_open(call):
    mode = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    return (call_name(call) == "open" and isinstance(mode, ast.Constant) and isinstance(mode.value, str)
            and any(c in mode.value for c in "wax") and "+" not in mode.value)


def is_path_read(call):
    """True for a call that reads a path: its content, or a presence check or listing of a collection of docs. A
    write, and a read of the layout file, are not."""
    name = call_name(call)
    if name not in PATH_READS and name not in PRESENCE:
        return False
    if is_write_open(call):
        return False
    texts = [n.value for n in subtree(call_inputs(call)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    if any(t.endswith(LAYOUT_FILE) for t in texts):
        return False
    return name in PATH_READS or any(COLLECTION_IN_PATH.search(t) for t in texts)


class Analysis:
    """What a Python file's units read. One taint model serves every scope: a name resolves to the nearest unit
    that binds it, a `self` attribute to its class, and a helper's parameters to the reads it passes them to."""

    def __init__(self, tree):
        self.units = units_of(tree)
        self.by_name = {}
        for unit in self.units:
            self.by_name.setdefault(unit.name, []).append(unit)
        self.copy_consts = copy_constants(tree)
        self.export_names, self.export_modules = export_imports(tree)
        self.copy_functions = {COPY_RESOLVER}
        self.attrs = {}  # class qual -> the `self` attributes that hold the copy folder
        self.opens = {}  # function name -> the parameters it passes to a path read
        while True:  # to a fixed point: each round can only add
            before = self.size()
            for unit in self.units:
                self.follow(unit)
            if self.size() == before:
                break

    def size(self):
        return (len(self.copy_functions), sum(map(len, self.opens.values())), sum(map(len, self.attrs.values())),
                sum(len(u.tainted) for u in self.units))

    def holds_copy(self, name, unit):
        while unit is not None:
            if name in unit.tainted:
                return True
            if name in unit.bound:
                return False
            unit = unit.parent
        return False

    def is_copy(self, node, unit):
        for sub in ast.walk(node):
            if id(sub) in self.copy_consts:
                return True
            if isinstance(sub, ast.Call) and call_name(sub) in self.copy_functions:
                return True
            if isinstance(sub, ast.Name) and self.holds_copy(sub.id, unit):
                return True
            if self_attribute(sub) in self.attrs.get(unit.cls, ()):
                return True
        return False

    def is_export_reader(self, call):
        func = call.func
        if isinstance(func, ast.Name):
            return func.id in self.export_names
        return (isinstance(func, ast.Attribute) and func.attr in EXPORT_FUNCTIONS and isinstance(func.value, ast.Name)
                and func.value.id in self.export_modules)

    def opened_positions(self, call):
        """The argument expressions of `call` that its callee passes to a path read. An export_page.py reading
        function imported here is read whole: its source is in another file."""
        if self.is_export_reader(call):
            return list(call.args) + [k.value for k in call.keywords]
        out = []
        for helper in self.by_name.get(call_name(call), ()):
            wanted = self.opens.get(helper.name, set())
            for index, arg in enumerate(call.args):
                if index < len(helper.params) and helper.params[index] in wanted:
                    out.append(arg)
            out += [k.value for k in call.keywords if k.arg in wanted]
        return out

    def read_inputs(self, unit):
        """(line, expressions) of each read in `unit`: a path read, a git read list, a helper call's opened arguments."""
        for call in unit.calls:
            if is_path_read(call):
                yield call.lineno, call_inputs(call)
            else:
                yield call.lineno, self.opened_positions(call)
        for node in git_reads(unit):
            yield node.lineno, [node]

    def follow(self, unit):
        for _ in range(3):
            for node in unit.assigns:
                names = assigned_names(node)
                if self.is_copy(node.value, unit):
                    unit.tainted |= names
                    attrs = {self_attribute(t) for t in targets_of(node)} - {None}
                    if attrs and unit.cls:
                        self.attrs.setdefault(unit.cls, set()).update(attrs)
                used = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
                for name in names:
                    unit.derived.setdefault(name, set()).update(*(unit.derived.get(u, ()) for u in used))
        if any(self.is_copy(value, unit) for value in unit.returns):
            self.copy_functions.add(unit.name)
        passed = set()
        for _, inputs in self.read_inputs(unit):
            for name in {n.id for n in subtree(inputs) if isinstance(n, ast.Name)}:
                passed |= unit.derived.get(name, set())
        if passed:
            self.opens.setdefault(unit.name, set()).update(passed)

    def sinks(self, unit):
        """The lines of `unit` that read the copy."""
        lines = {line for line, inputs in self.read_inputs(unit) if any(self.is_copy(e, unit) for e in inputs)}
        lines |= {c.lineno for c in unit.strings if GIT_IN_STRING.search(c.value) and names_copy(c.value)}
        return sorted(lines)

    def any_reads(self, unit):
        """The lines of `unit` that read any path, itself or through a helper. The command line front's calls of the
        mode functions are not reads."""
        skip = EXPORT_FRONT.get(unit.qual, ())
        return {c.lineno for c in unit.calls
                if is_path_read(c) or (call_name(c) not in skip and self.opened_positions(c))}


def python_readers(rel, text):
    """[line] of each read of the copy in the Python source `text`, less what ALLOWED lets through."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as err:
        raise Unreadable("%s: cannot parse: %s" % (rel, err))
    analysis = Analysis(tree)
    found = set()
    for unit in analysis.units:
        lines = analysis.sinks(unit)
        if rel == EXPORT:
            lines = [] if unit.name in EXPORT_FUNCTIONS else sorted(set(lines) | analysis.any_reads(unit))
        found.update(lines[ALLOWED.get((rel, unit.qual), 0):][:1])  # one finding per function: its first read
    return sorted(found)


def blank_code(text, shell):
    """(code lines, strings): `text` with each comment and the inside of each string blanked, split by line, and the
    strings as (line, body). A template literal, a shell string and a block comment may span lines. A JavaScript
    quote with no close on its line is text (a JSX `Don't`), not a string."""
    out, strings, i, n, line, word_start = [], [], 0, len(text), 1, True
    while i < n:
        ch = text[i]
        if shell and ch == "#" and word_start:
            while i < n and text[i] != "\n":
                i += 1
            continue
        if not shell and text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if not shell and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("\n" * text.count("\n", i, end))
            line += text.count("\n", i, end)
            i = end
            continue
        if ch in "'\"`":
            stops = ch if shell or ch == "`" else ch + "\n"
            j = i + 1
            while j < n and text[j] not in stops:
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == ch:
                body = text[i + 1:j]
                strings.append((line, body))
                out.append(ch + ch + "\n" * body.count("\n"))
                line += body.count("\n")
                i = j + 1
                word_start = False
                continue
        out.append(ch)
        if ch == "\n":
            line += 1
        word_start = ch in " \t\n;|&(" if shell else False
        i += 1
    return "".join(out).split("\n"), strings


ASSIGN = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*=(?![=>])")  # `name=` in shell, `name =` in JavaScript


def statements(code, shell):
    """[(first line, [lines])]: the code lines grouped into statements. A shell line that ends in `\\` and a
    JavaScript line inside open ( or [ go on to the next, so a wrapped call is one statement."""
    groups, depth = [], 0
    for number, c in enumerate(code, 1):
        if groups and (depth > 0 or (shell and code[number - 2].rstrip().endswith("\\"))):
            groups[-1][1].append(number)
        else:
            groups.append((number, [number]))
        if not shell:
            depth = max(0, depth + c.count("(") + c.count("[") - c.count(")") - c.count("]"))
    return groups


def line_readers(text, shell):
    """[line] of the first read in a JavaScript or shell file of the copy: a read word in a statement that names the
    copy, or names a variable assigned from it."""
    code, strings = blank_code(text, shell)
    groups = [(first, " ".join(code[n - 1] for n in lines), set(lines)) for first, lines in statements(code, shell)]
    texts = {first: [s for n, s in strings if n in lines] for first, _, lines in groups}
    layout_lines = {n for n, s in strings if s.endswith(LAYOUT_FILE)}
    tainted = set()

    def names(first, c):
        bodies = texts[first]
        if NAME_AFTER_SLASH.search(c) or NAME_IN_PATH.search(c) or any(names_copy(s) for s in bodies):
            return True
        return any(re.search(r"(?<![\w.$])%s(?![\w$])" % re.escape(v), c)
                   or any(re.search(r"\$\{?%s\b" % re.escape(v), s) for s in bodies) for v in tainted)

    while True:
        before = len(tainted)
        for first, c, _ in groups:
            if names(first, c):
                tainted |= set(ASSIGN.findall(c))
        if len(tainted) == before:
            break
    collection = any(COLLECTION_IN_PATH.search(s) or s in COLLECTIONS for _, s in strings) or any(
        re.search(r"\b(?:%s)\b" % "|".join(COLLECTIONS), c) for c in code)
    words = SHELL_READS | GIT_READS | (JS_READS - JS_PRESENCE)
    word = re.compile(r"(?<![\w-])(?:%s)(?![\w-])" % "|".join(sorted(map(re.escape, words))))
    presence = re.compile(r"\b(?:%s)\b" % "|".join(sorted(JS_PRESENCE)))
    for first, c, lines in groups:
        if lines & layout_lines or not names(first, c):
            continue
        git = any(s in GIT_READS or GIT_IN_STRING.search(s) for s in texts[first])
        if word.search(c) or git or (collection and presence.search(c)):
            return [first]
    return []


def kind_of(rel, text):
    name = os.path.basename(rel)
    if name.endswith(".py"):
        return "python"
    if name.endswith(JS_SUFFIXES):
        return "js"
    if name.endswith(SHELL_SUFFIXES):
        return "shell"
    if "." not in name:
        first = text.split("\n", 1)[0]
        if first.startswith("#!"):
            if "python" in first:
                return "python"
            if re.search(r"\b(?:ba|z|da)?sh\b", first):
                return "shell"
            if "node" in first:
                return "js"
    return None


def source_files(root):
    found = []
    for folder in SOURCE_FOLDERS:
        top = os.path.join(root, folder)
        for base, dirs, names in os.walk(top):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(names):
                rel = os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/")
                if guard.is_test_rel(rel) or name.startswith("_test"):
                    continue
                found.append(rel)
    return found


def read_text(path, rel):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as err:
        raise Unreadable("%s: cannot read: %s" % (rel, err))


def check_readers(root):
    """(findings, unknown, checked): checked counts the source files read as code."""
    findings, unknown, checked = [], [], 0
    for rel in source_files(root):
        path = os.path.join(root, *rel.split("/"))
        try:
            text = read_text(path, rel)
            kind = kind_of(rel, text)
            if kind is None:
                continue
            checked += 1
            hits = python_readers(rel, text) if kind == "python" else line_readers(text, kind == "shell")
        except Unreadable as err:
            unknown.append(str(err))
            continue
        findings += ["%s:%d: %s" % (rel, line, LIVE) for line in hits]
    return findings, unknown, checked


def says_backup(text):
    """True when one sentence of `text` has both the word copy and the word backup."""
    return any(re.search(r"\bcopy\b", s, re.I) and re.search(r"\bbackups?\b", s, re.I)
               for s in re.split(r"(?<=[.!?])\s+|\n\s*\n", text))


def check_prose(root):
    findings, unknown = [], []
    for rel in PROSE:
        try:
            text = read_text(os.path.join(root, *rel.split("/")), rel)
            if rel == EXPORT:  # the module docstring is the prose, not a code comment
                try:
                    text = ast.get_docstring(ast.parse(text)) or ""
                except (SyntaxError, ValueError) as err:
                    raise Unreadable("%s: cannot parse: %s" % (rel, err))
        except Unreadable as err:
            unknown.append(str(err))
            continue
        if not says_backup(text):
            findings.append("%s: %s" % (rel, NOT_BACKUP))
    return findings, unknown


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(HERE), help="the repo root to check (default: this repo)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    found, unknown, checked = check_readers(root)
    more, unread = check_prose(root)
    findings, unknown = found + more, unknown + unread
    for line in findings:
        print(line)
    if findings:
        return 1
    for line in unknown:
        print("unknown: " + line)
    if unknown:
        return 2
    print("checked %d source files and %d prose files: 0 findings" % (checked, len(PROSE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
