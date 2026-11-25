#!/usr/bin/env python3
"""Fails when a change adds an item to a crowded list that has a line of more than 8 items.

    python3 lint/check_list_lines.py --base origin/main [--root DIR] [--exclude PREFIX ...]
    python3 lint/check_list_lines.py --fix PATH

Rule: decision lists-one-line-per-item. A list that holds more than 8 items is crowded. A crowded list that the change
adds an item to has no line of more than 8 items (a list wrapped at 8 or fewer a line passes, whatever its length). Where
order cannot matter it is also sorted: Python import names, Python set
literals and the alternatives of one shell `case` arm. An ordered list (a Python list or tuple, dict keys, a shell
array) is never sorted, by the check or by --fix. Only a list the diff against the merge base adds an item to is judged:
some item of the head list starts on an added line, and the list holds more items than the base list it grew from (the
base list that shares the most items with it). An edit of an item adds none. A shell `NAME+=(...)` on an added line adds
to the last `NAME=(...)` before it. An old crowded list the change does not touch never fails, and a diff that only
removes, edits or reflows items never fails. A list with no base list that shares half its items is new, and passes.
A keep marker is a comment on the line above the list (above the `case` line for a shell arm):
`list-lines-ok: <reason>`. It opts the list out. A marker with no reason fails, and so does a marker on a list that is
not crowded.

Readers: Python is read by `ast` (comments by `tokenize`); shell by the scanner in lint/check_comment_narration.py
(shell_scan), which skips quoted text, comments and here-doc bodies. A shell array `NAME=(...)`, `NAME+=(...)` or
`declare -a NAME=(...)` holds one item per word: a quoted word, `$(...)` or `${...}` is one item, and a one-line or
a multi-line array is read alike. An array with a subscript (`NAME[0]=(`) is not read. Every other language row of
lint/code_check_standard.json that the diff adds a line to prints one `not read: <language>` line and passes.
Python `import a, b` (no `from`) and f-string parts are not read.

--fix reflows each crowded list of PATH that has a line of more than 8 items (or is unsorted where order cannot matter), in place: one item per line, a trailing comma,
and the Python AST unchanged (sorted only for set literals and import names; it checks the AST before it writes). A list
with a comment inside it is left alone and named. A shell arm comes out one alternative per line, sorted, each but the
last ending in `|\\`, the last ending in `)`, and the action on the next line. A shell array comes out one element per line, in its order.

Exit 0 clean. Exit 1 on a failure, printed as `path:line: list-lines: ...`. A base or a file the check cannot read
prints `unknown: ...` and exits 0, or 1 when env CI is set (decision ci-unknown-is-red). So does a Python or shell file
the diff cannot show: a binary file, or an untracked file that git does not ignore (`git add -N` it to have it read).

Cost: no hook, no log, no timer, no process left running. One git diff, one merge-base and one `git show` per changed
Python or shell file that holds a crowded list on an added line; Python files are parsed once, shell files scanned once.
Measured on this repo (Nov 25, 2026, quiet machine): 0.33 s wall for this 6-file branch diff against main, and over the last 20 merged pull
requests 0.65 s on average (0.13 s to 2.8 s), 12.9 s in all. The comment check on the same diff took 0.15 s.
"""
import argparse
import ast
import bisect
import io
import os
import re
import subprocess
import sys
import tokenize
import warnings
from collections import Counter

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import check_comment_narration as narration  # noqa: E402  the one home of the diff reader, the language table and the shell scan

Unread = narration.Unread
LIMIT = 8  # a list of more than this many items is crowded


def crowded(count):
    return count > LIMIT
RULE = "claude-settings decision lists-one-line-per-item"
FIX_CMD = "python3 ~/.claude/lint/check_list_lines.py --fix %s"
READ = ("python", "shell")
MARKER = re.compile(r"^#\s*list-lines-ok:(.*)$")
EOL = re.compile(r"\r\n|\r")


