#!/usr/bin/env python3
"""Fails when a GLOSSARY.md row has no home, or a change adds a path or a code name that uses a "not" name.

GLOSSARY.md holds one table under the `## Terms` heading: term, meaning, home, not. Three tests:

- Each row's home is an existing file, or `rule:<id>` that names a rule marker in RULE_FILES, and
  each tagged "not" name uses the one tag, `(this sense)`.
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
names a "not" word passes. A "not" word inside its own term, plural too (`hole` in `safety_holes`),
is the term. A line that holds `glossary-ok` is skipped, with its reason beside it.
A "not" name written `word (this sense)` retires one sense of an everyday word (`block`, `issue`):
it is read in paths, anchors and slugs, never in identifiers, strings or hook messages, where code
may use the other sense. Any other parenthesised tag on a "not" name fails. Claude Code's own names
stay (PLATFORM_NAMES, PLATFORM_PREFIXES). A path or a line that already exists on the base is not
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
THIS_SENSE = " (this sense)"  # `issue (this sense)`: read in paths, anchors and slugs, not in code names
TAG_RE = re.compile(r"[^()]+ \(this sense\)")  # the one allowed form of a tagged "not" name
WORD_RE = re.compile(r"[^a-z0-9]+")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")  # batchBranch reads as batch branch
SKIP_CODE = ("GLOSSARY.md", "docs/records.md", "lint/test_retired_names.py", "lint/test_check_glossary.py",
             "skills/impeccable/")
# GLOSSARY.md, the retired-names test and this check's own cases name the old words on purpose; records.md is generated; impeccable is vendored.
PLATFORM_NAMES = {"deny", "block", "SubagentStop", "SubagentStart", "subagent_type", "subagents"}  # Claude Code's own
PLATFORM_PREFIXES = ("CLAUDE_CODE_",)  # Claude Code's own settings keys
YAML_ONLY = {"issues"}  # GitHub's own permission key
OPT_OUT = "glossary-ok"
ANCHOR_REF = re.compile(r"rule:([a-z0-9][a-z0-9-]*)")
TICKED_SLUG = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+){2,})`")
IDENT = re.compile(r"[A-Za-z_$][\w$]*")
REGEX_LIKE = re.compile(r"\\|\(\?")  # a pattern, not a message
NAME_LIKE = re.compile(r"[\w.$/-]+")  # a string with no space is a name, not a sentence
# Per language of a non-Python file, how its text is cut: line comment, block comment open and close,
# whether a backtick opens a template literal, whether `/` can open a regex literal, whether `#` is a
# comment only at a word start, whether `<<WORD` opens a here-document, whether `@'` or `@"` opens a
# here-string, a pattern that makes a line a comment when it starts the line, and the string escape.
JS = {"line": "//", "open": "/*", "close": "*/", "template": True, "regex": True, "esc": "\\"}
SH = {"line": "#", "wordstart": True, "heredoc": True, "esc": "\\"}
PS = {"line": "#", "open": "<#", "close": "#>", "esc": "`", "tick": True, "herestring": True}
HASH = {"line": "#", "esc": "\\"}
PLAIN = {"esc": "\\"}
BAT = {"lead": re.compile(r"[ \t]*@?(?:rem(?=[ \t]|$)|::)", re.I | re.M), "esc": "\\"}  # rem, REM, ::
SCRIPT = {
    ".js": JS, ".mjs": JS, ".cjs": JS, ".ts": JS, ".tsx": JS, ".jsx": JS,
    ".sh": SH, ".bash": SH, ".ps1": PS, ".toml": HASH, ".json": PLAIN, ".cmd": BAT, ".bat": BAT,
    ".yml": None, ".yaml": None,  # YAML has its own reader
}
REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
REGEX_WORDS = ("return", "typeof", "case", "in", "of", "delete", "void", "throw", "else")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_]\w*)\1")
YAML_KEY = re.compile(r"^(\s*)(?:-\s+)*(?P<key>\"(?P<dq>[^\"\n]*)\"|'(?P<sq>[^'\n]*)'|(?P<bare>[A-Za-z_$][\w.$-]*))"
                      r"\s*:(?:\s+(?P<value>.*?))?\s*$")
YAML_QUOTED = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'")
YAML_ITEM = re.compile(r"^(\s*)-\s+(.*?)\s*$")
YAML_BLOCK = re.compile(r"[|>][+-]?\d?\s*(?:#.*)?$")


def read(rel):
    try:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8-sig") as f:
            return f.read()
    except (OSError, ValueError):  # unreadable, or not text
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


def tag_problems(term, names):
    """One problem per "not" name with a parenthesised tag other than (this sense)."""
    return ["row '%s': not name '%s' has an unknown tag; the one tag is%s" % (term, n, THIS_SENSE)
            for n in names if ("(" in n or ")" in n) and not TAG_RE.fullmatch(n)]


def same(got, name):
    """Whole words equal, with a plural `s` or `es` allowed on the last word."""
    return got[:-1] == name[:-1] and got[-1] in (name[-1], name[-1] + "s", name[-1] + "es")


def prepared(table):
    """(term words, [(name, name words)], index) of each row of `table`, built once per table, not per call.

    The index maps a text word to the (row, name) pairs whose first word it can be, so a call tests only
    the names that share a word with its text. A one-word name is indexed under its plural forms too."""
    if _PREPARED and _PREPARED[0] is table and _PREPARED[1] == len(table):
        return _PREPARED[2]
    rows_, index = [], {}
    for r, (term, _homes, names) in enumerate(table):
        got = []
        for name in names:
            tagged = name.endswith(THIS_SENSE)
            n = words(name[:-len(THIS_SENSE)] if tagged else name)
            got.append((tagged, n))
            if n:
                for key in ([n[0], n[0] + "s", n[0] + "es"] if len(n) == 1 else [n[0]]):
                    index.setdefault(key, []).append((r, len(got) - 1))
        rows_.append((term, words(term), got))
    _PREPARED[:] = [table, len(table), (rows_, index)]
    return rows_, index


_PREPARED = []
tick = None  # a callable that lib users set to stop a long read: it is called inside the name loop and raises to stop


def name_problems(where, text, table, plain=False, spans=()):
    """One problem per "not" name that the whole words of `text` hold.

    `plain` is a name of code that a person may spell for another sense (`block`, `entry`): a
    "not" name tagged (this sense) is then left to the reviewer. `spans`: word lists of terms of the
    checked repo's own glossary; a "not" word inside one of them is that term, like a term of the table."""
    out = []
    if tick:
        tick()
    # Read with and without case steps: HandOver may mean handover or hand over.
    forms = [words(text), words(text, camel=True)]
    rows_, index = prepared(table)
    seen = {r_n for form in forms for w in form for r_n in index.get(w, ())}
    for r, k in sorted(seen):
        if tick:
            tick()
        term, spelled, names = rows_[r]
        tagged, n = names[k]
        if plain and tagged:
            continue
        if any(same(w[i:i + len(n)], n) and not any(inside(w, i, len(n), t) for t in (spelled, *spans))
               for w in forms for i in range(len(w) - len(n) + 1)):
            name = table[r][2][k]
            out.append("%s uses '%s'; the glossary name is '%s'" % (where, name[:-len(THIS_SENSE)] if tagged else name, term))
    return out


