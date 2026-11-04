#!/usr/bin/env python3
"""The stale-prose merge check. Standard library only.

    python3 lint/stale_cites.py --range <base>...<head>

Refuses a range that leaves a tracked Markdown line naming a name the range removed.
  STALE001  the line names a path the range deleted or renamed, and the path is absent at head.
            A rename names its new home.
  STALE002  the line cites `<file.py> <name>` as "`file.py` `name`" or "(file.py name)", and `name` was bound
            in that file at base (read with `ast`) and is not bound at head. A name counts when a module-level
            def, class, assignment or import binds it, also under a module-level if or try, or when it is a
            def directly in a module-level class. A name that moved but is still bound in the file is not
            removed.
  STALE004  the line holds a value cite, `file: NAME = literal` in one backtick span, and the range changed that
            value while the cite still equals the base value; or the range added the line and the cite is not the
            value at head. `file` is a .py file (a module-level literal, read with py-facts) or a .json file (a
            dotted path, read with the `_walk` of lint/rule_audit.py). A line already wrong at base and left alone
            never fires.
  Unknown   the line cites `<file.mjs> <name>` (also .js, .cjs, .ts, .sh) in the same two forms, or a value cite of
            such a file, and the range touched that file. JavaScript and shell names and values are not read, so
            the line prints `stale-cites: unknown, <path>:<line> ...` and never fails the run. Only a run that
            already reads Markdown prints it; touching such a file never starts that read.
A line already stale at base, for a name the range did not remove, never fires. Left out: docs/records.md,
each file `.ste-lint-exclude` (and the EXCLUDE env of the ste-lint action) names, and a line marked
`<!-- ste-disable-line STALE001 -->` (or STALE002, STALE004). Fenced blocks count as prose.
Each Markdown file is read as committed at head, never from the working tree. Which files: every tracked one when
the range removed a path or name, or changed a literal (a .py module-level literal, or any .json file); else only
the Markdown the range touched, which is where a new wrong value cite can sit.
Output: `path:line: CODE message`, then `stale-cites: PASS` or `stale-cites: FAIL`. Exit 0 pass, 1 findings,
2 a read that could not run, except a base that does not resolve (a shallow clone): that prints
`stale-cites: unknown, ...` naming fetch-depth 0 and exits 0, so a repo that pins the ste-lint action and
checks out shallow is not red at its pin move. A touched .py that does not parse at base or head is unknown
the same way: `stale-cites: unknown, <file> ...`, and it alone never makes the exit non-zero.

Cost, per ste-lint changed-scope run (CostTests in lint/test_stale_cites.py proves it): one python3 start.
Git starts 3 (rev-parse, merge-base, diff) when the range removes or renames no path and touches no .py, .json
or .md. A touched .py, .json or .md adds one `git cat-file --batch`. A removed path or name, or a changed
literal, adds `ls-tree`, so 5 at most. Each Markdown file is read once. A touched .py also loads the py-facts
script once, in-process (no start, no .pyc); a cited .json value loads lint/rule_audit.py the same way. It
writes no file and leaves no process running.
"""
import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # the cost contract: a run writes no file, so no .pyc for the import below
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

RECORDS_PAGE = "docs/records.md"
RUN = r"[\w./@+~-]+"  # a run of path characters; a cite is one whole run, so a `-` or `.` before a path is no boundary
NOT_BEFORE = r"(?<![\w/.@+~-])"
RUN_RE = re.compile(RUN)
FOREIGN_EXT = r"(?:mjs|cjs|js|ts|sh)"  # code files whose names this check does not read: a cite of one is unknown


def pair_res(ext):
    """"`file.<ext>` `name`" and "(file.<ext> name)"."""
    return (
        re.compile(NOT_BEFORE + r"`?(%s\.%s)`?\s+`([A-Za-z_]\w*)`" % (RUN, ext)),
        re.compile(r"\(`?(%s\.%s)`?\s+([A-Za-z_]\w*)(?:\(\))?\)" % (RUN, ext)),
    )


