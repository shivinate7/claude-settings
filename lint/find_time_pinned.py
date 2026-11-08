#!/usr/bin/env python3
"""List the tests whose verdict depends on wall-clock speed. Read-only. Standard library only.

    python3 lint/find_time_pinned.py <root> [--json]

Lists the tests whose verdict can move with the real clock: a fixed wait, a bound on elapsed time,
a time limit, or a read of the real date. Decision test-practices P5 covers all four: no fixed
sleep, a synthetic clock for a verdict that depends on elapsed time, a hang guard allowed, and a
date read counted as a real clock. The tool fixes none, and it writes nothing. Each finding has one category:
- sleep: a real wait in a test file. Not a poll interval: a `sleep` in a Python loop that has both a
  condition and a cap is a wait-cap. A condition is a while-test term other than a bare `True` and a
  clock comparison, or an `if` in the body that returns, breaks, raises or fails and tests something
  other than a clock. A cap is a clock compared in the while test or in such an `if`, or
  `range(<literal>)` in a `for`. A bare sleep, `while True` with no exit, a condition with no cap, a cap
  with no condition and a sleep after the loop stay sleep.
- elapsed-assert: an assert that reads a wall-clock reading or a difference of two.
- test-cap: a per-test or per-suite time limit (a hang guard, like wait-cap).
- wait-cap: a fixed time bound on a wait for a condition or a child process, or the poll interval of such
  a capped wait loop (a hang guard). A hang guard
  (test-cap or wait-cap) is allowed (decision test-practices P5): it
  is listed, never counted as time-pinned, and never sets exit 1. Check that each cap sits well above
  the run, so it only stops a hang and never decides a verdict by speed.
- calendar: a read of the real date or the machine's zone (`datetime.now()`, `date.today()`,
  `time.localtime(<any>)`, `time.ctime(<any>)`, `time.gmtime()`, `time.asctime()`, `time.strftime(fmt)`,
  `datetime.fromtimestamp(<x>)` and `<x>.astimezone()` with no zone argument, Swift `Date()`,
  `Date.now`, `Date(timeIntervalSinceNow: <x>)`,
  `Calendar.current` and `TimeZone.current`, `time.tzname`, `time.timezone`, the date libraries `pendulum.now()`, `arrow.now()`, `arrow.utcnow()`,
  `pendulum.today()`, `pd.Timestamp.now()`, `pd.Timestamp.today()`, `pd.Timestamp.utcnow()` and Django
  `timezone.now()`, plus, with no argument or only a zone keyword (`tzinfo=` or `timezone=`),
  `arrow.get()`, `timezone.localtime()` and `timezone.localdate()`, JS
  `new Date()`, `new Date(<clock>)` where the argument reads `Date.now` or `performance.now` directly
  or through a name that holds one, any `Date(...)` call without `new`, and the JS date libraries
  `dayjs()`, `dayjs.utc()`, `new dayjs()`, `moment()`, `moment.utc()` and `Temporal.Now.*()`).
  `new Date(0)`, `new Date(EPOCH_MS)` with a declared constant, `dayjs(0)`, `moment.utc(EPOCH)`,
  `arrow.get(0)`, `timezone.localtime(fixed_dt)`, `pendulum.datetime(...)`, `time.gmtime(EPOCH)`, a
  `tz` argument on `fromtimestamp` or `astimezone`, and Swift `Date(timeIntervalSince1970: 0)` read no
  clock or local zone and are not listed. A Swift `Date()`, `Date.now` or `Date(timeIntervalSinceNow:)` that an assert subtracts is that assert's
  elapsed-assert row only. A fake clock hides every calendar row in its scope, even a read it does not fake: in Python a
  `@freeze_time(...)` def or class, or the body of a `with freeze_time(...)`; in JS a file that calls
  `jest.useFakeTimers()` or `vi.useFakeTimers()`. Its elapsed-assert rows stay. `time.tzname` and
  `time.timezone` stay listed under `freeze_time`, because freezegun fakes no zone. `Temporal.Now.*()`
  stays listed under JS fake timers, which fake Date only.

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

Blind spots of the patterns: a fake clock started by hand (`freeze_time(...).start()`, a `freezer`
fixture) is not seen, so the reads under it are still listed. A delay held in a variable (`setTimeout(r, ms)`) is not a literal, so
it is not listed. A clock name is tainted by a `const`/`let`/`var` (JS) or `let`/`var` (Swift)
declaration only, and it holds inside the `{...}` block of that declaration. Python taint stays in its
own function, so a nested def that asserts on a name its outer function tainted is missed. A function
value (an arrow or function expression, a closure, a lambda or def) taints its name only when its
return value reads a clock; a Swift `func` or a JS `function` declaration taints nothing. A clock handed
to a call is an input, which decision test-practices P5 endorses, so it taints nothing. In an assert
it still counts when it is an operand of `-` or the receiver or argument of `.timeIntervalSince` or
`.duration(to:`: that is a measured duration. An assert's message argument is not read. Clock reads inside a Swift interpolation
hole are masked.

Paths are relative to <root>. Output is one `<path>:<line>: <category>: <source line>` per finding
(one per line and category), then `UNREAD <path>: <reason>` per file that could not be read, then a
summary. A file that cannot be read or parsed is unread, never clean.
Exit 0: no time-pinned finding, nothing unread (hang-guard rows do not count). Exit 1: a finding that is
not a hang guard. Exit 2: the root cannot be read, or some file
is unread and nothing but hang guards was found, so the result is unknown.
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
CATEGORIES = ("sleep", "elapsed-assert", "test-cap", "wait-cap", "calendar")
HANG_GUARDS = ("test-cap", "wait-cap")  # the one home of the allowed, uncounted kinds
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
    """(files, unlisted folders). Tracked files when root is a git tree, else every file outside WALK_SKIP.
    The files are None when git fails. A folder the walk cannot list is returned, never skipped silently."""
    dotgit = os.path.join(root, ".git")
    if os.path.isfile(dotgit) or os.path.exists(os.path.join(dotgit, "HEAD")):  # an empty `.git` folder is no repo
        proc = _nowindow.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
        if proc.returncode != 0:
            return None, []  # a walk would add untracked files, so the result is unknown
        return sorted(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p), []
    out, unlisted = [], []

    def note(err):
        unlisted.append({"path": os.path.relpath(err.filename or root, root).replace(os.sep, "/"),
                         "reason": f"cannot be listed: {err.strerror or err}"})

    for dirpath, dirnames, filenames in os.walk(root, onerror=note):
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP]
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(out), unlisted


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


def open_brackets(m, a, p):
    """(bracket, callee or None, position) per bracket still open at p, in a value that starts at a. The
    callee is the called name before a `(`, or "" when a call result is called."""
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
            stack.append((ch, callee, tok.start()))
        elif stack:
            stack.pop()
    return stack


_READ = re.compile(r"(?<![\w$.])[A-Za-z_$][\w$]*(?![\w$])")
_DURATION_ARG = re.compile(r"\.\s*(?:timeIntervalSince\s*\(|duration\s*\(\s*to\s*:)\s*$")
_DURATION_MEMBER = re.compile(r"\s*(?:\?\s*)?\.\s*(?:timeIntervalSince(?:Now)?\b|duration\s*\(\s*to\s*:)")
_POSTFIX = re.compile(r"\s*(?:\?\s*)?\.\s*[A-Za-z_$][\w$]*|!(?!=)")
_MINUS_AFTER = re.compile(r"\s*-(?![-=>])")


def find_open(m, i):
    """Index of the bracket that opens the one that closes at m[i], or -1."""
    depth = 0
    for k in range(i, -1, -1):
        c = m[k]
        if c in ")]}":
            depth += 1
        elif c in "([{":
            depth -= 1
            if depth == 0:
                return k
    return -1


def measured(m, s, e):
    """True when the value read at m[s:e] is an operand of a binary `-`, or the receiver or argument of
    `.timeIntervalSince` or `.duration(to:`. That is a measured duration even inside another call's
    arguments, where a bare clock is only an input."""
    if _DURATION_ARG.search(m, max(0, s - 80), s):
        return True
    j = e
    if m[j - 1] in "([":  # a clock pattern that ends inside its own call
        j = find_close(m, j - 1) + 1
        if j == 0:
            return False
    while True:
        if _DURATION_MEMBER.match(m, j):
            return True
        if j < len(m) and m[j] in "([":
            j = find_close(m, j) + 1
            if j == 0:
                return False
            continue
        member = _POSTFIX.match(m, j)
        if not member:
            break
        j = member.end()
    if _MINUS_AFTER.match(m, j):
        return True
    before = m[max(0, s - 80):s].rstrip()
    if not before.endswith("-"):
        return False
    left = before[:-1].rstrip()
    word = re.search(r"[\w$]+$", left)
    return bool(left) and (left[-1] in ")]" or (word is not None and word.group() not in _KEYWORDS))


_FUNCTION_START = re.compile(r"=>|(?<![\w$])function(?![\w$])")


def counts(m, a, s, e, pass_through, durations):
    """True when a clock or tainted name read at m[s:e], in a value that starts at a, is a reading of that
    value. Inside the arguments of a call that is not a pass-through it is an input. With `durations` (an
    asserted value) it still counts as a measured duration, but never inside a function or block handed
    to that call (a wait condition)."""
    stack = open_brackets(m, a, s)
    foreign = [k for k, (ch, callee, pos) in enumerate(stack) if callee is not None and callee not in pass_through]
    if not foreign:
        return True
    if not durations:
        return False
    inner = foreign[-1]
    if any(ch == "{" for ch, callee, pos in stack[inner + 1:]) or _FUNCTION_START.search(m, stack[inner][2], s):
        return False
    return measured(m, s, e)


def reads_clock(m, a, b, clock_re, tainted, pass_through, durations):
    """True when the value m[a:b] reads a clock or a name inside the block of a tainted declaration of it.
    An object key or a call label (`at:` after `{`, `,` or `(`) is not a read. A clock handed to a call that
    is not a pass-through is an injected input, which decision test-practices P5 endorses. With
    `durations`, a measured duration in such a call's arguments still counts (see `counts`)."""
    if any(counts(m, a, hit.start(), hit.end(), pass_through, durations) for hit in clock_re.finditer(m, a, b)):
        return True
    for hit in _READ.finditer(m, a, b):
        for scope_start, scope_end, decl_pos in tainted.get(hit.group(), ()):
            if scope_start <= hit.start() < scope_end and decl_pos < hit.start():
                label = m[hit.end():b].lstrip().startswith(":") and m[a:hit.start()].rstrip()[-1:] in ("{", ",", "(")
                if not label and counts(m, a, hit.start(), hit.end(), pass_through, durations):
                    return True
    return False


