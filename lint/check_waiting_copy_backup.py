#!/usr/bin/env python3
"""Check that the waiting copy in git is a backup, never a live source (decision waiting-page-one-store).

The page's database is the one store. The copy folder (layout kind `waiting-data`) serves recovery and
account moves, so a tool that reads its content as a source treats a stale backup as the truth. Two checks:

  reader  a tool under skills/, hooks/, lint/ or bin/ that names the copy folder and reads its content
          in one function (a non-Python file: on one line). A test path (hooks/guard.py is_test_rel) is not a tool.
  prose   skills/waiting-page/SKILL.md, skills/waiting-page/reference/copies-and-accounts.md and the module
          docstring of skills/waiting-page/export_page.py each say "backup".

    python3 lint/check_waiting_copy_backup.py [--root DIR]

Exit 0 clean. Exit 1 findings, one line each:
    <path>:<line>: reads the waiting copy folder as a live source
    <path>: does not call the waiting copy a backup
Exit 2 unknown: a prose file or a source file cannot be read or parsed (and no finding).

Python is read with `ast`, so a mention in a docstring, a comment or a string never counts. JavaScript and
shell go through one small scanner that blanks comments and strings (it keeps the copy name and the git
read words when they stand alone as a string).
"""
import argparse
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import guard  # noqa: E402  is_test_rel is the one home of what a test path is (hooks/guard.py)

COPY_KIND = "waiting-data"  # the layout kind of the copy folder (lint/layout.json)
COPY_RESOLVER = "waiting_copy"  # a call that resolves the copy folder (hooks/feedback_guard.py)
READ_CALLS = frozenset(("open", "read", "read_text", "read_bytes", "load", "readFileSync", "readFile"))
READ_WORDS = frozenset(("grep", "cat-file", "show"))  # git read verbs, as a string in an argument list
SOURCE_FOLDERS = ("skills", "hooks", "lint", "bin")
SKIP_DIRS = frozenset(("__pycache__", "node_modules", ".git"))
JS_SUFFIXES = (".js", ".mjs", ".cjs", ".ts")
SHELL_SUFFIXES = (".sh", ".bash")
LIVE = "reads the waiting copy folder as a live source"
NOT_BACKUP = "does not call the waiting copy a backup"
BACKUP = re.compile(r"\bbackups?\b", re.IGNORECASE)
WAITING = "skills/waiting-page"
PROSE = (WAITING + "/SKILL.md", WAITING + "/reference/copies-and-accounts.md", WAITING + "/export_page.py")
DOCSTRING_PROSE = WAITING + "/export_page.py"  # the module docstring is the prose, not a code comment

# Functions that may read the copy, by (path, function name), each with the debt that files why. Rule
# building-allow-list-is-the-constant: the copy folder is named by COPY_KIND and COPY_RESOLVER above.
ALLOWED = {
    ("hooks/feedback_guard.py", "filed_numbers"): "filing-check-reads-copy",
}

NAMES_COPY = re.compile(r"(?<![\w-])" + re.escape(COPY_KIND) + r"(?![\w-])|\b" + COPY_RESOLVER + r"\s*\(")
READS = re.compile(r"\b(?:" + "|".join(sorted(re.escape(w) for w in READ_CALLS | READ_WORDS)) + r")\b")


class Unreadable(Exception):
    """A file could not be read or parsed: unknown, never a pass."""


def call_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def own_nodes(body):
    """Every node of the statements in `body`, leaving out the bodies of nested functions (their own units)."""
    stack, out = [n for n in body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))], []
    while stack:
        node = stack.pop()
        out.append(node)
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stack.append(child)
    return out


def units(tree):
    """(name, body) of the module's own statements and of each function."""
    found = [("<module>", tree.body)]
    found += [(n.name, n.body) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return found


def python_readers(rel, text):
    """[line] of each function (or the module body) in `text` that names the copy and reads."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as err:
        raise Unreadable("%s: cannot parse: %s" % (rel, err))
    facts = []
    for name, body in units(tree):
        docs = {id(n.value) for n in own_nodes(body) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        names, reads, calls = [], False, set()
        for node in own_nodes(body):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                if node.value == COPY_KIND:
                    names.append(node.lineno)
            elif isinstance(node, ast.List):  # a git argument list; a tuple or set of words is a table
                reads = reads or any(isinstance(e, ast.Constant) and e.value in READ_WORDS for e in node.elts)
            elif isinstance(node, ast.Call):
                called = call_name(node)
                if called == COPY_RESOLVER:
                    names.append(node.lineno)
                if called in READ_CALLS:
                    reads = True
                elif called:
                    calls.add(called)
        facts.append((name, min(names) if names else 0, reads, calls))
    reading = {name for name, _, reads, _ in facts if reads}
    # One step only: a helper that reads makes its caller a reader. A longer chain (layout.path reaches a
    # config read through two helpers) is a resolver, not a reader of the copy.
    reading |= {name for name, _, _, calls in facts if calls & reading}
    return [(line, name) for name, line, _, _ in facts if line and name in reading]


def blank_code(text, shell):
    """`text` with each comment blanked and each string cut to its content when that is the copy name or a git
    read word, else to empty quotes. Newlines stay, so a line number is still the source's. A template literal
    and a block comment may span lines."""
    out, i, n = [], 0, len(text)
    word_start = True
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
            i = end
            continue
        if ch in "'\"`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            body = text[i + 1:j]
            keep = body if body == COPY_KIND or body in READ_WORDS else ""
            out.append(ch + keep + ch + "\n" * body.count("\n"))
            i = j + 1
            word_start = False
            continue
        out.append(ch)
        word_start = ch in " \t\n;|&(" if shell else False
        i += 1
    return "".join(out)


def line_readers(text, shell):
    """[line] of each line of a JavaScript or shell file that names the copy and reads, on that one line."""
    found = []
    for number, line in enumerate(blank_code(text, shell).split("\n"), 1):
        if NAMES_COPY.search(line) and READS.search(line):
            found.append((number, ""))
    return found


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
    findings, unknown = [], []
    for rel in source_files(root):
        path = os.path.join(root, *rel.split("/"))
        try:
            text = read_text(path, rel)
            kind = kind_of(rel, text)
            if kind is None:
                continue
            hits = python_readers(rel, text) if kind == "python" else line_readers(text, kind == "shell")
        except Unreadable as err:
            unknown.append(str(err))
            continue
        for line, function in hits:
            if (rel, function) not in ALLOWED:
                findings.append("%s:%d: %s" % (rel, line, LIVE))
    return findings, unknown


def check_prose(root):
    findings, unknown = [], []
    for rel in PROSE:
        try:
            text = read_text(os.path.join(root, *rel.split("/")), rel)
            if rel == DOCSTRING_PROSE:
                try:
                    text = ast.get_docstring(ast.parse(text)) or ""
                except (SyntaxError, ValueError) as err:
                    raise Unreadable("%s: cannot parse: %s" % (rel, err))
        except Unreadable as err:
            unknown.append(str(err))
            continue
        if not BACKUP.search(text):
            findings.append("%s: %s" % (rel, NOT_BACKUP))
    return findings, unknown


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(HERE), help="the repo root to check (default: this repo)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    found, unknown = check_readers(root)
    more, unread = check_prose(root)
    findings, unknown = found + more, unknown + unread
    for line in findings:
        print(line)
    if findings:
        return 1
    for line in unknown:
        print("unknown: " + line)
    return 2 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
