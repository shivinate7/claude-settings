#!/usr/bin/env python3
"""The three quick checks of the starter CI (skills/project-ops, step "Add the starter CI"). Standard library only; fetches no URL.

    python3 quick_checks.py links|scripts|json

Run in the checkout root. `links`: each relative link in a tracked markdown file resolves to a file or folder. `scripts`: each tracked
Python file compiles and each shell file passes `bash -n`; a file with no extension counts when its first line is a `#!` of bash, sh or python. `json`: each tracked JSON file parses; a file with a name that tools read as
JSON with comments (JSONC_NAMES) may hold `//` and `/* */` comments. Exit 0 when every file of its kind
passes (none is a pass), 1 when one fails, 2 on a usage error. Each failing file is named on its own `FAIL <path>: <why>` line.
"""
import ast
import fnmatch
import json
import os
import re
import sys
import urllib.parse

# Anchored on this file, not the cwd: the action runs in the caller's checkout. GitHub fetches the whole repo at the pinned sha.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a child start with no console window (hooks/_nowindow.py)

MODES = ("links", "scripts", "json")
# The start of `[text](target)` and `![alt](target)`; link_targets reads the target after it.
INLINE_LINK_START = re.compile(r"!?\[[^\]\n]*\]\(\s*")
# A reference definition; a footnote definition `[^1]: text` is no link.
REFERENCE_LINK = re.compile(r"^ {0,3}\[(?!\^)[^\]\n]+\]:\s*(<[^>\n]*>|\S+)", re.M)
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")  # at any indent: a fence in a list item sits deeper than 3 spaces
# The names tools read as JSON with comments: TypeScript and JavaScript configs, ESLint's, the dev container's, and the
# VS Code files. A pattern with a slash matches the end of the path, since a bare settings.json is no VS Code file.
JSONC_NAMES = ("tsconfig*.json", "jsconfig.json", ".eslintrc.json", "devcontainer.json", ".devcontainer.json",
               ".vscode/settings.json", ".vscode/launch.json", ".vscode/tasks.json", ".vscode/extensions.json")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")  # a scheme, a protocol-relative URL, or a same-page anchor


def tracked_files():
    """The repo's files: what git tracks, else every file under the folder (a checkout with no .git, never `.git` itself)."""
    r = _nowindow.run(["git", "ls-files", "-z"], capture_output=True)
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
    target = urllib.parse.unquote(re.split(r"[#?]", target, maxsplit=1)[0])
    if not target:
        return None
    base = "." if target.startswith("/") else os.path.dirname(path) or "."
    if not os.path.exists(os.path.normpath(os.path.join(base, target.lstrip("/")))):
        return "link to %s resolves to no file" % target
    return None


def inline_target(text, start):
    """The target of an inline link whose `(` and spaces end at `start`: `<...>`, or the run up to a space or the `)` that
    closes the link, with balanced parentheses inside (`foo_(bar).md`)."""
    if text[start:start + 1] == "<":
        end = text.find(">", start)
        newline = text.find("\n", start)
        return text[start:end + 1] if end != -1 and (newline == -1 or end < newline) else ""
    depth, i = 0, start
    while i < len(text) and not text[i].isspace():
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            if depth == 0:
                break
            depth -= 1
        i += 1
    return text[start:i]


def check_links(path, data):
    text = outside_code(data.decode("utf-8-sig", "replace"))
    targets = [inline_target(text, m.end()) for m in INLINE_LINK_START.finditer(text)] + [m.group(1) for m in REFERENCE_LINK.finditer(text)]
    return [p for p in (link_problem(path, t) for t in targets) if p]


def shebang_language(first_line):
    """-> "python" or "bash" for a first line (bytes) that is a `#!` of python or of bash or sh, `env` form included, else None."""
    if not first_line.startswith(b"#!"):
        return None
    words = first_line[2:].decode("utf-8", "replace").split()
    if words and os.path.basename(words[0]) == "env":
        words = [w for w in words[1:] if not w.startswith("-") and "=" not in w]
    name = os.path.basename(words[0]) if words else ""
    if name in ("bash", "sh"):
        return "bash"
    return "python" if re.fullmatch(r"python[0-9.]*", name) else None


def is_script(path):
    """A file the scripts check takes: a listed extension, else no extension and a `#!` first line of python, bash or sh. Reads one line."""
    if path.lower().endswith(SCRIPT_SUFFIXES):
        return True
    if os.path.splitext(path)[1]:
        return False
    try:
        with open(path, "rb") as f:
            return shebang_language(f.readline(512)) is not None
    except OSError:
        return False


def check_scripts(path, data):
    if path.endswith(".py") or (not os.path.splitext(path)[1] and shebang_language(data.split(b"\n", 1)[0]) == "python"):
        try:
            ast.parse(data, filename=path)
        except (SyntaxError, ValueError) as e:  # ValueError: a null byte
            return ["python does not parse: %s" % e]
        return []
    r = _nowindow.run(["bash", "-n", path], capture_output=True, text=True)
    return [] if r.returncode == 0 else ["bash -n fails: %s" % " ".join(r.stderr.split())]


def strip_comments(text):
    """The text without `//` and `/* */` comments. A string is read as JSON reads it, so `//` or `/*` inside one stays. An unterminated
    block comment is left in the text, where the JSON parser rejects it."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] not in '"\n':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i) and "*/" in text[i + 2:]:
            i = text.index("*/", i + 2) + 2
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def is_jsonc(path):
    lowered = path.replace("\\", "/").lower()
    return any(fnmatch.fnmatchcase("/" + lowered if "/" in pattern else os.path.basename(lowered),
                                   "*/" + pattern if "/" in pattern else pattern) for pattern in JSONC_NAMES)


def check_json(path, data):
    try:
        text = data.decode("utf-8-sig")  # a byte order mark is no part of the JSON
        if is_jsonc(path):
            text = strip_comments(text)
        json.loads(text)
    except (ValueError, UnicodeDecodeError) as e:
        return ["json does not parse: %s" % e]
    return []


SCRIPT_SUFFIXES = (".py", ".sh", ".bash")
KINDS = {"links": (lambda p: p.lower().endswith((".md", ".markdown")), check_links), "scripts": (is_script, check_scripts),
         "json": (lambda p: p.lower().endswith(".json"), check_json)}


def main(argv):
    if len(argv) != 2 or argv[1] not in MODES:
        print("usage: quick_checks.py %s" % "|".join(MODES), file=sys.stderr)
        return 2
    takes, check = KINDS[argv[1]]
    failed = checked = 0
    for path in tracked_files():
        if not takes(path):
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