PAIR_RES = pair_res("py")
FOREIGN_PAIR_RES = pair_res(FOREIGN_EXT)
FOREIGN_FILE = re.compile(r"\.%s\Z" % FOREIGN_EXT)
DISABLE_RE = re.compile(r"<!--\s*ste-disable-line([^>]*?)-->")
SIMPLE_PATH = re.compile(r"^%s$" % RUN)


class Unknown(Exception):
    """A read that could not run."""


class BaseUnknown(Unknown):
    """The base of the range does not resolve, as in a shallow clone. Not a finding."""


def git(*args, on_fail=Unknown):
    done = _nowindow.run(["git", *args], capture_output=True)
    if done.returncode != 0:
        raise on_fail("git %s failed: %s" % (" ".join(args[:2]), done.stderr.decode("utf-8", "replace").strip()))
    return done.stdout


class BlobReader:
    """One `git cat-file --batch` process for every blob read."""

    def __init__(self):
        self.proc = None

    def get(self, spec):
        """Bytes of the blob, or None when the object does not exist."""
        if self.proc is None:
            self.proc = _nowindow.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.proc.stdin.write(spec.encode("utf-8") + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if not header:
            raise Unknown("git cat-file ended early")
        if header[-1] == b"missing":
            return None
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)
        return data if header[1] == b"blob" else b""

    def close(self):
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait()


def glob_regex(pattern):
    """A .ste-lint-exclude pathspec as a regex, read as git reads `:(exclude,glob)<pattern>`: `**/` spans
    zero or more folders, `*` stays in one. A pattern with no wildcard also matches each file under it as a
    folder, so `vendor` and `vendor/` leave out `vendor/a.md`. A wildcard pattern matches the whole path only."""
    literal = not any(c in pattern for c in "*?[")
    if literal:
        pattern = pattern.rstrip("/")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + (r"(?:/.*)?\Z" if literal else r"\Z"))


def exclude_patterns(root):
    lines = []
    try:
        with open(os.path.join(root, ".ste-lint-exclude"), encoding="utf-8") as f:
            lines += f.read().splitlines()
    except OSError:
        pass
    lines += os.environ.get("EXCLUDE", "").replace(",", "\n").splitlines()
    cleaned = (line.strip() for line in lines)
    return [glob_regex(p) for p in cleaned if p and not p.startswith("#")]


def parse_range(text):
    """(diff arguments, base spec, head spec). A three-dot range reads base blobs at the merge base."""
    if "..." in text:
        left, right = text.split("...", 1)
        base = git("merge-base", left, right, on_fail=BaseUnknown).decode().strip()
        return [text], base, right
    if ".." in text:
        left, right = text.split("..", 1)
        return [text], left, right
    raise Unknown("--range wants base...head, got %r" % text)


def changed_paths(diff_args):
    """(removed, renamed, modified, added): removed paths, {old: new}, paths changed in place, and new paths."""
    tokens = git("diff", "-M", "--name-status", "-z", *diff_args, on_fail=BaseUnknown).decode("utf-8", "replace").split("\0")
    removed, renamed, modified, added = [], {}, [], []
    i = 0
    while i < len(tokens) and tokens[i]:
        status = tokens[i][0]
        if status == "R" or status == "C":
            if status == "R":
                renamed[tokens[i + 1]] = tokens[i + 2]
            i += 3
            continue
        if status == "D":
            removed.append(tokens[i + 1])
        elif status == "M":
            modified.append(tokens[i + 1])
        elif status == "A":
            added.append(tokens[i + 1])
        i += 2
    return removed, renamed, modified, added


PY_FACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "plain-english-map",
                        "scripts", "lib", "py-facts.py")
_py_facts = []