def clock_taint(m, decl_re, clock_re, pass_through, function_returns):
    """{name: [(block start, block end, declaration position)]} for names whose value reads a clock or a
    tainted name, repeated until nothing changes. For a function value, the value is what it returns."""
    decls = declarations(m, decl_re)
    ranges = block_ranges(m, [d[1] for d in decls])
    values = []
    for name, pos, start, end in decls:
        returned = function_returns(m, start, end)
        values.append([(start, end)] if returned is None else returned)
    tainted, done, changed = {}, set(), True
    while changed:
        changed = False
        for idx, (name, pos, start, end) in enumerate(decls):
            if idx not in done and any(reads_clock(m, a, b, clock_re, tainted, pass_through, False)
                                       for a, b in values[idx]):
                tainted.setdefault(name, []).append(ranges[pos] + (pos,))
                done.add(idx)
                changed = True
    return tainted


_RETURN = re.compile(r"(?<![\w$.])return(?![\w$])")


def block_returns(m, open_idx, opens_function):
    """Spans of the values that the `return`s of the block at m[open_idx] give back, leaving out each
    `return` of a function nested inside it."""
    close = find_close(m, open_idx)
    if close < 0:
        return []
    spans = []
    for r in _RETURN.finditer(m, open_idx + 1, close):
        stack = []
        for tok in re.compile(r"[{}]").finditer(m, open_idx + 1, r.start()):
            if tok.group() == "{":
                stack.append(tok.start())
            elif stack:
                stack.pop()
        if not any(opens_function(m, o) for o in stack):
            spans.append((r.end(), scan_expr(m, r.end())))
    return spans


