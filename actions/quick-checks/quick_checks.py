#!/usr/bin/env python3
"""The three quick checks of the starter CI (skills/project-ops, step "Add the starter CI"). Standard library only; fetches no URL.

    python3 quick_checks.py links|scripts|json

Run in the checkout root. `links`: each relative link in a tracked markdown file resolves to a file or folder. `scripts`: each tracked
Python file compiles and each shell file passes `bash -n`. `json`: each tracked JSON file parses. Exit 0 when every file of its kind
passes (none is a pass), 1 when one fails, 2 on a usage error. Each failing file is named on its own `FAIL <path>: <why>` line.
"""
import ast
import json
import os
import re
import subprocess
import sys
import urllib.parse

MODES = ("links", "scripts", "json")
# `[text](target)` and `![alt](target)`; the target ends at the first space (a title follows) or the closing paren.
INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]*>|[^)\s]*)[^)\n]*\)")
REFERENCE_LINK = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]*>|\S+)", re.M)
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")  # a scheme, a protocol-relative URL, or a same-page anchor


def tracked_files():
    """The repo's files: what git tracks, else every file under the folder (a checkout with no .git, never `.git` itself)."""
    r = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
    if r.returncode == 0:
        return sorted(p for p in r.stdout.decode("utf-8", "replace").split("\0") if p and os.path.isfile(p))
    out = []
    for folder, dirs, names in os.walk("."):
        dirs[:] = [d for d in dirs if d != ".git"]
        out += [os.path.relpath(os.path.join(folder, n), ".").replace(os.sep, "/") for n in names]
    return sorted(out)


def outside_code(text):
    """The markdown text with fenced blocks and inline code spans blanked, so a link-shaped string in code is no link."""
    lines, fence = [], None
    for line in text.splitlines():
        m = FENCE.match(line)
        if fence is None and m:
            fence = m.group(1)
            lines.append("")
        elif fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and line.strip() == m.group(1):
                fence = None
            lines.append("")
        else:
            lines.append(CODE_SPAN.sub("", line))
    return "\n".join(lines)


def link_problem(path, target):
    """-> why `target`, written in markdown file `path`, does not resolve, or None."""
    target = target.strip("<>")
    if not target or EXTERNAL.match(target):
        return None
    target = urllib.parse.unquote(re.split(r"[#?]", target, 1)[0])
    if not target:
        return None
    base = "." if target.startswith("/") else os.path.dirname(path) or "."
    if not os.path.exists(os.path.normpath(os.path.join(base, target.lstrip("/")))):
        return "link to %s resolves to no file" % target
    return None


def check_links(path, data):
    text = outside_code(data.decode("utf-8", "replace"))
    targets = [m.group(1) for m in INLINE_LINK.finditer(text)] + [m.group(1) for m in REFERENCE_LINK.finditer(text)]
    return [p for p in (link_problem(path, t) for t in targets) if p]


def check_scripts(path, data):
    if path.endswith(".py"):
        try:
            ast.parse(data, filename=path)
        except (SyntaxError, ValueError) as e:  # ValueError: a null byte
            return ["python does not parse: %s" % e]
        return []
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    return [] if r.returncode == 0 else ["bash -n fails: %s" % " ".join(r.stderr.split())]


def check_json(path, data):
    try:
        json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return ["json does not parse: %s" % e]
    return []


KINDS = {"links": ((".md", ".markdown"), check_links), "scripts": ((".py", ".sh", ".bash"), check_scripts), "json": ((".json",), check_json)}


def main(argv):
    if len(argv) != 2 or argv[1] not in MODES:
        print("usage: quick_checks.py %s" % "|".join(MODES), file=sys.stderr)
        return 2
    suffixes, check = KINDS[argv[1]]
    failed = checked = 0
    for path in tracked_files():
        if not path.lower().endswith(suffixes):
            continue
        checked += 1
        with open(path, "rb") as f:
            problems = check(path, f.read())
        for why in problems:
            print("FAIL %s: %s" % (path, why))
        failed += bool(problems)
    print("%s: %d file%s checked, %d failed" % (argv[1], checked, "" if checked == 1 else "s", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
