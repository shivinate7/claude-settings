#!/usr/bin/env python3
"""Fails when a change adds a comment or docstring line that narrates history or review.

    python3 lint/check_comment_narration.py --base origin/main [--exclude PREFIX ...]

Rule: building-comments-say-why. A comment says what complex code does and why.
Only lines the diff against the merge base adds can fail, so old lines never do.
--exclude PREFIX (repeatable) drops each path that starts with PREFIX, a folder prefix such as `vendor/`.
Only .py files are read. Comments come from `tokenize`, docstrings from `ast`,
so the same words in any other string never fail.

Exit 0 clean. Exit 1 on a hit, printed as `path:line: pattern: matched text`.
Exit 2 when the base or a file cannot be read: an unread diff is never a clean one.
"""
import argparse
import ast
import io
import os
import re
import sys
import tokenize
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

PATTERNS = {
    "review round": re.compile(r"\bround\s*\d|\breview\s+(?:round|finding|points?)\b", re.I),
    "pr number": re.compile(r"\bPR\s*#?\s*\d{3,}"),
    "commit hash": re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b"),
    "status word": re.compile(r"\b(?:MEASURED|CORRECTED)\b|\bADDED\s+\d"),
    "date": re.compile(r"\b20\d\d-\d\d-\d\d\b"),
    "owner order": re.compile(r"\bowner(?:'s)?\s+(?:ruling|order|request|ask)\b", re.I),
}
REMEDY = "say what and why; the history goes in git or the decision"
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")


class Unread(Exception):
    pass


def git(*args):
    r = _nowindow.run(["git", "-c", "core.quotepath=off", *args], capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unread("git %s failed: %s" % (" ".join(args[:2]), r.stderr.strip() or r.returncode))
    return r.stdout


def added_lines(base):
    """Map each changed .py path to the set of line numbers the diff adds."""
    git("rev-parse", "--verify", "--quiet", base + "^{commit}")
    fork = git("merge-base", base, "HEAD").strip()
    diff = git("diff", "-U0", "-M", "--no-color", "--no-ext-diff", fork, "--", "*.py")
    added, path = {}, None
    for row in diff.split("\n"):
        if row.startswith("+++ "):
            path = None if row == "+++ /dev/null" else row[6:].split("\t")[0]
        elif path and (m := HUNK.match(row)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            added.setdefault(path, set()).update(range(start, start + count))
    return added


def narrated_lines(path):
    """Yield (line, text) for each comment token and each docstring line of a file."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        tree = ast.parse(data)
        tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
    except (OSError, SyntaxError, ValueError, tokenize.TokenError) as e:
        raise Unread("%s: cannot read: %s" % (path, e))
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            yield tok.start[0], tok.string
    rows = re.split(r"\r\n|\r|\n", data.decode("utf-8", "replace"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            doc = body[0]
            if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant) and isinstance(doc.value.value, str):
                for n in range(doc.lineno, doc.end_lineno + 1):
                    yield n, rows[n - 1]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="ref the change is measured against, such as origin/main")
    ap.add_argument("--exclude", action="append", default=[], metavar="PREFIX",
                    help="skip each path that starts with PREFIX (repeatable)")
    args = ap.parse_args(argv)
    hits = 0
    try:
        for path, lines in sorted(added_lines(args.base).items()):
            if path.startswith(tuple(args.exclude)):
                continue
            for n, text in sorted(set(narrated_lines(path))):
                if n in lines:
                    for name, pat in PATTERNS.items():
                        for m in pat.finditer(text):
                            print("%s:%d: %s: %s (%s)" % (path, n, name, m.group(0), REMEDY))
                            hits += 1
    except Unread as e:
        print("UNKNOWN: %s (base %s)" % (e, args.base), file=sys.stderr)
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
