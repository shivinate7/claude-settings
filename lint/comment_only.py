#!/usr/bin/env python3
"""Says whether a change to a Python or shell file touches comments only.

    python3 lint/comment_only.py OLD_REF NEW_REF PATH [PATH ...]

Exit 0 when every PATH holds the same code at OLD_REF and NEW_REF once its comments are stripped, and for Python its
docstrings too. Exit 1 in every other case: a code change, a path that is not .py or .sh, a path missing at either ref,
a file that does not parse, an unreadable ref. An unread file is never comment-only, so the caller keeps its suites on.
Used by .github/scripts/ci-scope.sh to skip the code suites for a comment-only delta from a fully green head.

Python compares the `tokenize` tokens, with each comment and each docstring (found with `ast`) dropped. A shebang and an
encoding cookie are comments to the tokenizer but pick the interpreter and the text decoder, so they stay. Shell strips
the comment spans that lint/check_comment_narration.py shell_comment_spans finds, the one scan that reads a `#` in a string,
a parameter expansion or a heredoc body as data. A line holding only a comment is dropped, and a trailing comment
takes the blank before it.
"""
import ast
import bisect
import io
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, HERE)
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import check_comment_narration as narration  # noqa: E402  the one home of the shell comment scan

COOKIE = re.compile(r"coding[:=]\s*[-\w.]+")


def py_code(data):
    """The (type, text) tokens of Python source with comments, blank-line tokens and docstrings dropped.
    Raises narration.Unread when the source does not parse."""
    try:
        tree = ast.parse(data)
        tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
    except (SyntaxError, ValueError, tokenize.TokenError) as e:
        raise narration.Unread("cannot read: %s" % e)
    docs = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            doc = body[0]
            if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant) and isinstance(doc.value.value, str):
                docs.append((doc.lineno, doc.col_offset, doc.end_lineno))

    def in_docstring(tok):
        row, col = tok.start
        byte_col = len(tok.line[:col].encode("utf-8")) if tok.line else col
        return any(first <= row <= last and (row > first or byte_col >= start_col) for first, start_col, last in docs)

    out = []
    after_doc = False
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.NL):
            continue
        if tok.type == tokenize.STRING and in_docstring(tok):
            after_doc = True
            continue
        if after_doc and tok.type == tokenize.NEWLINE:
            after_doc = False
            continue
        after_doc = False
        if tok.type == tokenize.COMMENT:
            if tok.start[0] == 1 and tok.string.startswith("#!") or tok.start[0] <= 2 and COOKIE.search(tok.string):
                out.append((tok.type, tok.string))
            continue
        out.append((tok.type, tok.string))
    return out


def sh_code(path, data):
    """The lines of shell source with each comment dropped: a line of only a comment goes, a trailing comment takes
    the blanks before it. Raises narration.Unread on an unclosed quote, expansion or heredoc."""
    try:
        src = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise narration.Unread("%s: cannot read: %s" % (path, e))
    src = re.sub(r"\r\n|\r", "\n", src)
    spans = narration.shell_comment_spans(path, src)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    hit = set()
    for start, end in spans:
        if "\n" in src[start:end]:
            raise narration.Unread("%s: a comment spans a line end" % path)
        hit.add(bisect.bisect_right(starts, start) - 1)
    for start, end in reversed(spans):
        src = src[:start] + src[end:]
    lines = []
    for n, line in enumerate(src.split("\n")):
        if n in hit:
            line = line.rstrip()
            if not line:
                continue
        lines.append(line)
    return lines


def blob(ref, path):
    r = _nowindow.run(["git", "cat-file", "blob", "%s:%s" % (ref, path)], capture_output=True)
    if r.returncode:
        raise narration.Unread("%s:%s is not readable" % (ref, path))
    return r.stdout


def comment_only(old_ref, new_ref, path):
    """True when `path` differs between the refs in comments only (docstrings too, for Python)."""
    ext = os.path.splitext(path)[1]
    if ext not in (".py", ".sh"):
        return False
    old, new = blob(old_ref, path), blob(new_ref, path)
    if ext == ".py":
        return py_code(old) == py_code(new)
    return sh_code(path, old) == sh_code(path, new)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    old_ref, new_ref, paths = argv[0], argv[1], argv[2:]
    try:
        return 0 if all(comment_only(old_ref, new_ref, p) for p in paths) else 1
    except narration.Unread as e:
        print("comment_only: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
