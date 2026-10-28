#!/usr/bin/env python3
"""Fails when a GLOSSARY.md row has no home, or a change adds a path or a code name that uses a "not" name.

GLOSSARY.md holds one table under the `## Terms` heading: term, meaning, home, not. Three tests:

- Each row's home is an existing file, or `rule:<id>` that names a rule marker in RULE_FILES.
- Each file the change adds (against origin/main, renames counted as adds) has no path segment
  that holds a name from a row's "not" cell. A name matches whole lowercase words inside one
  segment. Words split on any character that is not a letter or a digit, and the segment is read
  both with and without a split at each lower-to-upper case step. The last word may take a
  plural `s` or `es`. `handover` matches `hooks/handover_note.py`, `docs/handovers.md` and
  `HandoverNote.py`, not `docs/handoverly.md`.

- Each line the change adds (against origin/main) has no "not" name in a name of code, read by the
  same word rule as a path segment:
  - an identifier: a Python name, a bare word of a JS, shell, PowerShell or YAML file, or a JSON key;
  - a rule anchor: `rule:<id>`, in a comment too;
  - a record slug: a backticked id of three hyphen words or more in a Markdown file;
  - a hook message: a string with a space in a `.py` file under `hooks/`, a test file apart.

Comments, docstrings and every other string are prose, and a reviewer reads prose. A sentence that
names a "not" word passes. A line that holds `glossary-ok` is skipped, with its reason beside it.
A "not" name written `word (prose)` is an everyday word (`block`, `entry`): it is read in paths,
anchors and slugs, never in identifiers, strings or hook messages. Claude Code's own names stay
(PLATFORM_NAMES, PLATFORM_PREFIXES). A path or a line that already exists on the base is not
checked or renamed.

    python3 lint/check_glossary.py [file ...]
        # files given: check those paths and read each whole, skip git
"""
import ast
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, HERE)
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
from rule_audit import ANCHOR_RE, RULE_FILES  # noqa: E402  the one home of the rule marker list

ROOT = os.path.dirname(HERE)
GLOSSARY = "GLOSSARY.md"
SECTION = "## Terms"
NONE = ("", "-", "—")  # a "not" cell that lists no name
PROSE_TAG = " (prose)"  # `gap (prose)`: an everyday word, read in paths, anchors and slugs, not in code names
WORD_RE = re.compile(r"[^a-z0-9]+")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")  # batchBranch reads as batch branch
SKIP_CODE = ("GLOSSARY.md", "docs/records.md", "lint/test_retired_names.py", "lint/test_check_glossary.py",
             "skills/impeccable/")
# GLOSSARY.md, the retired-names test and this check's own cases name the old words on purpose; records.md is generated; impeccable is vendored.
PLATFORM_NAMES = {"deny", "block", "SubagentStop", "SubagentStart", "subagent_type"}  # Claude Code's own
PLATFORM_PREFIXES = ("CLAUDE_CODE_",)  # Claude Code's own settings keys
YAML_ONLY = {"issues"}  # GitHub's own permission key
OPT_OUT = "glossary-ok"
ANCHOR_REF = re.compile(r"rule:([a-z0-9][a-z0-9-]*)")
TICKED_SLUG = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+){2,})`")
IDENT = re.compile(r"[A-Za-z_$][\w$]*")
REGEX_LIKE = re.compile(r"\\|\(\?")  # a pattern, not a message
NAME_LIKE = re.compile(r"[\w.$/-]+")  # a string with no space is a name, not a sentence
# Per extension: line comment, block comment open, block comment close.
SCRIPT = {
    ".js": ("//", "/*", "*/"), ".mjs": ("//", "/*", "*/"), ".cjs": ("//", "/*", "*/"),
    ".sh": ("#", None, None), ".yml": ("#", None, None), ".yaml": ("#", None, None),
    ".ps1": ("#", "<#", "#>"), ".json": (None, None, None),
}


def read(rel):
    try:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return None


def words(text, camel=False):
    return [w for w in WORD_RE.split((CAMEL_RE.sub(" ", text) if camel else text).lower()) if w]


def cells(line):
    """The cells of one table row, or None when the line is not a row."""
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    return [c.strip() for c in line[1:-1].split("|")]


def items(cell):
    """The comma-separated values of a cell, with backticks removed."""
    return [v.strip().strip("`").strip() for v in cell.split(",") if v.strip().strip("`").strip()]


def rows(text):
    """(term, homes, not names) for each data row of the table under SECTION."""
    out, inside = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            inside = line.strip() == SECTION
            continue
        c = cells(line) if inside else None
        if not c or len(c) != 4 or set(c[0]) <= set("-: "):
            continue
        if c[0].lower() == "term":  # the header row
            continue
        names = [] if c[3] in NONE else items(c[3])
        out.append((c[0].strip("`"), items(c[2]), names))
    return out