def asserted_range(m, open_idx, close):
    """(start, end) of an assert call's arguments without a trailing message: a last argument that is a
    string or template literal, after at least one other argument, is the message."""
    spans = split_args(m, open_idx + 1, close)
    if len(spans) > 1 and m[spans[-1][0]:spans[-1][1]].lstrip()[:1] in ("'", '"', "`"):
        return open_idx + 1, spans[-2][1]
    return open_idx + 1, close


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
# duration, so the call's result is not tainted. In an assert, a difference there still counts
# (`assert to_ms(time.time() - t0) < 100`). These calls only reshape a number, so they pass it on.
PY_PASS_THROUGH = {"round", "int", "float", "abs", "max", "min", "sum", "divmod", "math.floor", "math.ceil"}


# A date or zone read with no time given. `time.strftime(fmt)`, `time.gmtime()` and `time.asctime()` read the
# clock only when no time argument is passed, so they are matched apart from the always-real forms. `time.tzname` and `time.timezone` are attribute reads.
PY_CALENDAR_NO_ARG = {"time.gmtime", "time.asctime", "pandas.Timestamp.utcnow"}
# These read the machine's zone even when given a fixed time, so a fixed time does not pin them:
# `time.localtime(x)` and `time.ctime(x)` always, `datetime.fromtimestamp(x)` and `x.astimezone()` unless a
# zone is given.
PY_CALENDAR_LOCAL_ZONE = {"time.localtime", "time.ctime"}
PY_CALENDAR_FROMTIMESTAMP = {"datetime.fromtimestamp", "datetime.datetime.fromtimestamp"}
# These read the real date unless a time is given, and take a zone by keyword: with no positional argument and
# nothing but that keyword, the call still reads the real date.
PY_CALENDAR_ZONE_KW = {"arrow.get": "tzinfo", "django.utils.timezone.localtime": "timezone",
                       "django.utils.timezone.localdate": "timezone", "timezone.localtime": "timezone",
                       "timezone.localdate": "timezone"}