class Lst:
    """One list as a reader found it: `items` are (text, line) in order; `first` is the line of the first item;
    `marker_line` is where a keep marker would sit; `sortable` is true where order cannot matter. `span` is the
    (start, end) offsets that --fix replaces and `rebuild(texts)` returns the replacement text for them, or None when the
    list cannot be reflowed (`why` then says why)."""

    def __init__(self, first, items, sortable, marker_line, span, rebuild, why=""):
        self.first, self.items, self.sortable, self.marker_line = first, items, sortable, marker_line
        self.span, self.rebuild, self.why = span, rebuild, why
        self.name, self.append = None, False  # a shell array's variable, and whether this is `NAME+=(...)`

    def texts(self):
        return [t for t, _ in self.items]

    def per_line(self):
        """(line, count) of the first line that holds more than LIMIT items, or None."""
        counts = {}
        for _, line in self.items:
            counts[line] = counts.get(line, 0) + 1
        return next(((line, n) for line, n in sorted(counts.items()) if crowded(n)), None)

    def faulty(self):
        """The fault of a crowded list: 'lines' (a line holds more than LIMIT items), 'order' (not sorted), or ''. A list
        wrapped at LIMIT items a line or fewer has no 'lines' fault, whatever its length."""
        if not crowded(len(self.items)):
            return ""
        if self.per_line():
            return "lines"
        return "order" if self.sortable and self.texts() != sorted(self.texts()) else ""


def indent_of(line_text):
    return line_text[:len(line_text) - len(line_text.lstrip(" \t"))]


