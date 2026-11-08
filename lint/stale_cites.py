#!/usr/bin/env python3
"""The stale-prose merge check. Standard library only.

    python3 lint/stale_cites.py --range <base>...<head>
    python3 lint/stale_cites.py --tree [REV]

Refuses a range that leaves a tracked Markdown line naming a name the range removed.
  STALE001  the line names a path the range deleted or renamed, and the path is absent at head.
            A rename names its new home.
  STALE002  the line cites `<file.py> <name>` as "`file.py` `name`" or "(file.py name)", and `name` was bound
            in that file at base (read with `ast`) and is not bound at head. `names_in` walks each module-level
            statement, also inside a module-level if, try, with, for, while or match, never inside a def or
            class. A name counts when a def, class, import or assignment binds it there, also a tuple, for,
            with-as or walrus target, or when it is a def directly in a module-level class. A name that moved
            but is still bound in the file is not removed. A test node id, `path.py::name` or
            `path.py::Class::name`, is read the same way, in a code span or not: each segment is a name.
  Unknown   the line cites `<file.mjs> <name>` (also .js, .cjs, .ts, .sh) in the same two forms, and the range
            touched that file. JavaScript and shell names are not read, so the line prints
            `stale-cites: unknown, <path>:<line> ...` and keeps the exit 0. It prints only when the range also
            removes a path or a Python name, since only then is Markdown read. A range that touches only such
            files prints nothing and passes. A value cite of such a file (STALE008) prints the same way, on an untouched
            line only when the whole tree is read and the range touched that file, and on an added line always. Its
            code is STALE008, so the mark for that code leaves it out. A JSON value cite is not read and prints nothing.
  STALE005  (range mode only, report only) a SENTENCE of governed prose, in a paragraph the range adds a line to,
            states a capability by route with no backing. A paragraph is a run of prose rows; a blank row, a heading,
            a quote row, a fence and a list item end one. A sentence ends at . ! or ? before a space, so a claim
            wrapped over lines fires on its first line and its backing may sit on a later line of the same sentence.
            It holds a capability verb (cannot, can't, won't, refuses, denies, blocks, is refused or blocked,
            is not available, works, does not work, a 403) outside a code span, a comment, a double-quoted text and a
            bare file path, and a route word
            (cloud, locally, local session, on the owner's computer, auto mode, classifier, gh, MCP, proxy,
            harness; `local` alone is none) outside a comment, in a code span too when the span names no path.
            It has none of these in parentheses: a premise kind from PREMISE_KINDS that is no weak kind
            (notes, assumed) with a source path (`(read hooks/x.py:12)`), `(test path::name)`, or `(route <id>)`
            whose id is a row of the rows file. A `(read ...)` or `(test ...)` whose file is absent at head is a
            dead backing; a route id that is no row is a dead route. The rows file is hooks/route_rows.json at
            head, or the file the env GUARD_ROUTE_ROWS names (hooks/route_match.py `rows_path()`, the one home of
            that path). An absent or unreadable rows file is one unknown line, and no route is called dead. A range
            that changes the rows file also reports each prose line at head that cites a row id it removes. It prints
            as `stale-cites: report, path:line: STALE005 ...` and never changes the exit code, so it ships dark
            (decision source-prose-lint-ships-dark). A line marked `<!-- ste-disable-line STALE005 -->` is left out.
  STALE008  (value cite, decision stale-cites-at-merge) the line holds `file.py: NAME = literal` in one backtick span,
            the grammar of MAP9 (`VALUE_CITE_RE` and `parse_literal`, a Python copy; the parity fixture holds the
            copies together), and a span with no file is no cite. It fires in three cases only. The range changed the
            module-level literal and the cite still equals the base value. The range removed the assignment and the
            cite equals the base value. Or the range added the line and the cite is not the value at head, even when
            no literal changed. An added line is counted, not looked up: a second copy of a line that was already
            wrong at base is an added line, and a line the range only moved is not. A value is the module-level
            literal py-facts `answer` reads (a value `ast.literal_eval` accepts and JSON can hold), compared by
            value, so a set cite ignores order. A head value that is no literal, such as a call, gives no finding.
            A name no module-level assignment ever bound is no removal: only an added line says so, without "removed".
            A .py cite the check cannot read is never skipped. On an added line, a cite whose value is no JSON literal
            (MAP9 reads none) or whose path no tracked file has is a finding. A cite of a name that holds no literal at
            head, or of a file that does not parse, is unknown. An untouched line prints each of these as unknown too,
            only when the whole tree is read. A cite of a path the range removed is STALE001's.
A line already stale at base, for a name the range did not remove, never fires. Left out: docs/records.md,
each file `.ste-lint-exclude` (and the EXCLUDE env of the ste-lint action) names, and a line marked
`<!-- ste-disable-line STALE001 -->` (or STALE002, STALE003, STALE004, STALE008). Fenced blocks count as prose.
Each Markdown file is read as committed at head, never from the working tree.
--tree [REV] reads every tracked Markdown file at REV (default HEAD) instead of a range, so it fires on lines no
change touched. It is opt-in (the ste-lint input `tree-cites`). It needs no base, so a shallow clone is fine.
  STALE003  the line names `<folder>/.../<file.ext>` that is no tracked file (or folder) at REV, as written or
            from the folder of the Markdown file. One tracked file with the same name elsewhere is named as a
            hint. A cite with a placeholder character, no extension, no folder part, or a first segment that is
            no tracked top folder is no path cite, so it never fires.
  STALE004  the line anchors `path:N` or `path:N-M` on a tracked file, and N is below 1, M is below N, or the
            last number is past the file's last line. A dead path gives STALE003 only.
--tree and --range are exclusive.

Output: `path:line: CODE message`, then `stale-cites: PASS` or `stale-cites: FAIL`. Exit 0 pass, 1 findings,
2 a read that could not run (a base that names nothing in a full clone, an unreadable .ste-lint-exclude), except
a gap in the history (a shallow clone, a base with no merge base with the head, or the first parent of a root commit, spelled `HEAD~1`, `HEAD^1`, `@~1` or `<head sha>~01`): that prints
`stale-cites: unknown, ...` naming fetch-depth 0 and exits 0, so a repo that pins the ste-lint action and
checks out shallow is not red at its pin move. A touched .py that does not parse at base or head is unknown
the same way: `stale-cites: unknown, <file> ...`, and it alone never makes the exit non-zero.

The report prints after the findings and never changes the exit code (decision claude-md-change-is-flagged). Each
line starts `stale-cites: report, `. It has two halves, and STALE005 lines first.
  Anchors   for each `<!-- rule:id -->` anchor whose sentence changed in a RULE_FILES file (a real anchor; one in a
            code span is a mention): the row in lint/rule_mechanisms.json (kind, ref, test), then the files this range
            changed under RULE_DIRS, or "none". It gives no verdict; the reviewer judges. A repo with no
            lint/rule_mechanisms.json prints no anchor line and no error. The same holds when a range changes only
            RULE_FILES and the mechanisms blob is missing (a partial clone): the tree is not listed, so the file reads
            as absent. The run prints no anchor line and no unknown, and exits 0. A changed non-Markdown file lists
            the tree, and then a listed file with no blob prints unknown.
  Home      for each changed non-Markdown file (added, changed, removed or renamed): each decision whose Home line
            names it, each mechanism row whose ref or test is it, and each decision prose line whose `(test ...)`
            or `(read ...)` backing points at it (`backed_lines`, the selector a prose judge calls).

Cost, per ste-lint changed-scope run (CostTests in lint/test_stale_cites.py proves it): one python3 start.
Git starts 3 (rev-parse, merge-base, diff) when the range removes or renames no path and changes only
Markdown outside RULE_FILES and adds no value cite of a code file (STALE008 below, which makes it 4). That one diff is `--raw -p -U0`, so it also carries the added lines STALE005 reads and
a code-only range pays only for the patch text. An added governed line that holds a verb or a route word reads its
file's head blob (the paragraph around it) and, when a sentence cites a route or a `(read ...)` or `(test ...)` file,
the rows file or that file's presence at head, all through the one `cat-file` the run opens: one more start, and none
for a range with no such line. A range that changes the rows file reads it at base and head through the same `cat-file`;
when a row id is gone it also lists the tree once and reads each tracked .md once.
A touched .py adds one `git cat-file --batch` and, through the report below, one `ls-tree`, so it starts 5. A removed
or renamed path adds `ls-tree` and that `cat-file --batch`, so 5 at most. Each tracked .md is read once, and only
when a removed or renamed path, or a name that a touched .py no longer defines, gives the findings something to
look for. A touched .py also loads the py-facts script once, in-process (no start, no .pyc). It writes no file and leaves no process running.
STALE008 starts at most the one `cat-file`. It reads every tracked .md, through the same `ls-tree` and `cat-file`, only
when a touched .py changed a module-level literal, as the removed-name read does. Otherwise it reads only the touched .md
whose added lines hold a value cite of a .py, .mjs, .js, .cjs, .ts or .sh file, found from the diff already read. Such a
Markdown-only range starts 4 (the 3 and that `cat-file`); one with no such line reads no blob and starts 3. A touched .json
starts nothing more.
The report adds, for a changed non-Markdown file, one `ls-tree` of the decisions folders and the mechanisms file (none
when the run already listed the whole tree) and the `cat-file --batch`, which reads each decision record whole (a regex
then takes its Home line) and the mechanisms file once. The decisions folder is the first of lint/layout.py
`candidates(root, "decisions")` that holds a file. A changed RULE_FILES file adds its base and head blobs and the
mechanisms file to that read. Its list of changed files comes from the diff the run already read, with no git start.
A range whose merge-base or diff failed adds starts to tell the cause apart, an upper bound: `a...b` four, `a..b`
three; a base with a first-parent suffix adds a `rev-list`, so five and four; the root form `HEAD~1..HEAD` five (its
three-dot form six); a passing run adds none.
A --tree run starts one python3, then git rev-parse, ls-tree and one cat-file --batch. It reads each tracked .md
once, and each file a line anchor names once more, even when that file is a .md. It writes no file and prints no report.
"""
import argparse
import ast
import bisect
import collections
import importlib.util
import json
import os
import posixpath
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # the cost contract: a run writes no file, so no .pyc for the import below
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import layout  # noqa: E402  the one home of where a repo keeps its decisions (lint/layout.py)
from precompact_handoff import PREMISE_KINDS  # noqa: E402  the one home of the premise kinds (hooks/precompact_handoff.py)
import route_match  # noqa: E402  the one home of the route rows file's path (hooks/route_match.py)
from rule_audit import ANCHOR_RE, RULE_FILES  # noqa: E402  the one home of the anchor pattern and the rule files

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
# A test node id, `file.py::name` or `file.py::Class::name`: the chain is one name per segment.
NODE_RE = re.compile(NOT_BEFORE + r"`?(%s\.py)::([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)" % RUN)
FOREIGN_PAIR_RES = pair_res(FOREIGN_EXT)
FOREIGN_FILE = re.compile(r"\.%s\Z" % FOREIGN_EXT)
DISABLE_RE = re.compile(r"<!--\s*ste-disable-line([^>]*?)-->")
SIMPLE_PATH = re.compile(r"^%s$" % RUN)
FILE_CITE = re.compile(r"^[^/]+(?:/[^/]+)*/[^/]*[^/.]\.[A-Za-z0-9]+$")  # a folder part and an extension
ANCHOR = re.compile(r":(\d+)(?:-(\d+))?(?!\w)")


