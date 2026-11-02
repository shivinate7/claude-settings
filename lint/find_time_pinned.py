#!/usr/bin/env python3
"""List the tests whose verdict depends on wall-clock speed. Read-only. Standard library only.

    python3 lint/find_time_pinned.py <root> [--json]

Decision test-strategy-reset, point 2: no test waits on a fixed sleep or a wall-clock bound. This
tool lists the tests that do. It fixes none, and it writes nothing. Each finding has one category:
- sleep: a real wait in a test file.
- elapsed-assert: an assert that reads a wall-clock reading or a difference of two.
- test-cap: a per-test or per-suite time limit.
- wait-cap: a fixed time bound on a wait for a condition or a child process (a hang guard).
  Kept apart because it may be fine. The plan decides case by case.

Scanned: test files only. Python is `test_*.py`, `*_test.py`, `conftest.py` or any `.py` under a
`tests` or `test` folder. JS and TS (`.js .mjs .cjs .jsx .ts .tsx .mts .cts`) is a `.test.` or
`.spec.` name, a `test_` or `test-` name, or any file under `__tests__`, `tests` or `test`. Swift is
`*Tests.swift`, `*Test.swift` or any file under a folder whose name ends `Tests`. Blind spot, by
design: shell, PowerShell and YAML tests are never read, so a sleep there is not listed.

Reading code, rule building-scanner-respects-strings: Python goes through `ast`, so a pattern
inside a comment or a string is never a call. This tool runs from `~/.claude/lint` against any
clone with no node install, so JS, TS and Swift cannot use the TypeScript or Swift parsers. Each
language family gets one single-pass masker instead. It returns text of the same length and the
same newlines, with every comment and every string or template body blanked. Patterns then run on
the masked text, so a comment opener inside a string, a multi-line template literal and a lone quote
cannot move a result. The JS masker keeps a stack for `${ ... }` holes (they are code), and treats
a `/` as a regex start by the token before it. A `'` or `"` opens a string only when the string
closes on the same line, so JSX text such as `<p>Don't</p>` stays text. The Swift masker nests
`/* */`, reads multi-line and `#"..."#` raw strings, and blanks an interpolation hole whole.

Blind spots of the patterns: a delay held in a variable (`setTimeout(r, ms)`) is not a literal, so
it is not listed. A clock name is tainted by a `const`/`let`/`var` (JS) or `let`/`var` (Swift)
declaration only, and it holds inside the `{...}` block of that declaration. Clock reads inside a Swift interpolation hole are masked.

Paths are relative to <root>. Output is one `<path>:<line>: <category>: <source line>` per finding
(one per line and category), then `UNREAD <path>: <reason>` per file that could not be read, then a
summary. A file that cannot be read or parsed is unread, never clean.
Exit 0: nothing found, nothing unread. Exit 1: findings. Exit 2: the root cannot be read, or nothing
found but some file unread, so the result is unknown.
Cost: one `git ls-files` (or one folder walk outside a git tree) and one read of each test file. No
process stays running.
"""
import argparse
import ast
import json
import os
import re
import sys
import warnings
from bisect import bisect_right

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

MAX_BYTES = 1_000_000
CATEGORIES = ("sleep", "elapsed-assert", "test-cap", "wait-cap")
WALK_SKIP = {".git", "node_modules", ".build", "DerivedData", "venv", ".venv"}
JS_EXTS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")
TEXT_MAX = 120


# ---- which files are tests -------------------------------------------------------------------------

def kind_of(rel):
    """The language family of a test file, or None for a file this tool never reads."""
    parts = rel.split("/")
    base, folders = parts[-1], parts[:-1]
    if base.endswith(".py"):
        if (base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py"
                or {"tests", "test"} & set(folders)):
            return "python"
    elif base.endswith(JS_EXTS):
        if (".test." in base or ".spec." in base or base.startswith(("test_", "test-"))
                or {"__tests__", "tests", "test"} & set(folders)):
            return "js"
    elif base.endswith(".swift"):
        if base.endswith(("Tests.swift", "Test.swift")) or any(f.endswith("Tests") for f in folders):
            return "swift"
    return None