PY_CALENDAR_ATTRS = {"time.tzname", "time.timezone"}
# The date libraries' `now` calls read the real date whatever zone they are given, as `datetime.now(tz)` does.
# Matched on the import-resolved name too, so `pd.Timestamp.now` and `from django.utils import timezone` land.
PY_CALENDAR_NOW = {"datetime.now", "datetime.utcnow", "datetime.datetime.now", "datetime.datetime.utcnow",
                   "date.today", "datetime.today", "datetime.date.today", "datetime.datetime.today",
                   "pendulum.now", "pendulum.today", "arrow.now", "arrow.utcnow", "pandas.Timestamp.now",
                   "pandas.Timestamp.today",
                   "django.utils.timezone.now", "timezone.now"}
# A call of these sets a fake clock for the code under it, so a real-date read there is not a read of the
# real date. A difference of two clock reads there is still an elapsed-assert.
PY_FAKE_CLOCKS = {"freeze_time", "freezegun.freeze_time"}


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def zone_given(call, index):
    """True when the call names a zone: a `tz` keyword, or the positional argument at index, that is not None.
    `tz=None` and `None` ask for the machine's zone. A `*args` or `**kwargs` may hold a zone, so it counts."""
    def real(node):
        return not (isinstance(node, ast.Constant) and node.value is None)

    return any(k.arg == "tz" and real(k.value) for k in call.keywords) or (
        len(call.args) > index and real(call.args[index])) or any(
        k.arg is None for k in call.keywords) or any(isinstance(a, ast.Starred) for a in call.args)


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
    """Every node of root's own scope, not entering a nested function, so a name stays in its own scope."""
    todo = [root]
    while todo:
        node = todo.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            todo.append(child)


# The positional arguments a unittest assert compares. The one after them is its message.
PY_COMPARED = {"assertTrue": 1, "assertFalse": 1, "assertIsNone": 1, "assertIsNotNone": 1,
               **{n: 2 for n in ("assertEqual", "assertNotEqual", "assertLess", "assertLessEqual", "assertGreater",
                                 "assertGreaterEqual", "assertIs", "assertIsNot", "assertIn", "assertNotIn",
                                 "assertIsInstance", "assertNotIsInstance", "assertCountEqual", "assertRegex",
                                 "assertNotRegex", "assertListEqual", "assertDictEqual", "assertSetEqual",
                                 "assertTupleEqual", "assertSequenceEqual", "assertMultiLineEqual")}}