def home_problems(term, homes, ids):
    if not homes:
        return ["row '%s' has no home" % term]
    out = []
    for h in homes:
        if h.startswith("rule:"):
            if h[5:] not in ids:
                out.append("row '%s': home %s is not a rule marker in %s" % (term, h, ", ".join(RULE_FILES)))
        elif read(h) is None and not os.path.isdir(os.path.join(ROOT, *h.rstrip("/").split("/"))):
            out.append("row '%s': home %s does not exist" % (term, h))
    return out


def same(got, name):
    """Whole words equal, with a plural `s` or `es` allowed on the last word."""
    return got[:-1] == name[:-1] and got[-1] in (name[-1], name[-1] + "s", name[-1] + "es")


def name_problems(where, text, table, plain=False):
    """One problem per "not" name that the whole words of `text` hold.

    `plain` is a name of code that a person may spell for another sense (`block`, `entry`): a
    "not" name tagged (prose) is then left to the reviewer."""
    out = []
    # Read with and without case steps: HandOver may mean handover or hand over.
    forms = [words(text), words(text, camel=True)]
    for term, _homes, names in table:
        for name in names:
            if plain and name.endswith(PROSE_TAG):
                continue
            name = name[:-len(PROSE_TAG)] if name.endswith(PROSE_TAG) else name
            n = words(name)
            if n and any(same(w[i:i + len(n)], n) for w in forms for i in range(len(w) - len(n) + 1)):
                out.append("%s uses '%s'; the glossary name is '%s'" % (where, name, term))
    return out


def path_problems(path, table):
    return [p for seg in path.replace("\\", "/").split("/") for p in name_problems(path, seg, table)]


def scan_python(text):
    """(identifiers, strings) of a Python file as (line, text) pairs, docstrings left out.

    Raises SyntaxError when the file does not parse."""
    tree = ast.parse(text)
    idents, strings, docs = [], [], set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
        line = getattr(node, "lineno", 0)
        for field in ("id", "attr", "name", "arg", "asname"):
            v = getattr(node, field, None)
            if isinstance(v, str) and line:
                idents.append((line, v))
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            idents += [(line, v) for v in node.names]
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            strings.append((line, node.value))
    return idents, strings


def scan_script(text, syntax):
    """(identifiers, strings) of a JS, shell, PowerShell, YAML or JSON file, comments left out.

    One pass, so a comment opener inside a string is text, and a lone quote inside a comment opens
    nothing. A ' or " string ends at its line end, so a lone quote in plain text swallows no later
    line. A template literal (`) spans lines."""
    line_c, open_c, close_c = syntax
    idents, strings = [], []
    i, line, n = 0, 1, len(text)
    while i < n:
        ch = text[i]
        if line_c and text.startswith(line_c, i):
            while i < n and text[i] != "\n":
                i += 1
        elif open_c and text.startswith(open_c, i):
            end = text.find(close_c, i + len(open_c))
            end = n if end < 0 else end + len(close_c)
            line += text.count("\n", i, end)
            i = end
        elif ch in "'\"`":
            start, j = line, i + 1
            while j < n and text[j] != ch and (ch == "`" or text[j] != "\n"):
                if text[j] == "\\":
                    j += 1
                if j < n and text[j] == "\n":
                    line += 1
                j += 1
            strings.append((start, text[i + 1:min(j, n)]))
            i = j + 1 if j < n and text[j] == ch else j
        else:
            m = IDENT.match(text, i)
            if m:
                idents.append((line, m.group(0)))
            if ch == "\n":
                line += 1
            i = m.end() if m else i + 1
    return idents, strings


