#!/usr/bin/env python3
"""Fails when a change adds a comment or docstring line that narrates history or review.

    python3 lint/check_comment_narration.py --base origin/main

Rule: building-comments-say-why. A comment says what complex code does and why.
Only lines the diff against the merge base adds can fail, so old lines never do.
Only .py files are read. Comments come from `tokenize`, docstrings from `ast`,
so the same words in any other string never fail.

Exit 0 clean. Exit 1 on a hit, printed as `path:line: pattern: matched text`.
Exit 2 when the base or a file cannot be read: an unread diff is never a clean one.
"""
import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize

PATTERNS = {
    "review round": re.compile(r"\bround\s*\d|\breview\s+(?:round|finding|points?)\b", re.I),
    "pr number": re.compile(r"\bPR\s*#?\s*\d{3,}"),
    "commit hash": re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b"),
    "status word": re.compile(r"\b(?:MEASURED|CORRECTED)\b|\bADDED\s+\d"),
    "date": re.compile(r"\b20\d\d-\d\d-\d\d\b"),
    "owner order": re.compile(r"\bowner(?:'s)?\s+(?:ruling|order|request|ask)\b", re.I),
}
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")


class Unread(Exception):
    pass


def git(*args):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unread("git %s failed: %s" % (" ".join(args[:2]), r.stderr.strip() or r.returncode))
    return r.stdout


def added_lines(base):
    """Map each changed .py path to the set of line numbers the diff adds."""
    git("rev-parse", "--verify", "--quiet", base + "^{commit}")
    fork = git("merge-base", base, "HEAD").strip()
    diff = git("diff", "-U0", "-M", "--no-color", "--no-ext-diff", fork, "--", "*.py")
    added, path = {}, None
    for row in diff.splitlines():
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
    rows = data.decode("utf-8", "replace").splitlines()
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
    args = ap.parse_args(argv)
    hits = 0
    try:
        for path, lines in sorted(added_lines(args.base).items()):
            for n, text in sorted(set(narrated_lines(path))):
                if n in lines:
                    for name, pat in PATTERNS.items():
                        for m in pat.finditer(text):
                            print("%s:%d: %s: %s" % (path, n, name, m.group(0)))
                            hits += 1
    except Unread as e:
        print("UNKNOWN: %s (base %s)" % (e, args.base), file=sys.stderr)
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