class Unknown(Exception):
    """A read that could not run."""


class UnknownText(str):
    """A message a reader that judges returns for a line it cannot judge: find_stale prints it as unknown, never as a
    finding."""


class BaseUnknown(Unknown):
    """The base of the range does not resolve, as in a shallow clone. Not a finding."""


def head_resolves(head):
    """True when `head` names a commit. Run only after a read failed, to tell a missing head (a read that could
    not run) from a missing base (a shallow clone)."""
    done = _nowindow.run(["git", "rev-parse", "--verify", "--quiet", head + "^{commit}"], capture_output=True)
    return done.returncode == 0


def resolves(rev):
    """True when `rev` names a commit."""
    done = _nowindow.run(["git", "rev-parse", "--verify", "--quiet", rev + "^{commit}"], capture_output=True)
    return done.returncode == 0


# A first-parent suffix: `~`, `^`, `~1`, `^1`, also zero-padded (`~01`). `~0` and `^0` name the commit itself: no match.
FIRST_PARENT_SUFFIX = re.compile(r"\A(.+?)[~^](?:0*1)?\Z")


def cut_base(base, head):
    """True when a base that does not resolve is a gap in the history, not a name that points at nothing: the clone is
    shallow (its base sha is cut away), or `base` is the first parent of `head` and `head` is a root commit, which a
    first push to the default branch reads by design. `base` is the first parent of `head` when it is a stem plus a
    first-parent suffix (`~`, `^`, `~1`, `^1`, `~01`) and the stem names the head's own commit: `HEAD~1`, `@~1` and
    `<sha>^` count, `<another root>^1` does not. A rev-list or rev-parse that exits non-zero is no root: the range
    is unknown. Run only after a read failed.
    The extra git starts are an upper bound: `a...b` four (head, base twice, shallow), `a..b` three. A base with a
    first-parent suffix adds a `rev-list`: `a...b` five, `a..b` four. The root form `HEAD~1..HEAD` five (those three
    plus `rev-list` and a `rev-parse` of the stem); its three-dot form six."""
    if resolves(base):
        return False
    shallow = _nowindow.run(["git", "rev-parse", "--is-shallow-repository"], capture_output=True)
    if shallow.stdout.strip() == b"true":
        return True
    suffixed = FIRST_PARENT_SUFFIX.match(base)
    if not suffixed:
        return False
    parents = _nowindow.run(["git", "rev-list", "--parents", "-n", "1", head], capture_output=True)
    shas = parents.stdout.split()
    if parents.returncode != 0 or len(shas) != 1:  # a failed rev-list is no root: unknown
        return False
    stem = _nowindow.run(["git", "rev-parse", "--verify", "--quiet", suffixed.group(1) + "^{commit}"],
                         capture_output=True)
    return stem.returncode == 0 and stem.stdout.split() == shas  # the stem must be the head's own commit


def history_gap(base, head):
    """True when a failed merge-base is a gap in the history: `base` resolves (no shared history with the head) or
    `cut_base`. False for a base that names nothing in a full clone. Run only after merge-base failed."""
    return resolves(base) or cut_base(base, head)


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
    except FileNotFoundError as exc:
        if os.path.lexists(os.path.join(root, ".ste-lint-exclude")):  # a link whose target is gone
            raise Unknown(".ste-lint-exclude cannot be read (%s)" % exc)
        # no exclude file is a repo with no excludes
    except (OSError, UnicodeDecodeError) as exc:  # present but unreadable: the check cannot tell what it should leave out
        raise Unknown(".ste-lint-exclude cannot be read (%s)" % exc)
    lines += os.environ.get("EXCLUDE", "").replace(",", "\n").splitlines()
    cleaned = (line.strip() for line in lines)
    return [glob_regex(p) for p in cleaned if p and not p.startswith("#")]


def parse_range(text):
    """(diff arguments, base spec, head spec). A three-dot range reads base blobs at the merge base."""
    if "..." in text:
        left, right = text.split("...", 1)
        try:
            base = git("merge-base", left, right).decode().strip()
        except Unknown as exc:
            if head_resolves(right) and history_gap(left, right):
                raise BaseUnknown(str(exc))  # the head is there and the history is not: a shallow clone or an orphan base
            raise
        return [text], base, right
    if ".." in text:
        left, right = text.split("..", 1)
        return [text], left, right
    raise Unknown("--range wants base...head, got %r" % text)


HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def added_markdown_lines(patch):
    """{path: [(number, text)]}: each line a `-U0` patch adds to a .md file, by its line number at head. A hunk's
    body is read by its counts, never by its first character, so an added line that starts `+++ ` or `@@ ` is no
    header. A `\\ No newline` marker is no line."""
    found, path, rows, i = {}, None, patch.split("\n"), 0
    while i < len(rows):
        row = rows[i]
        i += 1
        if row.startswith("+++ "):
            name = row[4:].split("\t")[0]
            path = name[2:] if name.startswith("b/") else None
            continue
        hunk = HUNK.match(row)
        if not hunk:
            continue
        gone = int(hunk.group(1)) if hunk.group(1) is not None else 1
        number, new = int(hunk.group(2)), int(hunk.group(3)) if hunk.group(3) is not None else 1
        while (gone or new) and i < len(rows):
            body = rows[i]
            i += 1
            if body.startswith("-"):
                gone -= 1
            elif body.startswith("+"):
                new -= 1
                if path is not None and path.endswith(".md"):
                    found.setdefault(path, []).append((number, body[1:].rstrip("\r")))
                number += 1
    return found