def code_problems(rel, text, table, lines=None):
    """Problems in the names of code, on the lines in `lines` only (None: every line).

    Raises SyntaxError when a Python file does not parse."""
    ext = os.path.splitext(rel)[1]
    rows = text.split("\n")
    out = []

    def hit(line, message):
        if (lines is None or line in lines) and OPT_OUT not in rows[line - 1]:
            out.extend("%s:%d: %s" % (rel, line, p) for p in message)

    if ext == ".py" or ext in SCRIPT:
        idents, strings = scan_python(text) if ext == ".py" else scan_script(text, SCRIPT[ext])
        base = os.path.basename(rel)
        # A test's and a mutation test's strings are cases and code text, not product text.
        fixture = base.startswith(("test_", "mutate_")) or ".test." in base
        in_hooks = rel.startswith("hooks/") and ext == ".py" and not fixture

        def platform(name):
            return name in PLATFORM_NAMES or name.startswith(PLATFORM_PREFIXES)
        for line, name in idents:
            if not platform(name) and not (name in YAML_ONLY and ext in (".yml", ".yaml")):
                hit(line, name_problems("name " + name, name, table, plain=True))
        for line, s in ([] if fixture else strings):
            if NAME_LIKE.fullmatch(s):
                if not platform(s):
                    hit(line, name_problems("name " + s, s, table, plain=True))
            elif in_hooks and " " in s.strip() and not REGEX_LIKE.search(s):
                hit(line, name_problems("message '%s'" % s.strip()[:50], s, table, plain=True))
    for number, row in enumerate(rows, 1):
        for anchor in ANCHOR_REF.findall(row):
            hit(number, name_problems("anchor " + anchor, anchor, table))
        for slug in TICKED_SLUG.findall(row) if ext == ".md" else ():
            hit(number, name_problems("slug " + slug, slug, table))
    return out


def git_diff(*opts):
    cmd = ["git", "diff", "--no-color", *opts, "origin/main...HEAD"]
    r = _nowindow.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_glossary: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there
    return r.stdout


def added():
    return git_diff("--name-only", "--no-renames", "--diff-filter=A").split("\n")


def added_lines():
    """{path: set of added line numbers} for each file the change adds or edits, renames followed."""
    out, path = {}, None
    for row in git_diff("-U0", "-M", "--diff-filter=AMR").split("\n"):
        if row.startswith("+++ "):
            path = row[6:] if row.startswith("+++ b/") else None
            out.setdefault(path, set())
        elif row.startswith("@@") and path:
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", row)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                out[path].update(range(start, start + count))
    return out


def main(args):
    unknown = [a for a in args if a.startswith("-")]
    if unknown:  # read as a path, an unknown option would skip git and check nothing
        print("check_glossary: FAIL: unknown option: %s" % " ".join(unknown))
        return 1
    text = read(GLOSSARY)
    if text is None:
        print("check_glossary: FAIL: %s cannot be read" % GLOSSARY)
        return 1
    table = rows(text)
    if not table:  # a parser that finds nothing must not read as clean
        print("check_glossary: FAIL: %s has no rows under '%s'" % (GLOSSARY, SECTION))
        return 1
    ids = {i for rel in RULE_FILES for i in ANCHOR_RE.findall(read(rel) or "")}
    bad = [p for term, homes, _names in table for p in home_problems(term, homes, ids)]
    paths = [p for p in (args or added()) if p]
    for path in paths:
        bad += path_problems(path, table)
    # Given files are read whole; a change is read on the lines it adds.
    scope = {p: None for p in args} if args else added_lines()
    unknown = []
    for rel, lines in sorted(scope.items()):
        text = read(rel)
        if text is None or rel.startswith(SKIP_CODE):
            continue
        try:
            bad += code_problems(rel, text, table, lines)
        except SyntaxError as e:
            unknown.append("%s does not parse (%s)" % (rel, e.msg))
    for p in bad:
        print("check_glossary: FAIL: " + p)
    for p in unknown:
        print("check_glossary: UNKNOWN, " + p)
    if bad:
        return 1
    return 1 if unknown and os.environ.get("CI") else 0  # as the git diff: unknown is red in CI


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