def list_files(root):
    """Tracked files when root is a git tree, else every file outside WALK_SKIP. None when git fails."""
    dotgit = os.path.join(root, ".git")
    if os.path.isfile(dotgit) or os.path.exists(os.path.join(dotgit, "HEAD")):  # an empty `.git` folder is no repo
        proc = _nowindow.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
        if proc.returncode != 0:
            return None  # a walk would add untracked files, so the result is unknown
        return sorted(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP]
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(out)


# ---- numbers and brackets, shared by the JS and Swift scanners -------------------------------------

_NUM = re.compile(r"(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?)n?")
_NUMEXPR = re.compile(r"[\d_.\s*+/()-]+")  # 60 * 1000 is a fixed bound as much as 60000 is


def is_num(text, positive=False):
    """True when text is a number literal, or arithmetic on literals only. `positive` demands a value over 0."""
    s = text.strip()
    if not s:
        return False
    if _NUM.fullmatch(s):
        if not positive:
            return True
        try:
            body = s.rstrip("n").replace("_", "")
            return (int(body, 0) if body[:2].lower() in ("0x", "0b") else float(body)) > 0
        except ValueError:
            return False
    return bool(_NUMEXPR.fullmatch(s)) and (not positive or re.search(r"[1-9]", s) is not None)


_BRACKET = re.compile(r"[()\[\]{}]")
_ARG_TOKEN = re.compile(r"[()\[\]{},]")


def find_close(m, i):
    """Index of the bracket that closes the one at m[i], or -1. m is masked, so no string holds a bracket."""
    depth = 0
    for tok in _BRACKET.finditer(m, i):
        depth += 1 if tok.group() in "([{" else -1
        if depth == 0:
            return tok.start()
        if depth < 0:
            return -1
    return -1


def split_args(m, a, b):
    """Spans of the top-level arguments in m[a:b]. A trailing comma adds no empty argument."""
    spans, depth, start = [], 0, a
    for tok in _ARG_TOKEN.finditer(m, a, b):
        ch = tok.group()
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            spans.append((start, tok.start()))
            start = tok.end()
    spans.append((start, b))
    if len(spans) > 1 and not m[spans[-1][0]:spans[-1][1]].strip():
        spans.pop()
    return spans


_CONTINUES_AFTER = set("+-*/%&|=<>?:.")
_CONTINUES_BEFORE = set(".?:+-*/%&|=<>")