def read_diff(diff_args, head=None, base=None):
    """(removed, renamed, modified, added, lines) from one `git diff -M --raw -p -z -U0`: removed paths, {old: new},
    paths changed in place, added paths, and `added_markdown_lines`. The raw records come first, then one empty
    record, then the patch text. One start serves both, so the added lines cost no start of their own."""
    try:
        out = git("diff", "-M", "--raw", "-p", "-z", "-U0", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/",
                  *diff_args).decode("utf-8", "replace")
    except Unknown as exc:
        if head is None or (head_resolves(head) and (base is None or cut_base(base, head))):
            raise BaseUnknown(str(exc))  # the head is there and the history is not: a shallow clone
        raise
    head, _, patch = out.partition("\0\0")
    tokens = head.split("\0")
    removed, renamed, modified, added = [], {}, [], []
    i = 0
    while i < len(tokens) and tokens[i].startswith(":"):
        status = tokens[i].split()[-1][0]
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
    return removed, renamed, modified, added, added_markdown_lines(patch)


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


def target_names(target):
    """Each name one binding target binds: a name, or each name inside a tuple, list or starred target."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from target_names(element)
    elif isinstance(target, ast.Starred):
        yield from target_names(target.value)


def statement_expressions(node):
    """Each expression node of one module-level statement. Nested statements are left out, since
    `module_statements` yields them on their own, and so is a lambda body, which is its own scope."""
    stack = [child for child in ast.iter_child_nodes(node) if not isinstance(child, ast.stmt)]
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(child, ast.Lambda):
            stack.extend(c for c in ast.iter_child_nodes(child) if not isinstance(c, ast.stmt))


def target_bindings(statements):
    """Names the module-level statements bind that py-facts `defined_names` does not read: each name in a
    tuple, list or starred assignment target, a for target, a with-as target, and a walrus target."""
    names = set()
    for node in statements:
        if isinstance(node, FUNCTIONS + (ast.ClassDef,)):
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            targets = [node.target]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            targets = [item.optional_vars for item in node.items if item.optional_vars is not None]
        else:
            targets = []
        for target in targets:
            names.update(target_names(target))
        names.update(e.target.id for e in statement_expressions(node) if isinstance(e, ast.NamedExpr))
    return names


def parse_python(source):
    """The `ast` of a Python source (str or bytes), or None when it does not parse."""
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def names_in(source):
    """Names a prose line can cite, read from every module-level statement (`module_statements`): each name
    py-facts `defined_names` finds (def, class, plain-name assignment, import), each name `target_bindings`
    finds, and each def directly in a module-level class. A def nested in a function is no public name. Read
    with `ast`; None when it does not parse."""
    tree = parse_python(source)
    if tree is None:
        return None
    flat = list(module_statements(tree.body))
    names = py_facts().defined_names(ast.Module(body=flat, type_ignores=[]))  # defined_names reads `.body` only
    names.update(target_bindings(flat))
    for node in flat:
        if isinstance(node, ast.ClassDef):
            names.update(m.name for m in module_statements(node.body) if isinstance(m, FUNCTIONS))
    return names


# The value cite grammar, `[FILE: ]SYMBOL = LITERAL` in one backtick span: a Python copy of `VALUE_CITE_RE`,
# `parseLiteral` and `sameValue` in skills/plain-english-map/scripts/map-check.mjs (the MAP9 check). The copy has a
# reason: the ste-lint action runs Python only, with no Node, so it cannot call MAP9's reader.
# skills/plain-english-map/tests/value-cite-parity.json holds the copies together: both suites read its rows. Two
# differences by design: a cite with no FILE takes its file from the map line above in MAP9, and here it is no cite;
# MAP9 skips fenced blocks, and here they count as prose, as for every other code.
VALUE_CITE_RE = re.compile(r"(?:(\S+?):\s+)?(\S+)\s+=\s+(.+)")
SPAN_RE = re.compile(r"`([^`]+)`")
GONE = "gone"  # `tree_value` answer: the module assigns no such name
ABSENT = "absent"  # `ValueReader.tree` answer: no tracked file has the path


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


def tree_value(tree, symbol):
    """`(value,)` the module-level literal `symbol` holds in a parsed .py file, read through py-facts `answer`, the
    reader MAP9 uses: a value `ast.literal_eval` accepts and JSON can hold. GONE when the module assigns no such
    name. None when the name has no value or its value is no literal, such as a call."""
    found = py_facts().answer({"file": "", "symbol": symbol}, tree, [])
    if found["ok"]:
        return (found["value"],)
    return GONE if found.get("gone") else None


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

    def __init__(self, base, head, removed, renamed, modified, batch, added=(), lines=None):
        self.base, self.head, self.removed, self.renamed, self.batch = base, head, removed, renamed, batch
        self.added_lines = lines or {}  # the .md lines the range adds, by path
        self.unknowns = []
        self.tree = None  # the head tree entries once a read listed the whole tree; the report reuses it
        self.changed = set(removed) | set(renamed) | set(renamed.values()) | set(modified) | set(added)
        self.py_files = {p: p for p in modified if p.endswith(".py")}
        self.py_files.update({old: new for old, new in renamed.items() if old.endswith(".py") and new.endswith(".py")})
        self.foreign_files = {p for p in list(modified) + list(renamed.values()) if FOREIGN_FILE.search(p)}
        # The Markdown the range touched, as {path at head: path at base, or None for a new file}.
        self.md_base = {p: p for p in modified if p.endswith(".md")}
        self.md_base.update({new: old for old, new in renamed.items() if new.endswith(".md")})
        self.md_base.update({p: None for p in added if p.endswith(".md")})


class PathReader:
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


class NameReader:
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
        for match in NODE_RE.finditer(text):
            path = match.group(1)
            for name in match.group(2).split("::"):
                if path not in claimed and name in state.get(path, ()):
                    messages.append("%s no longer defines %s at head; find its new home" % (path, name))
        return messages


class ForeignReader:
    """STALE002 unknown: a line that cites `file.mjs name` of a JavaScript or shell file the range touched. Those
    names are not read, so the line is reported as unknown. Reports through `unknown`, and only when another
    reader made the run read Markdown."""
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
        return messages


def foreign_value_text(path, symbol):
    return "%s %s: JavaScript and shell values are not checked" % (path, symbol)


def readable_cite(path):
    """True for a cite path a value reader answers for: a .py file, or a file whose values it cannot read."""
    return path.endswith(".py") or bool(FOREIGN_FILE.search(path))


class ForeignValueReader:
    """STALE008 unknown: a line that holds a value cite of a JavaScript or shell file the range touched. Those values
    are not read, so the line is reported as unknown. Its code is STALE008, so that mark leaves the line out. A JSON
    cite is not read and prints nothing. It runs on a whole-tree read only; ValueReader reports an added line's cite."""
    code = "STALE008"
    unknown = True

    def prepare(self, rng):
        return rng.foreign_files or None

    def line(self, state, text, claimed):
        messages = []
        for path, symbol, _ in value_cites(text):
            text_ = foreign_value_text(path, symbol)
            if path in state and text_ not in messages:
                messages.append(text_)
        return messages


