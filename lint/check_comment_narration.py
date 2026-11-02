#!/usr/bin/env python3
"""Fails when a change adds a comment or docstring line that narrates history or review.

    python3 lint/check_comment_narration.py --base origin/main [--exclude PREFIX ...]

Rule: building-comments-say-why. A comment says what complex code does and why.
Only lines the diff against the merge base adds can fail, so old lines never do.
--exclude PREFIX (repeatable) drops each path that starts with PREFIX, a folder prefix such as `vendor/`.
Languages come from the rows of actions/code-check/standard.json (extensions, and shebangs for a file with no
extension): python, typescript, javascript, astro and swift. Python comments come from `tokenize`, docstrings from
`ast`. JS, TS and Astro comments come from one lint/comment_scan.mjs process that parses with the pinned
TypeScript. Swift comments come from a one-pass scanner in this file. The same words in any string never fail.

Exit 0 clean. Exit 1 on a hit, printed as `path:line: pattern: matched text`.
Exit 2 when the base or a file cannot be read: an unread diff is never a clean one. An unread file does not stop
the scan: every other file is read, every hit prints, and the run then exits 2.
"""
import argparse
import ast
import bisect
import io
import json
import os
import re
import sys
import tokenize
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
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
STANDARD = os.path.join(HERE, "..", "actions", "code-check", "standard.json")
SCAN_SCRIPT = os.path.join(HERE, "comment_scan.mjs")
NODE_LANGUAGES = ("typescript", "javascript", "astro")
SCANNED = ("python", "swift") + NODE_LANGUAGES


class Unread(Exception):
    pass