def assert_parts(call, name):
    """The nodes of an assert call that hold the asserted value: no message argument, no `msg=`."""
    count = PY_COMPARED.get(name)
    args = call.args if count is None else call.args[:count]
    return [call.func] + args + [k.value for k in call.keywords if k.arg != "msg"]


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
        return names_of_node(call.func)

    def names_of_node(node):
        d = dotted(node)
        if d is None:
            return set()
        first, _, rest = d.partition(".")
        resolved = imports[first] + ("." + rest if rest else "") if first in imports else d
        return {d, resolved}

    def is_clock(node):
        return isinstance(node, ast.Call) and bool(names_of(node) & PY_CLOCKS)

    def holds_clock(node, tainted, durations=False):
        """True when node reads a clock call or a tainted name. The arguments of a call count only when that
        call is a pass-through, or, with `durations` (an asserted value), when they hold a difference with a
        clock in it. A lambda reads what it returns."""
        if isinstance(node, ast.Lambda):
            return holds_clock(node.body, tainted, durations)
        if isinstance(node, ast.Call):
            if is_clock(node):
                return True
            args = node.args + [k.value for k in node.keywords]
            if names_of(node) & PY_PASS_THROUGH:
                return any(holds_clock(p, tainted, durations) for p in [node.func] + args)
            return holds_clock(node.func, tainted, durations) or (
                durations and any(holds_difference(p, tainted) for p in args))
        if isinstance(node, ast.Name):
            return isinstance(node.ctx, ast.Load) and node.id in tainted
        return any(holds_clock(c, tainted, durations) for c in ast.iter_child_nodes(node))

    def holds_difference(node, tainted):
        """True when node, an input to a call, holds `a - b` with a clock or a tainted name in a or b: a
        measured duration, not an injected clock. A lambda's body is not searched."""
        if isinstance(node, ast.Lambda):
            return False
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub) and (
                holds_clock(node.left, tainted, True) or holds_clock(node.right, tainted, True)):
            return True
        return any(holds_difference(c, tainted) for c in ast.iter_child_nodes(node))

    scopes = {}

    def scope_taint(root):
        """The clock-tainted names of root's own scope, repeated until nothing changes. A def in that scope
        taints its name when a value it returns reads a clock."""
        if id(root) in scopes:
            return scopes[id(root)]
        tainted = scopes[id(root)] = set()
        nodes = list(walk_scope(root))
        assigns = []
        for n in nodes:
            if isinstance(n, ast.Assign):
                assigns.append(([x for t in n.targets for x in target_names(t)], n.value))
            elif isinstance(n, ast.AnnAssign) and n.value is not None:
                assigns.append((target_names(n.target), n.value))
            elif isinstance(n, (ast.AugAssign, ast.NamedExpr)):
                assigns.append((target_names(n.target), n.value))
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    inner = scope_taint(child)
                    if any(isinstance(r, ast.Return) and r.value is not None and holds_clock(r.value, inner)
                           for r in walk_scope(child)):
                        tainted.add(child.name)
        changed = True
        while changed:
            changed = False
            for targets, value in assigns:
                if not set(targets) <= tainted and holds_clock(value, tainted):
                    tainted.update(targets)
                    changed = True
        return tainted

    def frozen_node_ids():
        """Ids of every node under a fake clock: the body of a def or class that `@freeze_time(...)` wraps, and
        the body of a `with freeze_time(...)`. The decorator and the `with` items stay outside it."""
        def sets_clock(node):
            return isinstance(node, ast.Call) and bool(names_of(node) & PY_FAKE_CLOCKS)

        ids = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                frozen = any(sets_clock(d) for d in n.decorator_list)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                frozen = any(sets_clock(item.context_expr) for item in n.items)
            else:
                continue
            if frozen:
                ids.update(id(x) for stmt in n.body for x in ast.walk(stmt))
        return ids

    parents = {}
    for n in ast.walk(tree):
        for child in ast.iter_child_nodes(n):
            parents[id(child)] = n

    def terms_of(test):
        """The terms of a loop or if test, with `and` and `or` flattened."""
        if isinstance(test, ast.BoolOp):
            return [t for v in test.values for t in terms_of(v)]
        return [test]

    def own_nodes(stmts):
        """Every node under stmts, not entering a nested function, lambda or class."""
        todo = list(stmts)
        while todo:
            node = todo.pop()
            yield node
            for child in ast.iter_child_nodes(node):
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    todo.append(child)

    def exits(ifnode):
        """True when the if's own branch returns, breaks, raises or fails the test."""
        for n in own_nodes(ifnode.body):
            if isinstance(n, (ast.Return, ast.Break, ast.Raise)):
                return True
            if isinstance(n, ast.Call) and (n.func.attr if isinstance(n.func, ast.Attribute)
                                            else getattr(n.func, "id", "")) == "fail":
                return True
        return False

    def poll_loop_of(call):
        """The loop whose body holds this call directly in its own scope, or None."""
        child, node = call, parents.get(id(call))
        while node is not None and not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            if isinstance(node, (ast.While, ast.For, ast.AsyncFor)) and child in node.body:
                return node
            child, node = node, parents.get(id(node))
        return None

    def is_hang_guard_poll(call):
        """A sleep in a loop that has both a condition and a clock or count cap is a hang guard, not a fixed
        wait (decision test-practices P5). A condition is a while-test term that is neither `True` nor a clock
        comparison, or an if in the body that exits and tests something other than a clock. A cap is a clock
        comparison in the while test or in an exiting if, or `range(<literal>)` in a for."""
        loop = poll_loop_of(call)
        if loop is None:
            return False
        root = parents.get(id(loop))
        while root is not None and not isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef)):
            root = parents.get(id(root))
        tainted = scope_taint(root if root is not None else tree)

        def clock_term(t):
            return isinstance(t, ast.Compare) and holds_clock(t, tainted)

        def always_true(t):
            return isinstance(t, ast.Constant) and bool(t.value)

        ifs = [n for n in own_nodes(loop.body) if isinstance(n, ast.If) and exits(n)]
        has_cond = any(not all(clock_term(t) or always_true(t) for t in terms_of(i.test)) for i in ifs)
        cap = any(clock_term(t) for i in ifs for t in terms_of(i.test))
        if isinstance(loop, ast.While):
            terms = terms_of(loop.test)
            has_cond = has_cond or any(not (clock_term(t) or always_true(t)) for t in terms)
            cap = cap or any(clock_term(t) for t in terms)
        else:
            it = loop.iter
            cap = cap or (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"
                          and bool(it.args) and not it.keywords and all(py_number(a) for a in it.args))
        return has_cond and cap

    found = set()
    calendar_calls = []
    decorator_calls = {id(d) for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                       for d in n.decorator_list if isinstance(d, ast.Call)}
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        names = names_of(call)
        first = call.args[0] if call.args else None
        if names & PY_SLEEPS:
            if not (isinstance(first, ast.Constant) and not isinstance(first.value, bool)
                    and isinstance(first.value, (int, float)) and first.value == 0):
                # sleep(0) is a yield, not a wait. A poll interval of a capped wait loop is a hang guard.
                found.add((call.lineno, "wait-cap" if is_hang_guard_poll(call) else "sleep"))
        zone_kws = {PY_CALENDAR_ZONE_KW[n] for n in names if n in PY_CALENDAR_ZONE_KW}
        if names & PY_CALENDAR_NOW or names & PY_CALENDAR_LOCAL_ZONE or (
                not call.args and not call.keywords and names & PY_CALENDAR_NO_ARG) or (
                names & PY_CALENDAR_FROMTIMESTAMP and not zone_given(call, 1)) or (
                isinstance(call.func, ast.Attribute) and call.func.attr == "astimezone"
                and not zone_given(call, 0)) or (
                zone_kws and not call.args and all(k.arg in zone_kws for k in call.keywords)) or (
                len(call.args) == 1 and not call.keywords and names & {"time.strftime"}):
            calendar_calls.append(call)
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
        tainted = scope_taint(root)
        for n in walk_scope(root):
            if isinstance(n, ast.Assert) and holds_clock(n.test, tainted, True):
                found.add((n.lineno, "elapsed-assert"))
            elif isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if name.startswith("assert") and any(holds_clock(x, tainted, True) for x in assert_parts(n, name)):
                    found.add((n.lineno, "elapsed-assert"))
    frozen = frozen_node_ids()
    found.update((c.lineno, "calendar") for c in calendar_calls if id(c) not in frozen)
    found.update((n.lineno, "calendar") for n in ast.walk(tree)
                 if isinstance(n, (ast.Attribute, ast.Name)) and isinstance(n.ctx, ast.Load)
                 and names_of_node(n) & PY_CALENDAR_ATTRS)
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
    template_parts = []  # brace depth at each open `${`
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
                template_parts.append(depth)
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
            i, in_template_part = template(i + 1)
            last, word = ("{", "") if in_template_part else ("`", "")
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
            if template_parts and depth == template_parts[-1]:
                template_parts.pop()
                i, in_template_part = template(i + 1)
                last, word = ("{", "") if in_template_part else ("`", "")
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