def py_facts():
    """The py-facts module, the one home of a Python file's module-level names. Its file name has a hyphen, so
    importlib loads it by path; `sys.dont_write_bytecode` keeps the load from writing a .pyc."""
    if not _py_facts:
        spec = importlib.util.spec_from_file_location("py_facts", PY_FACTS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _py_facts.append(module)
    return _py_facts[0]


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def module_statements(body):
    """Each statement that runs at module level: the body itself and, inside any statement that is no def or
    class, its if, try, with, loop and match bodies. A def or class is kept whole; its inside is not module level."""
    for node in body:
        yield node
        if isinstance(node, FUNCTIONS + (ast.ClassDef,)):
            continue
        for field in ("body", "orelse", "finalbody"):
            yield from module_statements(getattr(node, field, None) or [])
        for part in (getattr(node, "handlers", None) or []) + (getattr(node, "cases", None) or []):
            yield from module_statements(part.body)


def parse_python(source):
    """The `ast` of a Python source, or None when it does not parse."""
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def names_in(source):
    """Names a prose line can cite: each name py-facts `defined_names` finds in the module-level statements
    (def, class, assignment, import; also under a module-level if or try), plus each def directly in a
    module-level class. A def nested in a function is no public name. Read with `ast`; None when it does not parse."""
    tree = parse_python(source)
    if tree is None:
        return None
    flat = list(module_statements(tree.body))
    names = py_facts().defined_names(ast.Module(body=flat, type_ignores=[]))  # defined_names reads `.body` only
    for node in flat:
        if isinstance(node, ast.ClassDef):
            names.update(m.name for m in module_statements(node.body) if isinstance(m, FUNCTIONS))
    return names


# The value cite grammar, `[FILE: ]SYMBOL = LITERAL` in one backtick span. This is a Python copy of
# `VALUE_CITE_RE`, `parseLiteral` and `sameValue` in skills/plain-english-map/scripts/map-check.mjs (the MAP9
# check). The copy has a reason: the ste-lint action runs Python only, with no Node, so it cannot call MAP9's
# reader. skills/plain-english-map/tests/value-cite-parity.json holds the two copies together: both suites read
# its rows, so a change to one grammar that the other lacks goes red. Two differences by design: a cite with no
# FILE reads its file from the map line above in MAP9, and here it is no cite; MAP9 skips fenced blocks, and
# here a fenced block counts as prose, as for every other code.
VALUE_CITE_RE = re.compile(r"(?:(\S+?):\s+)?(\S+)\s+=\s+(.+)")
SPAN_RE = re.compile(r"`([^`]+)`")


def value_cites(line):
    """(file, symbol, literal text) for each backtick span of the line that holds a value cite with a file."""
    found = []
    for span in SPAN_RE.finditer(line):
        match = VALUE_CITE_RE.fullmatch(span.group(1))
        if match and match.group(1):
            found.append((match.group(1), match.group(2), match.group(3)))
    return found


def _no_constant(name):
    raise ValueError(name)  # JSON.parse refuses NaN and Infinity, so this does too


def _loads(text):
    return json.loads(text, parse_constant=_no_constant)


def parse_literal(text):
    """(value, is_set) for the literal a cite says: JSON, or a `{...}` set of JSON items. None when it is neither."""
    t = text.strip()
    try:
        return _loads(t), False
    except ValueError:
        pass
    if t.startswith("{") and t.endswith("}"):
        try:
            return _loads("[" + t[1:-1] + "]"), True
        except ValueError:
            pass
    return None


def strict_equal(a, b):
    """Deep equality as JavaScript's isDeepStrictEqual reads JSON: a boolean is no number, 1 and 1.0 are one number."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def _by_text(items):
    return sorted(items, key=lambda v: json.dumps(v, separators=(",", ":"), ensure_ascii=False))


def same_value(lit, actual):
    """True when the parsed cite `lit` (from `parse_literal`) says `actual`. A set cite ignores order against a list."""
    value, is_set = lit
    if is_set and isinstance(actual, list):
        return strict_equal(_by_text(value), _by_text(actual))
    return strict_equal(value, actual)


def file_value(blob, path, symbol):
    """`(value,)` the symbol holds in the file's bytes, or None when it cannot be read. A .py file gives the module-level
    literal through py-facts `answer`, the same reader MAP9 uses. A .json file gives the dotted path, read with
    the `_walk` of lint/rule_audit.py, and a `[*]` path gives the list of every value."""
    if blob is None:
        return None
    if path.endswith(".py"):
        tree = parse_python(blob)
        if tree is None:
            return None
        found = py_facts().answer({"file": path, "symbol": symbol}, tree, [])
        return (found["value"],) if found["ok"] else None
    try:
        data = _loads(blob.decode("utf-8"))
    except ValueError:  # includes a UnicodeDecodeError
        return None
    import rule_audit  # here, so a run that cites no JSON value never loads it
    values = list(rule_audit._walk(data, symbol.split(".")))
    if not values:
        return None
    return (values if "[*]" in symbol else values[0],)


def disabled(line):
    codes = set()
    for match in DISABLE_RE.finditer(line):
        codes.update(re.split(r"[\s,:]+", match.group(1).strip()))
    return codes


def path_cites(line, gone, exotic):
    """Each removed path the line names, at a path boundary."""
    hits = []
    for run in RUN_RE.finditer(line):
        text = run.group(0)
        candidate = text.rstrip(".-")
        if candidate in gone and candidate not in hits:
            hits.append(candidate)
    for path in exotic:
        if re.search(NOT_BEFORE + r"%s(?![\w/]|[.-]\w)" % re.escape(path), line) and path not in hits:
            hits.append(path)
    return hits


class Range:
    """What the readers share: the range's blobs, its changed paths and the texts a read could not judge."""

    def __init__(self, base, head, removed, renamed, modified, added, batch):
        self.base, self.head, self.removed, self.renamed, self.batch = base, head, removed, renamed, batch
        self.unknowns = []
        self.py_files = {p: p for p in modified if p.endswith(".py")}
        self.py_files.update({old: new for old, new in renamed.items() if old.endswith(".py") and new.endswith(".py")})
        self.json_files = {p for p in modified if p.endswith(".json")}
        self.foreign_files = {p for p in list(modified) + list(renamed.values()) if FOREIGN_FILE.search(p)}
        # The Markdown the range touched, as {path at head: path at base, or None for a new file}.
        self.touched_md = {p: p for p in modified if p.endswith(".md")}
        self.touched_md.update({new: old for old, new in renamed.items() if new.endswith(".md")})
        self.touched_md.update({p: None for p in added if p.endswith(".md")})
        self.blobs = {}

    def blob(self, spec):
        """One blob by `rev:path`, read once."""
        if spec not in self.blobs:
            self.blobs[spec] = self.batch.get(spec)
        return self.blobs[spec]


class Reader:
    """What `scan()` asks of a reader beyond `code`, `prepare` and `line`. The defaults suit a reader that judges
    every tracked Markdown file."""

    def all_markdown(self, state):
        """True when the reader needs every tracked Markdown file, not only the ones the range touched."""
        return True

    def begin(self, state, md, rng):
        """Called before the lines of each Markdown file `md`."""


class PathReader(Reader):
    """STALE001: a line that names a path the range deleted or renamed."""
    code = "STALE001"

    def prepare(self, rng):
        """None when the range removes no path, else the state `line` reads."""
        gone = {}  # path -> new home or None
        for path in rng.removed + list(rng.renamed):
            if rng.batch.get("%s:%s" % (rng.head, path)) is None:
                gone[path] = rng.renamed.get(path)
        if not gone:
            return None
        simple = {p for p in gone if SIMPLE_PATH.match(p)}
        return gone, simple, [p for p in gone if p not in simple]

    def line(self, state, text, claimed):
        gone, simple, exotic = state
        messages = []
        for path in path_cites(text, simple, exotic):
            claimed.add(path)
            home = gone[path]
            messages.append("%s was renamed to %s in this range; name the new home" % (path, home) if home
                            else "%s was deleted in this range" % path)
        return messages


class NameReader(Reader):
    """STALE002: a line that cites `file.py name` for a name the range unbound in that file."""
    code = "STALE002"

    def prepare(self, rng):
        removed_names = {}  # file at base -> names the range removed
        for path in sorted(rng.py_files):
            old_src = rng.batch.get("%s:%s" % (rng.base, path))
            new_src = rng.batch.get("%s:%s" % (rng.head, rng.py_files[path]))
            before = names_in(old_src) if old_src is not None else None
            after = names_in(new_src) if new_src is not None else None
            bad = [side for side, names in (("base", before), ("head", after)) if names is None]
            if bad:
                rng.unknowns.append("%s does not parse at %s; the names it removed were not checked"
                                    % (path, " and ".join(bad)))
            elif before - after:
                removed_names[path] = before - after
        return removed_names or None

    def line(self, state, text, claimed):
        if ".py" not in text:
            return []
        messages = []
        for pair in PAIR_RES:
            for match in pair.finditer(text):
                path, name = match.group(1), match.group(2)
                if path not in claimed and name in state.get(path, ()):
                    messages.append("%s no longer defines %s at head; find its new home" % (path, name))
        return messages


class ForeignReader(Reader):
    """STALE002 unknown: a line that cites `file.mjs name` of a JavaScript or shell file the range touched. Those
    names are not read, so the line is reported as unknown, never as a pass. Reports through `unknown`."""
    code = "STALE002"
    unknown = True

    def prepare(self, rng):
        return rng.foreign_files or None

    def line(self, state, text, claimed):
        messages = []
        for pair in FOREIGN_PAIR_RES:
            for match in pair.finditer(text):
                path, name = match.group(1), match.group(2)
                text_ = "%s %s: JavaScript and shell names are not checked" % (path, name)
                if path in state and path not in claimed and text_ not in messages:
                    messages.append(text_)
        for path, symbol, _ in value_cites(text):
            text_ = "%s %s: JavaScript and shell values are not checked" % (path, symbol)
            if path in state and text_ not in messages:
                messages.append(text_)
        return messages


class ValueReader(Reader):
    """STALE004: a value cite `file: NAME = literal` that quotes what the range changed, or that the range added
    wrong. A cite of a value the range did not change, on a line the range did not add, is left alone."""
    code = "STALE004"

    class State:
        def __init__(self, rng, changed):
            self.rng, self.changed = rng, changed
            self.fresh = None  # the base lines of the Markdown file being read; None when the range did not touch it
            self.values = {}

    def prepare(self, rng):
        """None when the range changed no literal and touched no Markdown. `changed` is true when a module-level
        literal of a touched .py differs between base and head, or a .json file changed: every Markdown file is
        then read, since any line may cite it."""
        changed = bool(rng.json_files)
        for path, new in sorted(rng.py_files.items()):
            if path != new or changed:
                continue
            before, after = (self._literals(rng.blob("%s:%s" % (rev, path))) for rev in (rng.base, rng.head))
            # A source that does not parse is reported by NameReader, so it is skipped here.
            changed = before is not None and after is not None and any(
                name in after and after[name] != node for name, node in before.items())
        return self.State(rng, changed) if changed or rng.touched_md else None

    @staticmethod
    def _literals(source):
        """{name: dump of the value node} for each module-level assignment of the source, or None when it does not parse."""
        tree = parse_python(source)
        if tree is None:
            return None
        return {name: ast.dump(node) for name, node in py_facts().assigned(tree).items() if node is not None}

    def all_markdown(self, state):
        return state.changed

    def begin(self, state, md, rng):
        if md not in rng.touched_md:
            state.fresh = None
            return
        old = rng.touched_md[md]
        blob = rng.blob("%s:%s" % (rng.base, old)) if old else None
        state.fresh = set() if blob is None else {l.strip() for l in blob.decode("utf-8", "replace").split("\n")}

    def value(self, state, side, path, symbol):
        """(value,) the cite's symbol holds in the file at base or head, or None when it cannot be read."""
        key = (side, path, symbol)
        if key not in state.values:
            rev = state.rng.base if side == "base" else state.rng.head
            state.values[key] = file_value(state.rng.blob("%s:%s" % (rev, path)), path, symbol)
        return state.values[key]

    def line(self, state, text, claimed):
        messages = []
        for path, symbol, literal in value_cites(text):
            if not path.endswith((".py", ".json")):
                continue
            lit = parse_literal(literal)
            head = self.value(state, "head", path, symbol) if lit else None
            if head is None:
                continue  # no JSON literal, or the file or symbol is gone at head: STALE001 and STALE002 judge that
            touched = path in state.rng.py_files or path in state.rng.json_files
            base = self.value(state, "base", path, symbol) if touched else head
            if base is not None and not strict_equal(base[0], head[0]) and same_value(lit, base[0]):
                messages.append("%s says %s = %s, the value at base; this range changed it to %s"
                                % (path, symbol, literal, json.dumps(head[0])))
            elif state.fresh is not None and text.strip() not in state.fresh and not same_value(lit, head[0]):
                messages.append("%s says %s = %s, and the file has %s" % (path, symbol, literal, json.dumps(head[0])))
        return messages


# One entry per code. A reader has `code`, `prepare(rng)` (its state, or None when the range gives it nothing to
# check) and `line(state, text, claimed)` (messages for one Markdown line; `claimed` holds the paths an earlier
# reader already cited there). A reader with `unknown = True` reports its messages as unknown, not as findings.
# `Reader` holds the optional hooks: `all_markdown(state)` and `begin(state, md, rng)`. A new check adds one entry.
READERS = (PathReader(), NameReader(), ForeignReader(), ValueReader())


def scan(range_text):
    """(found, unknowns): {(path, line, code): [messages]}, and one text per touched .py that does not parse."""
    diff_args, base, head = parse_range(range_text)
    removed, renamed, modified, added = changed_paths(diff_args)
    found = {}
    batch = BlobReader()
    rng = Range(base, head, removed, renamed, modified, added, batch)
    if not removed and not renamed and not rng.py_files and not rng.json_files and not rng.touched_md:
        return found, rng.unknowns  # the cost contract: nothing removed or changed, so no blob, tree or Markdown read
    try:
        active = [(r, state) for r in READERS for state in [r.prepare(rng)] if state is not None]
        judges = [(r, state) for r, state in active if not getattr(r, "unknown", False)]
        if not judges:
            return found, rng.unknowns  # an unknown line never starts the Markdown read

        excludes = exclude_patterns(".")
        if any(r.all_markdown(state) for r, state in judges):
            tree = git("ls-tree", "-r", "-z", head).decode("utf-8", "replace").split("\0")
            tracked = [e.split("\t", 1)[1] for e in tree if "\t" in e and e.split(" ", 1)[0] in ("100644", "100755")]
            tracked = [t for t in tracked if t.endswith(".md")]
        else:
            tracked = sorted(rng.touched_md)  # a reader that needs only its own new lines reads the touched files

        for md in tracked:
            if not md or md == RECORDS_PAGE or any(rx.match(md) for rx in excludes):
                continue
            blob = batch.get("%s:%s" % (head, md))
            if blob is None:
                raise Unknown("%s is in the tree at %s but cannot be read" % (md, head))
            text = blob.decode("utf-8", "replace").replace("\r\n", "\n")  # a bad byte is U+FFFD, never a skip
            for reader, state in active:
                reader.begin(state, md, rng)
            for number, line in enumerate(text.split("\n"), 1):
                off = disabled(line) if "ste-disable-line" in line else set()
                claimed = set()
                for reader, state in active:
                    if reader.code not in off:
                        for message in reader.line(state, line, claimed):
                            if getattr(reader, "unknown", False):
                                rng.unknowns.append("%s:%d: %s" % (md, number, message))
                            else:
                                found.setdefault((md, number, reader.code), []).append(message)
    finally:
        batch.close()
    return found, rng.unknowns


def main(argv):
    parser = argparse.ArgumentParser(description="Refuse Markdown lines that name what the range removed.")
    parser.add_argument("--range", required=True, help="base...head, as the ste-lint step diffs")
    args = parser.parse_args(argv)
    try:
        root = git("rev-parse", "--show-toplevel").decode().strip()
        os.chdir(root)
        found, unknowns = scan(args.range)
    except BaseUnknown as exc:
        print("stale-cites: unknown, the base of %s does not resolve (%s). Check out with fetch-depth 0 "
              "(actions/checkout) so the range has history. Nothing was checked." % (args.range, exc))
        return 0
    except (Unknown, OSError) as exc:
        print("stale-cites: UNKNOWN, %s" % exc)
        return 2
    for (path, number, code), texts in sorted(found.items()):
        print("%s:%d: %s %s" % (path, number, code, "; ".join(texts)))
    for text in unknowns:
        print("stale-cites: unknown, %s" % text)
    print("stale-cites: %s" % ("FAIL, %d finding(s)" % len(found) if found else "PASS"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