class PySource:
    """A Python file read once: its tree, its tokens, and a map from ast positions to character offsets."""

    def __init__(self, path, text):
        self.text = EOL.sub("\n", text)
        self.lines = self.text.split("\n")
        self.starts = [0]
        for row in self.lines:
            self.starts.append(self.starts[-1] + len(row) + 1)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # a file's own SyntaxWarning (an invalid escape) is not this check's output
                self.tree = ast.parse(self.text)
            self.tokens = list(tokenize.generate_tokens(io.StringIO(self.text).readline))
        except (SyntaxError, ValueError, tokenize.TokenError) as e:
            raise Unread("%s: cannot read: %s" % (path, e))
        self.tok_off = [self.starts[t.start[0] - 1] + t.start[1] for t in self.tokens]
        self.comments = {t.start[0]: t.string for t in self.tokens if t.type == tokenize.COMMENT and not t.line[:t.start[1]].strip()}
        self.comment_off = [o for t, o in zip(self.tokens, self.tok_off) if t.type == tokenize.COMMENT]

    def off(self, line, col):
        """Character offset of an ast position, whose column counts UTF-8 bytes."""
        row = self.lines[line - 1]
        return self.starts[line - 1] + len(row.encode("utf-8")[:col].decode("utf-8", "ignore"))

    def span_of(self, node):
        return self.off(node.lineno, node.col_offset), self.off(node.end_lineno, node.end_col_offset)

    def tokens_in(self, start, end):
        return self.tokens[bisect.bisect_left(self.tok_off, start):bisect.bisect_left(self.tok_off, end)]

    def has_comment(self, start, end):
        return bisect.bisect_left(self.comment_off, start) < bisect.bisect_left(self.comment_off, end)

    def wrapped(self, start, end):
        """True when the tokens of [start, end) open with a ( that the last token closes."""
        toks = self.tokens_in(start, end)
        if not toks or toks[0].string != "(":
            return False
        depth = 0
        for n, t in enumerate(toks):
            if t.type == tokenize.OP and t.string in "([{":
                depth += 1
            elif t.type == tokenize.OP and t.string in ")]}":
                depth -= 1
                if depth == 0:
                    return n == len(toks) - 1
        return False

    def container(self, node, everything):
        """The Lst of a list, tuple, set or dict display, or of a `from x import (...)`; None for any other node, for a
        short list (unless `everything`)."""
        if isinstance(node, (ast.List, ast.Set)) or (isinstance(node, ast.Tuple) and isinstance(node.ctx, ast.Load)):
            return self.display(node, node.elts, everything)
        if isinstance(node, ast.Dict):
            return self.display(node, None, everything)
        if isinstance(node, ast.ImportFrom):
            return self.import_from(node, everything)
        return None

    def wanted(self, count, line, everything):
        return count > 1 and (everything or crowded(count) or MARKER.match(self.comments.get(line - 1, "")))

    def display(self, node, elts, everything):
        count = len(node.keys) if elts is None else len(elts)
        if not self.wanted(count, node.lineno, everything):
            return None
        start, end = self.span_of(node)
        spread = False
        if elts is None:
            items = []
            for k, v in zip(node.keys, node.values):
                if k is None:
                    spread = True
                    items.append((self.text[self.span_of(v)[0]:self.span_of(v)[1]], v.lineno))
                else:
                    items.append((self.text[self.span_of(k)[0]:self.span_of(v)[1]], k.lineno))
            opening, closing = "{", "}"
        else:
            items = [(self.text[self.span_of(e)[0]:self.span_of(e)[1]], e.lineno) for e in elts]
            opening, closing = {ast.List: "[]", ast.Set: "{}"}.get(type(node), "()")  # a tuple gets parens if it has none
        why = "a ** spread in the dict" if spread else ("a comment inside the list" if self.has_comment(start, end) else "")
        indent = indent_of(self.lines[node.lineno - 1])

        def rebuild(texts):
            return opening + "\n" + "".join("%s    %s,\n" % (indent, t) for t in texts) + indent + closing

        return Lst(items[0][1], items, isinstance(node, ast.Set), node.lineno - 1, (start, end), None if why else rebuild, why)

    def import_from(self, node, everything):
        if not self.wanted(len(node.names), node.lineno, everything) or node.names[0].name == "*":
            return None
        start, end = self.span_of(node)
        toks = self.tokens_in(start, end)
        at = next((n for n, t in enumerate(toks) if t.type == tokenize.NAME and t.string == "import"), None)
        if at is None:
            return None
        items, cur = [], []
        for t in toks[at + 1:] + [None]:
            if t is None or t.string == ",":
                if cur:
                    items.append((" ".join(c.string for c in cur), cur[0].start[0]))
                cur = []
            elif t.type not in (tokenize.NL, tokenize.COMMENT, tokenize.NEWLINE) and t.string not in "()":
                cur.append(t)
        if len(items) < 2:
            return None
        head = self.text[start:self.tok_off[self.tokens.index(toks[at])] + len("import")]
        indent = indent_of(self.lines[node.lineno - 1])
        why = "a comment inside the import" if self.has_comment(start, end) else ""

        def rebuild(texts):
            return head + " (\n" + "".join("%s    %s,\n" % (indent, t) for t in texts) + indent + ")"

        return Lst(items[0][1], items, True, node.lineno - 1, (start, end), None if why else rebuild, why)

    def lists(self, everything=False):
        """Every Lst of the file, f-string parts left out. `everything` also returns the short ones."""
        out, stack = [], [self.tree]
        while stack:
            node = stack.pop()
            stack.extend(c for c in ast.iter_child_nodes(node) if not isinstance(c, ast.JoinedStr))
            found = self.container(node, everything)
            if found:
                out.append(found)
        return sorted(out, key=lambda lst: lst.span)

    def marker(self, lst):
        """The text after `list-lines-ok:` on the line above the list, or None when that line holds no marker."""
        m = MARKER.match(self.comments.get(lst.marker_line, ""))
        return m.group(1).strip() if m else None