_JS_ASYNC = re.compile(r"\s*(?:async(?![\w$])\s*)?")
_JS_FUNCTION = re.compile(r"function(?![\w$])\s*\*?\s*[\w$]*\s*")
_JS_ARROW_AFTER_PARAMS = re.compile(r"\s*(?::[^;{}]*?)?=>")
_JS_ARROW_ONE_PARAM = re.compile(r"[A-Za-z_$][\w$]*\s*=>")
_JS_CONTROL = {"if", "for", "while", "switch", "catch", "with"}


def skip_generics(m, i, end):
    """Index after a `<...>` type parameter list that starts at m[i], and the space after it; else i."""
    if not m.startswith("<", i):
        return i
    depth, k = 0, i
    while k < end:
        if m.startswith("=>", k):
            k += 2
            continue
        if m[k] == "<":
            depth += 1
        elif m[k] == ">":
            depth -= 1
            if depth == 0:
                k += 1
                while k < end and m[k] in " \t\r\n":
                    k += 1
                return k
        k += 1
    return i


def js_opens_function(m, o):
    """True when the `{` at m[o] opens the body of an arrow, a function or a method, not a block or an object."""
    k = o - 1
    while k >= 0 and m[k] in " \t\r\n":
        k -= 1
    if k >= 1 and m[k - 1:k + 1] == "=>":
        return True
    if k < 0 or m[k] != ")":
        return False
    p = find_open(m, k)
    word = re.search(r"[\w$]+\s*$", m[max(0, p - 40):max(p, 0)])
    return not (word and word.group().strip() in _JS_CONTROL)