class ValueReader:
    """STALE008: a value cite `file.py: NAME = literal` that quotes what the range changed or removed, or that the
    range added wrong. A cite of a value the range did not change, on a line the range did not add, is left alone.
    It needs every tracked Markdown file only when a module-level literal changed; else it reads the touched pages
    whose added lines hold a value cite of a code file, which is where a new wrong cite can sit."""
    code = "STALE008"

    class State:
        def __init__(self, rng, changed, pages):
            self.rng, self.changed, self.pages = rng, changed, pages
            self.fresh = None  # how often each line holds at base in the page being read; None: the page is untouched
            self.seen = None  # how often each line has come up so far at head
            self.trees = {}  # (side, path) -> the parsed .py, or None
            self.values = {}  # (side, path, symbol) -> `tree_value`

    def prepare(self, rng):
        """None when the range changed no literal and added no cite of a .py file. A touched .py that does not parse
        is NameReader's unknown, so it is skipped here."""
        changed = False
        for path, new in sorted(rng.py_files.items()):
            if path != new:
                continue  # a renamed file: the cites of its old path are STALE001's
            trees = [parse_python(src) if src is not None else None
                     for src in (rng.batch.get("%s:%s" % (rev, path)) for rev in (rng.base, rng.head))]
            if None not in trees and self.literal_changed(*trees):
                changed = True
                break
        pages = [md for md in sorted(rng.md_base)
                 if any(readable_cite(path) for _, text in rng.added_lines.get(md, ()) for path, _, _ in value_cites(text))]
        return self.State(rng, changed, pages) if changed or pages else None

    @staticmethod
    def literal_changed(before, after):
        """True when a module-level name holds a literal at base, as `tree_value` reads it, and at head holds a
        different literal or is gone. A change to or from a call, or any value that is no literal, is none: a cite
        of it is never judged. A gone name counts: this reader judges its cite, and STALE002 never reads a value cite."""
        for name in py_facts().assigned(before):
            was = tree_value(before, name)
            if was is None or was == GONE:
                continue
            now = tree_value(after, name)
            if now == GONE or (now is not None and not strict_equal(was[0], now[0])):
                return True
        return False

    def needs_tree(self, state):
        return state.changed

    def pages(self, state):
        return state.pages

    def begin(self, state, md, rng):
        """Before the lines of a page: count its lines at base, so a line the range only moved is not an added one."""
        state.seen = collections.Counter()
        if md not in rng.md_base:
            state.fresh = None
            return
        old = rng.md_base[md]
        blob = rng.batch.get("%s:%s" % (rng.base, old)) if old else None
        text = blob.decode("utf-8", "replace").replace("\r\n", "\n") if blob is not None else ""
        state.fresh = collections.Counter(line.strip() for line in text.split("\n"))

    def tree(self, state, side, path):
        """The parsed .py at base or head: ABSENT when no tracked file has the path, None when it does not parse."""
        key = (side, path)
        if key not in state.trees:
            blob = state.rng.batch.get("%s:%s" % (state.rng.base if side == "base" else state.rng.head, path))
            state.trees[key] = ABSENT if blob is None else parse_python(blob)
        return state.trees[key]

    def value(self, state, side, path, symbol):
        """`tree_value` of the cite's symbol in the file at base or head. None when the file is absent or no parse."""
        key = (side, path, symbol)
        if key not in state.values:
            tree = self.tree(state, side, path)
            state.values[key] = None if tree is None or tree is ABSENT else tree_value(tree, symbol)
        return state.values[key]

    def line(self, state, text, claimed):
        if " = " not in text:
            return []
        key = text.strip()
        state.seen[key] += 1
        # The nth copy of a line is added when base holds fewer than n copies, so a second copy of an old line counts.
        added = state.fresh is not None and state.seen[key] > state.fresh[key]
        whole = state.rng.tree is not None  # every tracked page is read: an untouched line is read too
        messages = []

        def cannot_read(why, finding):
            """A cite this reader cannot judge: a finding on an added line, unknown on any line of a whole read."""
            if added and finding:
                messages.append(why)
            elif added or whole:
                messages.append(UnknownText(why))

        for path, symbol, literal in value_cites(text):
            if not path.endswith(".py"):
                if added and FOREIGN_FILE.search(path):  # a touched file's cite on an untouched line: ForeignValueReader's
                    messages.append(UnknownText(foreign_value_text(path, symbol)))
                continue
            if path in state.rng.removed or path in state.rng.renamed:
                continue  # STALE001 judges a cite of a path the range removed
            tree = self.tree(state, "head", path)
            lit = parse_literal(literal)
            if tree is ABSENT:
                cannot_read("%s names no tracked file at head" % path, True)
                continue
            if lit is None:  # MAP9 reads a cite as JSON, so a cite in any other form can never match
                cannot_read("%s says %s = %s, and %s is no JSON literal" % (path, symbol, literal, literal), True)
                continue
            head = self.value(state, "head", path, symbol)
            if head is None:  # the file does not parse, or the name holds no literal: neither can be compared
                cannot_read("%s %s holds no literal at head, so the cite is not checked" % (path, symbol), False)
                continue
            base = self.value(state, "base", path, symbol) if path in state.rng.py_files else head
            quotes_base = base not in (None, GONE) and same_value(lit, base[0])
            if head == GONE:
                if base != GONE and (quotes_base or added):
                    messages.append("%s no longer assigns %s at head; this range removed the assignment" % (path, symbol))
                elif added:
                    messages.append("%s assigns no module-level %s at head" % (path, symbol))
            elif quotes_base and not strict_equal(base[0], head[0]):
                messages.append("%s says %s = %s, the value at base; this range changed it to %s"
                                % (path, symbol, literal, json.dumps(head[0])))
            elif added and not same_value(lit, head[0]):
                messages.append("%s says %s = %s, and the file has %s" % (path, symbol, literal, json.dumps(head[0])))
        return messages


# The rows file as a repo path, for a read at head. Derived from the one home of its path, never copied.
ROWS_AT_HEAD = os.path.relpath(route_match.ROUTE_ROWS_FILE, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                       "..")).replace(os.sep, "/")
HTML_COMMENT = re.compile(r"<!--.*?-->")
# Text in straight or curly double quotes, or a bare file path (a folder part and an extension): a mention, no claim.
BARE_PATH = r"(?<![\w./@+~-])(?:[\w.@+~-]+/)+[\w.@+~-]*\.\w+"  # a file path with a folder part and an extension
MENTION = re.compile(r'"[^"]*"|\u201c[^\u201d]*\u201d|' + BARE_PATH)
PATH_SPAN = re.compile(BARE_PATH + r"\Z")
HEADING_OR_QUOTE = re.compile(r"^[ \t]{0,3}(?:#{1,6}(?:[ \t]|$)|>)")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
PAREN_GROUP = re.compile(r"\(([^()]*)\)")
TABLE_ROW = re.compile(r"^[ \t]{0,3}\|")
LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# A sentence ends at . ! or ? before a space or the end. "e.g.", "i.e.", "vs." and "cf." end none, so a paren group
# such as "(e.g. read hooks/x.py:2)" stays in one sentence.
SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bcf)[.!?](?=\s|\Z)")
# A capability verb. `is refused` and `are refused` are present; a bare `refused` is an incident and never matches.
VERB = re.compile(r"\b(?:cannot|can\s+not|can['’]t|won['’]t|will\s+not|refuses|denies|blocks"
                  r"|(?:is|are)\s+(?:not\s+)?(?:refused|blocked|denied)"
                  r"|not\s+available|(?:isn|aren)['’]t\s+available|works"
                  r"|(?:does\s+not|doesn['’]t|do\s+not|don['’]t)\s+work"
                  r"|gets?\s+an?\s+40[357])\b", re.I)
# `local` alone names a branch or a run, so it is no route word; the three forms below name the owner's computer.
ROUTE_WORD = re.compile(r"\b(?:cloud|locally|local\s+sessions?|auto[\s-]+mode|classifier|gh|mcp|proxy|harness)\b"
                        r"|\bon\s+the\s+owner['’]s\s+computer\b", re.I)
# A source is a path, with an optional line anchor; a bare date or version has neither a folder nor an extension.
SOURCE = re.compile(r"(?=[^\s]*(?:/|\.[A-Za-z]))[\w./@+~-]+(?::\d+(?:-\d+)?)?(?:::\w+)*\Z")
TEST_CITE = re.compile(r"(%s)::[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*\Z" % RUN)
ROUTE_CITE = re.compile(r"[\w.-]+\Z")
# A premise kind that backs nothing: its source is a note or a guess. The rest of PREMISE_KINDS back a claim.
WEAK_KINDS = ("notes", "assumed")
BACKING_KINDS = tuple(kind for kind in PREMISE_KINDS if kind not in WEAK_KINDS)