class ShSource:
    """A shell file scanned once: each case arm is a list of its alternatives."""

    def __init__(self, path, text):
        self.text = EOL.sub("\n", text)
        self.scan = narration.shell_scan(path, self.text)
        self.starts = [0] + [m.end() for m in re.finditer("\n", self.text)]
        self.comment_at = [a for a, _ in self.scan]
        self.comments = {}
        for a, b in self.scan:
            line = self.line_of(a)
            if not self.text[self.starts[line - 1]:a].strip():
                self.comments[line] = self.text[a:b]

    def line_of(self, offset):
        return bisect.bisect_right(self.starts, offset)

    def lists(self, everything=False):
        out = []
        for start, paren, seps, case_at in self.scan.arms:
            if not seps or not (everything or crowded(len(seps) + 1) or MARKER.match(self.comments.get(self.line_of(case_at) - 1, ""))):
                continue
            items = []
            for a, b in zip([start] + [s + 1 for s in seps], seps + [paren]):
                j = a
                while j < b and (self.text[j] in " \t" or self.text.startswith("\\\n", j)):
                    j += 2 if self.text[j] == "\\" else 1
                text = re.sub(r"\\\n", "", self.text[a:b]).strip()
                if text:
                    items.append((text, self.line_of(j)))
            if len(items) < 2:
                continue
            row_at = self.starts[self.line_of(start) - 1]
            indent = indent_of(self.text[row_at:start] + "x")
            line_end = self.text.find("\n", paren)
            line_end = len(self.text) if line_end < 0 else line_end
            rest = self.text[paren + 1:line_end]

            def rebuild(texts, indent=indent, rest=rest):
                text = ("|\\\n" + indent).join(texts) + ")"
                return text + ("\n" + indent + "  " + rest.lstrip() if rest.strip() else rest)

            out.append(Lst(items[0][1], items, True, self.line_of(case_at) - 1, (start, line_end if rest.strip() else paren + 1 + len(rest)),
                           rebuild))
        out += self.arrays(everything)
        return sorted(out, key=lambda lst: lst.span)

    def arrays(self, everything):
        """The Lst of each `NAME=(...)` array: one item per word, a quoted word or an expansion being one. An `NAME+=(...)`
        array of one word is kept (with `everything`) so the change can be judged against the array it grows."""
        out = []
        for open_at, close_at, starts in self.scan.arrays:
            items = []
            for n, a in enumerate(starts):
                end = starts[n + 1] if n + 1 < len(starts) else close_at
                at = bisect.bisect_left(self.comment_at, a)
                cut = self.comment_at[at] if at < len(self.comment_at) and self.comment_at[at] < end else end
                items.append((re.sub(r"\\\n", "", self.text[a:cut]).strip(), self.line_of(a)))
            named = re.search(r"([A-Za-z_][A-Za-z0-9_]*)(\+?)=$", self.text[max(0, open_at - 200):open_at])
            grows = bool(named and named.group(2))
            marker_line = self.line_of(open_at) - 1
            if len(items) < 2 and not (everything and grows and items):
                continue
            if len(items) > 1 and not (everything or crowded(len(items)) or MARKER.match(self.comments.get(marker_line, ""))):
                continue
            inside = bisect.bisect_right(self.comment_at, close_at) - bisect.bisect_right(self.comment_at, open_at)
            why = "a comment inside the array" if inside else ""
            indent = indent_of(self.text[self.starts[self.line_of(open_at) - 1]:open_at] + "x")

            def rebuild(texts, indent=indent):
                return "(\n" + "".join("%s  %s\n" % (indent, t) for t in texts) + indent + ")"

            lst = Lst(items[0][1], items, False, marker_line, (open_at, close_at + 1), None if why else rebuild, why)
            lst.name, lst.append = (named.group(1) if named else None), grows
            out.append(lst)
        return out

    def marker(self, lst):
        m = MARKER.match(self.comments.get(lst.marker_line, ""))
        return m.group(1).strip() if m else None


def parse(lang, path, text):
    return PySource(path, text) if lang == "python" else ShSource(path, text)


def failure(path, line, what):
    return "%s:%d: list-lines: %s Rule: %s. Fix: %s" % (path, line, what, RULE, FIX_CMD % path)


def base_items_of(lst, base_lists):
    """The item texts of the base list that `lst` grew from: the base list that shares the most items with it, provided
    it shares at least half of the smaller of the two lists; else None (the list is new)."""
    mine, best, best_key = Counter(lst.texts()), None, (0, 0)
    for other in base_lists:
        theirs = Counter(other.texts())
        shared = sum((mine & theirs).values())
        key = (shared, -abs(len(lst.items) - len(other.items)))
        if shared and shared * 2 >= min(len(lst.items), len(other.items)) and key > best_key:
            best, best_key = other.texts(), key
    return best