def js_function_returns(m, start, end):
    """None when the initializer m[start:end] is not an arrow or a function expression. Else the spans of the
    values it returns: its expression body, or each `return` of its block body at that body's own level.
    The parameter list is bracket-matched, so a TS type, a generic or a default call in it parses."""
    i = _JS_ASYNC.match(m, start, end).end()
    fn = _JS_FUNCTION.match(m, i, end)
    if fn:
        i = skip_generics(m, fn.end(), end)
        close = find_close(m, i) if m.startswith("(", i) else -1
        body = m.find("{", close, end) if 0 <= close < end else -1
        return block_returns(m, body, js_opens_function) if body >= 0 else None
    i = skip_generics(m, i, end)
    if m.startswith("(", i):
        close = find_close(m, i)
        arrow = _JS_ARROW_AFTER_PARAMS.match(m, close + 1, end) if 0 <= close < end else None
    else:
        arrow = _JS_ARROW_ONE_PARAM.match(m, i, end)
    if not arrow:
        return None
    j = arrow.end()
    while j < end and m[j] in " \t\r\n":
        j += 1
    if m.startswith("{", j):
        return block_returns(m, j, js_opens_function)
    if js_function_returns(m, j, end) is not None:
        return []  # it returns a function, and calling that is not a clock reading
    return [(j, end)]


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
        for mm in re.finditer(r"(?<![\w$])waitForTimeout\s*\(", m):
            got = args_of(mm.end() - 1)
            if got and is_num(m[got[1][0][0]:got[1][0][1]], True):
                hits.add(mm.start(), "sleep")
        for mm in re.finditer(r"(?<![\w$])Atomics\s*\.\s*wait\s*\(", m):
            got = args_of(mm.end() - 1)
            if got and is_num(m[got[1][-1][0]:got[1][-1][1]], True):
                hits.add(mm.start(), "sleep")

    tainted = clock_taint(m, JS_DECL, JS_CLOCK, JS_PASS_THROUGH, js_function_returns)
    if not fake_clock:  # under a fake clock the date is the faked one
        for mm in re.finditer(r"(?<![\w$])new\s+Date\s*\(|(?<![\w$.])(?:dayjs|moment)(?:\s*\.\s*utc)?\s*\(", m):
            if re.search(r"(?<![\w$])function\s+$", m[max(0, mm.start() - 12):mm.start()]):
                continue  # `function moment(` declares the name, it reads nothing
            got = args_of(mm.end() - 1)  # `new Date(<clock>)` reads the real date as `new Date()` does
            if got and (not m[mm.end():got[0]].strip()
                        or reads_clock(m, mm.end(), got[0], JS_CLOCK, tainted, JS_PASS_THROUGH, False)):
                hits.add(mm.start(), "calendar")
        for mm in re.finditer(r"(?<![\w$.])Date\s*\(", m):  # without `new`, Date(...) ignores its arguments
            if not re.search(r"(?<![\w$])(?:new|function)\s+$", m[max(0, mm.start() - 12):mm.start()]):
                hits.add(mm.start(), "calendar")
    for mm in re.finditer(r"(?<![\w$.])Temporal\s*\.\s*Now\s*\.\s*[A-Za-z]+\s*\(", m):
        hits.add(mm.start(), "calendar")  # fake timers fake Date, not Temporal

    for mm in JS_ASSERT.finditer(m):
        got = args_of(mm.end() - 1)
        if got:
            a, b = asserted_range(m, mm.end() - 1, got[0])
            if reads_clock(m, a, b, JS_CLOCK, tainted, JS_PASS_THROUGH, True):
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
# A read of the real date or the machine's calendar or zone.
SWIFT_CALENDAR = re.compile(r"(?<![\w$])Date\s*\(\s*\)|(?<![\w$])Date\.now\b"
                            r"|(?<![\w$])Date\s*\((?=\s*timeIntervalSinceNow\b)"
                            r"|(?<![\w$])(?:Calendar|TimeZone)\s*\.\s*current\b")
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

    def skip_interpolation(k):
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
                p = skip_interpolation(p + len(esc) + 1) if src.startswith("(", p + len(esc)) else p + len(esc) + 1
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