def fenced_lines(rows):
    """The numbers (from 1) of the rows inside a fenced block, the fence rows included. A backtick fence takes no
    backtick in its info string, so a span such as `` ``` `` that starts a line opens none."""
    inside, opener = set(), None
    for number, row in enumerate(rows, 1):
        fence = FENCE.match(row)
        if opener is None:
            if fence and not (fence.group(1)[0] == "`" and "`" in fence.group(2)):
                opener = fence.group(1)
                inside.add(number)
        else:
            inside.add(number)
            if fence and fence.group(1)[0] == opener[0] and len(fence.group(1)) >= len(opener) \
                    and not fence.group(2).strip():
                opener = None
    return inside


def paren_cites(row):
    """The text of each parenthesised group of the row that no code span swallows, with backticks dropped so
    "(read `hooks/x.py:2`)" reads as "(read hooks/x.py:2)". The one home of what a backing looks like on a line."""
    spans = [m.span() for m in CODE_SPAN.finditer(row)]
    return [m.group(1).replace("`", "").strip() for m in PAREN_GROUP.finditer(row)
            if not any(a <= m.start() < b for a, b in spans)]


def cite_kind(cite):
    """(kind, rest) of "kind rest": the first word lower-cased, and what follows it."""
    word, _, rest = cite.strip().partition(" ")
    return word.lower(), rest.strip()


def has_source(rest):
    """True when `rest` holds a source path as one of its words (split at spaces, commas and semicolons)."""
    return any(SOURCE.match(word.rstrip(".")) for word in re.split(r"[\s,;]+", rest) if word)


def backing_path(kind, rest):
    """The file a `read` or `test` backing points at, or None for any other kind."""
    if kind == "test":
        node = TEST_CITE.match(rest)
        return node.group(1) if node else None
    if kind == "read":
        word = next((w.rstrip(".") for w in re.split(r"[\s,;]+", rest) if SOURCE.match(w.rstrip("."))), None)
        return re.split(r"::?\d*", word, maxsplit=1)[0] if word else None
    return None