def judge(path, lang, head_text, base_text, added):
    """The failure lines for one changed file. `head_text` and `base_text` (None when the base holds no such file)
    are the file's text; `added` is the set of head line numbers the diff adds. Raises Unread on an unreadable head.
    A list is added to when an item of it starts on an added line and it holds more items than the base list it grew
    from (an edit or a removal is no add). A shell `NAME+=(...)` that starts on an added line adds to the last
    `NAME=(...)` before it. A pure function of its four arguments, so a fixture or a measure can feed it any pair of texts."""
    head = parse(lang, path, head_text)
    every = head.lists(True)
    lists = [lst for lst in every if len(lst.items) > 1 and (crowded(len(lst.items)) or head.marker(lst) is not None)]
    grown = set()
    for tail in (every if lang == "shell" else ()):
        if tail.append and any(line in added for _, line in tail.items):
            plain = [t for t in every if t.name == tail.name and not t.append and t.span[0] < tail.span[0]]
            if plain:
                grown.add(id(plain[-1]))
    cands = [lst for lst in lists if id(lst) in grown or any(line in added for _, line in lst.items)]
    if not cands:
        return []
    base_lists = []
    if base_text is not None:
        try:
            base_lists = parse(lang, path, base_text).lists(True)
        except Unread:
            base_lists = []  # an unreadable base holds no list: every item reads as new
    out = []
    for lst in cands:
        if id(lst) not in grown:
            grew_from = base_items_of(lst, base_lists)
            if grew_from is None or len(lst.items) <= len(grew_from):  # a new list is no add to an old one
                continue
        is_crowded = crowded(len(lst.items))
        reason = head.marker(lst)
        if reason is not None:
            if not reason:
                out.append((lst.marker_line, failure(path, lst.marker_line,
                            "the list-lines-ok marker has no reason; write the reason after the colon, or remove the marker.")))
            elif not is_crowded:
                out.append((lst.marker_line, failure(path, lst.marker_line,
                            "the list-lines-ok marker is on a list of %d items, which is not crowded (more than %d); remove it." % (len(lst.items), LIMIT))))
            continue
        fault = lst.faulty()
        if fault == "lines":
            line, n = lst.per_line()
            out.append((line, failure(path, line, "%d items on one line, and this change adds one." % n)))
        elif fault == "order":
            out.append((lst.first, failure(path, lst.first, "%d items not sorted, and this change adds one." % len(lst.items))))
    return [text for _, text in sorted(out, key=lambda r: r[0])]