def git(*args):
    r = _nowindow.run(["git", "-c", "core.quotepath=off", *args], capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unread("git %s failed: %s" % (" ".join(args[:2]), r.stderr.strip() or r.returncode))
    return r.stdout


def load_standard():
    try:
        with open(STANDARD, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Unread("%s: cannot read: %s" % (os.path.normpath(STANDARD), e))


def shebang_word(path):
    """The interpreter a file's shebang names, version digits dropped, or None (the rule of code_check.interpreter)."""
    try:
        with open(path, "rb") as f:
            first = f.readline(200).decode("utf-8", "replace").strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    words = [w for w in first[2:].split() if not w.startswith("-") and os.path.basename(w) != "env"]
    return re.sub(r"[\d.]+$", "", os.path.basename(words[0])) if words else None


def language_of(path, std):
    """The language row name for a path, or None when it is not a scanned language."""
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower() or (base.lower() if base.startswith(".") else "")
    rows = std["languages"]
    if ext:
        return next((n for n in SCANNED if ext in rows.get(n, {}).get("extensions", [])), None)
    word = shebang_word(path)
    return next((n for n in SCANNED if word and word in rows.get(n, {}).get("shebangs", [])), None)


def added_lines(base, std):
    """Map each changed path in a scanned language to (language, the set of line numbers the diff adds)."""
    git("rev-parse", "--verify", "--quiet", base + "^{commit}")
    fork = git("merge-base", base, "HEAD").strip()
    diff = git("diff", "-U0", "-M", "--no-color", "--no-ext-diff", fork)
    added, path = {}, None
    for row in diff.split("\n"):
        if row.startswith("+++ "):
            path = None if row == "+++ /dev/null" else row[6:].split("\t")[0]
            lang = language_of(path, std) if path else None
            if lang is None:
                path = None
            else:
                added.setdefault(path, (lang, set()))
        elif path and (m := HUNK.match(row)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            added[path][1].update(range(start, start + count))
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


def swift_block_end(src, i):
    """Index after the nested block comment that opens at i; the end of the file when it never closes."""
    depth, j = 0, i
    while j < len(src):
        if src.startswith("/*", j):
            depth += 1
            j += 2
        elif src.startswith("*/", j):
            depth -= 1
            j += 2
            if depth == 0:
                return j
        else:
            j += 1
    return j


def swift_string_end(src, i, hashes, triple, spans):
    """Index after the string whose body starts at i. An interpolation inside it is code, so it may hold comments and
    strings of its own; swift_code_end adds those comments to spans. A raw string takes `#` marks on its escapes."""
    close = ('"' * (3 if triple else 1)) + "#" * hashes
    escape = "\\" + "#" * hashes
    while i < len(src):
        if src.startswith(close, i):
            return i + len(close)
        if src.startswith(escape, i):
            i += len(escape)
            if src.startswith("(", i):
                i = swift_code_end(src, i + 1, spans, True)
            else:
                i += 1
        elif src[i] == "\n" and not triple:
            return i + 1
        else:
            i += 1
    return i


def swift_code_end(src, i, spans, in_interpolation=False):
    """Scan code from i, adding each comment as (start, end) to spans. In an interpolation, stop after its `)`."""
    depth = 0
    while i < len(src):
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = len(src) if end < 0 else end
            spans.append((i, end))
            i = end
        elif src.startswith("/*", i):
            end = swift_block_end(src, i)
            spans.append((i, end))
            i = end
        elif src[i] in '"#':
            k = i
            while k < len(src) and src[k] == "#":
                k += 1
            if k < len(src) and src[k] == '"':
                triple = src.startswith('"""', k)
                i = swift_string_end(src, k + (3 if triple else 1), k - i, triple, spans)
            else:
                i = k + 1  # a `#if` or `#warning` directive, not a raw string
        elif src[i] == "(":
            depth += 1
            i += 1
        elif src[i] == ")":
            if in_interpolation and depth == 0:
                return i + 1
            depth -= 1
            i += 1
        else:
            i += 1
    return i


def swift_comments(path):
    """Yield (line, text) for each line of each comment in a Swift file."""
    try:
        with open(path, "rb") as f:
            src = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Unread("%s: cannot read: %s" % (path, e))
    src = re.sub(r"\r\n|\r", "\n", src)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    spans = []
    swift_code_end(src, 0, spans)
    for start, end in spans:
        line = bisect.bisect_right(starts, start)
        for k, text in enumerate(src[start:end].split("\n")):
            yield line + k, text


def node_comments(paths, std):
    """Run comment_scan.mjs once over every JS, TS and Astro path. Returns ({path: [(line, text)]}, [unread])."""
    if os.environ.get("CODE_CHECK_TOOLS") == "path":
        cmd = ["node", SCAN_SCRIPT, *paths]
    else:
        cmd = ["npx", "--yes", "-p", "typescript@" + std["tools"]["typescript"], "node", SCAN_SCRIPT, *paths]
    try:
        r = _nowindow.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise Unread("comment scan for JS, TS and Astro could not start: %s" % e)
    if r.returncode:
        reason = (r.stderr.strip().splitlines() or ["exit %d" % r.returncode])[-1]
        raise Unread("comment scan for JS, TS and Astro failed: %s" % reason)
    found, unread = {}, []
    for row in r.stdout.splitlines():
        try:
            item = json.loads(row)
        except ValueError:
            raise Unread("comment scan for JS, TS and Astro printed a row that is not JSON: %s" % row[:80])
        if "error" in item:
            unread.append("%s: cannot read: %s" % (item["path"], item["error"]))
        else:
            found.setdefault(item["path"], []).append((item["line"], item["text"]))
    return found, unread


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="ref the change is measured against, such as origin/main")
    ap.add_argument("--exclude", action="append", default=[], metavar="PREFIX",
                    help="skip each path that starts with PREFIX (repeatable)")
    args = ap.parse_args(argv)
    try:
        std = load_standard()
        files = {p: v for p, v in added_lines(args.base, std).items() if not p.startswith(tuple(args.exclude))}
    except Unread as e:
        print("UNKNOWN: %s (base %s)" % (e, args.base), file=sys.stderr)
        return 2
    comments, unread = {}, []
    for path, (lang, _) in sorted(files.items()):
        if lang in ("python", "swift"):
            try:
                comments[path] = list(narrated_lines(path) if lang == "python" else swift_comments(path))
            except Unread as e:
                unread.append(str(e))
    node_paths = [p for p, (lang, _) in sorted(files.items()) if lang in NODE_LANGUAGES]
    if node_paths:
        try:
            found, bad = node_comments(node_paths, std)
            comments.update(found)
            unread += bad
        except Unread as e:
            unread.append(str(e))
    hits = 0
    for path in sorted(comments):
        for n, text in sorted(set(comments[path])):
            if n in files[path][1]:
                for name, pat in PATTERNS.items():
                    for m in pat.finditer(text):
                        print("%s:%d: %s: %s (%s)" % (path, n, name, m.group(0), REMEDY))
                        hits += 1
    if unread:
        print("UNKNOWN: %s (base %s)" % ("; ".join(" ".join(u.split()) for u in unread), args.base), file=sys.stderr)
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