def defined_line(text, name):
    """The first line where `name` is a def or class in the Python `text`, found through the AST so a comment, a docstring or a string
    that names it is never the answer. 0 when the text parses and defines no such name; None when it is not Python."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return min((n.lineno for n in ast.walk(tree) if isinstance(n, kinds) and n.name == name), default=0)


def cited_excerpt(cite, text, limit=40):
    """The numbered lines of a backing file's `text` that `cite` points at, at most `limit`: a `read path:N` or
    `path:N-M` gives those lines, a `test path::name` gives the lines from where `name` is defined, and any other
    cite with a backing path gives the top of the file. A cite with no backing path gives None. A prose judge sends
    this beside the line, so the model reads what the line cites."""
    kind, rest = cite_kind(cite)
    if backing_path(kind, rest) is None:
        return None
    rows = text.replace("\r\n", "\n").split("\n")
    first, last = 1, limit
    anchor = re.search(r"[\w./@+~-]:(\d+)(?:-(\d+))?\b", rest) if kind == "read" else None
    if anchor:
        first = int(anchor.group(1))
        last = int(anchor.group(2) or first)
    elif kind == "test" and TEST_CITE.match(rest):
        name = rest.rsplit("::", 1)[-1]
        line = defined_line(text.replace("\r\n", "\n"), name)
        if line is None:  # not Python: the first row that names it
            line = next((n for n, row in enumerate(rows, 1) if re.search(r"\b%s\b" % re.escape(name), row)), 0)
        first = line or 1
    first = max(first, 1)
    last = min(max(last, first), first + limit - 1, len(rows))
    return "\n".join("%d: %s" % (n, rows[n - 1]) for n in range(first, last + 1))


def backed_lines(texts, changed):
    """[(prose file, line, backing)]: each line of `texts` ({path: text}) with a `(test path::name)` or
    `(read path:N)` backing that points at one of the `changed` files, sorted. `backing` is the cite as written,
    such as "read hooks/guard.py:2". A prose judge calls this to learn which lines a changed file may have
    made stale. Lines in a fence, and groups in a code span, are mentions and never count."""
    found = []
    for path, text in sorted(texts.items()):
        rows = text.replace("\r\n", "\n").split("\n")
        fenced = fenced_lines(rows)
        for number, row in enumerate(rows, 1):
            if number in fenced or "(" not in row:
                continue
            for cite in paren_cites(row):
                kind, rest = cite_kind(cite)
                if backing_path(kind, rest) in changed:
                    found.append((path, number, cite))
    return found


def named_in_code_spans(row):
    """(paths, names) of the code spans on `row`: a span that is one file path is a path, any other span (a name or a number) is a name."""
    paths, names = [], []
    for match in CODE_SPAN.finditer(row):
        span = match.group(0).strip("`").strip()
        if not span:
            continue
        (paths if PATH_SPAN.match(span) else names).append(span)
    return list(dict.fromkeys(paths)), list(dict.fromkeys(names))


NAMED_MAX_BYTES = 256 * 1024  # a named file larger than this is skipped, never excerpted
NAMED_ROW_CHARS = 200  # an excerpt row longer than this is cut, with a marker


def named_too_large(text):
    """True when `text` is over NAMED_MAX_BYTES (UTF-8), so named_excerpt skips it. Exactly NAMED_MAX_BYTES is not too large."""
    return len(text) > NAMED_MAX_BYTES or (len(text) * 4 > NAMED_MAX_BYTES and len(text.encode("utf-8", "replace")) > NAMED_MAX_BYTES)


def named_excerpt(names, text, around=3, limit=40):
    """The numbered lines of a file's `text` within `around` lines of each line that holds one of `names` as a whole word, at most
    `limit` lines, a "..." row between two windows that do not touch. Each row is cut to NAMED_ROW_CHARS characters with a marker.
    When the `limit` drops later lines, the excerpt ends with a marker line that says so; it has none otherwise. None when no line holds
    a name, or when `text` is over NAMED_MAX_BYTES (named_too_large). A prose judge sends this beside a line that names the file in
    backticks, so the model reads the code the line talks about. Cost: at most `limit` rows of NAMED_ROW_CHARS characters."""
    if named_too_large(text):
        return None
    rows = text.replace("\r\n", "\n").split("\n")
    hits = [re.compile(r"(?<!\w)%s(?!\w)" % re.escape(name)) for name in names]
    keep = set()
    for n, row in enumerate(rows, 1):
        if any(h.search(row) for h in hits):
            keep.update(range(max(n - around, 1), min(n + around, len(rows)) + 1))
    ordered = sorted(keep)
    shown = ordered[:limit]
    if not shown:
        return None
    out, last = [], None
    for n in shown:
        if last is not None and n != last + 1:
            out.append("...")
        row = rows[n - 1]
        if len(row) > NAMED_ROW_CHARS:
            row = row[:NAMED_ROW_CHARS] + " [row cut at %d characters]" % NAMED_ROW_CHARS
        out.append("%d: %s" % (n, row))
        last = n
    if len(ordered) > limit:
        out.append("[more lines left out at the %d-row cap]" % limit)
    return "\n".join(out)


def blanked(text):
    """(outside, route): `text` twice, each the same length, with the newlines kept.
    outside: each code span and HTML comment blanked, so a verb or a sentence end inside one is a mention.
    route: the same, except the words of a code span that names no path stay: a route word used as the subject,
    "`gh` cannot close", still counts. A span with a `/` or `.` names a file, so its words are not a route.
    Both also blank text in straight or curly double quotes and a bare file path, the same way: each is a mention.
    An apostrophe is no quote and a lone quote pairs with none; single quotes are left as they are."""
    outside, route = list(text), list(text)

    def blank(chars, start, end):
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    for match in CODE_SPAN.finditer(text):
        start, end = match.span()
        ticks = len(match.group(1))
        blank(outside, start, end)
        if "/" in text[start:end] or "." in text[start:end]:
            blank(route, start, end)
        else:
            blank(route, start, start + ticks)
            blank(route, end - ticks, end)
    for match in MENTION.finditer("".join(outside)):
        blank(outside, *match.span())
        blank(route, *match.span())
    for match in HTML_COMMENT.finditer("".join(outside)):
        blank(outside, *match.span())
        blank(route, *match.span())
    return "".join(outside), "".join(route)


def paragraphs(rows, fenced):
    """[(first row number, [rows])]: the runs of prose rows. A blank row, a heading, a quote row, a fenced row and a
    list item each end a run; a list item also starts the next, so a code span never pairs across two items.
    A table row (a line starting with `|`) is a run of its own, so no quote or sentence runs across rows."""
    found, current = [], None
    for number, row in enumerate(rows, 1):
        if number in fenced or not row.strip() or HEADING_OR_QUOTE.match(row):
            current = None
            continue
        if TABLE_ROW.match(row):
            found.append((number, [row]))
            current = None
            continue
        if current is None or LIST_ITEM.match(row):
            current = (number, [])
            found.append(current)
        current[1].append(row)
    return found


def sentences(text, outside):
    """[(start, end)] offsets of each sentence of a paragraph, found in `outside` so that no code span or comment ends
    one, and trimmed in `text`. A sentence with nothing outside a span or comment is left out."""
    found, start = [], 0
    for match in list(SENTENCE_END.finditer(outside)) + [None]:
        end = match.end() if match else len(text)
        piece = text[start:end]
        lead = len(piece) - len(piece.lstrip())
        a, b = start + lead, start + len(piece.rstrip())
        if outside[a:b].strip():
            found.append((a, b))
        start = end
    return found


def blob_ids(blob):
    """The set of row ids of a rows file blob, or None when it is not {"rows": [...]}."""
    try:
        rows = json.loads(blob.decode("utf-8", "replace")).get("rows")
        return {row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}
    except (ValueError, AttributeError, TypeError):
        return None


class RouteClaimReader:
    """STALE005: a sentence of governed prose that states a capability by route with no backing, in a paragraph the
    range adds a line to. Report only: its messages never become findings (decision source-prose-lint-ships-dark).
    A sentence is judged whole, so a claim wrapped over several lines fires on its first line, and its backing may sit
    on a later line of the same sentence. The range also reports each prose line at head that cites a route row the
    range removes."""
    code = "STALE005"
    scope = "added"

    def prepare(self, rng):
        """(files, rows changed), or None. files: {path: [(number, text)]} of the governed Markdown files the range
        adds lines to. rows changed: the range touches the rows file."""
        excludes = exclude_patterns(".")
        files = {p: rows for p, rows in rng.added_lines.items() if rows and governed(p, excludes)}
        changed = ROWS_AT_HEAD in rng.changed
        return (files, changed) if files or changed else None

    def claims(self, rng, state):
        """[(path, number, message)]. The head blob of a file is read only when one of its added lines holds a verb or
        a route word, and the rows file or a backing file only when a sentence cites it; all go through `rng.batch`."""
        files, rows_changed = state
        found, rows_at_head = {}, []
        for path in sorted(files):
            added = dict(files[path])
            if not any(VERB.search(HTML_COMMENT.sub(" ", t)) or ROUTE_WORD.search(HTML_COMMENT.sub(" ", t))
                       for t in added.values()):
                continue
            blob = rng.batch.get("%s:%s" % (rng.head, path))
            rows = (blob or b"").decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
            numbers = sorted(added)
            for first, block in paragraphs(rows, fenced_lines(rows)):
                i = bisect.bisect_left(numbers, first)
                if i == len(numbers) or numbers[i] >= first + len(block):
                    continue  # the range adds no line to this paragraph
                for number, message in self.judge_paragraph(rng, first, block, set(numbers), rows_at_head):
                    found[(path, number)] = message
        if rows_changed:
            self.removed_rows(rng, found, rows_at_head)
        return [(path, number, message) for (path, number), message in found.items()]

    def judge_paragraph(self, rng, first, block, added, rows_at_head):
        """[(first row number of the sentence, message)] for each unbacked claim sentence of the paragraph that
        holds an added row and carries no `ste-disable-line STALE005` mark."""
        text = "\n".join(block)
        outside, route = blanked(text)
        starts, offset = [], 0
        for row in block:
            starts.append(offset)
            offset += len(row) + 1
        out = []
        for a, b in sentences(text, outside):
            if not (VERB.search(outside[a:b]) and ROUTE_WORD.search(route[a:b])):
                continue
            top, bottom = (first + bisect.bisect_right(starts, x) - 1 for x in (a, b - 1))
            if not any(n in added for n in range(top, bottom + 1)):
                continue
            if any("ste-disable-line" in block[n - first] and self.code in disabled(block[n - first])
                   for n in range(top, bottom + 1)):
                continue
            message = self.judge(rng, text[a:b], rows_at_head)
            if message:
                out.append((top, message))
        return out

    def judge(self, rng, sentence, rows_at_head):
        """The message for one claim sentence, or None when it is backed."""
        backed, dead, dead_files, unchecked = False, [], [], []
        for cite in paren_cites(sentence):
            kind, rest = cite_kind(cite)
            path = backing_path(kind, rest)
            if kind in BACKING_KINDS or kind == "test":
                sourced = bool(TEST_CITE.match(rest)) if kind == "test" else has_source(rest)
                if sourced and path is not None and rng.batch.get("%s:%s" % (rng.head, posixpath.normpath(path))) is None:
                    dead_files.append(path)  # a read or test backing is dead when its file is not at head
                else:
                    backed = backed or sourced
            elif kind == "route" and ROUTE_CITE.match(rest):
                ids, why = route_ids(rng, rows_at_head)
                if ids is None:
                    unchecked.append((rest, why))
                elif rest in ids:
                    backed = True
                else:
                    dead.append(rest)
        if dead:
            return "cites %s, a dead route: no row of the route rows at head has that id" % ", ".join(dead)
        if dead_files:
            return "cites %s as its backing, a file absent at head" % ", ".join(dead_files)
        if backed:
            return None
        if unchecked:
            return "cites route %s, not checked: the route rows file is %s" % (unchecked[0][0], unchecked[0][1])
        return ("states a capability by route with no backing; cite (KIND source) with KIND one of %s "
                "(%s back nothing), (test path::name), or (route <id>)"
                % (", ".join(BACKING_KINDS), " and ".join(WEAK_KINDS)))

    def removed_rows(self, rng, found, rows_at_head):
        """Add to `found` each prose line at head that cites a route row the range removes. Reads the rows file at
        base and at head, and the tracked Markdown only when a row id is gone."""
        base = rng.batch.get("%s:%s" % (rng.base, ROWS_AT_HEAD))
        base_ids = blob_ids(base) if base is not None else None
        head = rng.batch.get("%s:%s" % (rng.head, ROWS_AT_HEAD))
        head_ids = blob_ids(head) if head is not None else set()
        if not base_ids or head_ids is None:
            return
        gone = base_ids - head_ids
        if not gone:
            return
        if rng.tree is None:
            rng.tree = tracked_entries(rng.head)
        for md in markdown_files(rng.tree, exclude_patterns(".")):
            rows = read_markdown(rng.batch, rng.head, md).split("\n")
            fenced = fenced_lines(rows)
            for number, row in enumerate(rows, 1):
                if "(" not in row or number in fenced or HEADING_OR_QUOTE.match(row):
                    continue
                if "ste-disable-line" in row and self.code in disabled(row):
                    continue
                ids = [rest for kind, rest in map(cite_kind, paren_cites(row)) if kind == "route" and rest in gone]
                if ids:
                    found.setdefault((md, number), "cites %s, a route row this range removes" % ", ".join(ids))


def route_ids(rng, cache):
    """(ids, why) of the route rows at head, read once. ids is the set of row ids, or None with `why` ("absent" or
    "unreadable") when the file is missing or is not {"rows": [...]}: one unknown is noted, and no id is called dead.
    The env seam of hooks/route_match.py (`rows_path()`) names a file on disk and wins over the blob at head."""
    if not cache:
        seam = route_match.rows_path() != route_match.ROUTE_ROWS_FILE
        label = route_match.rows_path() if seam else ROWS_AT_HEAD
        if seam:
            try:
                with open(label, "rb") as f:
                    blob = f.read()
            except OSError:
                blob = None
        else:
            blob = rng.batch.get("%s:%s" % (rng.head, ROWS_AT_HEAD))
        ids = blob_ids(blob) if blob is not None else None
        why = ("absent" if seam else "absent at head") if blob is None else "unreadable, not {\"rows\": [...]}"
        if ids is None:
            rng.unknowns.append("%s is %s; route cites were not checked" % (label, why))
        cache.append((ids, why))
    return cache[0]


# One entry per code. A reader has `code`, `prepare(rng)` (its state, or None when the range gives it nothing to
# check) and `line(state, text, claimed)` (messages for one Markdown line; `claimed` holds the paths an earlier
# reader already cited there). A reader with `unknown = True` reports its messages as unknown, not as findings.
# A reader with `scope = "added"` reads the lines the range adds instead: `prepare(rng)` and `claims(rng, state)`, and
# its messages are report lines, never findings. A reader may also have `needs_tree(state)` and `pages(state)`: when
# no reader that judges needs the tree, the run reads only the pages those readers name, and only those readers.
# `begin(state, md, rng)` is called before the lines of each page. A new check adds one entry.
READERS = (PathReader(), NameReader(), ForeignReader(), ForeignValueReader(), ValueReader(), RouteClaimReader())


def tracked_entries(rev, *paths):
    """[(mode, path)] of every entry in the tree at rev, or only of the named folders and files, from one
    `ls-tree`."""
    tree = git("ls-tree", "-r", "-z", rev, *(["--"] + list(paths) if paths else [])).decode("utf-8", "replace").split("\0")
    return [(e.split(" ", 1)[0], e.split("\t", 1)[1]) for e in tree if "\t" in e]


def file_paths(entries):
    """The tracked file paths of ls-tree entries: regular files only, no symlink or submodule."""
    return [p for mode, p in entries if mode in ("100644", "100755")]


def governed(path, excludes):
    """True for a .md file a prose check reads: not the records page, not excluded."""
    return path.endswith(".md") and path != RECORDS_PAGE and not any(rx.match(path) for rx in excludes)


def markdown_files(entries, excludes):
    """The tracked .md files a prose check reads: regular files that are `governed`."""
    return [p for p in file_paths(entries) if governed(p, excludes)]


def read_markdown(batch, rev, md):
    blob = batch.get("%s:%s" % (rev, md))
    if blob is None:
        raise Unknown("%s is in the tree at %s but cannot be read" % (md, rev))
    return blob.decode("utf-8", "replace").replace("\r\n", "\n")  # a bad byte is U+FFFD, never a skip


def find_stale(rng):
    """{(path, line, code): [messages]}: the findings. Fills `rng.unknowns`."""
    found = {}
    if not rng.removed and not rng.renamed and not rng.py_files and not any(rng.added_lines.values()):
        return found  # the cost contract: nothing removed, so no blob, tree or Markdown read
    active = [(r, state) for r in READERS if getattr(r, "scope", "tree") == "tree"
              for state in [r.prepare(rng)] if state is not None]
    judges = [(r, state) for r, state in active if not getattr(r, "unknown", False)]
    if not judges:
        return found  # an unknown line never starts the Markdown read

    excludes = exclude_patterns(".")
    if any(getattr(r, "needs_tree", lambda state: True)(state) for r, state in judges):
        rng.tree = tracked_entries(rng.head)
        files = markdown_files(rng.tree, excludes)
    else:  # only the pages some reader names, and only those readers read them
        active = judges
        files = [md for r, state in judges for md in r.pages(state) if governed(md, excludes)]
    for md in files:
        text = read_markdown(rng.batch, rng.head, md)
        for reader, state in active:
            if hasattr(reader, "begin"):
                reader.begin(state, md, rng)
        for number, line in enumerate(text.split("\n"), 1):
            off = disabled(line) if "ste-disable-line" in line else set()
            claimed = set()
            for reader, state in active:
                if reader.code not in off:
                    for message in reader.line(state, line, claimed):
                        if getattr(reader, "unknown", False) or isinstance(message, UnknownText):
                            entry = "%s:%d: %s" % (md, number, message)
                            if entry not in rng.unknowns:  # two readers may say the same unknown
                                rng.unknowns.append(entry)
                        else:
                            found.setdefault((md, number, reader.code), []).append(message)
    return found


# The report (decision stale-cites-at-merge). Its lines are no finding and never set the exit code.
REPORT = "stale-cites: report, "
MECHANISMS = "lint/rule_mechanisms.json"
# Where a rule's guard, check or CI step lives. No other module holds this set (report_guard.ANSWERED_TOP_DIRS is the
# top dirs a source path may start with, a different set), so it lives here.
RULE_DIRS = ("hooks/", "lint/", "bin/", "actions/", ".github/")
HOME_LINE = re.compile(r"^Home:[ \t]*`?([^\s`]+)`?[ \t]*$", re.M)
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.S)


def anchor_sentences(text):
    """{slug: the prose since the previous anchor, or the paragraph start, spaces collapsed}. An anchor inside a
    code span is a mention of the form, not an anchor."""
    found = {}
    for block in re.split(r"\n[ \t]*\n", text.replace("\r\n", "\n")):
        spans = [m.span() for m in CODE_SPAN.finditer(block)]
        start = 0
        for match in ANCHOR_RE.finditer(block):
            if any(a <= match.start() < b for a, b in spans):
                continue
            found[match.group(1)] = " ".join(block[start:match.start()].split())
            start = match.end()
    return found


def decision_folders():
    """The places the layout lets a repo keep its decisions, first choice first (lint/layout.py candidates). A repo
    not rolled out to the layout may hold them at either place."""
    return layout.candidates(".", "decisions")


def mechanism_rows(rng, listed=False):
    """{slug: row} of lint/rule_mechanisms.json at head, or None for a repo that has none. One read. A file that
    is not JSON, or whose rules or rows are not objects with a `mechanism` object, raises Unknown naming the file:
    a row's fields are read as a dict afterwards."""
    blob = rng.batch.get("%s:%s" % (rng.head, MECHANISMS))
    if blob is None:
        if listed:  # the tree lists the file, so a missing blob is a read that could not run
            raise Unknown("%s is in the tree at %s but cannot be read" % (MECHANISMS, rng.head))
        return None
    try:
        rules = json.loads(blob.decode("utf-8", "replace"))
    except ValueError as exc:
        raise Unknown("%s is not JSON (%s)" % (MECHANISMS, exc))
    rules = rules.get("rules") if isinstance(rules, dict) else None
    if not isinstance(rules, dict):
        raise Unknown("%s holds no rules object" % MECHANISMS)
    for slug, row in rules.items():
        if not isinstance(row, dict) or not isinstance(row.get("mechanism"), dict):
            raise Unknown("%s: the row for %s is not an object with a mechanism object" % (MECHANISMS, slug))
    return rules