_SWIFT_IN = re.compile(r"[()\[\]{}]|(?<![\w$])in(?![\w$])")
_SWIFT_NOT_HEADER = re.compile(r"(?<![\w$])(?:for|let|var|if|while|guard|return|case|switch)(?![\w$])|;")
_SWIFT_CONTROL = re.compile(r"\s*(?:\}\s*)?(?:if|guard|for|while|switch|do|else|repeat|catch|defer)(?![\w$])"
                            r"|.*(?<![\w$])else\s*$", re.S)


def swift_opens_function(m, o):
    """True when the `{` at m[o] opens a closure or a function body, not the block of a control statement."""
    k = o - 1
    while k >= 0 and m[k] not in "\n;{}":
        k -= 1
    return not _SWIFT_CONTROL.match(m[k + 1 if k < 0 or m[k] != "}" else k:o])


def swift_function_returns(m, start, end):
    """None when the initializer m[start:end] is not a closure literal that nothing calls on the spot. Else
    the spans of the values it returns: each `return` at its own level, or else its one expression. The
    `params in` header is left out, so a clock type in it reads nothing."""
    open_idx = start
    while open_idx < end and m[open_idx] in " \t\r\n":
        open_idx += 1
    if not (open_idx < end and m[open_idx] == "{"):
        return None
    close = find_close(m, open_idx)
    if close < 0 or m[close + 1:end].strip():
        return None
    body, depth = open_idx + 1, 0
    for tok in _SWIFT_IN.finditer(m, open_idx + 1, close):
        word = tok.group()
        if word in "([{":
            depth += 1
        elif word in ")]}":
            depth -= 1
        elif depth == 0:
            if not _SWIFT_NOT_HEADER.search(m, open_idx + 1, tok.start()):
                body = tok.end()
            break
    spans = block_returns(m, open_idx, swift_opens_function)
    spans = [(a, b) for a, b in spans if a >= body]
    if spans:
        return spans
    s = body
    while s < close and m[s] in " \t\r\n":
        s += 1
    e = scan_expr(m, s)
    if s >= close or m[e:close].strip() or re.match(r"(?:let|var)(?![\w$])", m[s:e]):
        return []
    return [(s, e)]


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

    tainted = clock_taint(m, SWIFT_DECL, SWIFT_CLOCK, SWIFT_PASS_THROUGH, swift_function_returns)
    elapsed_spans = []
    for mm in SWIFT_ASSERT.finditer(m):
        close = find_close(m, mm.end() - 1)
        if close >= 0:
            a, b = asserted_range(m, mm.end() - 1, close)
            if reads_clock(m, a, b, SWIFT_CLOCK, tainted, SWIFT_PASS_THROUGH, True):
                hits.add(mm.start(), "elapsed-assert")
                elapsed_spans.append((a, b))

    # A `Date()` that an assert subtracts or hands to `timeIntervalSince` is that assert's elapsed row alone.
    for mm in SWIFT_CALENDAR.finditer(m):
        if mm.group().startswith("Date") and any(
                a <= mm.start() < b and measured(m, mm.start(), mm.end()) for a, b in elapsed_spans):
            continue
        hits.add(mm.start(), "calendar")

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
    files, unread = list_files(root)
    if files is None:
        print(f"unknown: git ls-files failed in {root}")
        return 2
    findings = []
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
        pinned = [f for f in findings if f["category"] not in HANG_GUARDS]
        nfiles = len({f["path"] for f in pinned})
        print("%d time-pinned in %d files (sleep %d, elapsed-assert %d, calendar %d); "
              "hang guards %d (allowed; check each cap sits well above the run); %d unread"
              % (len(pinned), nfiles, counts["sleep"], counts["elapsed-assert"],
                 counts["calendar"], sum(counts[c] for c in HANG_GUARDS), len(unread)))
    if any(f["category"] not in HANG_GUARDS for f in findings):
        return 1
    return 2 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