def scan_expr(m, i):
    """End of the expression that starts at m[i]: a `;` or `,` or closing bracket at depth 0, or a newline
    that no operator continues, else the end of text."""
    depth, n, j = 0, len(m), i
    while j < n:
        c = m[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif depth == 0:
            if c in ";,":
                return j
            if c == "\n":
                k = j - 1
                while k >= i and m[k] in " \t\r":
                    k -= 1
                q = j + 1
                while q < n and m[q] in " \t\r\n":
                    q += 1
                started = k >= i
                if started and m[k] not in _CONTINUES_AFTER and (q >= n or m[q] not in _CONTINUES_BEFORE):
                    return j
        j += 1
    return n


_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_ANNOT = re.compile(r"\s*(?::[^=;\n]*)?")
_ASSIGN = re.compile(r"\s*=(?![=>])")
_COMMA = re.compile(r"\s*,\s*")


def declarations(m, decl_re):
    """(name, keyword position, initializer start, initializer end) per declarator that `decl_re` introduces."""
    found = []
    for kw in decl_re.finditer(m):
        pos = kw.end()
        while True:
            ident = _IDENT.match(m, pos)
            if not ident:
                break
            p = _ANNOT.match(m, ident.end()).end()
            eq = _ASSIGN.match(m, p)
            if eq:
                end = scan_expr(m, eq.end())
                found.append((ident.group(), kw.start(), eq.end(), end))
                p = end
            nxt = _COMMA.match(m, p)
            if not nxt:
                break
            pos = nxt.end()
    return found


def block_ranges(m, positions):
    """{position: (start, end)} of the innermost `{...}` around each position, or the whole text when none.
    A clock name is only a clock inside the block that declares it, so a short name such as `run` in
    one test never taints the same name in another."""
    tokens = [(t.start(), t.group()) for t in re.finditer(r"[{}]", m)]
    close_of, stack = {}, []
    for pos, ch in tokens:
        if ch == "{":
            stack.append(pos)
        elif stack:
            close_of[stack.pop()] = pos
    ranges, stack, j = {}, [], 0
    for pos in sorted(set(positions)):
        while j < len(tokens) and tokens[j][0] < pos:
            if tokens[j][1] == "{":
                stack.append(tokens[j][0])
            elif stack:
                stack.pop()
            j += 1
        ranges[pos] = (stack[-1] + 1, close_of.get(stack[-1], len(m))) if stack else (0, len(m))
    return ranges


_KEYWORDS = {"if", "while", "for", "switch", "catch", "return", "typeof", "await", "in", "of", "void", "delete",
             "new", "case", "else", "do", "yield", "throw", "guard", "let", "var", "try", "func"}
_PAREN_OR_BRACE = re.compile(r"[()\[\]{}]")


def inside_foreign_call(m, a, p, pass_through):
    """True when position p, in an initializer that starts at a, sits inside the arguments of a call that
    is not one of `pass_through`. A clock handed to such a call is an input, not a measured duration."""
    stack = []
    for tok in _PAREN_OR_BRACE.finditer(m, a, p):
        ch = tok.group()
        if ch in "([{":
            callee = None
            if ch == "(":
                before = m[max(0, tok.start() - 80):tok.start()].rstrip()
                word = re.search(r"[\w$]+$", before)
                if before.endswith((")", "]")):
                    callee = ""
                elif word and word.group() not in _KEYWORDS:
                    callee = word.group()
            stack.append(callee)
        elif stack:
            stack.pop()
    return any(c is not None and c not in pass_through for c in stack)


_READ = re.compile(r"(?<![\w$.])[A-Za-z_$][\w$]*(?![\w$])")


def reads_tainted(m, a, b, tainted, pass_through=None):
    """True when m[a:b] reads a name inside the block of a tainted declaration of it. An object key or a
    call label (`at:` after `{`, `,` or `(`) is not a read. With `pass_through`, a read inside the
    arguments of any other call does not count."""
    for hit in _READ.finditer(m, a, b):
        for scope_start, scope_end, decl_pos in tainted.get(hit.group(), ()):
            if scope_start <= hit.start() < scope_end and decl_pos < hit.start():
                label = m[hit.end():b].lstrip().startswith(":") and m[a:hit.start()].rstrip()[-1:] in ("{", ",", "(")
                if not label and not (pass_through is not None
                                      and inside_foreign_call(m, a, hit.start(), pass_through)):
                    return True
    return False


def clock_taint(m, decl_re, clock_re, pass_through):
    """{name: [(block start, block end, declaration position)]} for names whose initializer holds a clock
    reading or a tainted name, repeated until nothing changes."""
    decls = declarations(m, decl_re)
    ranges = block_ranges(m, [d[1] for d in decls])
    tainted, done, changed = {}, set(), True
    while changed:
        changed = False
        for idx, (name, pos, start, end) in enumerate(decls):
            if idx in done:
                continue
            clocked = any(not inside_foreign_call(m, start, hit.start(), pass_through)
                          for hit in clock_re.finditer(m, start, end))
            if clocked or reads_tainted(m, start, end, tainted, pass_through):
                tainted.setdefault(name, []).append(ranges[pos] + (pos,))
                done.add(idx)
                changed = True
    return tainted


def reads_clock(m, a, b, clock_re, tainted):
    return clock_re.search(m, a, b) is not None or reads_tainted(m, a, b, tainted)


class Hits:
    """One finding per (line, category). Lines come from a masked text, whose newlines match the source."""

    def __init__(self, m):
        self.starts = [0] + [x.end() for x in re.finditer("\n", m)]
        self.found = set()

    def add(self, pos, category):
        self.found.add((bisect_right(self.starts, pos), category))


# ---- Python, through ast -----------------------------------------------------------------------------

PY_CLOCKS = {"time.time", "time.monotonic", "time.perf_counter", "time.process_time", "time.time_ns",
             "time.monotonic_ns", "time.perf_counter_ns", "datetime.now", "datetime.datetime.now",
             "datetime.utcnow", "datetime.datetime.utcnow"}
PY_SLEEPS = {"time.sleep", "asyncio.sleep"}
PY_MARK_CAP = {"pytest.mark.timeout"}
PY_DECORATOR_CAP = {"timeout", "timeout_decorator.timeout"}
PY_SIGNAL_CAP = {"signal.alarm", "signal.setitimer"}
# A clock handed to any other call (`decisions = sweep(now=time.time())`) is an input, not a measured
# duration, so the call's result is not tainted. These calls only reshape a number, so they pass it on.
PY_PASS_THROUGH = {"round", "int", "float", "abs", "max", "min", "sum", "divmod", "math.floor", "math.ceil"}


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def py_number(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


def target_names(t):
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        return [n for e in t.elts for n in target_names(e)]
    if isinstance(t, ast.Starred):
        return target_names(t.value)
    return []


def walk_scope(root):
    """Every node under the module root, not entering a function, so a function's names stay in its own scope."""
    todo = [root]
    while todo:
        node = todo.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            todo.append(child)


def scan_python(text):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # an odd escape in a string is a warning, not a reason to skip the file
        tree = ast.parse(text)
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                imports[a.asname or a.name] = node.module + "." + a.name

    def names_of(call):
        d = dotted(call.func)
        if d is None:
            return set()
        first, _, rest = d.partition(".")
        resolved = imports[first] + ("." + rest if rest else "") if first in imports else d
        return {d, resolved}

    def is_clock(node):
        return isinstance(node, ast.Call) and bool(names_of(node) & PY_CLOCKS)

    def holds_clock(node, tainted, pass_through_only=False):
        """True when node reads a clock call or a tainted name. With the flag on, the arguments of a call
        count only when that call is a pass-through."""
        if isinstance(node, ast.Call):
            if is_clock(node):
                return True
            parts = [node.func]
            if not pass_through_only or names_of(node) & PY_PASS_THROUGH:
                parts += node.args + [k.value for k in node.keywords]
            return any(holds_clock(p, tainted, pass_through_only) for p in parts)
        if isinstance(node, ast.Name):
            return isinstance(node.ctx, ast.Load) and node.id in tainted
        return any(holds_clock(c, tainted, pass_through_only) for c in ast.iter_child_nodes(node))

    found = set()
    decorator_calls = {id(d) for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                       for d in n.decorator_list if isinstance(d, ast.Call)}
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        names = names_of(call)
        first = call.args[0] if call.args else None
        if names & PY_SLEEPS:
            if not (isinstance(first, ast.Constant) and not isinstance(first.value, bool)
                    and isinstance(first.value, (int, float)) and first.value == 0):
                found.add((call.lineno, "sleep"))  # sleep(0) is a yield, not a wait
        capped = bool(names & PY_MARK_CAP) or (id(call) in decorator_calls and bool(names & PY_DECORATOR_CAP))
        if names & PY_SIGNAL_CAP and not (
                names & {"signal.alarm"} and isinstance(first, ast.Constant) and first.value == 0):
            capped = True  # signal.alarm(0) cancels a limit, so it is not one
        if capped:
            found.add((call.lineno, "test-cap"))
        elif any(k.arg == "timeout" and py_number(k.value) for k in call.keywords):
            found.add((call.lineno, "wait-cap"))

    roots = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for root in roots:
        nodes = list(walk_scope(root)) if isinstance(root, ast.Module) else list(ast.walk(root))
        assigns = []
        for n in nodes:
            if isinstance(n, ast.Assign):
                assigns.append(([x for t in n.targets for x in target_names(t)], n.value))
            elif isinstance(n, ast.AnnAssign) and n.value is not None:
                assigns.append((target_names(n.target), n.value))
            elif isinstance(n, ast.AugAssign):
                assigns.append((target_names(n.target), n.value))
            elif isinstance(n, ast.NamedExpr):
                assigns.append((target_names(n.target), n.value))
        tainted, changed = set(), True
        while changed:
            changed = False
            for targets, value in assigns:
                if not set(targets) <= tainted and holds_clock(value, tainted, True):
                    tainted.update(targets)
                    changed = True
        for n in nodes:
            if isinstance(n, ast.Assert) and holds_clock(n.test, tainted):
                found.add((n.lineno, "elapsed-assert"))
            elif isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if name.startswith("assert") and holds_clock(n, tainted):
                    found.add((n.lineno, "elapsed-assert"))
    return found


# ---- JS and TS: one-pass masker, then patterns -------------------------------------------------------

_RE_PREV = set("(,=:[!&|?{};+-*%<>~^")
_RE_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "yield", "await", "delete", "void",
             "throw", "new"}


def mask_js(src):
    """src with every comment and every string, template or regex body blanked. Same length, same newlines.
    Quote and backtick delimiters stay."""
    n = len(src)
    out = list(src)
    holes = []  # brace depth at each open `${`
    depth = 0
    last, word = "", ""  # last significant code char, and the identifier ending there
    i = 0

    def blank(a, b):
        for k in range(a, b):
            if out[k] not in "\r\n":
                out[k] = " "

    def template(k):
        """Blank template text from k. Returns (next index, True when it stopped at a `${`)."""
        while k < n:
            ch = src[k]
            if ch == "\\":
                blank(k, min(k + 2, n))
                k += 2
            elif ch == "`":
                return k + 1, False
            elif ch == "$" and src[k + 1:k + 2] == "{":
                holes.append(depth)
                return k + 2, True
            else:
                blank(k, k + 1)
                k += 1
        return n, False

    def string_end(k, q):
        """Index after the closing quote of the string opened at k, or -1 when the line ends first."""
        k += 1
        while k < n:
            ch = src[k]
            if ch == "\\":
                k += 3 if src[k + 1:k + 3] == "\r\n" else 2
            elif ch == q:
                return k + 1
            elif ch == "\n":
                return -1
            else:
                k += 1
        return -1

    def regex_end(k):
        """(index of the closing slash, index after the flags) of the regex opened at k, or None."""
        k += 1
        in_class = False
        while k < n:
            ch = src[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "\n":
                return None
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                end = k + 1
                while end < n and src[end].isalpha():
                    end += 1
                return k, end
            k += 1
        return None

    while i < n:
        c = src[i]
        if c in " \t\r\n\f\v":
            i += 1
            continue
        d = src[i + 1] if i + 1 < n else ""
        if c == "/" and d == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and d == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c == "`":
            i, hole = template(i + 1)
            last, word = ("{", "") if hole else ("`", "")
            continue
        if c in "'\"":
            j = string_end(i, c)
            if j > 0:
                blank(i + 1, j - 1)
                i = j
            else:
                i += 1  # a lone quote in text such as JSX: not a string
            last, word = c, ""
            continue
        if c == "/":
            span = regex_end(i) if (last == "" or last in _RE_PREV or word in _RE_WORDS) else None
            if span:
                blank(i + 1, span[0])
                i = span[1]
                last, word = ")", ""
            else:
                i += 1
                last, word = "/", ""
            continue
        if c.isalnum() or c in "_$":
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            word, last = src[i:j], src[j - 1]
            i = j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if holes and depth == holes[-1]:
                holes.pop()
                i, hole = template(i + 1)
                last, word = ("{", "") if hole else ("`", "")
                continue
            depth = max(depth - 1, 0)
        last, word = c, ""
        i += 1
    return "".join(out)


JS_CLOCK = re.compile(r"(?<![\w$])(?:Date\.now|performance\.now)\s*\(|(?<![\w$])process\.hrtime(?:\.bigint)?\s*\("
                      r"|(?<![\w$])new\s+Date\s*\(\s*\)")
JS_PASS_THROUGH = {"round", "floor", "ceil", "trunc", "abs", "max", "min", "Number", "parseInt", "parseFloat",
                   "BigInt", "hrtime"}
JS_DECL = re.compile(r"(?<![\w$.])(?:const|let|var)\s+(?=[A-Za-z_$])")
JS_ASSERT = re.compile(r"(?<![\w$.])(?:expect|assert)(?:\s*\.\s*[A-Za-z_$][\w$]*)*\s*\(")
JS_TEST_HEAD = re.compile(r"(?<![\w$.])(?:it|test|describe)\b")
JS_TEST_MODS = {"only", "skip", "concurrent", "fails", "todo", "sequential", "serial", "failing", "each"}
JS_MOD = re.compile(r"\.\s*([A-Za-z_$][\w$]*)")
JS_TIMEOUT_KEY = re.compile(r"(?<![\w$])timeout\s*:")


def parse_test_head(m, i):
    """Index of the `(` that opens the argument list of an it/test/describe call whose name ends at i."""
    n = len(m)
    while True:
        j = i
        while j < n and m[j] in " \t\r\n":
            j += 1
        if j >= n:
            return None
        if m[j] == ".":
            mod = JS_MOD.match(m, j)
            if not mod or mod.group(1) not in JS_TEST_MODS:
                return None
            i = mod.end()
            if mod.group(1) == "each":  # the table call, or a template table, comes before the test call
                k = i
                while k < n and m[k] in " \t\r\n":
                    k += 1
                if k < n and m[k] == "(":
                    close = find_close(m, k)
                elif k < n and m[k] == "`":
                    close = m.find("`", k + 1)
                else:
                    return None
                if close < 0:
                    return None
                i = close + 1
            continue
        return j if m[j] == "(" else None


def scan_js(text):
    m = mask_js(text)
    hits = Hits(m)
    fake_clock = re.search(r"(?<![\w$])useFakeTimers\s*\(", m) is not None
    claimed = []  # character ranges whose `timeout:` a test-cap finding already holds

    def args_of(open_idx):
        close = find_close(m, open_idx)
        return None if close < 0 else (close, split_args(m, open_idx + 1, close))

    if not fake_clock:  # under a fake clock nothing really waits
        for mm in re.finditer(r"(?<![\w$])setTimeout\s*\(", m):
            before = m[max(0, mm.start() - 80):mm.start()]
            if before.endswith("jest."):
                continue
            got = args_of(mm.end() - 1)
            if not got:
                continue
            spans = got[1]
            awaited = re.search(r"(?<![\w$])await\s+(?:[\w$]+\s*\.\s*)*$", before) is not None
            if (awaited and is_num(m[spans[0][0]:spans[0][1]], True)) or (
                    len(spans) >= 2 and is_num(m[spans[-1][0]:spans[-1][1]], True)):
                hits.add(mm.start(), "sleep")
        for mm in re.finditer(r"(?<![\w$])await\s+(?:sleep|delay|wait|setTimeoutPromise)\s*\(", m):
            got = args_of(mm.end() - 1)
            if got and is_num(m[got[1][0][0]:got[1][0][1]], True):
                hits.add(mm.start(), "sleep")
        for mm in re.finditer(r"(?<![\w$])Atomics\s*\.\s*wait\s*\(", m):
            got = args_of(mm.end() - 1)
            if got and is_num(m[got[1][-1][0]:got[1][-1][1]], True):
                hits.add(mm.start(), "sleep")

    tainted = clock_taint(m, JS_DECL, JS_CLOCK, JS_PASS_THROUGH)
    for mm in JS_ASSERT.finditer(m):
        got = args_of(mm.end() - 1)
        if got and reads_clock(m, mm.end(), got[0], JS_CLOCK, tainted):
            hits.add(mm.start(), "elapsed-assert")

    for mm in re.finditer(r"(?<![\w$])jest\s*\.\s*setTimeout\s*\(|(?<![\w$])this\s*\.\s*timeout\s*\(", m):
        hits.add(mm.start(), "test-cap")
    for mm in re.finditer(r"(?<![\w$])vi\s*\.\s*setConfig\s*\(", m):
        got = args_of(mm.end() - 1)
        if got and re.search(r"(?<![\w$])testTimeout(?![\w$])", m[mm.end():got[0]]):
            hits.add(mm.start(), "test-cap")
            claimed.append((mm.end(), got[0]))
    for mm in re.finditer(r"(?<![\w$])testTimeout\s*:", m):
        if not any(a <= mm.start() < b for a, b in claimed):
            hits.add(mm.start(), "test-cap")
    for head in JS_TEST_HEAD.finditer(m):
        open_idx = parse_test_head(m, head.end())
        got = args_of(open_idx) if open_idx is not None else None
        if not got:
            continue
        spans = got[1]
        capped = len(spans) >= 2 and is_num(m[spans[-1][0]:spans[-1][1]])
        for s, e in spans:
            if m[s:e].lstrip().startswith("{"):
                for key in JS_TIMEOUT_KEY.finditer(m, s, e):
                    capped = True
                    claimed.append((key.start(), key.end()))
        if capped:
            hits.add(head.start(), "test-cap")

    for mm in JS_TIMEOUT_KEY.finditer(m):
        if any(a <= mm.start() < b for a, b in claimed):
            continue
        end = re.compile(r"[,})\]\n]").search(m, mm.end())
        if is_num(m[mm.end():end.start() if end else len(m)]):
            hits.add(mm.start(), "wait-cap")
    for mm in re.finditer(r"(?<![\w$])AbortSignal\s*\.\s*timeout\s*\(", m):
        got = args_of(mm.end() - 1)
        if got and is_num(m[got[1][0][0]:got[1][0][1]]):
            hits.add(mm.start(), "wait-cap")
    return hits.found


# ---- Swift: one-pass masker, then patterns -----------------------------------------------------------

SWIFT_CLOCK = re.compile(
    r"(?<![\w$])Date\s*\(\s*\)|(?<![\w$])Date\.now\b|CFAbsoluteTimeGetCurrent\s*\(|DispatchTime\s*\.\s*now\s*\("
    r"|ProcessInfo\s*\.\s*processInfo\s*\.\s*systemUptime|mach_absolute_time\s*\("
    r"|\b(?:Continuous|Suspending)Clock\b|\.timeIntervalSince(?:Now)?\b|\.duration\s*\(\s*to\s*:"
    r"|\bclock\s*\.\s*measure\b")
SWIFT_PASS_THROUGH = {"abs", "max", "min", "round", "floor", "ceil", "trunc", "Double", "Int", "Float", "CGFloat",
                      "timeIntervalSince", "distance", "duration", "advanced"}
SWIFT_DECL = re.compile(r"(?<![\w$.])(?:let|var)\s+(?=[A-Za-z_])")
SWIFT_ASSERT = re.compile(r"(?<![\w$])(?:XCTAssert\w*|#expect|#require)\s*\(")


def mask_swift(src):
    """src with every comment and every string body blanked, interpolation holes included. Same length,
    same newlines. String delimiters stay."""
    n = len(src)
    out = list(src)

    def blank(a, b):
        for k in range(a, b):
            if out[k] not in "\r\n":
                out[k] = " "

    def raw_start(k):
        while k < n and src[k] == "#":
            k += 1
        return k < n and src[k] == '"'

    def skip_hole(k):
        """Index after the `)` that closes an interpolation whose body starts at k."""
        d = 1
        while k < n and d:
            ch = src[k]
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
            elif ch == '"' or (ch == "#" and raw_start(k)):
                k = string_span(k)[2]
                continue
            k += 1
        return k

    def string_span(k):
        """(body start, body end, index after the string) for the string whose `#`s or quote start at k."""
        hashes = 0
        while src[k] == "#":
            hashes += 1
            k += 1
        triple = src.startswith('"""', k)
        body = k + (3 if triple else 1)
        close = ('"' * (3 if triple else 1)) + "#" * hashes
        esc = "\\" + "#" * hashes
        p = body
        while p < n:
            if src.startswith(esc, p):
                p = skip_hole(p + len(esc) + 1) if src.startswith("(", p + len(esc)) else p + len(esc) + 1
                continue
            if src.startswith(close, p):
                return body, p, p + len(close)
            if not triple and src[p] == "\n":
                return body, p, p  # a one-line string that never closes ends with its line
            p += 1
        return body, n, n

    i = 0
    while i < n:
        c = src[i]
        d = src[i + 1] if i + 1 < n else ""
        if c == "/" and d == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "/" and d == "*":
            depth, k = 1, i + 2
            while k < n and depth:
                if src.startswith("/*", k):
                    depth += 1
                    k += 2
                elif src.startswith("*/", k):
                    depth -= 1
                    k += 2
                else:
                    k += 1
            blank(i, k)
            i = k
        elif c == '"' or (c == "#" and raw_start(i)):
            start, end, after = string_span(i)
            blank(start, end)
            i = max(after, i + 1)
        else:
            i += 1
    return "".join(out)


def scan_swift(text):
    m = mask_swift(text)
    hits = Hits(m)

    def args_of(open_idx):
        close = find_close(m, open_idx)
        return None if close < 0 else m[open_idx + 1:close]

    def declared(pos):
        return re.search(r"\bfunc\s+$", m[max(0, pos - 20):pos]) is not None

    for mm in re.finditer(r"(?<![\w.])(?:sleep|usleep)\s*\(|(?<![\w])(?:Thread|Task)\s*\.\s*sleep\s*\(", m):
        if not declared(mm.start()):
            hits.add(mm.start(), "sleep")

    tainted = clock_taint(m, SWIFT_DECL, SWIFT_CLOCK, SWIFT_PASS_THROUGH)
    for mm in SWIFT_ASSERT.finditer(m):
        close = find_close(m, mm.end() - 1)
        if close >= 0 and reads_clock(m, mm.end(), close, SWIFT_CLOCK, tainted):
            hits.add(mm.start(), "elapsed-assert")

    for mm in re.finditer(r"(?<![\w.])measure\s*[({]|(?<![\w])self\s*\.\s*measure\s*[({]|executionTimeAllowance"
                          r"|\.timeLimit\s*\(", m):
        if not declared(mm.start()):
            hits.add(mm.start(), "test-cap")

    for mm in re.finditer(r"(?<![\w])(wait|fulfillment|waitForExpectations|waitForExistence)\s*\(", m):
        body = args_of(mm.end() - 1)
        if body is None or declared(mm.start()) or not re.search(r"(?<![\w])timeout\s*:", body):
            continue
        label = {"wait": r"(?<![\w])for\s*:", "fulfillment": r"(?<![\w])of\s*:"}.get(mm.group(1))
        if label is None or re.search(label, body):
            hits.add(mm.start(), "wait-cap")
    return hits.found


# ---- driver ------------------------------------------------------------------------------------------

def scan_file(root, rel, kind):
    """(findings as (line, category) pairs, lines of the file) or (None, reason) when it cannot be read."""
    path = os.path.join(root, rel)
    try:
        if not os.path.isfile(path):
            return None, "not a regular file"
        if os.path.getsize(path) > MAX_BYTES:
            return None, f"over {MAX_BYTES} bytes"
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return None, f"cannot be read: {e.strerror or e}"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "not UTF-8"
    try:
        found = {"python": scan_python, "js": scan_js, "swift": scan_swift}[kind](text)
    except SyntaxError as e:
        return None, f"syntax error at line {e.lineno}: {e.msg}"
    except (ValueError, RecursionError, MemoryError) as e:
        return None, f"cannot be parsed: {type(e).__name__}: {e}"
    return found, re.split(r"\r\n|\r|\n", text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", help="the repo root, or any folder")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"unknown: the folder {root} cannot be read")
        return 2
    files = list_files(root)
    if files is None:
        print(f"unknown: git ls-files failed in {root}")
        return 2
    findings, unread = [], []
    for rel in files:
        kind = kind_of(rel)
        if kind is None:
            continue
        found, detail = scan_file(root, rel, kind)
        if found is None:
            unread.append({"path": rel, "reason": detail})
            continue
        for line, category in sorted(found):
            src = detail[line - 1].strip() if 0 < line <= len(detail) else ""
            findings.append({"path": rel, "line": line, "category": category, "lang": kind,
                             "text": src[:TEXT_MAX]})
    counts = {c: sum(1 for f in findings if f["category"] == c) for c in CATEGORIES}
    if args.json:
        print(json.dumps({"findings": findings, "unread": unread, "counts": counts}, indent=1))
    else:
        for f in findings:
            print(f"{f['path']}:{f['line']}: {f['category']}: {f['text']}")
        for u in unread:
            print(f"UNREAD {u['path']}: {u['reason']}")
        nfiles = len({f["path"] for f in findings})
        print(f"{len(findings)} time-pinned in {nfiles} files (sleep {counts['sleep']}, "
              f"elapsed-assert {counts['elapsed-assert']}, test-cap {counts['test-cap']}, "
              f"wait-cap {counts['wait-cap']}); {len(unread)} unread")
    if findings:
        return 1
    return 2 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