def rule_dir_changes(rng):
    """`changed under <RULE_DIRS>: <files>`, the files this range changed there, or `none`. No verdict: a guard row's
    logic can sit in any module, so the reviewer judges. Read from the diff; no git start."""
    hit = sorted(p for p in rng.changed if p.startswith(RULE_DIRS))
    return "changed under %s: %s" % (", ".join(RULE_DIRS), ", ".join(hit) if hit else "none")


def anchor_report(rng, rules):
    """One line per anchor whose sentence differs between base and head in a rule file the range changed."""
    lines, changes = [], rule_dir_changes(rng)
    for path in (p.replace(os.sep, "/") for p in RULE_FILES):
        if path not in rng.changed:
            continue
        old, new = rng.batch.get("%s:%s" % (rng.base, path)), rng.batch.get("%s:%s" % (rng.head, path))
        before = anchor_sentences(old.decode("utf-8", "replace")) if old is not None else {}
        after = anchor_sentences(new.decode("utf-8", "replace")) if new is not None else {}
        for slug in sorted(s for s in set(before) | set(after) if before.get(s) != after.get(s)):
            what = "added" if slug not in before else "removed" if slug not in after else "changed"
            row = (rules.get(slug) or {}).get("mechanism")
            if not isinstance(row, dict):
                lines.append("%sanchor %s %s in %s; no row in %s; %s" % (REPORT, slug, what, path, MECHANISMS, changes))
                continue
            ref = row.get("ref")
            lines.append("%sanchor %s %s in %s; kind %s%s%s; %s" % (
                REPORT, slug, what, path, row.get("kind"), ", ref %s" % ref if ref else "",
                ", test %s" % row["test"] if row.get("test") else "", changes))
    return lines