def canon(tree):
    """The dump of a tree with the items of sets and the names of from-imports in one order: what a fix may change."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Set):
            n.elts.sort(key=ast.dump)
        elif isinstance(n, ast.ImportFrom):
            n.names.sort(key=ast.dump)
    return ast.dump(tree)


def reflow(lang, path, text):
    """(new text, [why a list was left alone]) with every crowded list reflowed; the text is unchanged when none needs it.
    Python is read again after each pass, so a crowded list inside a crowded list is laid out on the next one."""
    notes = []
    for turn in range(8):
        src = parse(lang, path, text)
        todo = []
        for lst in src.lists():
            if lst.faulty() and not src.marker(lst):
                if lst.rebuild is None:  # named on the first read only: later reads count lines that the edits moved
                    note = "%s:%d: not reflowed, %s" % (path, lst.first, lst.why)
                    if turn == 0:
                        notes.append(note)
                else:
                    todo.append(lst)
        chosen, edge = [], -1
        for lst in todo:  # lists are in start order: keep the outermost of any overlap
            if lst.span[0] >= edge:
                chosen.append(lst)
                edge = lst.span[1]
        if not chosen:
            return text, notes
        new = src.text
        for lst in reversed(chosen):
            texts = sorted(lst.texts()) if lst.sortable else lst.texts()
            new = new[:lst.span[0]] + lst.rebuild(texts) + new[lst.span[1]:]
        if lang == "python":
            try:
                same = canon(ast.parse(new)) == canon(ast.parse(src.text))
            except SyntaxError:
                same = False
            if not same:
                return text, notes + ["%s: not reflowed, the reflow would change the program" % path]
        else:
            again = [sorted(lst.texts()) for lst in ShSource(path, new).lists(True)]
            before = [sorted(lst.texts()) for lst in src.lists(True)]
            if again != before:
                return text, notes + ["%s: not reflowed, the arms read differently after the reflow" % path]
        text = new
    return text, notes


def do_fix(path):
    try:
        std = narration.load_standard()
    except Unread as e:
        print("unknown: %s" % e)
        return 1
    lang = narration.language_of(path, std, tuple(std["languages"]))
    if lang not in READ:
        print("not read: %s" % (lang or os.path.basename(path)))
        return 0
    try:
        with open(path, "rb") as f:
            raw = f.read().decode("utf-8")
        new, notes = reflow(lang, path, raw)
    except (OSError, UnicodeDecodeError, Unread) as e:
        print("unknown: %s" % e)
        return 1
    if "\r\n" in raw:
        new = new.replace("\n", "\r\n")
    if new != EOL.sub("\n", raw) and new != raw:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        print("fixed: %s" % path)
    elif not notes:
        print("nothing to fix: %s" % path)
    for note in notes:
        print(note)
    return 1 if notes else 0


def git_show(root, ref, path):
    done = subprocess.run(["git", "-c", "core.quotepath=off", "show", "%s:%s" % (ref, path)], cwd=root, capture_output=True)
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None


def old_path(root, fork, path):
    """The path a renamed file had at the fork, or the path itself."""
    try:
        for row in narration.git("diff", "-M", "--name-status", fork, cwd=root).splitlines():
            cols = row.split("\t")
            if cols[0].startswith("R") and cols[-1] == path:
                return cols[1]
    except Unread:
        pass
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="ref the change is measured against, such as origin/main")
    ap.add_argument("--root", default=".", help="the repo to judge (default: the current folder)")
    ap.add_argument("--exclude", action="append", default=[], metavar="PREFIX", help="skip each path that starts with PREFIX (repeatable)")
    ap.add_argument("--fix", metavar="PATH", help="reflow the crowded lists of PATH in place, then exit")
    args = ap.parse_args(argv)
    if args.fix:
        return do_fix(args.fix)
    if not args.base:
        ap.error("--base is required unless --fix is given")
    unknown_exit = 1 if os.environ.get("CI") else 0
    root = os.path.abspath(args.root)
    os.chdir(root)
    try:
        std = narration.load_standard()
        try:
            narration.git("rev-parse", "--verify", "--quiet", args.base + "^{commit}", cwd=root)
        except Unread:
            print("unknown: base %s not in this clone; fetch it with: git fetch origin %s" % (args.base, re.sub(r"^origin/", "", args.base)))
            return unknown_exit
        files = narration.added_lines(args.base, std, tuple(args.exclude), cwd=root,
                                      classify=lambda p: narration.language_of(p, std, tuple(std["languages"])))
        fork = narration.git("merge-base", args.base, "HEAD", cwd=root).strip()
        exclude = tuple(args.exclude)
        unseen = narration.unseen_files(args.base, lambda p: not p.startswith(exclude) and narration.language_of(p, std, READ) is not None,
                                        cwd=root)
    except Unread as e:
        print("unknown: %s (base %s)" % (" ".join(str(e).split()), args.base))
        return unknown_exit
    failures, unknown = [], ["unknown: %s: %s" % row for row in unseen]
    for path, (lang, added) in sorted(files.items()):
        if lang not in READ or not added:
            continue
        try:
            with open(path, "rb") as f:
                head_text = f.read().decode("utf-8")
            base_text = git_show(root, fork, path)
            if base_text is None:
                base_text = git_show(root, fork, old_path(root, fork, path))
            failures += judge(path, lang, head_text, base_text, added)
        except (OSError, UnicodeDecodeError) as e:
            unknown.append("unknown: %s: cannot read: %s" % (path, e))
        except Unread as e:
            unknown.append("unknown: %s" % " ".join(str(e).split()))
    for row in failures + unknown:
        print(row)
    for lang in sorted({lang for lang, added in files.values() if added and lang not in READ}):
        print("not read: %s" % lang)
    return 1 if failures or (unknown and unknown_exit) else 0


if __name__ == "__main__":
    sys.exit(main())