def inside(w, i, count, term):
    """True when words w[i:i + count] lie within one spelling of the term's words in w, plural too."""
    return any(same(w[j:j + len(term)], term) and j <= i and i + count <= j + len(term)
               for j in range(len(w) - len(term) + 1))


def child_spans(child_table, table):
    """The word lists of the terms of a repo's own glossary that `name_problems` may honour as `spans`.

    A term equal to a term of `table`, or to a "not" name (plural too), is left out: it is no spelling of its own."""
    ours = [words(term) for term, _homes, _names in table]
    retired = [words(name[:-len(THIS_SENSE)] if name.endswith(THIS_SENSE) else name)
               for _term, _homes, names in table for name in names]
    out = []
    for term, _homes, _names in child_table:
        w = words(term)
        if w and not any(o and (same(w, o) or same(o, w)) for o in ours + retired):
            out.append(w)
    return out


def path_problems(path, table, spans=()):
    return [p for seg in path.replace("\\", "/").split("/") for p in name_problems(path, seg, table, spans=spans)]


def scan_python(text):
    """(identifiers, strings) of a Python file, docstrings left out. An identifier is (line, name),
    a string is (first line, last line, text). An f-string is one string, its fields as `{}`.

    Raises SyntaxError when the file does not parse."""
    tree = ast.parse(text)
    idents, strings, skip = [], [], set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(id(first.value))
        line = getattr(node, "lineno", 0)
        for field in ("id", "attr", "name", "arg", "asname", "module"):
            v = getattr(node, field, None)
            if isinstance(v, str) and line:
                idents.append((line, v))
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            idents += [(line, v) for v in node.names]
        if isinstance(node, ast.JoinedStr) and id(node) not in skip:
            parts = [c.value if isinstance(c, ast.Constant) else "{}" for c in node.values]
            strings.append((line, node.end_lineno, "".join(str(p) for p in parts)))
            skip.update(id(c) for c in ast.walk(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            strings.append((line, node.end_lineno, node.value))
    return idents, strings


def regex_starts(text, i):
    """True when the `/` at text[i] opens a regex literal: what comes before it expects a value."""
    j = i - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] == "\n":
        return True
    if j > 0 and text[j] in "+-" and text[j - 1] == text[j]:
        return False  # `i++ / 2`: a division after an increment or a decrement
    if text[j] == "}" and text[i + 1:i + 2] == ">":
        return False  # `a={x} />`: the end of a JSX tag that closes itself
    if text[j] in REGEX_AFTER:
        return True
    k = j
    while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
        k -= 1
    return text[k + 1:j + 1] in REGEX_WORDS


def regex_end(text, i):
    """The index after the regex literal that starts at text[i], or -1 when the line holds none."""
    j, n, in_class = i + 1, len(text), False
    while j < n and text[j] != "\n":
        c = text[j]
        if c == "\\":
            j += 1
        elif c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < n and text[j].isalpha():
                j += 1
            return j
        j += 1
    return -1


def template_end(text, i):
    """The index after the template literal that opens at text[i]. A `${...}` field may hold
    strings and template literals of its own, so their backticks and braces do not end it."""
    j, n = i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
        elif text[j] == "`":
            return j + 1
        elif text.startswith("${", j):
            j, depth = j + 2, 1
            while j < n and depth:
                c = text[j]
                if c == "`":
                    j = template_end(text, j)
                    continue
                if c in "'\"":  # a string in the field ends at its quote or its line end
                    j += 1
                    while j < n and text[j] not in (c, "\n"):
                        j += 2 if text[j] == "\\" else 1
                elif c in "{}":
                    depth += 1 if c == "{" else -1
                j += 1
        else:
            j += 1
    return n


def scan_script(text, lang):
    """(identifiers, strings) of a JS, shell, PowerShell, batch, TOML or JSON file, comments left out.

    One pass, so a comment opener inside a string is text, and a lone quote inside a comment opens
    nothing. A ' or " string ends at its line end, so a lone quote in plain text swallows no later
    line. A template literal (`) spans lines, nested ones too, a regex literal is skipped whole, and
    the body of a here-document or a PowerShell here-string is prose. A shell `<<<` here-string and
    a `<<` shift inside `((...))` open no here-document."""
    idents, strings = [], []
    i, line, n, doc, arith = 0, 1, len(text), None, 0
    line_c, open_c, esc, lead = lang.get("line"), lang.get("open"), lang["esc"], lang.get("lead")
    while i < n:
        ch = text[i]
        if lead and (i == 0 or text[i - 1] == "\n") and lead.match(text, i):
            while i < n and text[i] != "\n":
                i += 1
        elif line_c and text.startswith(line_c, i) and (
                not lang.get("wordstart") or i == 0 or text[i - 1] in " \t\n;|&("):
            while i < n and text[i] != "\n":
                i += 1
        elif open_c and text.startswith(open_c, i):
            end = text.find(lang["close"], i + len(open_c))
            end = n if end < 0 else end + len(lang["close"])
            line += text.count("\n", i, end)
            i = end
        elif ch == "@" and lang.get("herestring") and text[i + 1:i + 2] in ("'", '"') \
                and not text[i + 2:(text.find("\n", i) + 1 or n + 1) - 1].strip():
            close = text.find("\n" + text[i + 1] + "@", i)  # the closing '@ or "@ starts its line
            end = n if close < 0 else close + 3
            strings.append((line, line + text.count("\n", i, end), text[i + 2:end]))
            line += text.count("\n", i, end)
            i = end
        elif ch == "`" and lang.get("template"):
            end = template_end(text, i)
            strings.append((line, line + text.count("\n", i, end), text[i + 1:end].rstrip("`")))
            line += text.count("\n", i, end)
            i = end
        elif ch in "'\"":
            start, j = line, i + 1
            quote_esc = esc if not (lang.get("tick") and ch == "'") else None
            while j < n and text[j] != ch and text[j] != "\n":
                if quote_esc and text[j] == quote_esc:
                    j += 1
                if j < n and text[j] == "\n":
                    line += 1
                j += 1
            strings.append((start, line, text[i + 1:min(j, n)]))
            i = j + 1 if j < n and text[j] == ch else j
        elif ch == "`" and lang.get("tick"):  # PowerShell: escape, or a line continuation
            line += 1 if text[i + 1:i + 2] == "\n" else 0
            i += 2
        elif ch == "/" and lang.get("regex") and regex_starts(text, i) and regex_end(text, i) > 0:
            i = regex_end(text, i)
        elif lang.get("heredoc") and text.startswith(("((", "))", "<<<"), i):
            if text.startswith("<<<", i):
                i += 3
            else:  # arithmetic depth, so `$((1 << n))` is a shift
                arith = arith + 1 if ch == "(" else max(0, arith - 1)
                i += 2
        elif ch == "<" and lang.get("heredoc") and not arith and HEREDOC.match(text, i):
            doc = HEREDOC.match(text, i).group(2)
            i = HEREDOC.match(text, i).end()
        else:
            m = IDENT.match(text, i)
            if m:
                idents.append((line, m.group(0)))
            if ch == "\n":
                line += 1
                if doc:  # skip the body, up to the line that holds only the delimiter
                    i += 1
                    while i < n:
                        eol = text.find("\n", i)
                        eol = n if eol < 0 else eol
                        done = text[i:eol].strip() == doc
                        line += 1 if eol < n else 0
                        i = eol + 1
                        if done:
                            break
                    doc = None
                    continue
            i = m.end() if m else i + 1
    return idents, strings


def scan_yaml(text):
    """(identifiers, strings) of a YAML file: each key, and each value that is one bare name.

    A value with a space is prose or a command and is left to a reviewer, as are the lines under a
    `|` or `>` block."""
    idents, strings, block = [], [], None
    for number, row in enumerate(text.split("\n"), 1):
        indent = len(row) - len(row.lstrip())
        if block is not None and (not row.strip() or indent > block):
            continue
        block = None
        if not row.strip() or row.lstrip().startswith("#"):
            continue
        key, item = YAML_KEY.match(row), YAML_ITEM.match(row)
        value = None
        if key:
            idents.append((number, next(k for k in key.group("dq", "sq", "bare") if k is not None)))
            value = key.group("value")
        elif item:
            value = item.group(2)
        if value and YAML_BLOCK.match(value):
            # Lines under `- run: |` sit deeper than the key `run`, not than its dash.
            block = key.start("key") if key else indent
            continue
        value = re.sub(r"\s+#.*$", "", value or "").strip()
        if value.startswith(("[", "{")):  # a flow list or map: bare words are names, a quoted item is a value
            idents += [(number, w) for w in IDENT.findall(YAML_QUOTED.sub(" ", value))]
            quoted = ["".join(q) for q in YAML_QUOTED.findall(value)]
            strings += [(number, number, q) for q in quoted if NAME_LIKE.fullmatch(q)]
            continue
        value = value.strip("'\"")
        if NAME_LIKE.fullmatch(value):
            strings.append((number, number, value))
    return idents, strings


def code_problems(rel, text, table, lines=None, spans=()):
    """Problems in the names of code, on the lines in `lines` only (None: every line).

    `spans`: the terms of the checked repo's own glossary (`name_problems`).
    Raises SyntaxError when a Python file does not parse."""
    ext = os.path.splitext(rel)[1]
    rows = text.split("\n")
    opted = [OPT_OUT in row for row in rows]  # once per line: a name asks it again for each of its hits
    out = []

    def hit(line, message, last=None):
        span = range(line, (last or line) + 1)
        if (lines is None or any(n in lines for n in span)) and not any(opted[n - 1] for n in span):
            out.extend("%s:%d: %s" % (rel, line, p) for p in message)

    if ext == ".py" or ext in SCRIPT:
        if ext == ".py":
            idents, strings = scan_python(text)
        elif SCRIPT[ext] is None:
            idents, strings = scan_yaml(text)
        else:
            idents, strings = scan_script(text, SCRIPT[ext])
        base = os.path.basename(rel)
        # A test's and a mutation test's strings are cases and code text, not product text.
        fixture = base.startswith(("test_", "mutate_")) or ".test." in base
        in_hooks = rel.startswith("hooks/") and ext == ".py" and not fixture

        def platform(name):
            return name in PLATFORM_NAMES or name.startswith(PLATFORM_PREFIXES)
        for line, name in idents:
            if not platform(name) and not (name in YAML_ONLY and ext in (".yml", ".yaml")):
                hit(line, name_problems("name " + name, name, table, plain=True, spans=spans))
        for line, last, s in ([] if fixture else strings):
            if NAME_LIKE.fullmatch(s):
                if not platform(s):
                    hit(line, name_problems("name " + s, s, table, plain=True, spans=spans), last)
            elif in_hooks and s.strip() and not REGEX_LIKE.search(s):
                hit(line, name_problems("message '%s'" % s.strip()[:50], s, table, plain=True, spans=spans), last)
    for number, row in enumerate(rows, 1):
        for anchor in ANCHOR_REF.findall(row):
            hit(number, name_problems("anchor " + anchor, anchor, table, spans=spans))
        for slug in TICKED_SLUG.findall(row) if ext == ".md" else ():
            hit(number, name_problems("slug " + slug, slug, table, spans=spans))
    return out


def git_diff(*opts):
    # Fixed prefixes and no external diff, so diff.noprefix, diff.mnemonicPrefix or a diff tool
    # in the user's config cannot change the `+++ b/<path>` headers that added_lines reads.
    cmd = ["git", "diff", "--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", *opts,
           "origin/main...HEAD"]
    r = _nowindow.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_glossary: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there
    return r.stdout


def added():
    return git_diff("--name-only", "--no-renames", "--diff-filter=A").split("\n")


def diff_path(header):
    """The path of a `+++ b/<path>` header, unquoted when the diff quoted it; None for no path.

    Git ends the header with a TAB when the path holds a space."""
    header = header.rstrip("\t")
    if header.startswith('"'):
        try:
            header = ast.literal_eval(header).encode("latin-1").decode("utf-8")
        except (SyntaxError, ValueError, UnicodeError):
            return None
    return header[2:] if header.startswith("b/") else None


def added_lines():
    """({path: set of added line numbers}, unknowns) for each file the change adds or edits, renames
    followed. A `+++ ` header that yields no path is an unknown, never a skip.

    A `+++ ` row is a header only between `diff --git` and the first `@@`: past that, it is an
    added line that starts with `++`."""
    out, unknown, path, header = {}, [], None, False
    for row in git_diff("-U0", "-M", "--diff-filter=AMR").split("\n"):
        if row.startswith("diff --git "):
            path, header = None, True
        elif header and row.startswith("+++ "):
            path = diff_path(row[4:])
            if path:
                out.setdefault(path, set())
            else:
                unknown.append("the diff header '%s' names no path" % row[:80])
        elif row.startswith("@@"):
            header = False
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", row)
            if m and path:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                out[path].update(range(start, start + count))
    return out, unknown


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
    bad = [p for term, homes, names in table for p in home_problems(term, homes, ids) + tag_problems(term, names)]
    paths = [p for p in (args or added()) if p]
    for path in paths:
        bad += path_problems(path, table)
    # Given files are read whole; a change is read on the lines it adds.
    scope, unknown = ({p: None for p in args}, []) if args else added_lines()
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