def home_report(rng, rules, entries, folders):
    """One line per changed code file that a decision's Home line or a mechanism row names. The decisions are read
    from the first of `folders` that holds a file at head."""
    code = sorted(p for p in rng.changed if not p.endswith(".md"))
    paths = file_paths(entries)
    folder = next((f for f in folders if any(p.startswith(f + "/") for p in paths)), None)
    homes = {}  # file -> decision stems whose Home names it
    texts = {}  # decision path -> its text, for the prose lines whose backing points at a changed file
    for path in (p for p in paths if folder is not None and p.startswith(folder + "/")):
        if path.endswith(".md"):
            blob = rng.batch.get("%s:%s" % (rng.head, path))
            if blob is None:  # listed in the tree, so a missing blob is a read that could not run
                rng.unknowns.append("%s is in the tree at %s but cannot be read" % (path, rng.head))
            texts[path] = (blob or b"").decode("utf-8", "replace")
            for home in HOME_LINE.findall(texts[path]):
                homes.setdefault(home, []).append(os.path.basename(path)[:-3])
    backed = {}  # changed file -> ["prose.md:line", ...]
    for prose, number, backing in backed_lines(texts, set(code)):
        backed.setdefault(backing_path(*cite_kind(backing)), []).append("%s:%d" % (prose, number))
    lines = []
    for path in code:
        parts = []
        if homes.get(path):
            parts.append("Home of decision %s" % ", ".join(sorted(homes[path])))
        named_by = sorted(slug for slug, row in (rules or {}).items()
                          if isinstance(row.get("mechanism"), dict)
                          and path in (row["mechanism"].get("ref"), str(row["mechanism"].get("test", "")).split("::")[0]))
        if named_by:
            parts.append("named by row %s" % ", ".join(named_by))
        if backed.get(path):
            parts.append("backs prose %s" % ", ".join(backed[path]))
        if parts:
            lines.append("%s%s changed; %s" % (REPORT, path, "; ".join(parts)))
    return lines


def report(rng):
    """The report lines. A repo with no lint/rule_mechanisms.json gets the Home half only, and no error.
    A changed code file lists the decision folder and the mechanisms file in one `ls-tree`, or reuses the whole-tree
    listing the findings read already; the mechanisms file is read only when that listing says it exists."""
    rule_files = [p.replace(os.sep, "/") for p in RULE_FILES]
    code = any(not p.endswith(".md") for p in rng.changed)
    if not code and not rng.changed & set(rule_files):
        return []
    entries, folders = None, ()
    if code:
        folders = decision_folders()
        entries = rng.tree if rng.tree is not None else tracked_entries(rng.head, *[f + "/" for f in folders], MECHANISMS)
    present = entries is None or any(p == MECHANISMS for _, p in entries)
    rules = None
    if present:
        try:
            rules = mechanism_rows(rng, listed=entries is not None)
        except Unknown as exc:  # the Home half still prints, without rows
            rng.unknowns.append(str(exc))
    lines = anchor_report(rng, rules) if rules is not None else []
    return lines + (home_report(rng, rules, entries, folders) if code else [])


def claim_states(rng):
    """[(reader, state)] for each reader that reads added lines and has work. A read it cannot make (an unreadable
    `.ste-lint-exclude`) raises Unknown: `scan` calls this outside the report's try, so the run exits 2."""
    return [(reader, state) for reader in READERS if getattr(reader, "scope", "tree") == "added"
            for state in [reader.prepare(rng)] if state is not None]


def claim_lines(rng, states):
    """The report lines of each reader that reads added lines, sorted by file and line."""
    found = []
    for reader, state in states:
        found += [(path, number, reader.code, message) for path, number, message in reader.claims(rng, state)]
    return ["%s%s:%d: %s %s" % (REPORT, path, number, code, message) for path, number, code, message in sorted(found)]


def scan(range_text):
    """(found, unknowns, report): {(path, line, code): [messages]}, one text per read that could not run, and the
    report lines. The report adds no finding, and a report read that fails is one unknown."""
    diff_args, base, head = parse_range(range_text)
    removed, renamed, modified, added, lines = read_diff(diff_args, head, base)
    batch = BlobReader()
    rng = Range(base, head, removed, renamed, modified, batch, added, lines)
    lines = []
    try:
        found = find_stale(rng)
        states = claim_states(rng)
        try:
            lines = claim_lines(rng, states) + report(rng)
        except (Unknown, OSError, ValueError, layout.LayoutError) as exc:  # LayoutError: a layout or extras file that does not read
            rng.unknowns.append("report not read, %s" % exc)
    finally:
        batch.close()
    return found, rng.unknowns, lines


def placeholder_adjacent(line, start, end):
    """A run touching a glob, template or shell-variable character names no one file. A `*` before the run is
    Markdown emphasis (`**path**`), so only a lone `*` after it counts."""
    before = line[start - 1] if start else ""
    after = line[end] if end < len(line) else ""
    return bool(before and before in "${") or bool(after and after in "?<{[$") or (after == "*" and before != "*")


def line_count(data):
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def scan_tree(rev):
    """(found, unknowns) for every tracked Markdown line at rev: STALE003 dead path cites, STALE004 bad anchors."""
    found = {}
    entries = tracked_entries(rev)
    files = {p for _, p in entries}
    folders = {p.rsplit("/", i)[0] for p in files for i in range(1, p.count("/") + 1)}
    tops = {p.split("/", 1)[0] for p in files if "/" in p}
    by_name = {}
    for p in sorted(files):
        by_name.setdefault(p.rsplit("/", 1)[-1], []).append(p)
    mds = markdown_files(entries, exclude_patterns("."))
    batch = BlobReader()
    regular = set(file_paths(entries))
    counts = {}  # tracked file -> its line count, read once

    def lines_of(path):
        if path not in counts:
            data = batch.get("%s:%s" % (rev, path))
            if data is None and path in regular:  # listed as a file, so a missing blob is a read that could not run
                raise Unknown("%s is in the tree at %s but cannot be read" % (path, rev))
            counts[path] = line_count(data) if data is not None else None
        return counts[path]

    try:
        for md in mds:
            folder = posixpath.dirname(md)
            for number, line in enumerate(read_markdown(batch, rev, md).split("\n"), 1):
                if "/" not in line:
                    continue
                off = disabled(line) if "ste-disable-line" in line else set()
                for run in RUN_RE.finditer(line):
                    cite = run.group(0).rstrip(".-")
                    if not FILE_CITE.match(cite) or cite.split("/", 1)[0] not in tops \
                            or placeholder_adjacent(line, run.start(), run.end()):
                        continue
                    home = next((c for c in (cite, posixpath.normpath(posixpath.join(folder, cite)))
                                 if c in files or c in folders), None)
                    if home is None:
                        if "STALE003" not in off:
                            same = by_name.get(cite.rsplit("/", 1)[-1], [])
                            hint = " (did you mean %s?)" % same[0] if len(same) == 1 else ""
                            found.setdefault((md, number, "STALE003"), []).append(
                                "%s names no tracked file at %s%s" % (cite, rev, hint))
                        continue
                    anchor = ANCHOR.match(line, run.end()) if cite == run.group(0) and home in files else None
                    if anchor is None or "STALE004" in off:
                        continue
                    first, last = int(anchor.group(1)), int(anchor.group(2) or anchor.group(1))
                    total = lines_of(home)
                    if total is not None and (first < 1 or last < first or last > total):
                        found.setdefault((md, number, "STALE004"), []).append(
                            "%s%s is not a line of that file, which has %d" % (home, anchor.group(0), total))
    finally:
        batch.close()
    return found, []


def main(argv):
    parser = argparse.ArgumentParser(description="Refuse Markdown lines that name what no longer exists.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--range", help="base...head, as the ste-lint step diffs")
    mode.add_argument("--tree", nargs="?", const="HEAD", metavar="REV",
                      help="every tracked Markdown line at REV (default HEAD): dead paths, bad line anchors")
    args = parser.parse_args(argv)
    try:
        root = git("rev-parse", "--show-toplevel").decode().strip()
        os.chdir(root)
        found, unknowns, lines = scan(args.range) if args.range else (*scan_tree(args.tree), [])
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
    for line in lines:
        print(line)
    print("stale-cites: %s" % ("FAIL, %d finding(s)" % len(found) if found else "PASS"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
